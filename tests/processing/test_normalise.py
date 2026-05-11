"""Unit tests for normalise: scaling, inverse transform, and view structure."""

import numpy as np
import pandas as pd
import pytest

from agri_sense.processing.normalise import NUMERIC_FEATURE_COLS, normalise


def _minimal_df() -> pd.DataFrame:
    """A minimal DataFrame with the columns normalise.py needs."""
    return pd.DataFrame(
        {
            "province_key": ["can_tho", "an_giang", "dak_lak", "thai_binh"],
            "province": ["Cần Thơ", "An Giang", "Đắk Lắk", "Thái Bình"],
            "year": [2021, 2021, 2022, 2022],
            "season": ["Đông Xuân", "Hè Thu", "main", "Mùa"],
            "crop": ["rice_paddy", "rice_paddy", "coffee_green", "maize"],
            "area_ha": [100, 200, 50, 300],
            "production_tonnes": [600, 1100, 130, 1600],
            "yield_tonnes_per_ha": [6.0, 5.5, 2.6, 5.3],
            "ph": [5.0, 6.0, 7.0, 5.5],
            "mean_temp_c": [24.0, 27.0, 20.0, 22.0],
            "soil_texture_class": ["clay", "clay", "loam", "silt"],
        }
    )


# ---------------------------------------------------------------------------
# Scaling correctness
# ---------------------------------------------------------------------------


def test_scaled_values_in_unit_interval() -> None:
    """All scaled numeric features must lie in [0, 1]."""
    df = _minimal_df()
    views, _ = normalise(df, fit=True)
    clf = views["classifier_view"]

    present = [c for c in NUMERIC_FEATURE_COLS if c in clf.columns]
    for col in present:
        assert clf[col].between(0.0, 1.0).all(), f"{col} has out-of-range values"


def test_min_maps_to_zero_max_maps_to_one() -> None:
    """The minimum value must scale to 0 and the maximum to 1."""
    df = _minimal_df()
    views, params = normalise(df, fit=True)
    clf = views["classifier_view"]

    for col in ["ph", "mean_temp_c"]:
        assert clf[col].min() == pytest.approx(0.0, abs=1e-9)
        assert clf[col].max() == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Inverse transform
# ---------------------------------------------------------------------------


def test_inverse_recovers_original_values() -> None:
    """Applying the inverse of min-max scaling recovers the original numeric values."""
    df = _minimal_df()
    views, params = normalise(df, fit=True)
    clf = views["classifier_view"]

    for col in ["ph", "mean_temp_c"]:
        lo = params["feature_min"][col]
        hi = params["feature_max"][col]
        recovered = clf[col] * (hi - lo) + lo
        pd.testing.assert_series_equal(
            recovered.reset_index(drop=True),
            df[col].astype(float).reset_index(drop=True),
            check_names=False,
            rtol=1e-6,
        )


# ---------------------------------------------------------------------------
# OHE structure
# ---------------------------------------------------------------------------


def test_season_ohe_columns_present() -> None:
    """classifier_view must contain season_* OHE columns, no raw season column."""
    df = _minimal_df()
    views, _ = normalise(df, fit=True)
    clf = views["classifier_view"]

    season_ohe_cols = [c for c in clf.columns if c.startswith("season_")]
    assert len(season_ohe_cols) > 0
    assert "season" not in clf.columns


def test_crop_not_ohe_in_classifier_view() -> None:
    """classifier_view must have crop as a string label, not as OHE columns."""
    df = _minimal_df()
    views, _ = normalise(df, fit=True)
    clf = views["classifier_view"]

    crop_ohe_cols = [c for c in clf.columns if c.startswith("crop_")]
    assert len(crop_ohe_cols) == 0
    assert "crop" in clf.columns


def test_crop_ohe_in_regressor_view() -> None:
    """regressor_view must have crop as OHE columns, no raw crop column."""
    df = _minimal_df()
    views, _ = normalise(df, fit=True)
    reg = views["regressor_view"]

    crop_ohe_cols = [c for c in reg.columns if c.startswith("crop_")]
    assert len(crop_ohe_cols) > 0
    assert "crop" not in reg.columns


def test_season_ohe_rows_sum_to_one() -> None:
    """Each row's season OHE columns must sum to exactly 1 (one-hot)."""
    df = _minimal_df()
    views, _ = normalise(df, fit=True)
    clf = views["classifier_view"]

    season_cols = [c for c in clf.columns if c.startswith("season_")]
    row_sums = clf[season_cols].sum(axis=1)
    np.testing.assert_allclose(row_sums.to_numpy(), 1.0, rtol=1e-9)


# ---------------------------------------------------------------------------
# Target and metadata preservation
# ---------------------------------------------------------------------------


def test_yield_target_preserved_and_unscaled() -> None:
    """yield_tonnes_per_ha must appear in both views and must NOT be scaled."""
    df = _minimal_df()
    views, _ = normalise(df, fit=True)

    for view_name, view in views.items():
        assert "yield_tonnes_per_ha" in view.columns, f"missing in {view_name}"
        pd.testing.assert_series_equal(
            view["yield_tonnes_per_ha"].reset_index(drop=True),
            df["yield_tonnes_per_ha"].reset_index(drop=True),
            check_names=False,
        )


def test_params_contain_expected_keys() -> None:
    """params dict must contain feature_min, feature_max, and category lists."""
    _, params = normalise(_minimal_df(), fit=True)

    assert "feature_min" in params
    assert "feature_max" in params
    assert "season_categories" in params
    assert "crop_categories" in params
    assert set(params["feature_min"].keys()) == set(params["feature_max"].keys())


# ---------------------------------------------------------------------------
# fit=False reproduces fit=True transform
# ---------------------------------------------------------------------------


def test_fit_false_reproduces_fit_true(tmp_path: pytest.TempPathFactory) -> None:
    """Applying a saved scaler (fit=False) must produce the same values as fit=True."""
    df = _minimal_df()
    scaler_path = tmp_path / "scaler.pkl"  # type: ignore[operator]

    views_fit, params_fit = normalise(df, fit=True, scaler_path=scaler_path)  # type: ignore[arg-type]
    views_inf, _params_inf = normalise(df, fit=False, scaler_path=scaler_path)  # type: ignore[arg-type]

    for col in ["ph", "mean_temp_c"]:
        pd.testing.assert_series_equal(
            views_fit["classifier_view"][col].reset_index(drop=True),
            views_inf["classifier_view"][col].reset_index(drop=True),
            check_names=False,
        )
