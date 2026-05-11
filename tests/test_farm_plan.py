"""Tests for the farm capacity optimisation module."""

from __future__ import annotations

import pytest

from agri_sense.recommendations.farm_plan import compute_farm_plan

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RECS = [
    {"crop": "rice_paddy",   "probability": 0.60, "predicted_yield_t_ha": 5.0},
    {"crop": "maize",        "probability": 0.30, "predicted_yield_t_ha": 3.0},
    {"crop": "cashew_raw",   "probability": 0.10, "predicted_yield_t_ha": 1.5},
]

_PRICE_FC = {
    "rice_paddy":   {"month_3": 7_200_000},
    "maize":        {"month_3": 7_300_000},
    "cashew_raw":   {"month_3": 31_500_000},
}

_FARM_SIZE = 5.0


def _plan(farm_size: float = _FARM_SIZE, is_high_risk: bool = False) -> dict:
    return compute_farm_plan(_RECS, _PRICE_FC, farm_size, is_high_risk)


# ---------------------------------------------------------------------------
# Reserve + plantable
# ---------------------------------------------------------------------------

def test_reserve_is_10_pct() -> None:
    plan = _plan()
    assert plan["reserve_ha"] == pytest.approx(_FARM_SIZE * 0.10, rel=1e-6)


def test_plantable_is_90_pct() -> None:
    plan = _plan()
    assert plan["plantable_ha"] == pytest.approx(_FARM_SIZE * 0.90, rel=1e-6)


def test_reserve_plus_plantable_equals_farm_size() -> None:
    plan = _plan()
    assert plan["reserve_ha"] + plan["plantable_ha"] == pytest.approx(_FARM_SIZE, rel=1e-6)


# ---------------------------------------------------------------------------
# Allocation areas
# ---------------------------------------------------------------------------

def test_allocations_sum_to_plantable_ha() -> None:
    """Sum of all allocation areas must equal plantable_ha (within float tolerance)."""
    plan = _plan()
    total_allocated = sum(a["area_ha"] for a in plan["allocations"])
    assert total_allocated == pytest.approx(plan["plantable_ha"], abs=0.01)


def test_allocations_sum_to_plantable_ha_high_risk() -> None:
    plan = _plan(is_high_risk=True)
    total_allocated = sum(a["area_ha"] for a in plan["allocations"])
    assert total_allocated == pytest.approx(plan["plantable_ha"], abs=0.01)


def test_allocation_count_matches_recommendations() -> None:
    plan = _plan()
    assert len(plan["allocations"]) == len(_RECS)


# ---------------------------------------------------------------------------
# Weather hedge
# ---------------------------------------------------------------------------

def test_no_hedge_when_low_risk() -> None:
    plan = _plan(is_high_risk=False)
    assert plan["weather_hedge_applied"] is False


def test_hedge_caps_top_crop_at_60_pct() -> None:
    """When is_high_risk=True and top crop would exceed 60%, it must be capped."""
    overweight_recs = [
        {"crop": "rice_paddy", "probability": 0.80, "predicted_yield_t_ha": 5.0},
        {"crop": "maize",      "probability": 0.12, "predicted_yield_t_ha": 3.0},
        {"crop": "cashew_raw", "probability": 0.08, "predicted_yield_t_ha": 1.5},
    ]
    plan = compute_farm_plan(overweight_recs, _PRICE_FC, _FARM_SIZE, is_high_risk=True)
    top_share = plan["allocations"][0]["area_ha"] / plan["plantable_ha"]
    assert top_share <= 0.60 + 1e-6
    assert plan["weather_hedge_applied"] is True


def test_no_single_crop_exceeds_60_pct_when_hedged() -> None:
    """No individual allocation should be more than 60% of plantable area when hedged."""
    overweight_recs = [
        {"crop": "rice_paddy", "probability": 0.90, "predicted_yield_t_ha": 5.0},
        {"crop": "maize",      "probability": 0.06, "predicted_yield_t_ha": 3.0},
        {"crop": "cashew_raw", "probability": 0.04, "predicted_yield_t_ha": 1.5},
    ]
    plan = compute_farm_plan(overweight_recs, _PRICE_FC, _FARM_SIZE, is_high_risk=True)
    plantable = plan["plantable_ha"]
    for alloc in plan["allocations"]:
        share = alloc["area_ha"] / plantable
        assert share <= 0.60 + 1e-6, (
            f"Crop {alloc['crop']} has share {share:.2%} > 60% after hedge"
        )


def test_hedge_not_triggered_when_top_already_under_60() -> None:
    """If top crop is already ≤ 60%, weather_hedge_applied should be False
    even when is_high_risk=True."""
    plan = _plan(is_high_risk=True)  # top crop is 60% exactly
    assert plan["weather_hedge_applied"] is False


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------

def test_total_revenue_positive() -> None:
    plan = _plan()
    assert plan["total_expected_revenue_vnd"] > 0


def test_total_revenue_sum_of_allocations() -> None:
    plan = _plan()
    alloc_sum = sum(a["expected_revenue_vnd"] for a in plan["allocations"])
    assert alloc_sum == pytest.approx(plan["total_expected_revenue_vnd"], rel=0.01)


# ---------------------------------------------------------------------------
# Share percentages
# ---------------------------------------------------------------------------

def test_share_pcts_sum_to_100() -> None:
    """Individual share_pct values should sum to approximately 100."""
    plan = _plan()
    total_pct = sum(a["share_pct"] for a in plan["allocations"])
    assert abs(total_pct - 100) <= 2  # allow ±2% due to rounding


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_single_crop() -> None:
    """Plan with one crop should allocate 100% of plantable area to it."""
    recs = [{"crop": "rice_paddy", "probability": 1.0, "predicted_yield_t_ha": 5.0}]
    prices = {"rice_paddy": {"month_3": 7_200_000}}
    plan = compute_farm_plan(recs, prices, 4.0, is_high_risk=False)
    assert len(plan["allocations"]) == 1
    assert plan["allocations"][0]["area_ha"] == pytest.approx(plan["plantable_ha"], abs=0.01)


def test_different_farm_sizes() -> None:
    """Reserve and plantable should scale correctly with different farm sizes."""
    for size in [1.0, 2.5, 10.0, 100.0]:
        plan = _plan(farm_size=size)
        assert plan["reserve_ha"] == pytest.approx(size * 0.10, rel=1e-4)
        assert plan["plantable_ha"] == pytest.approx(size * 0.90, rel=1e-4)
