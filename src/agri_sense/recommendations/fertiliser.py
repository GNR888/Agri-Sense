"""Rule-based fertiliser recommendation engine for Vietnamese crops.

Rates and adjustment rules are based on:
  - Vietnamese Ministry of Agriculture and Rural Development (MARD) technical
    guidelines for crop nutrition (Circular 05/2010/TT-BNNPTNT and provincial
    extension service bulletins).
  - IRRI Vietnam extension recommendations for paddy rice NPK rates.
  - Lê Văn Hòa et al. (2019) coffee nutrition guidelines for the Central Highlands.

All rates are in kg/ha for a single growing season.
"""

from __future__ import annotations

from typing import TypedDict


def _as_int(v: object, default: int = 0) -> int:
    return int(v) if isinstance(v, (int, float)) else default


class _AppTemplate(TypedDict):
    timing: str
    day_start: int
    day_end: int
    N_frac: float
    P_frac: float
    K_frac: float
    method: str
    product_examples: list[str]


# ---------------------------------------------------------------------------
# Application schedule templates
# ---------------------------------------------------------------------------
# Each entry: timing label, application day window (day_start/day_end from
# transplant/planting), split fractions for N / P2O5 / K2O, agronomic method,
# and suggested product examples.
_SCHEDULE_TEMPLATES: dict[str, list[_AppTemplate]] = {
    "rice_paddy": [
        {
            "timing": "At planting (Day 0)",
            "day_start": 0, "day_end": 0,
            "N_frac": 0.28, "P_frac": 1.0, "K_frac": 0.50,
            "method": "Broadcast and incorporate into topsoil before transplanting.",
            "product_examples": [
                "Triple superphosphate for P",
                "Muriate of potash (KCl) for K",
                "Urea (46% N)",
            ],
        },
        {
            "timing": "Tillering stage (Day 21–25)",
            "day_start": 21, "day_end": 25,
            "N_frac": 0.39, "P_frac": 0.0, "K_frac": 0.25,
            "method": (
                "Broadcast into standing water for flooded rice. "
                "Drain field 24 h before application if using urea to reduce volatilisation."
            ),
            "product_examples": ["Urea (46% N)", "NPK 16-16-8 as split option"],
        },
        {
            "timing": "Panicle initiation (Day 45–50)",
            "day_start": 45, "day_end": 50,
            "N_frac": 0.33, "P_frac": 0.0, "K_frac": 0.25,
            "method": (
                "Foliar or soil application. "
                "Avoid application during flowering (Day 55–65) — leaf burn risk."
            ),
            "product_examples": ["Urea", "KCl"],
        },
    ],
    "maize": [
        {
            "timing": "At planting (Day 0)",
            "day_start": 0, "day_end": 0,
            "N_frac": 0.25, "P_frac": 1.0, "K_frac": 0.50,
            "method": (
                "Band application 5 cm below and to the side of the seed row "
                "to avoid fertiliser burn."
            ),
            "product_examples": ["DAP (18-46-0) for P + N", "Muriate of potash (KCl) for K"],
        },
        {
            "timing": "V6 stage (Day 35–42)",
            "day_start": 35, "day_end": 42,
            "N_frac": 0.50, "P_frac": 0.0, "K_frac": 0.25,
            "method": (
                "Side-dress along crop rows at 15 cm depth. "
                "Cultivate lightly to incorporate. Irrigate after if no rain within 48 h."
            ),
            "product_examples": ["Urea (46% N)", "Ammonium sulphate (21% N)"],
        },
        {
            "timing": "Tasselling (Day 55–65)",
            "day_start": 55, "day_end": 65,
            "N_frac": 0.25, "P_frac": 0.0, "K_frac": 0.25,
            "method": (
                "Top-dress between rows or foliar spray. "
                "Keep off leaves in high temperatures to reduce burn risk."
            ),
            "product_examples": ["Urea", "KCl"],
        },
    ],
    "coffee_green": [
        {
            "timing": "Post-harvest (Day 0)",
            "day_start": 0, "day_end": 0,
            "N_frac": 0.25, "P_frac": 0.50, "K_frac": 0.25,
            "method": (
                "Broadcast within the drip circle. "
                "Water in if rainfall < 20 mm expected in the next week."
            ),
            "product_examples": ["NPK 16-16-8", "Triple superphosphate"],
        },
        {
            "timing": "Pre-flowering (Day 60–90)",
            "day_start": 60, "day_end": 90,
            "N_frac": 0.25, "P_frac": 0.50, "K_frac": 0.25,
            "method": (
                "Apply around the drip line before the main flowering flush. "
                "Avoid disturbing shallow roots."
            ),
            "product_examples": ["NPK 20-10-10 or urea + triple superphosphate blend"],
        },
        {
            "timing": "Fruit set (Day 120–150)",
            "day_start": 120, "day_end": 150,
            "N_frac": 0.25, "P_frac": 0.0, "K_frac": 0.25,
            "method": (
                "Broadcast and water in during the main rainy season. "
                "Split into two sub-applications if rainfall is irregular."
            ),
            "product_examples": ["Urea (46% N)", "KCl"],
        },
        {
            "timing": "Fruit development (Day 210–240)",
            "day_start": 210, "day_end": 240,
            "N_frac": 0.25, "P_frac": 0.0, "K_frac": 0.25,
            "method": (
                "Apply during the second rainy pulse. "
                "Avoid application within 4 weeks of harvest."
            ),
            "product_examples": ["Urea (46% N)", "KCl"],
        },
    ],
    "pepper_black": [
        {
            "timing": "Start of rains (Day 0)",
            "day_start": 0, "day_end": 0,
            "N_frac": 0.33, "P_frac": 0.60, "K_frac": 0.34,
            "method": "Broadcast under canopy within the drip zone and water in.",
            "product_examples": ["NPK 15-15-15", "Triple superphosphate"],
        },
        {
            "timing": "Mid-season (Day 60–75)",
            "day_start": 60, "day_end": 75,
            "N_frac": 0.34, "P_frac": 0.40, "K_frac": 0.33,
            "method": (
                "Broadcast and allow rain to incorporate. "
                "Avoid application in waterlogged conditions."
            ),
            "product_examples": ["Urea", "NPK 12-12-17"],
        },
        {
            "timing": "End of rains (Day 120–135)",
            "day_start": 120, "day_end": 135,
            "N_frac": 0.33, "P_frac": 0.0, "K_frac": 0.33,
            "method": "Apply potassium-heavy blend to build reserves before the dry season.",
            "product_examples": ["KCl", "Sulphate of potash (SOP)"],
        },
    ],
    "cashew_raw": [
        {
            "timing": "Start of rains (Day 0)",
            "day_start": 0, "day_end": 0,
            "N_frac": 0.33, "P_frac": 0.60, "K_frac": 0.34,
            "method": (
                "Broadcast under canopy within the drip zone and water in. "
                "For young trees, apply in a ring at half the drip radius."
            ),
            "product_examples": ["NPK 15-15-15", "Triple superphosphate"],
        },
        {
            "timing": "Mid-season (Day 60–75)",
            "day_start": 60, "day_end": 75,
            "N_frac": 0.34, "P_frac": 0.40, "K_frac": 0.33,
            "method": (
                "Broadcast and allow rain to incorporate. "
                "Avoid application in waterlogged conditions."
            ),
            "product_examples": ["Urea", "NPK 12-12-17"],
        },
        {
            "timing": "End of rains (Day 120–135)",
            "day_start": 120, "day_end": 135,
            "N_frac": 0.33, "P_frac": 0.0, "K_frac": 0.33,
            "method": "Apply potassium-heavy blend to build reserves before the dry season.",
            "product_examples": ["KCl", "Sulphate of potash (SOP)"],
        },
    ],
}

_GENERAL_NOTES: dict[str, list[str]] = {
    "rice_paddy": [
        "Never apply all nitrogen at once — split into at least 3 applications to reduce volatilisation and leaching losses.",
        "Store fertiliser in a dry place. Caked urea has reduced effectiveness.",
        "Wear gloves when handling — avoid inhaling fertiliser dust.",
    ],
    "maize": [
        "Never apply all nitrogen at once — split into at least 3 applications to reduce losses.",
        "Irrigate after each application if no significant rain (≥ 10 mm) is expected within 48 hours.",
        "Wear gloves when handling — avoid inhaling fertiliser dust.",
    ],
    "coffee_green": [
        "Do not apply fertiliser to dry soil — water trees before and after application.",
        "Avoid applying nitrogen within 6 weeks of harvest as it can affect bean quality.",
        "Wear gloves when handling — avoid inhaling fertiliser dust.",
    ],
    "pepper_black": [
        "Do not over-apply nitrogen — excess N promotes vegetative growth at the expense of flowering.",
        "Combine with 2–3 t/ha organic compost to improve soil structure for vine rooting.",
        "Wear gloves when handling — avoid inhaling fertiliser dust.",
    ],
    "cashew_raw": [
        "Young trees (< 3 years): apply at 50% of recommended rate.",
        "Do not apply nitrogen immediately before or during flowering — it can reduce fruit set.",
        "Wear gloves when handling — avoid inhaling fertiliser dust.",
    ],
}

# Base fertiliser rates per crop (kg/ha) — Vietnamese MARD recommended range midpoints.
# N   = elemental nitrogen
# P2O5 = phosphorus pentoxide equivalent
# K2O  = potassium oxide equivalent
BASE_RATES: dict[str, dict[str, float]] = {
    "rice_paddy":   {"N": 90.0,  "P2O5": 60.0,  "K2O": 60.0},
    "maize":        {"N": 150.0, "P2O5": 80.0,  "K2O": 80.0},
    "coffee_green": {"N": 200.0, "P2O5": 100.0, "K2O": 200.0},
    "pepper_black": {"N": 180.0, "P2O5": 90.0,  "K2O": 150.0},
    "cashew_raw":   {"N": 120.0, "P2O5": 60.0,  "K2O": 100.0},
}

# Fallback for crops not explicitly listed
_DEFAULT_RATES: dict[str, float] = {"N": 100.0, "P2O5": 60.0, "K2O": 80.0}


def recommend_fertiliser(
    crop: str,
    rainfall_mm: float,
    mean_temp_c: float,
    soil_ph: float,
    soc_g_per_kg: float,
) -> dict[str, object]:
    """Compute weather- and soil-adjusted NPK rates for a crop.

    Args:
        crop:          Canonical crop name.
        rainfall_mm:   Seasonal total rainfall (mm).
        mean_temp_c:   Seasonal mean air temperature (°C).
        soil_ph:       Soil pH (0–30 cm, from SoilGrids).
        soc_g_per_kg:  Soil organic carbon (g/kg, from SoilGrids).

    Returns:
        Dict with keys N_kg_per_ha, P2O5_kg_per_ha, K2O_kg_per_ha,
        lime_tonnes_per_ha, notes.
    """
    base = dict(BASE_RATES.get(crop, _DEFAULT_RATES))
    n = base["N"]
    p = base["P2O5"]
    k = base["K2O"]
    lime = 0.0
    notes: list[str] = []

    # -- Rainfall adjustments
    if rainfall_mm > 1200:
        n *= 0.85  # high rainfall leaches nitrate — reduce N to limit losses
        notes.append("High rainfall forecast — reduced N by 15% to limit leaching")
    if rainfall_mm < 600:
        k *= 1.10  # drought stress tolerance improved by extra potassium
        notes.append("Low rainfall forecast — increased K2O by 10% for drought tolerance")

    # -- Temperature adjustments
    if mean_temp_c > 32.0:
        n *= 0.90  # heat accelerates ammonia volatilisation
        notes.append("High temperature forecast — reduced N by 10% to limit volatilisation")
    if mean_temp_c < 20.0:
        p *= 1.15  # cold soils restrict phosphorus uptake by root enzymes
        notes.append("Cool temperature forecast — increased P2O5 by 15% for uptake efficiency")

    # -- Soil pH adjustments (MARD acid soil management guidelines)
    if soil_ph < 5.0:
        lime = 2.0  # lime application to correct strong acidity before planting
        n *= 0.80   # low-pH soils have high denitrification losses
        notes.append("Soil pH < 5.0 — apply 2 t/ha lime; reduced N by 20% due to acidic denitrification")
    elif soil_ph > 7.5:
        p *= 0.85   # calcareous soils fix phosphorus as calcium phosphate
        notes.append("Soil pH > 7.5 — reduced P2O5 by 15% to account for calcareous fixation")
    else:
        notes.append("Soil pH within optimal range (5.0–7.5) — no pH adjustment needed")

    # -- Soil organic carbon adjustment
    # SOC > 3% (= 30 g/kg) indicates organically rich soil with high N mineralisation
    if soc_g_per_kg > 30.0:
        n *= 0.90
        notes.append("High soil organic carbon (>3%) — reduced N by 10%; soil mineralisation covers deficit")

    return {
        "N_kg_per_ha": round(n),
        "P2O5_kg_per_ha": round(p),
        "K2O_kg_per_ha": round(k),
        "lime_tonnes_per_ha": round(lime, 1),
        "notes": notes,
    }


def _rain_warning(
    day_start: int,
    day_end: int,
    daily_precip: list[float],
) -> str | None:
    """Return a warning string if > 20 mm rain is forecast within 2 days of the application window."""
    if not daily_precip or day_start >= len(daily_precip):
        return None
    check_start = max(0, day_start - 2)
    check_end = min(len(daily_precip) - 1, day_end + 2)
    for day in range(check_start, check_end + 1):
        if daily_precip[day] > 20.0:
            return (
                f"⚠ Forecast shows {daily_precip[day]:.0f} mm rain on Day {day}"
                " — consider rescheduling this application to avoid nitrogen leaching."
            )
    return None


def fertiliser_schedule(
    crop: str,
    soil: dict[str, float],  # noqa: ARG001  — reserved for future pH-dependent timing
    forecast: dict[str, object],
    rates: dict[str, object],
) -> dict[str, object]:
    """Return a split fertiliser application schedule with 14-day weather warnings.

    Args:
        crop:     Canonical crop name.
        soil:     Soil properties (ph, soc_g_per_kg). Reserved for future use.
        forecast: Dict from fetch_forecast_risk; must include daily_precip_mm
                  (list[float], up to 14 values, one per day from today).
        rates:    Adjusted NPK totals from recommend_fertiliser()
                  (keys: N_kg_per_ha, P2O5_kg_per_ha, K2O_kg_per_ha).

    Returns:
        Dict with keys: applications, total_N_kg_per_ha, total_P2O5_kg_per_ha,
        total_K2O_kg_per_ha, general_notes.
    """
    template = _SCHEDULE_TEMPLATES.get(crop)
    total_n = _as_int(rates.get("N_kg_per_ha"))
    total_p = _as_int(rates.get("P2O5_kg_per_ha"))
    total_k = _as_int(rates.get("K2O_kg_per_ha"))
    raw_precip = forecast.get("daily_precip_mm")
    daily_precip: list[float] = (
        [float(v) for v in raw_precip if isinstance(v, (int, float))]
        if isinstance(raw_precip, list) else []
    )

    if template is None:
        return {
            "applications": [
                {
                    "timing": "At planting (Day 0)",
                    "N_kg_per_ha": total_n,
                    "P2O5_kg_per_ha": total_p,
                    "K2O_kg_per_ha": total_k,
                    "method": "Broadcast and incorporate before planting.",
                    "product_examples": ["NPK compound fertiliser"],
                    "warnings": [],
                }
            ],
            "total_N_kg_per_ha": total_n,
            "total_P2O5_kg_per_ha": total_p,
            "total_K2O_kg_per_ha": total_k,
            "general_notes": [
                "Apply fertiliser in split doses to reduce leaching losses.",
                "Wear gloves when handling — avoid inhaling fertiliser dust.",
            ],
        }

    applications: list[dict[str, object]] = []
    for tmpl in template:
        n_kg = round(total_n * float(tmpl["N_frac"]))
        p_kg = round(total_p * float(tmpl["P_frac"]))
        k_kg = round(total_k * float(tmpl["K_frac"]))
        warnings: list[str] = []
        rain_warn = _rain_warning(int(tmpl["day_start"]), int(tmpl["day_end"]), daily_precip)
        if rain_warn:
            warnings.append(rain_warn)
        applications.append(
            {
                "timing": str(tmpl["timing"]),
                "N_kg_per_ha": n_kg,
                "P2O5_kg_per_ha": p_kg,
                "K2O_kg_per_ha": k_kg,
                "method": str(tmpl["method"]),
                "product_examples": list(tmpl["product_examples"]),
                "warnings": warnings,
            }
        )

    return {
        "applications": applications,
        "total_N_kg_per_ha": total_n,
        "total_P2O5_kg_per_ha": total_p,
        "total_K2O_kg_per_ha": total_k,
        "general_notes": _GENERAL_NOTES.get(crop, [
            "Apply fertiliser in split doses to reduce leaching losses.",
            "Wear gloves when handling — avoid inhaling fertiliser dust.",
        ]),
    }
