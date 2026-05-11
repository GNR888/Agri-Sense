"""Build the master training DataFrame joining yields, climate, soil, NDVI, and market prices.

Output: data/interim/master.parquet
Each row = (province, year, season, crop) with all features needed for modelling.
"""

import argparse
import logging
import time
from datetime import date
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from agri_sense.ingestion.gso_yields import load_yields
from agri_sense.ingestion.market_prices import load_prices
from agri_sense.ingestion.nasa_power import fetch_daily_weather
from agri_sense.ingestion.sentinel import fetch_ndvi_timeseries
from agri_sense.ingestion.soilgrids import fetch_soil_properties
from agri_sense.processing.features import add_province_features
from agri_sense.utils.config import config
from agri_sense.utils.geo import PROVINCE_NAME_TO_KEY, PROVINCES

logger = logging.getLogger(__name__)

# Sentinel-2 L2A reliable coverage starts 2017; earlier windows get NaN NDVI.
_SENTINEL2_START_YEAR: int = 2017


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def gdd(temp_series: pd.Series, base: float = 10.0) -> float:  # type: ignore[type-arg]
    """Return growing degree days: Σ max(0, T_mean − base) over the series."""
    return float((temp_series - base).clip(lower=0.0).sum())


def season_window(year: int, season: str) -> tuple[date, date]:
    """Return (start, end) inclusive date window for a (year, season) pair.

    Đông Xuân spans two calendar years: Nov(year-1) → Apr(year).
    "main" covers the full calendar year for annual/perennial crops.
    """
    if season == "Đông Xuân":
        return date(year - 1, 11, 1), date(year, 4, 30)
    if season == "Hè Thu":
        return date(year, 5, 1), date(year, 8, 31)
    if season == "Mùa":
        return date(year, 9, 1), date(year, 12, 31)
    if season == "main":
        return date(year, 1, 1), date(year, 12, 31)
    raise ValueError(f"Unknown season {season!r}")


def aggregate_weather(df: pd.DataFrame, window_start: date) -> dict[str, float]:
    """Summarise a NASA POWER daily DataFrame into season-level features."""
    nan = float("nan")
    if df.empty:
        return {
            "total_precip_mm": nan,
            "mean_temp_c": nan,
            "max_temp_c": nan,
            "min_temp_c": nan,
            "gdd_base10": nan,
            "mean_solar_mj": nan,
            "mean_humidity_pct": nan,
            "precip_cv": nan,
        }

    monthly_precip = df["precip_mm"].resample("ME").sum()
    monthly_mean = float(monthly_precip.mean())
    precip_cv = float(monthly_precip.std() / monthly_mean) if monthly_mean > 0.0 else nan

    return {
        "total_precip_mm": float(df["precip_mm"].sum()),
        "mean_temp_c": float(df["temp_mean_c"].mean()),
        "max_temp_c": float(df["temp_max_c"].mean()),   # mean of daily maxima
        "min_temp_c": float(df["temp_min_c"].mean()),   # mean of daily minima
        "gdd_base10": gdd(df["temp_mean_c"]),
        "mean_solar_mj": float(df["solar_mj"].mean()),
        "mean_humidity_pct": float(df["humidity_pct"].mean()),
        "precip_cv": precip_cv,
    }


def aggregate_ndvi(df: pd.DataFrame, window_start: date) -> dict[str, float]:
    """Summarise a Sentinel-2 NDVI timeseries into season-level features.

    Returns NaN for all columns when the DataFrame is empty (pre-2017 data,
    or no cloud-free scenes found).
    """
    nan = float("nan")
    if df.empty or df["ndvi_mean"].isna().all():
        return {"ndvi_peak": nan, "ndvi_days_to_peak": nan, "ndvi_mean_season": nan}

    peak_idx = int(df["ndvi_mean"].idxmax())
    peak_ts: pd.Timestamp = df.loc[peak_idx, "date"]
    days_to_peak = float((peak_ts - pd.Timestamp(window_start)).days)

    return {
        "ndvi_peak": float(df["ndvi_mean"].max()),
        "ndvi_days_to_peak": days_to_peak,
        "ndvi_mean_season": float(df["ndvi_mean"].mean()),
    }


# ---------------------------------------------------------------------------
# Sentinel-2 fetch with retry
# ---------------------------------------------------------------------------

_EMPTY_NDVI = pd.DataFrame(columns=["date", "ndvi_mean", "ndvi_std", "valid_pixel_pct"])
_NDVI_BACKOFF: tuple[int, ...] = (1, 4, 16)  # seconds between attempts 1→2, 2→3, 3→4


def _fetch_ndvi_resilient(
    lat: float,
    lon: float,
    start: date,
    end: date,
    key: tuple[str, int, str],
) -> pd.DataFrame:
    """Fetch NDVI with up to 4 attempts (3 retries, backoff 1 s / 4 s / 16 s).

    Returns an empty DataFrame on final failure and logs the specific
    (province, year, season) combo so missing data is traceable.
    """
    for attempt, wait in enumerate((*_NDVI_BACKOFF, None), start=1):
        try:
            return fetch_ndvi_timeseries(lat, lon, start, end)
        except Exception as exc:
            if wait is None:
                logger.warning(
                    "Sentinel-2 FAILED all %d attempts — province=%s year=%d season=%s → NaN NDVI | %s",
                    len(_NDVI_BACKOFF) + 1,
                    key[0],
                    key[1],
                    key[2],
                    exc,
                )
            else:
                logger.warning(
                    "Sentinel-2 attempt %d/%d failed for province=%s year=%d season=%s, retrying in %ds | %s",
                    attempt,
                    len(_NDVI_BACKOFF) + 1,
                    key[0],
                    key[1],
                    key[2],
                    wait,
                    exc,
                )
                time.sleep(wait)
    return _EMPTY_NDVI


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def build(force: bool = False) -> pd.DataFrame:
    """Run the feature-engineering pipeline and return the master DataFrame.

    Saves output to data/interim/master.parquet. Skips if the file already
    exists unless *force* is True.
    """
    output_path: Path = config.interim_dir / "master.parquet"
    if output_path.exists() and not force:
        logger.info("master.parquet already exists — loading from disk (pass force=True to rebuild)")
        return pd.read_parquet(output_path)

    # ------------------------------------------------------------------ 1. yields (row universe)
    yields_df = load_yields()
    yields_df = yields_df.copy()
    yields_df["province_key"] = yields_df["province"].map(PROVINCE_NAME_TO_KEY)

    unknown = yields_df.loc[yields_df["province_key"].isna(), "province"].unique()
    if len(unknown) > 0:
        raise ValueError(f"Province(s) not found in PROVINCE_NAME_TO_KEY: {list(unknown)}")

    # ------------------------------------------------------------------ 2. soil (one fetch per province)
    unique_pkeys: list[str] = [str(k) for k in yields_df["province_key"].dropna().unique()]
    soil_cache: dict[str, dict[str, float | str]] = {}

    logger.info("Fetching soil for %d provinces...", len(unique_pkeys))
    for pkey in tqdm(unique_pkeys, desc="SoilGrids", unit="province"):
        info = PROVINCES[pkey]
        soil_cache[pkey] = fetch_soil_properties(info.farm_lat, info.farm_lon)

    # ------------------------------------------------------------------ 3. climate + NDVI (one fetch per province×year×season)
    unique_combos = (
        yields_df[["province_key", "year", "season"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    combo_list: list[tuple[str, int, str]] = [
        (str(pk), int(yr), str(sn)) for pk, yr, sn in unique_combos
    ]

    climate_cache: dict[tuple[str, int, str], dict[str, float]] = {}
    ndvi_cache: dict[tuple[str, int, str], dict[str, float]] = {}

    logger.info("Fetching climate + NDVI for %d unique (province, year, season) combos...", len(combo_list))
    for pkey, year, season in tqdm(combo_list, desc="Climate+NDVI", unit="combo"):
        key = (pkey, year, season)
        info = PROVINCES[pkey]
        start, end = season_window(year, season)

        weather_df = fetch_daily_weather(
            info.farm_lat, info.farm_lon, start, end,
            cache_tag=f"{pkey}_{season}_{year}",
        )
        climate_cache[key] = aggregate_weather(weather_df, start)

        if start.year >= _SENTINEL2_START_YEAR:
            ndvi_df = _fetch_ndvi_resilient(info.farm_lat, info.farm_lon, start, end, key)
        else:
            ndvi_df = _EMPTY_NDVI
        ndvi_cache[key] = aggregate_ndvi(ndvi_df, start)

    # ------------------------------------------------------------------ 4. market prices (latest available per crop)
    prices_df = load_prices()
    latest_prices: dict[str, int] = (
        prices_df.sort_values("year").groupby("crop")["price_vnd_per_kg"].last().to_dict()
    )

    # ------------------------------------------------------------------ 5. assemble row by row
    records: list[dict[str, object]] = []
    for row in tqdm(yields_df.itertuples(index=False), total=len(yields_df), desc="Assembling rows"):
        pkey = str(row.province_key)
        key = (pkey, int(row.year), str(row.season))
        info = PROVINCES[pkey]

        record: dict[str, object] = {
            "province": row.province,
            "province_key": pkey,
            "year": int(row.year),
            "season": row.season,
            "crop": row.crop,
            "area_ha": int(row.area_ha),
            "production_tonnes": int(row.production_tonnes),
            "yield_tonnes_per_ha": float(row.yield_tonnes_per_ha),
            "farm_lat": info.farm_lat,
            "farm_lon": info.farm_lon,
        }
        record.update(climate_cache[key])
        record.update(soil_cache[pkey])
        record.update(ndvi_cache[key])
        record["price_vnd_per_kg"] = latest_prices.get(str(row.crop))
        record.update(add_province_features(pkey, info.region))
        records.append(record)

    master = pd.DataFrame(records)

    config.interim_dir.mkdir(parents=True, exist_ok=True)
    master.to_parquet(output_path, index=False)
    logger.info("Saved → %s  (%d rows × %d cols)", output_path, *master.shape)
    return master


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    parser = argparse.ArgumentParser(description="Build master training dataset (data/interim/master.parquet).")
    parser.add_argument("--force", action="store_true", help="Rebuild even if master.parquet already exists")
    args = parser.parse_args()

    master = build(force=args.force)

    print(f"\nShape: {master.shape}")

    print("\n── df.head() ─────────────────────────────────────────────────────────")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(master.head().to_string())

    print("\n── df.dtypes ──────────────────────────────────────────────────────────")
    print(master.dtypes.to_string())

    print("\n── NaN counts per column ──────────────────────────────────────────────")
    nan_counts = master.isna().sum()
    nan_pct = (master.isna().mean() * 100).round(1)
    nan_df = pd.DataFrame({"nan_count": nan_counts, "nan_pct_%": nan_pct})
    has_nans = nan_df[nan_df["nan_count"] > 0]
    if has_nans.empty:
        print("No NaNs in any column.")
    else:
        print(has_nans.to_string())

    ndvi_nan_mask = master["ndvi_peak"].isna()
    if ndvi_nan_mask.any():
        print("\n── Rows with NaN NDVI (province / year / season) ─────────────────────")
        breakdown = (
            master.loc[ndvi_nan_mask, ["province", "year", "season", "crop"]]
            .sort_values(["province", "year", "season"])
            .to_string(index=False)
        )
        print(breakdown)
    else:
        print("\nAll NDVI values populated — no NaN NDVI rows.")


if __name__ == "__main__":
    main()
