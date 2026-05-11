"""Fetch 14-day weather forecast from Open-Meteo (free API, no key required).

Used for weather-risk adjustments to price forecasts and farm planning.
Caches results for 6 hours — forecasts change slowly enough that more
frequent re-fetches waste quota without improving accuracy.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from agri_sense.utils.config import config

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_CACHE_TTL_SECONDS = 6 * 3600  # 6 hours

# Vietnam seasonal temperature baselines by month (°C) — used for anomaly detection.
# Source: Vietnamese Meteorological and Hydrological Administration long-run averages.
_SEASONAL_MEAN_TEMP: dict[int, float] = {
    1: 22.0, 2: 23.0, 3: 25.5, 4: 28.0, 5: 29.5,
    6: 29.5, 7: 29.5, 8: 29.0, 9: 28.5, 10: 27.0,
    11: 25.0, 12: 23.0,
}


def _cache_path(lat: float, lon: float) -> Path:
    cache_dir = config.raw_dir / "open_meteo"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{lat:.4f}_{lon:.4f}_forecast.json"


def _fetch_from_api(lat: float, lon: float) -> dict[str, object]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_mean",
        "forecast_days": 14,
        "timezone": "Asia/Ho_Chi_Minh",
    }
    logger.info("Fetching Open-Meteo forecast: lat=%.4f lon=%.4f", lat, lon)
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(_BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


def fetch_forecast_risk(lat: float, lon: float) -> dict[str, object]:
    """Return weather-risk indicators derived from the 14-day Open-Meteo forecast.

    Fails silently: on any network or parsing error the function returns a
    safe no-risk default so downstream callers always get a well-typed dict.

    Returns:
        extreme_rain_days:       int   — days with precipitation > 30 mm/day
        mean_temp_c:             float — 14-day mean daily temperature
        temp_anomaly:            bool  — True if mean_temp > seasonal_mean + 2°C
        is_high_risk:            bool  — True if extreme_rain_days > 3 OR temp_anomaly
        supply_shock_multiplier: float — 1.06 (rain), 1.04 (heat), 1.08 (both), 1.0 (none)
    """
    cache = _cache_path(lat, lon)

    if cache.exists():
        try:
            cached = json.loads(cache.read_text())
            age = time.time() - float(cached.get("_fetched_at", 0))
            if age < _CACHE_TTL_SECONDS:
                logger.info("Open-Meteo cache hit (age=%.0f s): %s", age, cache)
                return {k: v for k, v in cached.items() if not k.startswith("_")}
        except Exception:  # noqa: BLE001
            pass  # stale / corrupt cache → fall through to fresh fetch

    try:
        payload = _fetch_from_api(lat, lon)
        daily = payload.get("daily", {})
        precip: list[float | None] = daily.get("precipitation_sum", [])  # type: ignore[assignment]
        temp_mean_list: list[float | None] = daily.get("temperature_2m_mean", [])  # type: ignore[assignment]

        extreme_rain_days = sum(1 for p in precip if p is not None and p > 30.0)
        rain_days_14d = sum(1 for p in precip if p is not None and p > 5.0)
        total_rain_mm_14d = sum(p for p in precip if p is not None)
        valid_temps = [t for t in temp_mean_list if t is not None]
        mean_temp = sum(valid_temps) / len(valid_temps) if valid_temps else 28.0

        import datetime as _dt  # noqa: PLC0415
        current_month = _dt.date.today().month
        seasonal_mean = _SEASONAL_MEAN_TEMP[current_month]
        temp_anomaly = mean_temp > seasonal_mean + 2.0

        is_high_risk = extreme_rain_days > 3 or temp_anomaly

        if extreme_rain_days > 3 and temp_anomaly:
            supply_shock: float = 1.08
        elif extreme_rain_days > 3:
            supply_shock = 1.06
        elif temp_anomaly:
            supply_shock = 1.04
        else:
            supply_shock = 1.0

        daily_precip_mm = [float(p) if p is not None else 0.0 for p in precip]

        result: dict[str, object] = {
            "extreme_rain_days": extreme_rain_days,
            "rain_days_14d": rain_days_14d,
            "total_rain_mm_14d": round(total_rain_mm_14d, 1),
            "mean_temp_c": round(mean_temp, 1),
            "temp_anomaly": temp_anomaly,
            "is_high_risk": is_high_risk,
            "supply_shock_multiplier": supply_shock,
            "daily_precip_mm": daily_precip_mm,
        }

        cache.write_text(json.dumps({**result, "_fetched_at": time.time()}, indent=2))
        logger.info("Cached Open-Meteo forecast → %s", cache)
        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning("Open-Meteo forecast failed: %s — using no-risk defaults", exc)
        return {
            "extreme_rain_days": 0,
            "rain_days_14d": 0,
            "total_rain_mm_14d": 100.0,
            "mean_temp_c": 28.0,
            "temp_anomaly": False,
            "is_high_risk": False,
            "supply_shock_multiplier": 1.0,
            "daily_precip_mm": [],
        }
