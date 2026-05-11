"""Bootstrap Agri-Sense from scratch on a fresh checkout.

Runs the full pipeline in order:
  1. Build dataset     →  data/interim/master.parquet
  2. Process pipeline  →  data/processed/training.parquet + scaler artefacts
  3. Train models      →  data/processed/classifier.json + regressor.json

Then prints a summary: dataset shape, classifier accuracy, regressor RMSE,
and the size of every artefact written to data/processed/.

Usage:
  uv run python scripts/bootstrap.py                  # full run (fetches APIs)
  uv run python scripts/bootstrap.py --skip-ingestion # skip API fetches (master.parquet must exist)
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time

# Configure logging before any agri_sense imports so all handlers are in place.
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metric capture — listens to the loggers in crop_classifier / yield_regressor
# ---------------------------------------------------------------------------

class _MetricCapture(logging.Handler):
    """Scrape classifier accuracy and regressor RMSE from log records."""

    def __init__(self) -> None:
        super().__init__()
        self.clf_accuracy: float | None = None
        self.reg_rmse: float | None = None

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if m := re.search(r"Classifier .* test accuracy=([\d.]+)", msg):
            self.clf_accuracy = float(m.group(1))
        elif m := re.search(r"Regressor .* test RMSE=([\d.]+)", msg):
            self.reg_rmse = float(m.group(1))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _banner(step: str) -> None:
    bar = "─" * 64
    print(f"\n{bar}\n  {step}\n{bar}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap Agri-Sense: build dataset → process → train.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help=(
            "Skip API data fetching and assume data/interim/master.parquet already exists. "
            "Useful when re-running process + train after data is already downloaded."
        ),
    )
    args = parser.parse_args()

    # Attach capture handler to the root logger so it sees every module.
    capture = _MetricCapture()
    logging.getLogger().addHandler(capture)

    t_start = time.perf_counter()

    # ── Step 1: build dataset ───────────────────────────────────────────────
    _banner("STEP 1 / 3 — Build dataset (ingestion + feature engineering)")

    import pandas as pd
    from agri_sense.processing.build_dataset import build
    from agri_sense.utils.config import config

    if args.skip_ingestion:
        master_path = config.interim_dir / "master.parquet"
        if not master_path.exists():
            logger.error(
                "--skip-ingestion was set but %s does not exist.\n"
                "Run without --skip-ingestion to fetch data from the APIs.",
                master_path,
            )
            sys.exit(1)
        logger.info("--skip-ingestion: loading existing master.parquet from %s", master_path)
        master = pd.read_parquet(master_path)
    else:
        master = build(force=True)

    print(f"\n  master.parquet:  {master.shape[0]:,} rows × {master.shape[1]} columns")
    print(f"  Seasons:  {sorted(master['season'].unique())}")
    print(f"  Crops:    {sorted(master['crop'].unique())}")
    print(f"  Provinces: {master['province_key'].nunique()}")

    # ── Step 2: processing pipeline ─────────────────────────────────────────
    _banner("STEP 2 / 3 — Processing pipeline (clean → impute → normalise)")

    from agri_sense.processing.pipeline import run_pipeline

    run_pipeline()

    training = pd.read_parquet(config.processed_dir / "training.parquet")
    nan_counts = training.select_dtypes("number").isna().sum()
    n_nan_cols = int((nan_counts > 0).sum())

    print(f"\n  training.parquet: {training.shape[0]:,} rows × {training.shape[1]} columns")
    if n_nan_cols:
        print(f"  WARNING: {n_nan_cols} numeric columns still contain NaNs after imputation.")
    else:
        print("  NaN check: OK — no NaNs in numeric columns.")

    # ── Step 3: train models ─────────────────────────────────────────────────
    _banner("STEP 3 / 3 — Train models (XGBoost classifier + regressor)")

    from agri_sense.models.train import train_all

    train_all()

    # ── Final summary ────────────────────────────────────────────────────────
    elapsed = time.perf_counter() - t_start
    processed_dir = config.processed_dir

    print(f"\n{'═' * 64}")
    print("  BOOTSTRAP COMPLETE")
    print(f"{'═' * 64}")
    print(f"  Total time:         {elapsed / 60:.1f} min  ({elapsed:.0f} s)")
    print(f"  Dataset:            {master.shape[0]:,} rows × {master.shape[1]} columns")
    print(f"  Training set:       {training.shape[0]:,} rows × {training.shape[1]} columns")

    if capture.clf_accuracy is not None:
        print(f"  Classifier acc:     {capture.clf_accuracy:.3f}")
    else:
        print("  Classifier acc:     (see training output above)")

    if capture.reg_rmse is not None:
        print(f"  Regressor RMSE:     {capture.reg_rmse:.3f} t/ha")
    else:
        print("  Regressor RMSE:     (see training output above)")

    print(f"\n  Artefacts saved to {processed_dir}/")
    artefacts = sorted(processed_dir.iterdir()) if processed_dir.exists() else []
    for f in artefacts:
        size_kb = f.stat().st_size / 1_024
        print(f"    {f.name:<38}  {size_kb:>8.1f} KB")

    print(f"\n  Next steps:")
    print(f"    uv run python scripts/serve.py          # start the FastAPI backend")
    print(f"    cd app && npm run dev                   # start the frontend (port 3000)")
    print(f"{'═' * 64}\n")


if __name__ == "__main__":
    main()
