"""Unit tests for subset-mean imputation fallback chain."""

import numpy as np
import pandas as pd
import pytest

from agri_sense.processing.impute import impute


def _make_df(**kwargs: list) -> pd.DataFrame:  # type: ignore[type-arg]
    return pd.DataFrame(kwargs)


# ---------------------------------------------------------------------------
# Level-1 fill: (province_key, soil_texture_class) group mean
# ---------------------------------------------------------------------------


def test_l1_fills_from_province_texture_group() -> None:
    """A missing value is filled by the mean of its (province_key, texture) group."""
    df = _make_df(
        province_key=["prov_a", "prov_a", "prov_a"],
        soil_texture_class=["clay", "clay", "loam"],
        ph=[6.0, np.nan, 7.0],  # prov_a/clay group mean = 6.0
    )
    result = impute(df)

    assert result.loc[1, "ph"] == pytest.approx(6.0)
    assert bool(result.loc[1, "ph_imputed"])
    # Non-missing cell is unchanged and NOT flagged
    assert result.loc[0, "ph"] == pytest.approx(6.0)
    assert not bool(result.loc[0, "ph_imputed"])


def test_l1_multiple_values_in_group() -> None:
    """Group mean uses all non-missing values in the group."""
    df = _make_df(
        province_key=["p", "p", "p", "p"],
        soil_texture_class=["clay", "clay", "clay", "clay"],
        ph=[4.0, 6.0, 8.0, np.nan],  # mean of [4, 6, 8] = 6.0
    )
    result = impute(df)

    assert result.loc[3, "ph"] == pytest.approx(6.0)
    assert bool(result.loc[3, "ph_imputed"])


# ---------------------------------------------------------------------------
# Level-2 fallback: (region, soil_texture_class) group mean
# ---------------------------------------------------------------------------


def test_l2_fallback_when_province_group_empty() -> None:
    """Province group has no values → falls back to region mean."""
    # can_tho and an_giang are both in mekong_delta
    df = _make_df(
        province_key=["can_tho", "an_giang", "an_giang"],
        soil_texture_class=["clay", "clay", "clay"],
        ph=[np.nan, 6.5, 5.5],  # can_tho/clay: no values → region mean = (6.5+5.5)/2 = 6.0
    )
    result = impute(df)

    assert result.loc[0, "ph"] == pytest.approx(6.0)
    assert bool(result.loc[0, "ph_imputed"])


def test_l1_used_when_province_has_values_l2_skipped() -> None:
    """Province group has values → L1 is used; L2 region values are NOT used."""
    # can_tho/clay has one value (5.0), region has additional values from an_giang (9.0)
    df = _make_df(
        province_key=["can_tho", "can_tho", "an_giang"],
        soil_texture_class=["clay", "clay", "clay"],
        ph=[5.0, np.nan, 9.0],
    )
    result = impute(df)

    # L1 group mean for can_tho/clay = 5.0 (only one non-missing value)
    assert result.loc[1, "ph"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Level-3 fallback: global mean
# ---------------------------------------------------------------------------


def test_l3_global_mean_when_both_groups_empty() -> None:
    """Unknown province + texture → no L1 or L2 match → global mean."""
    df = _make_df(
        province_key=["unknown_prov", "prov_x", "prov_y"],
        soil_texture_class=["mystery_soil", "loam", "loam"],
        ph=[np.nan, 6.0, 7.0],  # global mean = (6+7)/2 = 6.5
    )
    result = impute(df)

    assert result.loc[0, "ph"] == pytest.approx(6.5)
    assert bool(result.loc[0, "ph_imputed"])


# ---------------------------------------------------------------------------
# Imputed-flag semantics
# ---------------------------------------------------------------------------


def test_imputed_flag_only_set_for_filled_cells() -> None:
    """Rows that already had values must have flag=False."""
    df = _make_df(
        province_key=["p", "p"],
        soil_texture_class=["clay", "clay"],
        ph=[6.0, np.nan],
    )
    result = impute(df)

    assert not bool(result.loc[0, "ph_imputed"])
    assert bool(result.loc[1, "ph_imputed"])


def test_no_imputed_flag_when_no_missing() -> None:
    """Column without missing values gets no imputed flag."""
    df = _make_df(
        province_key=["p", "p"],
        soil_texture_class=["clay", "clay"],
        ph=[6.0, 7.0],
    )
    result = impute(df)

    assert "ph_imputed" not in result.columns


# ---------------------------------------------------------------------------
# Multiple columns
# ---------------------------------------------------------------------------


def test_multiple_columns_imputed_independently() -> None:
    """Each numeric column gets its own imputed flag; fills are independent."""
    df = _make_df(
        province_key=["p", "p", "p"],
        soil_texture_class=["clay", "clay", "clay"],
        ph=[np.nan, 5.0, 6.0],  # group mean = 5.5
        mean_temp_c=[25.0, np.nan, 27.0],  # group mean = 26.0
    )
    result = impute(df)

    assert result.loc[0, "ph"] == pytest.approx(5.5)
    assert bool(result.loc[0, "ph_imputed"])
    assert result.loc[1, "mean_temp_c"] == pytest.approx(26.0)
    assert bool(result.loc[1, "mean_temp_c_imputed"])
