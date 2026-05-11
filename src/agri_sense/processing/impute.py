"""Subset-mean imputation for Agri-Sense numeric features.

Fallback chain (per CLAUDE.md modeling notes):
  Level 1 — group by (province_key, soil_texture_class)
  Level 2 — group by (region, soil_texture_class)
  Level 3 — global mean

Each imputed numeric column gains a companion boolean '{col}_imputed' flag.
Categorical missingness is filled with 'unknown' with a warning.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Maps province_key → region name. Defined in CLAUDE.md.
_PROVINCE_TO_REGION: dict[str, str] = {
    "can_tho":   "mekong_delta",
    "an_giang":  "mekong_delta",
    "dong_thap": "mekong_delta",
    "soc_trang": "mekong_delta",
    "dak_lak":   "central_highlands",
    "lam_dong":  "central_highlands",
    "gia_lai":   "central_highlands",
    "thai_binh": "red_river_delta",
    "nam_dinh":  "red_river_delta",
}
_DEFAULT_REGION = "other"

# Columns that carry metadata — never impute these.
_NO_IMPUTE: frozenset[str] = frozenset(
    {"year", "area_ha", "production_tonnes", "price_vnd_per_kg", "is_outlier_clipped"}
)


def impute(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with numeric NaNs filled via subset-mean imputation.

    For each imputed feature column a boolean '{feature}_imputed' flag column is
    added (True = this cell was filled by imputation).
    """
    out = df.copy()

    # Attach a temporary region column for the level-2 fallback
    pkey_str = out["province_key"].astype(str) if "province_key" in out.columns else pd.Series(
        "", index=out.index
    )
    out["_region"] = pkey_str.map(_PROVINCE_TO_REGION).fillna(_DEFAULT_REGION)

    # Fill categorical NaN first
    cat_cols = [
        c
        for c in out.select_dtypes(include=["object", "str", "category"]).columns
        if c != "_region" and out[c].isna().any()
    ]
    for col in cat_cols:
        n_missing = int(out[col].isna().sum())
        logger.warning(
            "Categorical column %r has %d missing values — filling with 'unknown'", col, n_missing
        )
        if hasattr(out[col], "cat") and "unknown" not in out[col].cat.categories:
            out[col] = out[col].cat.add_categories("unknown")
        out[col] = out[col].fillna("unknown")

    # Identify numeric columns to impute
    numeric_cols = [
        c
        for c in out.select_dtypes(include="number").columns
        if c not in _NO_IMPUTE and out[c].isna().any()
    ]

    for col in numeric_cols:
        flag_col = f"{col}_imputed"
        out[flag_col] = False

        n_total = int(out[col].isna().sum())
        n_l1 = n_l2 = n_l3 = 0

        # Level 1 — (province_key, soil_texture_class)
        if "province_key" in out.columns and "soil_texture_class" in out.columns:
            grp1 = out.groupby(
                [out["province_key"].astype(str), out["soil_texture_class"].astype(str)],
                observed=True,
            )[col].transform("mean")
            missing = out[col].isna()
            can_fill = missing & grp1.notna()
            out.loc[can_fill, col] = grp1[can_fill]
            out.loc[can_fill, flag_col] = True
            n_l1 = int(can_fill.sum())

        # Level 2 — (region, soil_texture_class)
        if out[col].isna().any() and "soil_texture_class" in out.columns:
            grp2 = out.groupby(
                ["_region", out["soil_texture_class"].astype(str)],
                observed=True,
            )[col].transform("mean")
            missing = out[col].isna()
            can_fill = missing & grp2.notna()
            out.loc[can_fill, col] = grp2[can_fill]
            out.loc[can_fill, flag_col] = True
            n_l2 = int(can_fill.sum())

        # Level 3 — global mean
        if out[col].isna().any():
            global_mean = float(out[col].mean())
            missing = out[col].isna()
            out.loc[missing, col] = global_mean
            out.loc[missing, flag_col] = True
            n_l3 = int(missing.sum())

        logger.info(
            "Imputed %r: %d NaN(s) → L1(province+texture)=%d, L2(region+texture)=%d, L3(global)=%d",
            col,
            n_total,
            n_l1,
            n_l2,
            n_l3,
        )

    out = out.drop(columns=["_region"])
    return out
