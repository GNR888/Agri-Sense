"""Min-max normalisation and one-hot encoding for the Agri-Sense feature matrix.

Returns two views of the transformed DataFrame:
  - 'classifier_view': features for the XGBClassifier; crop kept as string label.
  - 'regressor_view':  features for the XGBRegressor; crop replaced with OHE columns.
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Continuous features to scale to [0, 1].
NUMERIC_FEATURE_COLS: list[str] = [
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
    # Geographic features — province-level signals (see processing/features.py)
    "region_code",
    "salinity_risk",
    "elevation_zone",
]

_SEASON_COL = "season"
_CROP_COL = "crop"
_SOIL_TEX_COL = "soil_texture_class"
_TARGET_COL = "yield_tonnes_per_ha"

# Columns passed through as metadata (not model inputs, not scaled).
_METADATA_COLS: list[str] = [
    "province",
    "province_key",
    "year",
    "area_ha",
    "production_tonnes",
    "is_outlier_clipped",
]


def normalise(
    df: pd.DataFrame,
    fit: bool = True,
    scaler_path: Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Min-max scale continuous features; OHE season, crop (regressor only), and soil texture.

    Args:
        df:          Input DataFrame (post-clean and post-impute).
        fit:         Compute and save scaler params from *df*.
                     Pass False at inference time and supply *scaler_path* to load params.
        scaler_path: Path to read (fit=False) or write (fit=True) the scaler pickle.

    Returns:
        A (views, params) tuple where:
        - views["classifier_view"]: features + crop label + target (crop as string, not OHE).
        - views["regressor_view"]:  features + crop OHE + target (crop OHE, no string crop col).
        - params: scaler metadata dict (min, max, category lists) for inference reproducibility.
    """
    # ------------------------------------------------------------------ 1. load or fit params
    if fit:
        present_numeric = [c for c in NUMERIC_FEATURE_COLS if c in df.columns]
        feature_min = {c: float(df[c].min()) for c in present_numeric}
        feature_max = {c: float(df[c].max()) for c in present_numeric}
        season_cats = (
            sorted(df[_SEASON_COL].astype(str).unique().tolist())
            if _SEASON_COL in df.columns
            else []
        )
        crop_cats = (
            sorted(df[_CROP_COL].astype(str).unique().tolist())
            if _CROP_COL in df.columns
            else []
        )
        soil_tex_cats = (
            sorted(df[_SOIL_TEX_COL].astype(str).unique().tolist())
            if _SOIL_TEX_COL in df.columns
            else []
        )
        params: dict[str, Any] = {
            "feature_min": feature_min,
            "feature_max": feature_max,
            "season_categories": season_cats,
            "crop_categories": crop_cats,
            "soil_texture_categories": soil_tex_cats,
        }
    else:
        if scaler_path is None or not scaler_path.exists():
            raise ValueError(f"fit=False but scaler_path not found: {scaler_path}")
        with open(scaler_path, "rb") as fh:
            params = pickle.load(fh)
        feature_min = params["feature_min"]
        feature_max = params["feature_max"]

    # ------------------------------------------------------------------ 2. min-max scale
    out = df.copy()
    for col, lo in feature_min.items():
        if col not in out.columns:
            continue
        hi = feature_max[col]
        rng = hi - lo
        if rng == 0.0:
            # Constant feature — set to 0 rather than divide by zero
            out[col] = 0.0
        else:
            out[col] = (out[col] - lo) / rng

    # ------------------------------------------------------------------ 3. OHE season
    season_dummies: pd.DataFrame = pd.DataFrame(index=out.index)
    if _SEASON_COL in out.columns:
        season_dummies = pd.get_dummies(
            out[_SEASON_COL].astype(str), prefix="season", dtype=float
        )
        # Align to fitted categories so inference columns are consistent
        fitted_season_cols = [f"season_{c}" for c in params["season_categories"]]
        season_dummies = season_dummies.reindex(columns=fitted_season_cols, fill_value=0.0)

    # ------------------------------------------------------------------ 4. OHE soil texture
    soil_tex_dummies: pd.DataFrame = pd.DataFrame(index=out.index)
    if _SOIL_TEX_COL in out.columns:
        soil_tex_dummies = pd.get_dummies(
            out[_SOIL_TEX_COL].astype(str), prefix="soil_tex", dtype=float
        )
        fitted_soil_cols = [f"soil_tex_{c}" for c in params["soil_texture_categories"]]
        soil_tex_dummies = soil_tex_dummies.reindex(columns=fitted_soil_cols, fill_value=0.0)

    # ------------------------------------------------------------------ 5. OHE crop (regressor only)
    crop_dummies: pd.DataFrame = pd.DataFrame(index=out.index)
    if _CROP_COL in out.columns:
        crop_dummies = pd.get_dummies(
            out[_CROP_COL].astype(str), prefix="crop", dtype=float
        )
        fitted_crop_cols = [f"crop_{c}" for c in params["crop_categories"]]
        crop_dummies = crop_dummies.reindex(columns=fitted_crop_cols, fill_value=0.0)

    # ------------------------------------------------------------------ 6. assemble base frame
    # Collect imputed-flag columns added by impute.py
    imputed_flag_cols = [c for c in out.columns if c.endswith("_imputed")]

    # Columns to keep in both views (scaled numerics only — no raw categoricals)
    present_numeric = [c for c in NUMERIC_FEATURE_COLS if c in out.columns]
    metadata = [c for c in _METADATA_COLS if c in out.columns]

    base_cols = present_numeric + metadata + imputed_flag_cols
    target_col_list = [_TARGET_COL] if _TARGET_COL in out.columns else []

    base = out[base_cols + target_col_list].copy()

    # Attach OHE columns
    base = pd.concat([base, season_dummies, soil_tex_dummies], axis=1)

    # ------------------------------------------------------------------ 7. build two views
    # classifier_view: crop as string label, no crop OHE
    clf_view = base.copy()
    if _CROP_COL in out.columns:
        clf_view[_CROP_COL] = out[_CROP_COL].astype(str)

    # regressor_view: crop as OHE, no string crop col
    reg_view = pd.concat([base, crop_dummies], axis=1)

    views: dict[str, pd.DataFrame] = {
        "classifier_view": clf_view,
        "regressor_view": reg_view,
    }

    # ------------------------------------------------------------------ 8. save
    if fit and scaler_path is not None:
        scaler_path.parent.mkdir(parents=True, exist_ok=True)
        with open(scaler_path, "wb") as fh:
            pickle.dump(params, fh)

        # Also write a human-readable JSON alongside the pickle
        json_path = scaler_path.with_suffix(".json").with_name("scaler_params.json")
        json_path.write_text(json.dumps(params, indent=2, ensure_ascii=False))
        logger.info("Saved scaler → %s (+ scaler_params.json)", scaler_path)

    return views, params
