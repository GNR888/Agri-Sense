"""Load curated GSO/FAOSTAT-derived crop yield data for Vietnamese provinces."""

from pathlib import Path

import pandas as pd

from agri_sense.utils.config import config
from agri_sense.utils.crops import normalise_crop_name

_DTYPES: dict[str, str] = {
    "province": "string",
    "year": "int32",
    "season": "string",
    "crop": "string",
    "area_ha": "int32",
    "production_tonnes": "int32",
    "yield_tonnes_per_ha": "float32",
    "source": "string",
}


def load_yields(path: Path | None = None) -> pd.DataFrame:
    """Return the curated provincial yield table.

    Columns: province, year, season, crop, area_ha, production_tonnes,
    yield_tonnes_per_ha, source.
    """
    csv_path = path if path is not None else config.raw_dir / "gso" / "yields.csv"
    df = pd.read_csv(csv_path, dtype=_DTYPES)
    df["crop"] = df["crop"].map(normalise_crop_name)
    return df
