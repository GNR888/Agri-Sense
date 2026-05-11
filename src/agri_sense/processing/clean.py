"""Clean raw master dataset: drop missing targets, cast dtypes, clip yield outliers."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Per-crop plausible yield bounds (tonnes/ha). Outside → clipped and flagged.
_YIELD_BOUNDS: dict[str, tuple[float, float]] = {
    "rice_paddy":   (0.5, 12.0),
    "maize":        (1.0, 12.0),
    "coffee_green": (0.1,  5.0),
    "pepper_black": (0.1,  6.0),
    "cashew_raw":   (0.1,  3.5),
}
_DEFAULT_YIELD_BOUNDS: tuple[float, float] = (0.1, 20.0)

_CATEGORICAL_COLS: list[str] = [
    "province",
    "province_key",
    "season",
    "crop",
    "soil_texture_class",
]
_NUMERIC_COLS: list[str] = [
    "area_ha",
    "production_tonnes",
    "yield_tonnes_per_ha",
    "year",
    "farm_lat",
    "farm_lon",
    "total_precip_mm",
    "mean_temp_c",
    "max_temp_c",
    "min_temp_c",
    "gdd_base10",
    "mean_solar_mj",
    "mean_humidity_pct",
    "precip_cv",
    "bulk_density_kg_per_dm3",
    "cec_mmol_per_kg",
    "clay_pct",
    "nitrogen_cg_per_kg",
    "ph",
    "sand_pct",
    "silt_pct",
    "soc_g_per_kg",
    "ndvi_peak",
    "ndvi_days_to_peak",
    "ndvi_mean_season",
    "price_vnd_per_kg",
    "region_code",
    "salinity_risk",
    "elevation_zone",
]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Return a cleaned copy of *df*.

    Steps:
    1. Drop rows with missing yield_tonnes_per_ha (the training target).
    2. Cast categorical and numeric columns to proper dtypes.
    3. Clip per-crop yield outliers; mark clipped rows with 'is_outlier_clipped'.
    """
    out = df.copy()

    # 1. Drop rows missing the target
    n_before = len(out)
    out = out.dropna(subset=["yield_tonnes_per_ha"]).reset_index(drop=True)
    if (dropped := n_before - len(out)):
        logger.warning("Dropped %d rows with missing yield_tonnes_per_ha", dropped)

    # 2. Cast dtypes
    for col in _CATEGORICAL_COLS:
        if col in out.columns:
            out[col] = out[col].astype("category")
    for col in _NUMERIC_COLS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    # 3. Clip per-crop outliers
    out["is_outlier_clipped"] = False

    # Build a complete bounds map including any crops not in _YIELD_BOUNDS
    all_crops = (
        [str(c) for c in out["crop"].cat.categories]
        if hasattr(out["crop"], "cat")
        else out["crop"].unique().tolist()
    )
    bounds: dict[str, tuple[float, float]] = {
        c: _YIELD_BOUNDS.get(c, _DEFAULT_YIELD_BOUNDS) for c in all_crops
    }

    for crop_name, (lo, hi) in bounds.items():
        crop_mask = out["crop"] == crop_name
        if not crop_mask.any():
            continue
        outlier = crop_mask & (
            (out["yield_tonnes_per_ha"] < lo) | (out["yield_tonnes_per_ha"] > hi)
        )
        if outlier.any():
            logger.warning(
                "Clipping %d %s yield outliers to [%.1f, %.1f] t/ha",
                int(outlier.sum()),
                crop_name,
                lo,
                hi,
            )
            out.loc[outlier, "is_outlier_clipped"] = True
        out.loc[crop_mask, "yield_tonnes_per_ha"] = (
            out.loc[crop_mask, "yield_tonnes_per_ha"].clip(lower=lo, upper=hi)
        )

    return out
