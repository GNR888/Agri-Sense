"""End-to-end processing pipeline: clean → impute → normalise → write.

Reads:  data/interim/master.parquet
Writes: data/processed/training.parquet
        data/processed/scaler.pkl
        data/processed/scaler_params.json
"""

import logging

import pandas as pd

from agri_sense.processing.clean import clean
from agri_sense.processing.impute import impute
from agri_sense.processing.normalise import normalise
from agri_sense.utils.config import config

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """Read master.parquet, run clean → impute → normalise, write processed outputs."""
    master_path = config.interim_dir / "master.parquet"
    if not master_path.exists():
        raise FileNotFoundError(
            f"master.parquet not found at {master_path}. Run scripts/build_dataset.py first."
        )

    df: pd.DataFrame = pd.read_parquet(master_path)
    logger.info("Loaded  master.parquet: %d rows × %d cols", *df.shape)

    df = clean(df)
    logger.info("cleaned: %d rows × %d cols", *df.shape)

    df = impute(df)
    logger.info("imputed: %d rows × %d cols", *df.shape)

    config.processed_dir.mkdir(parents=True, exist_ok=True)
    scaler_path = config.processed_dir / "scaler.pkl"

    views, _params = normalise(df, fit=True, scaler_path=scaler_path)

    training_path = config.processed_dir / "training.parquet"
    views["classifier_view"].to_parquet(training_path, index=False)
    logger.info(
        "Saved → %s  shape=%s",
        training_path,
        views["classifier_view"].shape,
    )

    # Verify no NaNs remain in numeric columns of the classifier view
    clf = views["classifier_view"]
    numeric_nan = clf.select_dtypes(include="number").isna().sum()
    bad = numeric_nan[numeric_nan > 0]
    if bad.empty:
        logger.info("OK — no NaNs in numeric columns of training.parquet")
    else:
        logger.warning("NaN columns still present after pipeline:\n%s", bad.to_string())
