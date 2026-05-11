"""Run the cleaning / imputation / normalisation pipeline.

Usage:
    uv run python scripts/process.py

Reads:  data/interim/master.parquet
Writes: data/processed/training.parquet
        data/processed/scaler.pkl
        data/processed/scaler_params.json
"""

import logging

import pandas as pd

from agri_sense.processing.pipeline import run_pipeline
from agri_sense.utils.config import config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    run_pipeline()

    training_path = config.processed_dir / "training.parquet"
    clf_view = pd.read_parquet(training_path)

    print(f"\ntraining.parquet shape: {clf_view.shape}")

    print("\n── dtypes ─────────────────────────────────────────────────────────────")
    pd.set_option("display.max_rows", None)
    print(clf_view.dtypes.to_string())

    print("\n── NaN counts (numeric columns) ────────────────────────────────────────")
    numeric_nan = clf_view.select_dtypes(include="number").isna().sum()
    bad = numeric_nan[numeric_nan > 0]
    if bad.empty:
        print("No NaNs in numeric columns.")
    else:
        print(bad.to_string())

    print("\n── head ────────────────────────────────────────────────────────────────")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(clf_view.head().to_string())


if __name__ == "__main__":
    main()
