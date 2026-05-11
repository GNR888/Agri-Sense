"""Province-level geographic feature engineering.

Encodes region, salinity risk, and elevation zone from province_key.
These features carry location signal that lat/lon alone can't provide
on a small (~200 row) training set.
"""

from __future__ import annotations

# region: 0=Mekong Delta, 1=Red River Delta, 2=Central Highlands, 3=other
REGION_CODES: dict[str, int] = {
    "Mekong Delta": 0,
    "Red River Delta": 1,
    "Central Highlands": 2,
}

# Provinces with documented salinity / tidal intrusion risk (Mekong Delta coast)
SALINITY_RISK_PROVINCE_KEYS: frozenset[str] = frozenset(
    {"can_tho", "kien_giang", "soc_trang", "dong_thap"}
)

# Elevation zone: 0=low (<100 m), 1=mid (100–500 m), 2=high (>500 m)
# Based on dominant farming elevation within each province's farm zone.
ELEVATION_ZONE: dict[str, int] = {
    "can_tho":    0,  # Mekong floodplain, ~1 m
    "kien_giang": 0,  # Coastal delta, <5 m
    "an_giang":   0,  # Mekong flood-recession plain, ~3 m
    "dong_thap":  0,  # Floodplain paddies, <5 m
    "soc_trang":  0,  # Delta coastal plain, <3 m
    "thai_binh":  0,  # Red River coastal plain, <5 m
    "nam_dinh":   0,  # Red River coastal plain, <5 m
    "nghe_an":    0,  # Alluvial rice plain, ~10–30 m
    "quang_nam":  0,  # Coastal plain, <50 m
    "dong_nai":   1,  # Rolling terrain, ~200 m
    "dak_lak":    2,  # Basaltic plateau, 400–600 m
    "lam_dong":   2,  # Highland plateau, 900–1 000 m
    "gia_lai":    2,  # Basaltic plateau, 700–900 m
}


def add_province_features(
    province_key: str,
    region: str,
) -> dict[str, int]:
    """Return geographic feature dict for a province.

    Args:
        province_key: snake_case province identifier (key in PROVINCES).
        region:       ProvinceInfo.region string (e.g. "Mekong Delta").

    Returns:
        Dict with keys: region_code, salinity_risk, elevation_zone.
    """
    return {
        "region_code": REGION_CODES.get(region, 3),
        "salinity_risk": int(province_key in SALINITY_RISK_PROVINCE_KEYS),
        "elevation_zone": ELEVATION_ZONE.get(province_key, 0),
    }
