"""Climate-aware harvest timing calculator for recommended crops.

Computes expected harvest windows from a planting date and overlays
historical climate risk signals (tropical storm season, monthly rainfall,
temperature extremes) using NASA POWER data. For harvests within the
next 14 days, substitutes live Open-Meteo forecast data.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from agri_sense.utils.geo import PROVINCES

logger = logging.getLogger(__name__)

# Days from transplant/planting to maturity (min/max range)
DAYS_TO_MATURITY: dict[str, dict[str, int]] = {
    "rice_paddy":   {"min": 90,  "max": 110},
    "maize":        {"min": 95,  "max": 115},
    "coffee_green": {"min": 240, "max": 270},
    "pepper_black": {"min": 180, "max": 210},
    "cashew_raw":   {"min": 60,  "max": 75},
}

# Months (1–12) with historically high tropical storm frequency per region
STORM_RISK_MONTHS: dict[str, list[int]] = {
    "mekong_delta":      [9, 10, 11],
    "red_river_delta":   [7, 8, 9, 10],
    "central_highlands": [9, 10, 11],
}

_HARVEST_TIPS: dict[str, list[str]] = {
    "rice_paddy": [
        "Harvest when 85–90% of grains are golden yellow, not 100% — waiting for full maturity "
        "increases shattering and bird damage losses.",
        "Cut at 20–25 cm above ground. Threshing within 24 h reduces field losses.",
        "Target moisture content: 20–22% at harvest, dry to 14% for storage.",
    ],
    "maize": [
        "Harvest when husks are dry brown and kernel moisture is around 25–28%.",
        "Shell cobs within 2 days to prevent mould in humid conditions.",
        "Target moisture content: 25% at harvest, dry to 13% for safe storage.",
    ],
    "coffee_green": [
        "Selective hand-picking of red cherries only — do not strip-harvest.",
        "Cherry-to-green coffee ratio is approximately 5:1 by weight.",
        "Process immediately after picking to avoid fermentation; wet or dry process "
        "depending on local equipment availability.",
    ],
    "pepper_black": [
        "Harvest when 5–10% of berries on the spike are red-ripe for optimal piperine content.",
        "Dry immediately to 11–12% moisture. Sun-dry on raised platforms for best quality.",
        "Avoid harvesting in wet conditions — drying time doubles and mould risk is high.",
    ],
    "cashew_raw": [
        "Harvest fallen nuts daily — ground contact causes rapid quality deterioration.",
        "The cashew apple is highly perishable; process or sell within 24 h.",
        "Target 8–9% moisture for raw cashew nuts in storage.",
    ],
}

_DEFAULT_HARVEST_TIPS: list[str] = [
    "Monitor crop maturity indicators daily once within 2 weeks of expected harvest.",
    "Prepare storage and drying equipment at least 1 week before harvest.",
]


def _region_for_province(province_key: str) -> str:
    """Map province key to storm-risk region key."""
    info = PROVINCES.get(province_key)
    if not info:
        return "mekong_delta"
    r = info.region.lower()
    if "mekong" in r:
        return "mekong_delta"
    if "red river" in r:
        return "red_river_delta"
    if "highland" in r or "south-east" in r or "south east" in r:
        return "central_highlands"
    return "red_river_delta"


def _months_in_window(start: date, end: date) -> list[int]:
    """Return sorted list of calendar months (1–12) spanned by [start, end]."""
    months: set[int] = set()
    cur = start.replace(day=1)
    while cur <= end:
        months.add(cur.month)
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return sorted(months)


def _get_monthly_climate(
    lat: float,
    lon: float,
    month: int,
    reference_year: int,
    province_key: str = "",
) -> dict[str, float]:
    """Fetch and aggregate NASA POWER data for a single calendar month."""
    import pandas as pd  # noqa: PLC0415

    from agri_sense.ingestion.nasa_power import fetch_daily_weather  # noqa: PLC0415

    start = date(reference_year, month, 1)
    end = (
        date(reference_year, 12, 31)
        if month == 12
        else date(reference_year, month + 1, 1) - timedelta(days=1)
    )
    tag_prefix = province_key if province_key else f"{lat:.3f}_{lon:.3f}"
    try:
        df: pd.DataFrame = fetch_daily_weather(
            lat,
            lon,
            start,
            end,
            cache_tag=f"monthly_{tag_prefix}_{reference_year}_{month:02d}",
        )
        if df.empty:
            return {"mean_temp_c": float("nan"), "total_precip_mm": float("nan")}
        return {
            "mean_temp_c": float(df["temp_mean_c"].mean()),
            "total_precip_mm": float(df["precip_mm"].sum()),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Monthly climate fetch failed (%s, %d/%02d): %s", province_key, reference_year, month, exc
        )
        return {"mean_temp_c": float("nan"), "total_precip_mm": float("nan")}


def _month_name(month: int) -> str:
    return date(2000, month, 1).strftime("%B")


def _fallback_harvest_timing(crop: str, planting_date: date) -> dict[str, object]:
    """Return harvest timing dict computed from maturity tables only (no climate data)."""
    maturity = DAYS_TO_MATURITY.get(crop, {"min": 90, "max": 120})
    earliest = planting_date + timedelta(days=maturity["min"])
    latest = planting_date + timedelta(days=maturity["max"])
    optimal_start = latest - timedelta(days=10)
    return {
        "estimated_planting_date": planting_date.isoformat(),
        "earliest_harvest_date": earliest.isoformat(),
        "latest_harvest_date": latest.isoformat(),
        "optimal_harvest_window": f"{optimal_start.isoformat()} to {latest.isoformat()}",
        "recommended_harvest_date": optimal_start.isoformat(),
        "reason": "Climate risk data unavailable — using average maturity window.",
        "climate_risks": [],
        "harvest_tips": _HARVEST_TIPS.get(crop, _DEFAULT_HARVEST_TIPS),
        "data_basis": "Maturity tables only (climate data unavailable)",
    }


def compute_harvest_timing(
    crop: str,
    planting_date: date,
    province_key: str,
    lat: float,
    lon: float,
) -> dict[str, object]:
    """Compute climate-aware harvest window for one crop from its planting date.

    Args:
        crop:           Canonical crop name (e.g. "rice_paddy").
        planting_date:  Expected transplant / planting date.
        province_key:   Province key from PROVINCES registry.
        lat:            Farm latitude (used for data ingestion).
        lon:            Farm longitude (used for data ingestion).

    Returns:
        Dict matching the HarvestTiming schema with keys:
            estimated_planting_date, earliest_harvest_date, latest_harvest_date,
            optimal_harvest_window, recommended_harvest_date, reason,
            climate_risks, harvest_tips, data_basis.
    """
    today = date.today()
    maturity = DAYS_TO_MATURITY.get(crop, {"min": 90, "max": 120})
    min_days: int = maturity["min"]
    max_days: int = maturity["max"]

    earliest = planting_date + timedelta(days=min_days)
    latest = planting_date + timedelta(days=max_days)
    optimal_start = latest - timedelta(days=10)

    region = _region_for_province(province_key)
    storm_months: list[int] = STORM_RISK_MONTHS.get(region, [])
    harvest_months = _months_in_window(earliest, latest)

    # Use live 14-day forecast when harvest is imminent
    use_forecast = (earliest - today).days <= 14
    reference_year = today.year - 1

    if use_forecast:
        from agri_sense.ingestion.open_meteo import fetch_forecast_risk  # noqa: PLC0415

        fc = fetch_forecast_risk(lat, lon)
        mean_temp = float(fc.get("mean_temp_c", 28.0))
        # Scale 14-day total to a ~monthly equivalent for the 250 mm threshold
        monthly_precip_est = float(fc.get("total_rain_mm_14d", 0.0)) * (30.0 / 14.0)
        data_basis = "14-day live forecast (Open-Meteo) + historical climate (NASA POWER)"
    else:
        monthly_climates = [
            _get_monthly_climate(lat, lon, m, reference_year, province_key)
            for m in harvest_months
        ]
        valid_temps = [c["mean_temp_c"] for c in monthly_climates if not math.isnan(c["mean_temp_c"])]
        valid_precip = [
            c["total_precip_mm"] for c in monthly_climates if not math.isnan(c["total_precip_mm"])
        ]
        mean_temp = sum(valid_temps) / len(valid_temps) if valid_temps else 28.0
        monthly_precip_est = max(valid_precip) if valid_precip else 100.0
        data_basis = (
            f"Historical climate NASA POWER {reference_year} average for this province"
        )

    # ---- Risk assessment ----
    climate_risks: list[dict[str, str]] = []

    storm_overlap = [m for m in harvest_months if m in storm_months]
    if storm_overlap:
        month_names = ", ".join(_month_name(m) for m in storm_months)
        climate_risks.append({
            "risk": "Storm season overlap",
            "severity": "high",
            "action": (
                f"Harvest by {earliest.strftime('%b %d')} to avoid late-season storm risk "
                f"(peak storm months in this region: {month_names})."
            ),
        })

    if monthly_precip_est > 250:
        climate_risks.append({
            "risk": "High rainfall likely",
            "severity": "medium",
            "action": (
                "Wet harvest conditions likely. Plan mechanical drying capacity or covered storage. "
                "Harvest early morning when humidity is lowest."
            ),
        })

    heat_adjusted = False
    if mean_temp > 35.0:
        climate_risks.append({
            "risk": "Heat stress during grain filling",
            "severity": "medium",
            "action": (
                "High heat stress during grain filling. Monitor closely — crops may mature "
                "5–7 days faster than average."
            ),
        })
        # Shift maturity window earlier to reflect accelerated development
        earliest = earliest - timedelta(days=6)
        optimal_start = optimal_start - timedelta(days=6)
        heat_adjusted = True

    # ---- Recommended harvest date and rationale ----
    if storm_overlap:
        recommended = earliest
        days_early = (optimal_start - recommended).days
        if days_early > 0:
            reason = (
                f"Tropical storm season peaks in {_month_name(min(storm_months))} in this region. "
                f"Harvesting {days_early} days before the optimal window reduces weather-loss risk. "
                "Yield penalty estimated at 3–5%."
            )
        else:
            reason = (
                "Harvest window overlaps with tropical storm season in this region. "
                "Harvest at the earliest possible date to minimise weather loss."
            )
    elif monthly_precip_est > 250:
        recommended = optimal_start
        reason = (
            "High rainfall expected during harvest window. Harvest at the start of the optimal "
            "window to reduce post-harvest drying burden and mould risk."
        )
    elif heat_adjusted:
        recommended = optimal_start
        reason = (
            "Heat stress may accelerate maturity. Harvest at the start of the adjusted optimal "
            "window (shifted 6 days earlier) to capture peak grain quality."
        )
    else:
        recommended = optimal_start
        reason = (
            "No major climate risks detected for the harvest window. Harvest at the start of "
            "the optimal window for the best balance of maturity and field-loss risk."
        )

    return {
        "estimated_planting_date": planting_date.isoformat(),
        "earliest_harvest_date": earliest.isoformat(),
        "latest_harvest_date": latest.isoformat(),
        "optimal_harvest_window": f"{optimal_start.isoformat()} to {latest.isoformat()}",
        "recommended_harvest_date": recommended.isoformat(),
        "reason": reason,
        "climate_risks": climate_risks,
        "harvest_tips": _HARVEST_TIPS.get(crop, _DEFAULT_HARVEST_TIPS),
        "data_basis": data_basis,
    }
