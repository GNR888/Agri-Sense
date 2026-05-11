"""Integration test — fetches soil data for Cần Thơ from SoilGrids 2.0."""

import math

import pytest

from agri_sense.ingestion.soilgrids import VALID_TEXTURE_CLASSES, fetch_soil_properties

# Cần Thơ — Mekong Delta, Vietnam
LAT = 10.0341
LON = 105.7880

EXPECTED_FLOAT_KEYS = {
    "ph",
    "soc_g_per_kg",
    "nitrogen_cg_per_kg",
    "sand_pct",
    "silt_pct",
    "clay_pct",
    "cec_mmol_per_kg",
    "bulk_density_kg_per_dm3",
}


@pytest.mark.integration
def test_fetch_soil_properties_can_tho() -> None:
    props = fetch_soil_properties(LAT, LON)

    # All expected keys present
    assert EXPECTED_FLOAT_KEYS | {"soil_texture_class"} == set(props.keys())

    # No NaN values — API should have data for this well-covered location
    for key in EXPECTED_FLOAT_KEYS:
        assert not math.isnan(float(props[key])), f"{key} is NaN"

    # pH must be in plausible agricultural range
    assert 3.0 <= float(props["ph"]) <= 10.0, f"pH out of range: {props['ph']}"

    # Sand + silt + clay should sum to roughly 100 % (small rounding drift allowed)
    pct_sum = float(props["sand_pct"]) + float(props["silt_pct"]) + float(props["clay_pct"])
    assert abs(pct_sum - 100.0) < 5.0, f"Sand+silt+clay = {pct_sum:.1f}, expected ~100"

    # Texture class must be one of the 12 USDA classes
    assert props["soil_texture_class"] in VALID_TEXTURE_CLASSES, (
        f"Unknown texture class: {props['soil_texture_class']}"
    )
