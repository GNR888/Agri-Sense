"""Print soil properties for Cần Thơ and Buôn Ma Thuột to compare delta vs. highlands."""

import logging

from agri_sense.ingestion.soilgrids import fetch_soil_properties

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

LOCATIONS: list[tuple[str, float, float]] = [
    ("Cần Thơ (Mekong Delta)", 10.0341, 105.7880),
    ("Buôn Ma Thuột (Central Highlands)", 12.6797, 108.0377),
]

LABELS: dict[str, str] = {
    "ph": "pH",
    "soc_g_per_kg": "Organic carbon (g/kg)",
    "nitrogen_cg_per_kg": "Nitrogen (cg/kg)",
    "sand_pct": "Sand (%)",
    "silt_pct": "Silt (%)",
    "clay_pct": "Clay (%)",
    "cec_mmol_per_kg": "CEC (mmol/kg)",
    "bulk_density_kg_per_dm3": "Bulk density (kg/dm³)",
    "soil_texture_class": "Texture class",
}

if __name__ == "__main__":
    for name, lat, lon in LOCATIONS:
        print(f"\n=== {name}  (lat={lat}, lon={lon}) ===")
        props = fetch_soil_properties(lat, lon)
        for key, label in LABELS.items():
            val = props.get(key, "N/A")
            print(f"  {label:<30} {val}")
