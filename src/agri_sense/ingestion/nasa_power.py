"""Fetch historical daily weather from NASA POWER for a lat/lon point."""

import logging
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from agri_sense.utils.config import config

logger = logging.getLogger(__name__)

_PARAMETERS = ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN", "WS2M"]
_COLUMN_MAP = {
    "T2M": "temp_mean_c",
    "T2M_MAX": "temp_max_c",
    "T2M_MIN": "temp_min_c",
    "PRECTOTCORR": "precip_mm",
    "RH2M": "humidity_pct",
    "ALLSKY_SFC_SW_DWN": "solar_mj",
    "WS2M": "wind_ms",
}
_MISSING_VALUE = -999.0


def _cache_path(
    lat: float,
    lon: float,
    start: date,
    end: date,
    cache_tag: str | None = None,
) -> Path:
    cache_dir = config.raw_dir / "nasa_power"
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = cache_tag if cache_tag else f"{lat}_{lon}_{start}_{end}"
    return cache_dir / f"{name}.parquet"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def _fetch_from_api(lat: float, lon: float, start: date, end: date) -> dict:  # type: ignore[return]
    params = {
        "parameters": ",".join(_PARAMETERS),
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    logger.info("Fetching NASA POWER: lat=%s lon=%s %s→%s", lat, lon, start, end)
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(config.nasa_power_base_url, params=params)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


def fetch_daily_weather(
    lat: float,
    lon: float,
    start: date,
    end: date,
    cache_tag: str | None = None,
) -> pd.DataFrame:
    """Return daily weather for (lat, lon) between start and end inclusive.

    Columns: temp_mean_c, temp_max_c, temp_min_c, precip_mm, humidity_pct,
    solar_mj, wind_ms.  Index: pd.DatetimeIndex.

    Args:
        cache_tag: Optional override for the cache filename, e.g.
                   ``f"{province}_{season}_{year}"``. If omitted, the key
                   is derived from lat/lon/date range.
    """
    cache = _cache_path(lat, lon, start, end, cache_tag=cache_tag)
    if cache.exists():
        logger.info("Cache hit: %s", cache)
        return pd.read_parquet(cache)

    payload = _fetch_from_api(lat, lon, start, end)
    raw: dict[str, dict[str, float]] = payload["properties"]["parameter"]

    records: dict[str, list[float]] = {col: [] for col in _COLUMN_MAP.values()}
    dates: list[pd.Timestamp] = []

    first_param = raw[_PARAMETERS[0]]
    for date_str in sorted(first_param.keys()):
        dates.append(pd.Timestamp(date_str))
        for param, col in _COLUMN_MAP.items():
            val: float = raw[param].get(date_str, _MISSING_VALUE)
            records[col].append(float("nan") if val == _MISSING_VALUE else val)

    df = pd.DataFrame(records, index=pd.DatetimeIndex(dates, name="date"))
    # Replace any remaining sentinel values that slipped through as exact float
    df.replace(_MISSING_VALUE, float("nan"), inplace=True)
    # Normalize to second precision so parquet round-trips are stable
    df.index = df.index.astype("datetime64[s]")

    df.to_parquet(cache)
    logger.info("Cached to %s (%d rows)", cache, len(df))
    return df
