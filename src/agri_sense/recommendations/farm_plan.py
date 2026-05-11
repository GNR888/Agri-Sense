"""Farm capacity optimisation: allocate land across recommended crops.

Algorithm:
  1. Compute expected revenue per ha for each crop (yield × 3-month forward price).
  2. Use classifier probability as confidence weight to produce initial land shares.
  3. If weather risk is high, cap the top crop at 60% and redistribute.
  4. Reserve 10% of total farm area as an unplanted buffer.
"""

from __future__ import annotations


def compute_farm_plan(
    recommendations: list[dict[str, object]],
    price_forecasts: dict[str, dict[str, int]],
    farm_size_ha: float,
    is_high_risk: bool,
) -> dict[str, object]:
    """Return a land-allocation plan across the recommended crops.

    Args:
        recommendations: List of recommend() dicts (crop, probability, predicted_yield_t_ha).
        price_forecasts:  crop → {"month_1": vnd_per_tonne, ..., "month_6": vnd_per_tonne}.
        farm_size_ha:     Total farm area in hectares.
        is_high_risk:     True when the 14-day forecast shows extreme weather.

    Returns:
        Structured dict matching the /recommend API farm_plan schema.
    """
    reserve_ha = round(farm_size_ha * 0.10, 2)
    plantable_ha = round(farm_size_ha * 0.90, 2)

    # Step 1 — expected revenue per ha (yield × month-3 price)
    revenues: list[float] = []
    for r in recommendations:
        crop = str(r["crop"])
        yield_t = float(r["predicted_yield_t_ha"])
        month3_price = price_forecasts.get(crop, {}).get("month_3", 0)
        revenues.append(yield_t * float(month3_price))

    # Step 2 — probability-weighted allocation shares
    probs = [float(r["probability"]) for r in recommendations]
    total_prob = sum(probs) or 1.0
    shares = [p / total_prob for p in probs]

    # Step 3 — weather-risk hedge: cap top allocation at 60%
    weather_hedge = False
    notes: list[str] = []

    if is_high_risk and shares and shares[0] > 0.60:
        weather_hedge = True
        overflow = shares[0] - 0.60
        shares[0] = 0.60
        # Redistribute overflow proportionally to remaining crops
        remaining_total = sum(shares[1:]) or 1.0
        for i in range(1, len(shares)):
            shares[i] += overflow * (shares[i] / remaining_total)
        notes.append(
            "Allocation capped at 60% for top crop due to high weather-risk forecast"
        )

    if is_high_risk:
        notes.append(
            "10% reserve recommended due to high rainfall/heat forecast — "
            "buffer for potential replanting"
        )
    else:
        notes.append("10% of farm area reserved as standard replanting buffer")

    # Step 4 — apply shares to plantable_ha
    allocations: list[dict[str, object]] = []
    total_revenue = 0.0

    for i, r in enumerate(recommendations):
        area = round(plantable_ha * shares[i], 2)
        share_pct = round(shares[i] * 100)
        rev = round(area * revenues[i])
        total_revenue += rev
        allocations.append(
            {
                "crop": r["crop"],
                "area_ha": area,
                "share_pct": share_pct,
                "expected_revenue_vnd": rev,
            }
        )

    return {
        "farm_size_ha": round(farm_size_ha, 2),
        "reserve_ha": reserve_ha,
        "plantable_ha": plantable_ha,
        "allocations": allocations,
        "total_expected_revenue_vnd": round(total_revenue),
        "weather_hedge_applied": weather_hedge,
        "notes": notes,
    }
