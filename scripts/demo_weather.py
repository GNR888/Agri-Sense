"""Pull 1 year of NASA POWER weather for Cần Thơ and print summary stats."""

import logging
from datetime import date

from agri_sense.ingestion.nasa_power import fetch_daily_weather

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

LAT, LON = 10.0341, 105.7880
START, END = date(2023, 1, 1), date(2023, 12, 31)

if __name__ == "__main__":
    df = fetch_daily_weather(LAT, LON, START, END)
    print(f"\n=== Cần Thơ daily weather {START} → {END} ===")
    print(f"Rows: {len(df)}  |  Missing values per column:")
    print(df.isna().sum().to_string())
    print("\nSummary statistics:")
    print(df.describe().round(2).to_string())
