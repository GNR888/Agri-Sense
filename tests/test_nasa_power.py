"""Integration test — pulls 30 days of weather for Cần Thơ from NASA POWER."""

from datetime import date

import pandas as pd
import pytest

from agri_sense.ingestion.nasa_power import fetch_daily_weather

LAT = 10.0341
LON = 105.7880
START = date(2024, 1, 1)
END = date(2024, 1, 30)
EXPECTED_COLUMNS = {"temp_mean_c", "temp_max_c", "temp_min_c", "precip_mm", "humidity_pct", "solar_mj", "wind_ms"}


@pytest.mark.integration
def test_fetch_daily_weather_can_tho() -> None:
    df = fetch_daily_weather(LAT, LON, START, END)

    assert not df.empty, "DataFrame must not be empty"
    assert EXPECTED_COLUMNS == set(df.columns), f"Unexpected columns: {df.columns.tolist()}"

    # No -999 sentinel values anywhere
    assert not (df == -999).any().any(), "Found -999 sentinel values — should be NaN"

    # Dates are continuous (no gaps)
    expected_index = pd.date_range(START, END, freq="D", name="date")
    pd.testing.assert_index_equal(df.index, expected_index, check_names=False)
