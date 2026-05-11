"""Rule-based farming methods advisor for Vietnamese crops.

Cross-references crop type, soil texture, season, and 14-day weather forecast
to produce structured agronomic guidance across five practice categories.

Sources: Vietnamese MARD extension bulletins; IRRI Vietnam agronomic guidelines;
WASI (Western Highlands Agriculture & Forestry Science Institute) for coffee/pepper.
All content represents generalised regional guidance — local extension advice
should take precedence where available.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Soil texture grouping
# ---------------------------------------------------------------------------

_TEXTURE_GROUP: dict[str, str] = {
    "clay":             "heavy_clay",
    "silty clay":       "heavy_clay",
    "sandy clay":       "heavy_clay",
    "clay loam":        "clay_loam",
    "silty clay loam":  "clay_loam",
    "sandy clay loam":  "clay_loam",
    "loam":             "loam",
    "silt loam":        "loam",
    "silt":             "loam",
    "sandy loam":       "loam",
    "sand":             "sandy",
    "loamy sand":       "sandy",
}


def _texture_group(texture_class: str) -> str:
    return _TEXTURE_GROUP.get(texture_class.lower().strip(), "loam")


# ---------------------------------------------------------------------------
# 1. Land preparation
# ---------------------------------------------------------------------------

_LAND_PREP: dict[str, dict[str, list[str]]] = {
    "rice_paddy": {
        "heavy_clay": [
            "Plough to 20–25 cm depth. Puddle field for 3–5 days to form a hardpan that retains flood water.",
            "Level field to ±2 cm tolerance — uneven surface causes waterlogging in low spots and dry patches on raised ground.",
            "Apply 2–3 t/ha compost before puddling to restore organic matter depleted by intensive cropping.",
        ],
        "clay_loam": [
            "Plough to 20 cm depth. Light puddling for 2 days is sufficient on clay loam — over-puddling destroys soil structure.",
            "Level field carefully; clay loam drains faster than heavy clay, so even water distribution is important.",
        ],
        "loam": [
            "Plough to 15–20 cm. Puddle lightly; sandy loam may need raised bunds to prevent lateral water loss.",
            "Apply 2–3 t/ha organic matter or chopped rice straw before final levelling to improve water retention.",
        ],
        "sandy": [
            "Deep plough to 25 cm to disrupt porous subsoil layer.",
            "Incorporate 4–5 t/ha compost or chopped rice straw — sandy soils lose water rapidly through seepage.",
            "Bund construction and maintenance is critical; inspect bunds after each irrigation event.",
        ],
    },
    "coffee_green": {
        "heavy_clay": [
            "Rip subsoil to 50–60 cm to break compaction and improve drainage.",
            "Form raised beds or rows 30–40 cm high on slopes >15% to prevent root waterlogging.",
            "Avoid puddling — coffee is highly sensitive to anaerobic root conditions.",
        ],
        "clay_loam": [
            "Rip to 50 cm depth. Form raised rows on any slope to improve drainage.",
            "Incorporate 5 t/ha organic matter during land preparation to open pore structure.",
        ],
        "loam": [
            "Rip to 40–50 cm. Loam suits coffee well — minimal soil amendment required.",
            "On flat land, form slight mounds around each planting hole to direct surface drainage away from root crown.",
        ],
        "sandy": [
            "Rip to 40 cm. Incorporate 6–8 t/ha organic matter — sandy soil cannot hold the nutrients coffee requires.",
            "Install drip irrigation infrastructure before planting; sandy profiles need more frequent irrigation.",
        ],
    },
    "pepper_black": {
        "heavy_clay": [
            "Prepare raised mounds 40–50 cm high — pepper roots die rapidly in waterlogged heavy clay.",
            "Mix mound soil with 5–8 t/ha compost to improve drainage and nutrient supply.",
            "Install concrete or hardwood support stakes (2.5–3 m tall) at the time of mound preparation.",
        ],
        "clay_loam": [
            "Prepare raised mounds 30–40 cm high for drainage. Blend 4–5 t/ha compost into each mound.",
            "Install stakes before planting to avoid root disturbance later.",
        ],
        "loam": [
            "Prepare mounds 30 cm high. Loam provides adequate natural drainage for pepper.",
            "Add 3–4 t/ha compost to mounds. Install stakes 2.5 m tall.",
        ],
        "sandy": [
            "Prepare mounds 30 cm high enriched with 6–8 t/ha organic matter — sandy soil dries too fast for pepper without amendment.",
            "Plan drip irrigation infrastructure at land preparation stage. Install stakes.",
        ],
    },
    "cashew_raw": {
        "heavy_clay": [
            "Dig planting holes 60 × 60 × 60 cm to break compact clay around the root zone.",
            "Backfill with a mix of topsoil + 5 kg compost + 200 g phosphate per hole to improve drainage.",
            "Cashew can tolerate clay if drainage is managed — avoid sites with seasonal waterlogging.",
        ],
        "clay_loam": [
            "Dig planting holes 50 × 50 × 50 cm. Backfill with topsoil + 3 kg compost per hole.",
            "Minimal tillage beyond hole preparation — cashew develops a deep taproot; avoid mechanical disturbance.",
        ],
        "loam": [
            "Dig planting holes 40 × 40 × 40 cm. Loam is well-suited to cashew — no special amendment needed.",
        ],
        "sandy": [
            "Dig planting holes 40 × 40 × 40 cm. Add 5 kg compost + 100 g NPK per hole.",
            "Sandy soils provide good drainage for cashew — the main benefit of organic matter here is nutrient supply.",
        ],
    },
    "maize": {
        "heavy_clay": [
            "Deep plough to 25–30 cm to break compact subsoil — maize roots require well-aerated soil.",
            "Ridge planting (rows on 15–20 cm raised ridges) significantly improves drainage on heavy clay.",
        ],
        "clay_loam": [
            "Plough to 20–25 cm. Ridge planting recommended on lower-lying clay loam fields.",
            "Apply 2 t/ha compost before final tillage to improve aeration.",
        ],
        "loam": [
            "Plough to 20 cm. Loam is ideal for maize — no special preparation needed.",
            "Incorporate previous-crop residues to maintain organic matter level.",
        ],
        "sandy": [
            "Minimal tillage or direct sowing into loose sandy soil — deep ploughing exposes infertile subsoil.",
            "Apply 3–4 t/ha organic mulch after sowing to reduce moisture loss and improve nutrient retention.",
        ],
    },
}

_LAND_PREP_DEFAULT: list[str] = [
    "Plough to 20 cm depth and remove previous-crop residues.",
    "Apply 2–3 t/ha organic matter before final tillage.",
    "Inspect field drainage before planting season.",
]


# ---------------------------------------------------------------------------
# 2. Planting method
# ---------------------------------------------------------------------------

_PLANTING_BASE: dict[str, dict[str, list[str]]] = {
    "rice_paddy": {
        "Đông Xuân": [
            "Use transplanting method — cooler Đông Xuân conditions give better seedling establishment than direct seeding.",
            "Nursery period: 20–25 days. Target transplanting before mid-December (Mekong Delta) or mid-November (Red River Delta).",
            "Spacing: 20 × 20 cm, 2–3 seedlings per hill. Nursery seed rate: 40–50 kg/ha.",
        ],
        "Hè Thu": [
            "Direct wet seeding is standard in Hè Thu for faster field turnover between seasons.",
            "Broadcast 120–130 kg/ha pre-germinated seed onto puddled field. Alternatively transplant 25–30-day nursery seedlings at 20 × 20 cm.",
            "Seed rate (direct): 120–150 kg/ha wet seed.",
        ],
        "Mùa": [
            "Transplanting or direct seeding are both viable in the Mùa season.",
            "Nursery period: 20–25 days. Spacing: 20 × 20 cm or 25 × 25 cm for traditional long-duration varieties.",
            "Seed rate: 40–60 kg/ha (transplant) or 120–130 kg/ha (direct).",
        ],
        "main": [
            "Transplant at 20–25 days nursery age at 20 × 20 cm spacing.",
            "Nursery seed rate: 40–50 kg/ha.",
        ],
    },
    "coffee_green": {
        "main": [
            "Plant grafted seedlings (10–12 months old from nursery) at the start of the rainy season (May–June) when soil is reliably moist.",
            "Spacing: 3 m × 3 m (1,111 trees/ha standard); 3 × 4 m on steeper slopes.",
            "Pre-fill planting holes with 10 kg compost + 0.5 kg phosphate per hole before transplanting.",
        ],
    },
    "pepper_black": {
        "main": [
            "Plant rooted stem cuttings (3–4 nodes, 25–30 cm long) at the onset of rains.",
            "2–3 cuttings per stake at the base. Spacing: 2.5 × 2.5 m (1,600 poles/ha).",
            "Provide 50% shade for the first 3 months using coconut leaves or shade netting.",
        ],
    },
    "cashew_raw": {
        "main": [
            "Plant grafted seedlings at the start of the dry season — taproots establish before rains arrive.",
            "Spacing: 7 × 7 m (200 trees/ha) or 10 × 10 m (100 trees/ha) for mechanised harvest operations.",
            "Plant 1 seedling per prepared hole; backfill firmly and stake if site is exposed to wind.",
        ],
    },
    "maize": {
        "Đông Xuân": [
            "Target planting in November. Cool Đông Xuân weather reduces fall armyworm pressure and disease risk.",
            "Direct sow 2–3 seeds per hill at 5 cm depth; thin to 1 plant after germination.",
            "Row spacing: 70 cm; hill spacing: 25 cm (57,000 plants/ha target).",
        ],
        "Hè Thu": [
            "Target planting in March–April. Ensure drainage infrastructure is in place before sowing.",
            "Direct sow 2–3 seeds per hill at 5 cm depth; thin to 1 plant.",
            "Row spacing: 70 cm; hill spacing: 25 cm.",
        ],
        "Mùa": [
            "Plant at start of rainy season. Drainage is critical — avoid low-lying fields for Mùa maize.",
            "Direct sow 2–3 seeds per hill at 5 cm depth; row spacing: 70 cm; hill spacing: 25 cm.",
        ],
        "main": [
            "Direct sow 2–3 seeds per hill at 5 cm depth; thin to 1 plant after germination.",
            "Row spacing: 70 cm; hill spacing: 25 cm (57,000 plants/ha target).",
        ],
    },
}


# ---------------------------------------------------------------------------
# 3. Water management
# ---------------------------------------------------------------------------

_WATER_BASE: dict[str, list[str]] = {
    "rice_paddy": [
        "Maintain 5 cm flood depth during vegetative stage (days 0–45).",
        "Mid-season drainage: drain field for 3–5 days around day 35 to suppress weeds and aerate roots, then re-flood.",
        "Return to 5 cm flood at heading/flowering (days 45–75) — the most drought-sensitive growth period.",
        "Drain field completely 10 days before harvest to firm soil for mechanised access.",
    ],
    "coffee_green": [
        "Critical water need is at flowering to early fruit set (March–June). Maintain adequate soil moisture throughout.",
        "Stress-flower technique: withhold irrigation for 2 weeks before expected flowering, then flood heavily (60–80 mm) to trigger simultaneous bloom.",
        "Apply 10–15 cm organic mulch around tree basins to retain moisture and reduce irrigation frequency.",
    ],
    "pepper_black": [
        "Pepper does not tolerate waterlogging — inspect and clear drainage channels after each heavy rain event.",
        "Critical irrigation period: flowering and early fruiting (December–March in most regions).",
        "Allow soil to partially dry between irrigations — consistently wet soil promotes Phytophthora foot rot.",
    ],
    "cashew_raw": [
        "Mature cashew (>3 years old) is drought-tolerant and rarely requires irrigation.",
        "Young trees (year 1–2): irrigate every 10–14 days during dry months (December–April).",
        "No irrigation needed from June–October when rainy season provides sufficient moisture.",
    ],
    "maize": [
        "Maize requires 500–700 mm total water over the full growing season.",
        "Most critical stage: silking (days 55–70). Water stress at silking reduces final yield by 30–50%.",
        "Check soil moisture by pressing a handful of soil — if it crumbles and does not form a ball, irrigate.",
    ],
}


# ---------------------------------------------------------------------------
# 4. Pest & disease watch
# ---------------------------------------------------------------------------

_PEST_BASE: dict[str, dict[str, list[str]]] = {
    "rice_paddy": {
        "Đông Xuân": [
            "Rice blast (Magnaporthe oryzae): cool-wet Đông Xuân conditions are ideal for blast. Avoid excess nitrogen in first 4 weeks. Apply tricyclazole at first sign of lesions.",
            "Stem borer (Scirpophaga spp.): scout from week 2. Install pheromone traps; manually remove egg masses from seedlings.",
            "Golden apple snail: inspect bunds and early-stage flooded fields weekly. Hand-collect or apply approved molluscicide.",
        ],
        "Hè Thu": [
            "Brown planthopper (BPH, Nilaparvata lugens): hot-humid Hè Thu conditions are prime BPH outbreak conditions. Scout weekly from week 3 after planting.",
            "Bacterial leaf blight (Xanthomonas oryzae): likely after flooding events. Use resistant varieties — no effective curative chemical.",
            "Leaf folder (Cnaphalocrocis medinalis): common in dense plantings. Apply insecticide only when >25% of leaves show damage.",
        ],
        "Mùa": [
            "Sheath blight (Rhizoctonia solani): warm-wet Mùa conditions favour sheath blight. Avoid overly dense planting; apply validamycin if spreading to upper leaves.",
            "Rats and birds are significant threats at grain ripening stage — install rodent bait stations and bird netting.",
            "Brown planthopper risk is moderate in Mùa — weekly scouting recommended from transplanting.",
        ],
        "main": [
            "Scout weekly from week 3 for stem borers and planthoppers.",
            "Use resistant varieties and integrated pest management. Contact local extension service for current outbreak alerts.",
        ],
    },
    "coffee_green": {
        "main": [
            "Coffee berry borer (CBB, Hypothenemus hampei): use 8–10 pheromone traps per hectare and inspect every 30 days during fruiting (June–December). Most critical window is August–November.",
            "White stem borer (Xylotrechus quadripes): inspect lower trunk monthly for sawdust or gum secretions indicating boring activity.",
            "Leaf rust (Hemileia vastatrix): inspect undersides of leaves for orange-yellow spore deposits. Apply copper-based fungicide at first sign.",
            "Coffee wilt disease (Gibberella xylarioides): no cure — remove and burn affected trees immediately to prevent spread to neighbouring trees.",
        ],
    },
    "pepper_black": {
        "main": [
            "Phytophthora foot rot (Phytophthora capsici): #1 killer of pepper plantations. Inspect the crown area weekly during wet season. Remove infected vines immediately and treat surrounding soil with metalaxyl.",
            "Broad mite (Polyphagotarsonemus latus): look for distorted and hardened shoot tips in dry season. Apply sulphur-based miticide.",
            "Root-knot nematode (Meloidogyne spp.): yellowing and stunted growth indicate infestation. Apply nematicide at planting; plan host-rotation every 5–7 years.",
            "Virga disease (pepper die-back): spread by insect vectors. No chemical cure — remove and destroy infected vines promptly.",
        ],
    },
    "cashew_raw": {
        "main": [
            "Tea mosquito bug (Helopeltis spp.): main pest at leaf flushing and flowering. Spray neem extract or approved pyrethroid weekly during these stages.",
            "Anthracnose (Colletotrichum gloeosporioides): inspect new shoots for brown-black lesions. Apply copper-based fungicide at bud break and repeat after 14 days.",
            "Stem and root borer: check base of trunk for entry holes and sawdust deposits. Apply chlorpyrifos solution to the trunk base as a preventive measure.",
        ],
    },
    "maize": {
        "Đông Xuân": [
            "Fall armyworm (Spodoptera frugiperda): scout leaf whorls from week 2. Apply emamectin benzoate or chlorantraniliprole if >5 larvae per 10 plants.",
            "Downy mildew (Peronosclerospora maydis): inspect seedlings for white powdery coating. Apply metalaxyl at first sign; remove and burn affected plants.",
        ],
        "Hè Thu": [
            "Fall armyworm: peak risk in Hè Thu due to warm conditions. Scout every 5 days from week 2 and apply threshold-based treatments.",
            "Earworm (Helicoverpa armigera): inspect silks at early silking stage. Apply contact insecticide to silk if >10% of plants are infested.",
            "Downy mildew: inspect seedlings weekly — warm humid conditions accelerate spread.",
        ],
        "Mùa": [
            "Fall armyworm: scout weekly from week 2 throughout Mùa season.",
            "Stem rot and downy mildew are elevated risks in Mùa wet conditions — ensure good field drainage.",
        ],
        "main": [
            "Scout weekly for fall armyworm from week 2.",
            "Monitor for downy mildew on young plants and stem rot in wet conditions.",
        ],
    },
}


# ---------------------------------------------------------------------------
# 5. Irrigation schedule (growth-stage tables)
# ---------------------------------------------------------------------------

_IRRIGATION_SCHEDULES: dict[str, list[dict[str, str]]] = {
    "rice_paddy": [
        {"stage": "Germination",    "days": "0–7",    "moisture_target": "Saturated, no standing water",   "frequency": "Daily check",    "note": "Flooding before germination causes seed rot — keep moist not flooded"},
        {"stage": "Seedling",       "days": "7–21",   "moisture_target": "Shallow flood 2–3 cm",           "frequency": "Every 2 days",   "note": "Increase depth gradually; avoid flooding deeper than 5 cm at this stage"},
        {"stage": "Tillering",      "days": "21–45",  "moisture_target": "Continuous flood 5 cm",          "frequency": "Maintain flood", "note": "Mid-tillering drainage (day 35): remove water for 3–5 days to aerate roots and suppress weeds"},
        {"stage": "Heading/Flower", "days": "45–75",  "moisture_target": "Continuous flood 5 cm",          "frequency": "Maintain flood", "note": "Most critical stage — do not allow field to dry during heading or flowering"},
        {"stage": "Ripening",       "days": "75–100", "moisture_target": "Drain field",                    "frequency": "No irrigation",  "note": "Drain 10 days before harvest to firm soil for machinery access"},
    ],
    "maize": [
        {"stage": "Germination",  "days": "0–10",  "moisture_target": "60–70% field capacity",    "frequency": "Daily if no rain",   "note": "Critical for uniform emergence; waterlogging at germination causes damping-off"},
        {"stage": "Vegetative",   "days": "10–40", "moisture_target": "50–65% field capacity",    "frequency": "Every 4–5 days",     "note": "30–50 mm per irrigation event; adjust based on daily rainfall"},
        {"stage": "Silking",      "days": "40–65", "moisture_target": "70–80% field capacity",    "frequency": "Every 2–3 days",     "note": "Most critical stage — water stress here permanently reduces yield by 30–50%"},
        {"stage": "Grain fill",   "days": "65–90", "moisture_target": "60–70% field capacity",    "frequency": "Every 5–7 days",     "note": "Reduce frequency as grain hardens; excess moisture at this stage risks lodging"},
        {"stage": "Maturity",     "days": "90–110","moisture_target": "Allow gradual drying",     "frequency": "Stop irrigation",    "note": "Stop 2–3 weeks before harvest to allow dry-down for mechanised harvesting"},
    ],
    "coffee_green": [
        {"stage": "Establishment (yr 1, 0–90 d)",     "days": "0–90",    "moisture_target": "Consistently moist",         "frequency": "Every 5–7 days (dry months)",   "note": "200–250 L per tree per week; mulch reduces required frequency by 30–40%"},
        {"stage": "Growth (yr 1–2, dry months)",      "days": "90–730",  "moisture_target": "Moist with dry intervals",   "frequency": "Every 10–14 days (dry months)", "note": "10–15 cm organic mulch around basins; stop irrigation during rainy season"},
        {"stage": "Stress-flower (annual, Mar–Apr)",  "days": "—",       "moisture_target": "Dry stress then heavy flood","frequency": "Withhold 2 wk then flood once", "note": "Withhold all water for 14 days, then apply 60–80 mm to synchronise bloom"},
        {"stage": "Fruit set (annual, Apr–Jun)",      "days": "—",       "moisture_target": "Consistently moist",         "frequency": "Every 7–10 days",               "note": "Fruit size is set in first 8 weeks after fruit set — critical moisture period"},
        {"stage": "Ripening (annual, Sep–Jan)",       "days": "—",       "moisture_target": "Reduce moisture",            "frequency": "Reduce or stop",                "note": "Reduced moisture concentrates sugars and promotes even ripening"},
    ],
    "pepper_black": [
        {"stage": "Cutting establishment", "days": "0–90",   "moisture_target": "Moist, not waterlogged",  "frequency": "Every 3–4 days",         "note": "Standing water kills cuttings — ensure drainage mound is functional"},
        {"stage": "Vine growth",           "days": "90–365", "moisture_target": "Moist with dry intervals","frequency": "Every 7–10 days",         "note": "Reduce frequency in rainy season; increase in dry months (Dec–Apr)"},
        {"stage": "Flowering (Jan–Mar)",   "days": "—",      "moisture_target": "Consistent moisture",     "frequency": "Every 5–7 days",          "note": "Moisture is critical during berry set — water stress reduces fruit set significantly"},
        {"stage": "Fruiting (Apr–Aug)",    "days": "—",      "moisture_target": "Moderate moisture",       "frequency": "Every 7 days",            "note": "Do not overwater during fruiting — excess moisture triggers Phytophthora rot"},
        {"stage": "Harvest rest (Sep–Dec)","days": "—",      "moisture_target": "Slight dry stress",       "frequency": "Reduce or stop",          "note": "Allow soil to partially dry between irrigations to harden berries before harvest"},
    ],
    "cashew_raw": [
        {"stage": "Transplant (yr 1, 0–30 d)",           "days": "0–30",   "moisture_target": "Consistently moist",    "frequency": "Every 3–5 days",               "note": "Irrigate until new leaf flush is confirmed — indicates successful root establishment"},
        {"stage": "Early growth (yr 1, dry months)",     "days": "30–180", "moisture_target": "Moist in top 30 cm",    "frequency": "Every 7–10 days (dry months)", "note": "Stop irrigation entirely during rainy season; drought-tolerant once established"},
        {"stage": "Flush/flower (annual, Nov–Feb)",      "days": "—",      "moisture_target": "Allow dry stress",      "frequency": "None if possible",             "note": "Dry conditions promote heavier and more uniform flowering"},
        {"stage": "Fruit development (annual, Mar–Jun)", "days": "—",      "moisture_target": "Moderate moisture",     "frequency": "Once if dry spell >14 days",   "note": "One supplemental irrigation during nut sizing improves kernel weight by 10–15%"},
        {"stage": "Post-harvest (annual, Jul–Oct)",      "days": "—",      "moisture_target": "Allow full stress",     "frequency": "None",                         "note": "Rainy season provides sufficient moisture; supplemental irrigation not needed"},
    ],
}

_IRRIGATION_DEFAULT: list[dict[str, str]] = [
    {"stage": "All stages", "days": "0–120", "moisture_target": "Adequate moisture", "frequency": "As needed", "note": "Follow local extension service guidelines for this crop and region."},
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def farming_methods_for_crop(
    crop: str,
    soil_texture_class: str,
    season: str,
    forecast_rain_14d: float,
    forecast_rain_days: int,
    forecast_mean_temp_c: float,
) -> dict[str, object]:
    """Return structured farming guidance for a crop given environmental context.

    Args:
        crop:                 Canonical crop name (from crops.py).
        soil_texture_class:   USDA texture class from SoilGrids or farmer override.
        season:               Season name — "Đông Xuân", "Hè Thu", "Mùa", or "main".
        forecast_rain_14d:    Total forecast precipitation over the next 14 days (mm).
        forecast_rain_days:   Days with >5 mm precipitation forecast in the next 14 days.
        forecast_mean_temp_c: 14-day mean air temperature forecast (°C).

    Returns:
        Dict with keys: land_preparation, planting, water_management,
        pest_watch, irrigation_schedule.
    """
    tex_group = _texture_group(soil_texture_class)

    # --- Land preparation
    land_prep: list[str] = list(
        _LAND_PREP.get(crop, {}).get(tex_group)
        or _LAND_PREP.get(crop, {}).get("loam")
        or _LAND_PREP_DEFAULT
    )

    # --- Planting method (season-specific, with weather adjustments)
    crop_planting = _PLANTING_BASE.get(crop, {})
    planting: list[str] = list(
        crop_planting.get(season)
        or crop_planting.get("main")
        or [
            "Follow standard planting guidelines for this crop.",
            "Confirm seed source and variety suitability for this region before planting.",
        ]
    )

    if forecast_rain_days > 5:
        if crop == "rice_paddy" and season in ("Hè Thu", "Mùa"):
            planting.append(
                f"⚠ {forecast_rain_days} rainy days forecast in the next 14 days — delay direct seeding. "
                "Wet soil at sowing significantly increases damping-off risk. "
                "Transplanting from a nursery is more resilient under this forecast."
            )
        elif crop in ("maize", "cashew_raw", "pepper_black"):
            planting.append(
                f"⚠ {forecast_rain_days} rainy days forecast — if soil is waterlogged, delay planting by "
                "5–7 days. Saturated soil at planting increases damping-off and root rot risk."
            )

    # --- Water management (crop-specific base + forecast adjustments)
    water: list[str] = list(
        _WATER_BASE.get(crop, ["Follow standard irrigation guidelines for this crop."])
    )
    if forecast_rain_14d > 200:
        water.append(
            f"⚠ High rainfall forecast ({forecast_rain_14d:.0f} mm over 14 days) — "
            "prepare or clear drainage channels before planting. Excess water during establishment "
            "risks oxygen depletion and root damage."
        )
    elif forecast_rain_14d < 50:
        water.append(
            f"⚠ Dry forecast ({forecast_rain_14d:.0f} mm over 14 days) — plan supplemental irrigation "
            "at 3–5 day intervals. Confirm borehole or canal water access before committing to planting."
        )

    # --- Pest & disease watch (season-specific + temperature adjustments)
    crop_pests = _PEST_BASE.get(crop, {})
    pest: list[str] = list(
        crop_pests.get(season)
        or crop_pests.get("main")
        or ["Scout weekly for common pests. Contact the local extension service for current regional alerts."]
    )
    if forecast_mean_temp_c > 30 and season == "Hè Thu" and crop == "rice_paddy":
        pest.append(
            f"⚠ Heat + humidity ({forecast_mean_temp_c:.0f} °C forecast mean) is a known brown "
            "planthopper outbreak trigger — increase scouting frequency to twice weekly."
        )
    if forecast_mean_temp_c > 30 and crop == "maize":
        pest.append(
            f"⚠ High temperature ({forecast_mean_temp_c:.0f} °C forecast mean) accelerates fall "
            "armyworm development — scout every 5 days from week 2 onwards."
        )

    # --- Irrigation schedule (static growth-stage table per crop)
    irrigation: list[dict[str, str]] = _IRRIGATION_SCHEDULES.get(crop, _IRRIGATION_DEFAULT)

    return {
        "land_preparation": land_prep,
        "planting": planting,
        "water_management": water,
        "pest_watch": pest,
        "irrigation_schedule": irrigation,
    }
