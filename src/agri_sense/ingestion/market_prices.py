# TODO: v2 should scrape agromonitor.vn or partner with cooperatives for live data.
"""Hardcoded farmgate market prices for the MVP."""

from pathlib import Path

import pandas as pd

from agri_sense.utils.config import config
from agri_sense.utils.crops import normalise_crop_name

_DTYPES: dict[str, str] = {
    "crop": "string",
    "price_vnd_per_kg": "int32",
    "year": "int32",
    "source": "string",
}


def load_prices(path: Path | None = None) -> pd.DataFrame:
    """Return the curated farmgate price table.

    Columns: crop, price_vnd_per_kg, year, source.
    """
    csv_path = path if path is not None else config.raw_dir / "market" / "prices.csv"
    df = pd.read_csv(csv_path, dtype=_DTYPES)
    df["crop"] = df["crop"].map(normalise_crop_name)
    return df
