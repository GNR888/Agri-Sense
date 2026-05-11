"""Tests for sentinel NDVI ingestion."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from agri_sense.ingestion.sentinel import _INVALID_SCL, fetch_ndvi_timeseries

# ---------------------------------------------------------------------------
# Unit tests — NDVI math (no network)
# ---------------------------------------------------------------------------


def _compute_ndvi(b04: np.ndarray, b08: np.ndarray) -> np.ndarray:
    """Mirror the production NDVI formula for testing."""
    denom = b08 + b04
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denom > 0, (b08 - b04) / denom, np.nan)


def test_ndvi_pure_vegetation() -> None:
    """High NIR, low red → NDVI close to +1."""
    b04 = np.array([[100.0, 200.0]], dtype=np.float32)
    b08 = np.array([[900.0, 800.0]], dtype=np.float32)
    ndvi = _compute_ndvi(b04, b08)
    assert np.all(ndvi > 0.5), f"Expected NDVI > 0.5 for vegetation, got {ndvi}"


def test_ndvi_bare_soil() -> None:
    """Balanced reflectance → NDVI near 0."""
    b04 = np.array([[500.0, 500.0]], dtype=np.float32)
    b08 = np.array([[550.0, 450.0]], dtype=np.float32)
    ndvi = _compute_ndvi(b04, b08)
    assert np.all(np.abs(ndvi) < 0.1), f"Expected |NDVI| < 0.1 for bare soil, got {ndvi}"


def test_ndvi_water() -> None:
    """High red, low NIR (water) → negative NDVI."""
    b04 = np.array([[1200.0]], dtype=np.float32)
    b08 = np.array([[300.0]], dtype=np.float32)
    ndvi = _compute_ndvi(b04, b08)
    assert ndvi[0, 0] < 0.0, f"Expected negative NDVI for water, got {ndvi[0, 0]}"


def test_ndvi_zero_denominator() -> None:
    """Zero denominator (both bands 0) → NaN, not crash."""
    b04 = np.array([[0.0]], dtype=np.float32)
    b08 = np.array([[0.0]], dtype=np.float32)
    ndvi = _compute_ndvi(b04, b08)
    assert np.isnan(ndvi[0, 0]), "Expected NaN when B04=B08=0"


def test_ndvi_bounded() -> None:
    """NDVI must lie in [-1, +1] for all valid (positive) pixels."""
    rng = np.random.default_rng(42)
    b04 = rng.integers(1, 10000, size=(50, 50)).astype(np.float32)
    b08 = rng.integers(1, 10000, size=(50, 50)).astype(np.float32)
    ndvi = _compute_ndvi(b04, b08)
    finite = ndvi[np.isfinite(ndvi)]
    assert np.all(finite >= -1.0) and np.all(finite <= 1.0), "NDVI out of [-1, 1] bounds"


def test_invalid_scl_values() -> None:
    """_INVALID_SCL must include all cloud, shadow, water, and noise classes."""
    # Original cloud/shadow/snow classes
    required_cloud = {3, 8, 9, 10, 11}
    # Water and ambiguous classes that bias NDVI downward
    required_water_noise = {0, 1, 2, 6, 7}
    required = required_cloud | required_water_noise
    assert required.issubset(_INVALID_SCL), f"Missing SCL values: {required - _INVALID_SCL}"
    # Vegetation (4) and bare soil (5) must NOT be excluded
    assert 4 not in _INVALID_SCL, "SCL 4 (vegetation) must not be in _INVALID_SCL"
    assert 5 not in _INVALID_SCL, "SCL 5 (bare soil) must not be in _INVALID_SCL"


def test_cloud_masking_removes_cloud_pixels() -> None:
    """Pixels with cloud SCL values should not contribute to NDVI mean."""
    # 2x2: top row is clear vegetation, bottom row is high-cloud (SCL=9)
    b04 = np.array([[100.0, 100.0], [100.0, 100.0]], dtype=np.float32)
    b08 = np.array([[900.0, 900.0], [900.0, 900.0]], dtype=np.float32)
    scl = np.array([[4, 4], [9, 9]], dtype=np.uint8)  # 4=vegetation, 9=high-prob cloud

    cloud_mask = np.isin(scl, list(_INVALID_SCL))
    denom = b08 + b04
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi: np.ndarray = np.where((denom > 0) & ~cloud_mask, (b08 - b04) / denom, np.nan)

    assert np.isnan(ndvi[1, 0]) and np.isnan(ndvi[1, 1]), "Cloud pixels should be NaN"
    assert np.isfinite(ndvi[0, 0]) and np.isfinite(ndvi[0, 1]), "Clear pixels should be finite"
    assert float(np.nanmean(ndvi)) == pytest.approx((900 - 100) / (900 + 100), abs=1e-4)


# ---------------------------------------------------------------------------
# Integration test (slow — live network, skipped in normal CI)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_fetch_ndvi_timeseries_can_tho() -> None:
    """Live integration test: fetch NDVI for Cần Thơ over one month."""
    df = fetch_ndvi_timeseries(
        lat=10.0341,
        lon=105.7880,
        start=date(2024, 1, 1),
        end=date(2024, 3, 1),
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"date", "ndvi_mean", "ndvi_std", "valid_pixel_pct"}

    if df.empty:
        pytest.skip("No cloud-free scenes found for this period — acceptable for CI")

    assert df["ndvi_mean"].between(-1.0, 1.0).all(), "NDVI values out of range"
    assert (df["valid_pixel_pct"] >= 50.0).all(), "valid_pixel_pct below threshold"
    assert df["date"].is_monotonic_increasing, "Dates not sorted"
    assert not df["date"].duplicated().any(), "Duplicate dates in result"
