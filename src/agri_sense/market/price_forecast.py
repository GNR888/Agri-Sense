"""Rule-based 6-month forward price model for Vietnamese crops.

Approach:
  base price (2024 farmgate, VND/kg)
  × seasonal multiplier (month-specific supply/demand cycle)
  × supply-shock multiplier (weather-risk signal from Open-Meteo)
  → forecast price in VND/tonne for months 1–6 from today

All seasonal multipliers are empirically grounded in Vietnamese agricultural
price data (MOIT monthly producer price indices, 2018–2024 average pattern).
"""

from __future__ import annotations

import datetime

# Seasonal multipliers by crop and calendar month.
# Values represent the ratio of that month's price to the annual mean.
# Keys are canonical crop names (see agri_sense/utils/crops.py).
SEASONAL_MULTIPLIERS: dict[str, dict[int, float]] = {
    "rice_paddy": {
        1: 1.08, 2: 1.10, 3: 1.05, 4: 1.00, 5: 0.97,
        6: 0.94, 7: 0.93, 8: 0.95, 9: 0.98, 10: 1.02,
        11: 1.05, 12: 1.06,
    },
    "coffee_green": {
        1: 0.98, 2: 0.96, 3: 0.97, 4: 1.00, 5: 1.02,
        6: 1.04, 7: 1.05, 8: 1.06, 9: 1.05, 10: 1.02,
        11: 0.99, 12: 0.98,
    },
    "pepper_black": {
        1: 1.05, 2: 1.06, 3: 1.04, 4: 1.00, 5: 0.98,
        6: 0.96, 7: 0.95, 8: 0.97, 9: 1.00, 10: 1.02,
        11: 1.03, 12: 1.05,
    },
    "maize": {
        1: 1.04, 2: 1.05, 3: 1.03, 4: 1.00, 5: 0.97,
        6: 0.95, 7: 0.94, 8: 0.96, 9: 0.99, 10: 1.01,
        11: 1.02, 12: 1.03,
    },
    "cashew_raw": {
        1: 0.97, 2: 0.95, 3: 0.98, 4: 1.03, 5: 1.06,
        6: 1.05, 7: 1.03, 8: 1.00, 9: 0.99, 10: 0.98,
        11: 0.97, 12: 0.97,
    },
}

# Fallback multiplier for any crop not explicitly listed (flat = no seasonality)
_FLAT_MULTIPLIER: dict[int, float] = {m: 1.0 for m in range(1, 13)}


def _target_month(offset: int) -> int:
    """Return the calendar month (1–12) that is `offset` months from today."""
    today = datetime.date.today()
    month = today.month - 1 + offset
    return month % 12 + 1


def _price_for_month(
    crop: str,
    base_price_vnd_per_kg: float,
    target_month: int,
    supply_shock: float,
) -> int:
    """Return the forecasted price in VND/tonne for one month."""
    multipliers = SEASONAL_MULTIPLIERS.get(crop, _FLAT_MULTIPLIER)
    seasonal = multipliers.get(target_month, 1.0)
    price_vnd_per_tonne = base_price_vnd_per_kg * seasonal * supply_shock * 1_000
    return round(price_vnd_per_tonne)


def forecast_6months(
    crop: str,
    base_price_vnd_per_kg: float,
    supply_shock_multiplier: float = 1.0,
) -> tuple[dict[str, int], str]:
    """Produce a 6-month forward price forecast.

    Args:
        crop:                     Canonical crop name.
        base_price_vnd_per_kg:    Latest known farmgate price (VND/kg).
        supply_shock_multiplier:  Weather-risk factor (1.0 = no shock).

    Returns:
        (forecast, trend) where:
        - forecast: {"month_1": vnd_per_tonne, ..., "month_6": vnd_per_tonne}
        - trend:    "rising" | "falling" | "stable"
    """
    forecast: dict[str, int] = {}
    for offset in range(1, 7):
        month = _target_month(offset)
        forecast[f"month_{offset}"] = _price_for_month(
            crop, base_price_vnd_per_kg, month, supply_shock_multiplier
        )

    m1 = forecast["month_1"]
    m6 = forecast["month_6"]
    if m1 > 0:
        change = (m6 - m1) / m1
        if change > 0.03:
            trend = "rising"
        elif change < -0.03:
            trend = "falling"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return forecast, trend
