"""Tests for the rule-based fertiliser recommendation engine."""

from __future__ import annotations

import pytest

from agri_sense.recommendations.fertiliser import BASE_RATES, recommend_fertiliser

_ALL_CROPS = list(BASE_RATES.keys())


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

def test_required_keys_present() -> None:
    result = recommend_fertiliser("rice_paddy", 900, 27, 6.0, 15.0)
    required = {"N_kg_per_ha", "P2O5_kg_per_ha", "K2O_kg_per_ha", "lime_tonnes_per_ha", "notes"}
    assert required == set(result.keys())


def test_all_numeric_values_positive() -> None:
    """N, P, K must be > 0 for all crops under normal conditions."""
    for crop in _ALL_CROPS:
        result = recommend_fertiliser(crop, 900, 27, 6.0, 15.0)
        assert result["N_kg_per_ha"] > 0, f"{crop}: N should be > 0"
        assert result["P2O5_kg_per_ha"] > 0, f"{crop}: P2O5 should be > 0"
        assert result["K2O_kg_per_ha"] > 0, f"{crop}: K2O should be > 0"
        assert result["lime_tonnes_per_ha"] >= 0, f"{crop}: lime should be >= 0"


# ---------------------------------------------------------------------------
# Rainfall adjustments
# ---------------------------------------------------------------------------

def test_high_rainfall_reduces_nitrogen() -> None:
    """Rainfall > 1200 mm should reduce N below the base rate."""
    base = recommend_fertiliser("rice_paddy", 900, 27, 6.0, 15.0)
    high_rain = recommend_fertiliser("rice_paddy", 1400, 27, 6.0, 15.0)
    assert high_rain["N_kg_per_ha"] < base["N_kg_per_ha"]


def test_high_rainfall_note_present() -> None:
    result = recommend_fertiliser("rice_paddy", 1400, 27, 6.0, 15.0)
    assert any("leach" in n.lower() for n in result["notes"])


def test_low_rainfall_increases_k2o() -> None:
    """Rainfall < 600 mm should increase K2O above the base rate."""
    base = recommend_fertiliser("rice_paddy", 900, 27, 6.0, 15.0)
    low_rain = recommend_fertiliser("rice_paddy", 400, 27, 6.0, 15.0)
    assert low_rain["K2O_kg_per_ha"] > base["K2O_kg_per_ha"]


# ---------------------------------------------------------------------------
# Temperature adjustments
# ---------------------------------------------------------------------------

def test_high_temp_reduces_nitrogen() -> None:
    """Mean temp > 32°C should reduce N below the base rate."""
    base = recommend_fertiliser("rice_paddy", 900, 27, 6.0, 15.0)
    hot = recommend_fertiliser("rice_paddy", 900, 35, 6.0, 15.0)
    assert hot["N_kg_per_ha"] < base["N_kg_per_ha"]


def test_cold_temp_increases_phosphorus() -> None:
    """Mean temp < 20°C should increase P2O5 above base rate."""
    base = recommend_fertiliser("rice_paddy", 900, 27, 6.0, 15.0)
    cold = recommend_fertiliser("rice_paddy", 900, 15, 6.0, 15.0)
    assert cold["P2O5_kg_per_ha"] > base["P2O5_kg_per_ha"]


# ---------------------------------------------------------------------------
# Soil pH adjustments
# ---------------------------------------------------------------------------

def test_low_ph_recommends_lime() -> None:
    """Soil pH < 5.0 must return lime_tonnes_per_ha > 0."""
    result = recommend_fertiliser("rice_paddy", 900, 27, 4.5, 15.0)
    assert result["lime_tonnes_per_ha"] > 0


def test_low_ph_lime_equals_2_tonnes() -> None:
    """Per MARD guidelines, lime rate for pH < 5.0 is exactly 2 t/ha."""
    result = recommend_fertiliser("rice_paddy", 900, 27, 4.5, 15.0)
    assert result["lime_tonnes_per_ha"] == pytest.approx(2.0)


def test_normal_ph_no_lime() -> None:
    """pH between 5.0 and 7.5 should not recommend lime."""
    result = recommend_fertiliser("rice_paddy", 900, 27, 6.5, 15.0)
    assert result["lime_tonnes_per_ha"] == 0.0


def test_high_ph_reduces_phosphorus() -> None:
    """pH > 7.5 (calcareous soil) should reduce P2O5 below base rate."""
    base = recommend_fertiliser("rice_paddy", 900, 27, 6.5, 15.0)
    alkaline = recommend_fertiliser("rice_paddy", 900, 27, 8.0, 15.0)
    assert alkaline["P2O5_kg_per_ha"] < base["P2O5_kg_per_ha"]


def test_low_ph_reduces_nitrogen() -> None:
    """pH < 5.0 should reduce N below the no-lime-needed rate."""
    normal_ph = recommend_fertiliser("rice_paddy", 900, 27, 6.5, 15.0)
    acid = recommend_fertiliser("rice_paddy", 900, 27, 4.5, 15.0)
    assert acid["N_kg_per_ha"] < normal_ph["N_kg_per_ha"]


# ---------------------------------------------------------------------------
# SOC adjustments
# ---------------------------------------------------------------------------

def test_high_soc_reduces_nitrogen() -> None:
    """SOC > 30 g/kg (3%) should reduce N below normal SOC rate."""
    normal_soc = recommend_fertiliser("rice_paddy", 900, 27, 6.0, 15.0)
    rich_soc = recommend_fertiliser("rice_paddy", 900, 27, 6.0, 35.0)
    assert rich_soc["N_kg_per_ha"] < normal_soc["N_kg_per_ha"]


# ---------------------------------------------------------------------------
# All crops smoke test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crop", _ALL_CROPS)
def test_smoke_all_crops(crop: str) -> None:
    """Recommendation must not raise and must return positive NPK for all crops."""
    result = recommend_fertiliser(crop, 900, 27, 6.0, 15.0)
    assert result["N_kg_per_ha"] > 0
    assert result["P2O5_kg_per_ha"] > 0
    assert result["K2O_kg_per_ha"] > 0
