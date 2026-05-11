"""Plain-language soil health scoring for the 'Your Land' panel."""
from __future__ import annotations

import math

_GOOD_TEXTURES = frozenset({"loam", "silt loam", "clay loam", "sandy loam", "silty clay loam"})
_POOR_TEXTURES = frozenset({"sand", "loamy sand"})
_HEAVY_TEXTURES = frozenset({"clay", "silty clay", "sandy clay"})


def _safe_float(v: object, default: float) -> float:
    if v is None:
        return default
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return default if (math.isnan(f) or math.isinf(f)) else f


def soil_health_summary(soil: dict[str, object]) -> dict[str, object]:
    """Score soil health and return plain-language issues.

    Args:
        soil: Keys expected: ph, soc_g_per_kg, nitrogen_cg_per_kg, soil_texture_class.

    Returns:
        health_score (1–10), nutrient_status per-key, and top-2 issues with fix suggestions.
    """
    ph  = _safe_float(soil.get("ph"), 6.5)
    soc = _safe_float(soil.get("soc_g_per_kg"), 15.0)        # g/kg
    n   = _safe_float(soil.get("nitrogen_cg_per_kg"), 100.0)  # cg/kg
    tex = str(soil.get("soil_texture_class") or "loam")

    # --- pH ---
    if 5.5 <= ph <= 7.0:
        ph_sc, ph_st, ph_fix = 10.0, "adequate", None
    elif ph < 5.5:
        ph_sc = max(1.0, 10.0 - (5.5 - ph) * 4.0)
        ph_st = "deficient"
        lime_t = round(max(1.0, (5.5 - ph) * 2.0), 1)
        ph_fix = (
            f"Your soil is acidic (pH {ph:.1f}). Apply agricultural lime at {lime_t} t/ha "
            "before planting to raise pH to 5.5–6.0."
        )
    else:
        ph_sc = max(1.0, 10.0 - (ph - 7.0) * 3.0)
        ph_st = "excess"
        ph_fix = (
            f"Your soil is alkaline (pH {ph:.1f}). Add sulfur or organic matter to "
            "slightly lower pH; avoid over-liming."
        )

    # --- Organic carbon (SOC in g/kg; display as %) ---
    pct = soc / 10.0
    if soc >= 20.0:
        soc_sc, soc_st, soc_fix = 10.0, "adequate", None
    elif soc >= 15.0:
        soc_sc, soc_st, soc_fix = 7.0, "adequate", None
    elif soc >= 8.0:
        soc_sc, soc_st = 5.0, "deficient"
        soc_fix = (
            f"Organic carbon is low ({pct:.1f}%). Apply 2–3 t/ha of compost or rice straw "
            "to build soil organic matter."
        )
    else:
        soc_sc, soc_st = 2.0, "deficient"
        soc_fix = (
            f"Very low organic carbon ({pct:.1f}%). Incorporate compost (3–5 t/ha) or green "
            "manure each season to build soil health."
        )

    # --- Nitrogen (cg/kg; display as g/kg) ---
    n_g = n / 100.0
    if n >= 200.0:
        n_sc, n_st, n_fix = 10.0, "adequate", None
    elif n >= 150.0:
        n_sc, n_st, n_fix = 7.0, "adequate", None
    elif n >= 100.0:
        n_sc, n_st = 5.0, "deficient"
        n_fix = (
            f"Nitrogen is marginal ({n_g:.1f} g/kg). Apply 20–40 kg/ha extra urea at "
            "early vegetative stage."
        )
    else:
        n_sc, n_st = 2.0, "deficient"
        n_fix = (
            f"Very low nitrogen ({n_g:.1f} g/kg). Apply 50 kg/ha urea split across "
            "transplanting and tillering stages."
        )

    # --- Texture ---
    if tex in _GOOD_TEXTURES:
        tex_sc, tex_st, tex_fix = 10.0, "adequate", None
    elif tex in _HEAVY_TEXTURES:
        tex_sc, tex_st = 5.0, "deficient"
        tex_fix = (
            f"Heavy {tex} soil can waterlog easily. "
            "Use raised beds and avoid over-irrigation."
        )
    elif tex in _POOR_TEXTURES:
        tex_sc, tex_st = 3.0, "deficient"
        tex_fix = (
            f"Sandy soil ({tex}) drains too fast. "
            "Apply mulch and compost (4+ t/ha) to improve water retention."
        )
    else:
        tex_sc, tex_st, tex_fix = 7.0, "adequate", None

    health_score = max(
        1.0,
        min(10.0, round(ph_sc * 0.30 + soc_sc * 0.30 + n_sc * 0.25 + tex_sc * 0.15, 1)),
    )

    issues = [fix for fix in (ph_fix, soc_fix, n_fix, tex_fix) if fix is not None]

    return {
        "health_score": health_score,
        "nutrient_status": {
            "ph": ph_st,
            "organic_carbon": soc_st,
            "nitrogen": n_st,
            "texture": tex_st,
        },
        "issues": issues[:2],
    }
