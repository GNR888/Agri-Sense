"""Train crop classifier and yield regressor from processed training data."""

from __future__ import annotations

import json
import logging

import pandas as pd

from agri_sense.models.crop_classifier import CropClassifier
from agri_sense.models.yield_regressor import YieldRegressor
from agri_sense.utils.config import config

logger = logging.getLogger(__name__)

# Columns that are metadata — not model inputs
_METADATA_COLS: frozenset[str] = frozenset(
    {"province", "province_key", "year", "area_ha", "production_tonnes", "is_outlier_clipped"}
)
_TARGET_COL = "yield_tonnes_per_ha"
_CROP_COL = "crop"


def _split_classifier(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Return (X_clf, y_clf) from the classifier view."""
    drop = (_METADATA_COLS | {_TARGET_COL, _CROP_COL}) & set(df.columns)
    X = df.drop(columns=list(drop))
    y = df[_CROP_COL]
    return X, y


def _split_regressor(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (X_reg, y_reg, crop_labels) by OHE-ing the crop column."""
    crop_dummies = pd.get_dummies(df[_CROP_COL].astype(str), prefix="crop", dtype=float)
    drop = (_METADATA_COLS | {_TARGET_COL, _CROP_COL}) & set(df.columns)
    base = df.drop(columns=list(drop))
    X = pd.concat([base, crop_dummies], axis=1)
    y = df[_TARGET_COL]
    crop_labels = df[_CROP_COL]
    return X, y, crop_labels


def train_all() -> None:
    """Load training.parquet, train both models, save to data/processed/."""
    training_path = config.processed_dir / "training.parquet"
    if not training_path.exists():
        raise FileNotFoundError(
            f"training.parquet not found at {training_path}. Run scripts/process.py first."
        )

    df = pd.read_parquet(training_path)
    logger.info("Loaded training.parquet: %d rows × %d cols", *df.shape)

    print(f"\nDataset: {df.shape[0]} rows, {df.shape[1]} columns")
    print(f"Crops:   {dict(df[_CROP_COL].value_counts())}")

    # -- Classifier
    X_clf, y_clf = _split_classifier(df)
    clf = CropClassifier()
    clf.fit(X_clf, y_clf)
    clf_path = config.processed_dir / "classifier.json"
    clf.save(clf_path)

    # -- Regressor
    X_reg, y_reg, crop_labels = _split_regressor(df)
    reg = YieldRegressor()
    reg.fit(X_reg, y_reg, crop_labels=crop_labels)
    reg_path = config.processed_dir / "regressor.json"
    reg.save(reg_path)

    # -- feature_columns.json (convenience manifest for predict.py and debugging)
    fc_path = config.processed_dir / "feature_columns.json"
    fc_path.write_text(
        json.dumps(
            {
                "classifier_features": clf.feature_columns,
                "regressor_features": reg.feature_columns,
                "crop_classes": clf.classes_,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    logger.info("Saved feature_columns.json → %s", fc_path)

    print(f"\nAll artefacts saved to {config.processed_dir}/")
    print(f"  classifier.json ({len(clf.feature_columns)} features, {len(clf.classes_)} classes)")
    print(f"  regressor.json  ({len(reg.feature_columns)} features)")
    print("  feature_columns.json")
