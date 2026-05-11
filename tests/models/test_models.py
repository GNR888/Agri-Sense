"""Smoke tests for CropClassifier, YieldRegressor, and recommend()."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agri_sense.models.crop_classifier import CropClassifier
from agri_sense.models.yield_regressor import YieldRegressor
from agri_sense.utils.config import config


# ---------------------------------------------------------------------------
# Tiny synthetic dataset helpers
# ---------------------------------------------------------------------------

_CROPS = ["rice_paddy", "maize", "coffee_green", "pepper_black", "cashew_raw"]
_SEASONS = ["Đông Xuân", "Hè Thu", "Mùa", "main"]
_SOIL_TEXTURES = ["loam", "clay", "silty clay loam"]
_RNG = np.random.default_rng(0)


def _make_training_df(n: int = 60) -> pd.DataFrame:
    """Return a tiny training DataFrame that mirrors the real training.parquet schema."""
    crops = _RNG.choice(_CROPS, n)
    rows = {
        # Scaled numeric features
        "farm_lat": _RNG.uniform(0, 1, n),
        "farm_lon": _RNG.uniform(0, 1, n),
        "total_precip_mm": _RNG.uniform(0, 1, n),
        "mean_temp_c": _RNG.uniform(0, 1, n),
        "max_temp_c": _RNG.uniform(0, 1, n),
        "min_temp_c": _RNG.uniform(0, 1, n),
        "gdd_base10": _RNG.uniform(0, 1, n),
        "mean_solar_mj": _RNG.uniform(0, 1, n),
        "mean_humidity_pct": _RNG.uniform(0, 1, n),
        "precip_cv": _RNG.uniform(0, 1, n),
        "bulk_density_kg_per_dm3": _RNG.uniform(0, 1, n),
        "cec_mmol_per_kg": _RNG.uniform(0, 1, n),
        "clay_pct": _RNG.uniform(0, 1, n),
        "nitrogen_cg_per_kg": _RNG.uniform(0, 1, n),
        "ph": _RNG.uniform(0, 1, n),
        "sand_pct": _RNG.uniform(0, 1, n),
        "silt_pct": _RNG.uniform(0, 1, n),
        "soc_g_per_kg": _RNG.uniform(0, 1, n),
        "ndvi_peak": _RNG.uniform(0, 1, n),
        "ndvi_days_to_peak": _RNG.uniform(0, 1, n),
        "ndvi_mean_season": _RNG.uniform(0, 1, n),
        "price_vnd_per_kg": _RNG.uniform(0, 1, n),
        # Geographic features
        "region_code": _RNG.integers(0, 4, n).astype(float),
        "salinity_risk": _RNG.integers(0, 2, n).astype(float),
        "elevation_zone": _RNG.integers(0, 3, n).astype(float),
        # Imputed flags
        "ndvi_peak_imputed": _RNG.integers(0, 2, n).astype(bool),
        "ndvi_days_to_peak_imputed": _RNG.integers(0, 2, n).astype(bool),
        "ndvi_mean_season_imputed": _RNG.integers(0, 2, n).astype(bool),
        # OHE season
        "season_Đông Xuân": _RNG.integers(0, 2, n).astype(float),
        "season_Hè Thu": _RNG.integers(0, 2, n).astype(float),
        "season_Mùa": _RNG.integers(0, 2, n).astype(float),
        "season_main": _RNG.integers(0, 2, n).astype(float),
        # OHE soil texture
        "soil_tex_loam": _RNG.integers(0, 2, n).astype(float),
        "soil_tex_clay": _RNG.integers(0, 2, n).astype(float),
        "soil_tex_silty clay loam": _RNG.integers(0, 2, n).astype(float),
        # Label + target
        "crop": crops,
        "yield_tonnes_per_ha": _RNG.uniform(1, 10, n),
        # Metadata (should be excluded from features)
        "province": ["Cần Thơ"] * n,
        "province_key": ["can_tho"] * n,
        "year": _RNG.integers(2017, 2024, n),
        "area_ha": _RNG.integers(100, 5000, n),
        "production_tonnes": _RNG.integers(500, 50000, n),
        "is_outlier_clipped": _RNG.integers(0, 2, n).astype(bool),
    }
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CropClassifier smoke test
# ---------------------------------------------------------------------------


def test_crop_classifier_fit_predict() -> None:
    from agri_sense.models.train import _split_classifier

    df = _make_training_df(60)
    X, y = _split_classifier(df)

    clf = CropClassifier()
    clf.fit(X, y)

    assert len(clf.classes_) == len(_CROPS)
    assert len(clf.feature_columns) == X.shape[1]

    preds = clf.predict(X)
    assert preds.shape == (len(X),)
    assert set(preds).issubset(set(_CROPS))

    proba = clf.predict_proba(X)
    assert proba.shape == (len(X), len(_CROPS))
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5)


def test_crop_classifier_save_load(tmp_path: Path) -> None:
    from agri_sense.models.train import _split_classifier

    df = _make_training_df(60)
    X, y = _split_classifier(df)

    clf = CropClassifier()
    clf.fit(X, y)

    model_path = tmp_path / "classifier.json"
    clf.save(model_path)

    clf2 = CropClassifier()
    clf2.load(model_path)

    assert clf2.classes_ == clf.classes_
    assert clf2.feature_columns == clf.feature_columns

    np.testing.assert_array_equal(clf2.predict(X), clf.predict(X))


# ---------------------------------------------------------------------------
# YieldRegressor smoke test
# ---------------------------------------------------------------------------


def test_yield_regressor_fit_predict() -> None:
    from agri_sense.models.train import _split_regressor

    df = _make_training_df(60)
    X, y, crop_labels = _split_regressor(df)

    reg = YieldRegressor()
    reg.fit(X, y, crop_labels=crop_labels)

    assert len(reg.feature_columns) == X.shape[1]

    preds = reg.predict(X)
    assert preds.shape == (len(X),)
    assert np.all(np.isfinite(preds))


def test_yield_regressor_save_load(tmp_path: Path) -> None:
    from agri_sense.models.train import _split_regressor

    df = _make_training_df(60)
    X, y, crop_labels = _split_regressor(df)

    reg = YieldRegressor()
    reg.fit(X, y, crop_labels=crop_labels)

    model_path = tmp_path / "regressor.json"
    reg.save(model_path)

    reg2 = YieldRegressor()
    reg2.load(model_path)

    assert reg2.feature_columns == reg.feature_columns
    np.testing.assert_allclose(reg2.predict(X), reg.predict(X), rtol=1e-5)


# ---------------------------------------------------------------------------
# Full pipeline smoke test against real training.parquet
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (config.processed_dir / "training.parquet").exists(),
    reason="training.parquet not built",
)
def test_train_all_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Load real data, train both models, assert outputs have correct shapes."""
    import shutil

    from agri_sense.models.train import train_all

    real_processed = config.processed_dir
    tmp_processed = tmp_path / "processed"
    tmp_processed.mkdir()

    # Copy files that train_all() reads but doesn't write
    for fname in ("training.parquet", "scaler.pkl", "scaler_params.json"):
        src = real_processed / fname
        if src.exists():
            shutil.copy(src, tmp_processed / fname)

    # Patch the computed property at class level so config.processed_dir returns tmp_processed.
    # config.__dict__ assignment doesn't work for @computed_field properties in pydantic v2.
    monkeypatch.setattr(type(config), "processed_dir", property(lambda self: tmp_processed))

    train_all()
    # classifier_meta.json is always written regardless of backend (XGBoost or sklearn).
    assert (tmp_processed / "classifier_meta.json").exists()
    assert (tmp_processed / "regressor_meta.json").exists()
    assert (tmp_processed / "feature_columns.json").exists()


# ---------------------------------------------------------------------------
# recommend() structure test (uses saved models if present)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (config.processed_dir / "classifier_meta.json").exists(),
    reason="trained models not present; run scripts/train.py first",
)
def test_recommend_structure() -> None:
    """Verify recommend() returns a well-formed dict without asserting specific values."""
    from agri_sense.models.predict import recommend

    result = recommend(lat=10.0341, lon=105.7880, season="Đông Xuân", top_k=3)

    assert isinstance(result, dict)
    assert "recommendations" in result
    assert "farm_plan" in result
    assert "is_high_risk" in result

    recs = result["recommendations"]
    assert isinstance(recs, list)
    assert 1 <= len(recs) <= 3

    required_keys = {
        "crop",
        "probability",
        "predicted_yield_t_ha",
        "expected_revenue_vnd_per_ha",
        "confidence",
        "price_forecast_vnd_per_tonne",
        "price_trend",
        "fertiliser_recommendation",
    }
    for rec in recs:
        assert required_keys == set(rec.keys()), f"Missing keys in {rec}"
        assert 0.0 <= float(str(rec["probability"])) <= 1.0
        assert float(str(rec["predicted_yield_t_ha"])) >= 0.0
        assert rec["confidence"] in ("high", "medium", "low")
        assert rec["price_trend"] in ("rising", "falling", "stable")
        pf = rec["price_forecast_vnd_per_tonne"]
        assert all(f"month_{i}" in pf for i in range(1, 7))
        fert = rec["fertiliser_recommendation"]
        assert "N_kg_per_ha" in fert and "notes" in fert

    # farm_plan is None when farm_size_ha not provided
    assert result["farm_plan"] is None

    # With farm_size_ha, farm_plan should be populated
    result2 = recommend(lat=10.0341, lon=105.7880, season="Đông Xuân", top_k=3, farm_size_ha=5.0)
    assert result2["farm_plan"] is not None
    fp = result2["farm_plan"]
    assert fp["farm_size_ha"] == 5.0
    assert len(fp["allocations"]) <= 3
