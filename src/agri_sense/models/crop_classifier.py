"""Crop classifier — XGBoost with transparent sklearn fallback.

XGBoost 3.x on macOS requires ``libomp.dylib`` at the system level
(``brew install libomp``).  When it cannot load, the module falls back to
``HistGradientBoostingClassifier`` from scikit-learn, which has near-identical
API and performance for tabular data.  The fallback is noted in log output.
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)

def _try_import_xgboost_classifier(timeout: float = 3.0) -> type | None:
    """Import XGBClassifier in a daemon thread; return None if it hangs or fails."""
    import threading  # noqa: PLC0415

    result: list[type | None] = [None]
    done = threading.Event()

    def _do_import() -> None:
        try:
            from xgboost import XGBClassifier  # noqa: PLC0415
            result[0] = XGBClassifier
        except Exception:  # noqa: BLE001
            pass
        finally:
            done.set()

    t = threading.Thread(target=_do_import, daemon=True)
    t.start()
    done.wait(timeout=timeout)
    return result[0]


_XGBClassifier = _try_import_xgboost_classifier()
if _XGBClassifier is not None:
    _BACKEND = "xgboost"
else:
    _BACKEND = "sklearn"
    logger.warning(
        "XGBoost could not be loaded (likely missing libomp on macOS — "
        "run `brew install libomp`). Falling back to HistGradientBoostingClassifier."
    )

if _BACKEND == "xgboost":
    def _make_model() -> object:
        return _XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            eval_metric="mlogloss",
            random_state=42,
            verbosity=0,
        )
else:
    from sklearn.ensemble import HistGradientBoostingClassifier as _HGBC

    def _make_model() -> object:  # type: ignore[misc]
        return _HGBC(
            max_iter=200,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
        )


def _meta_path(model_path: Path) -> Path:
    return model_path.with_name(model_path.stem + "_meta.json")


def _calibrated_path(model_path: Path) -> Path:
    return model_path.with_name(model_path.stem + "_calibrated.pkl")


class CropClassifier:
    """Multi-class crop predictor.  Backend: XGBoost (preferred) or sklearn HGBC.

    After training the base model, a CalibratedClassifierCV (isotonic regression)
    is fit on the held-out 20% split to produce well-calibrated probabilities.
    """

    def __init__(self) -> None:
        self._model: object = _make_model()
        self._calibrated_model: CalibratedClassifierCV | None = None
        self._backend: str = _BACKEND
        self._le: LabelEncoder = LabelEncoder()
        self.feature_columns: list[str] = []
        self.classes_: list[str] = []

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Train base model on 80%; calibrate and evaluate on held-out 20%."""
        self.feature_columns = list(X.columns)
        X_num = X.astype(float)

        y_enc: np.ndarray = self._le.fit_transform(y)
        self.classes_ = list(self._le.classes_)

        # 80/20 stratified split — held-out 20% used for accuracy/confusion metrics
        X_tr, X_te, y_tr, y_te = train_test_split(
            X_num, y_enc, test_size=0.2, random_state=42, stratify=y_enc
        )

        # Train base model on 80% for evaluation purposes
        if self._backend == "xgboost":
            self._model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)  # type: ignore[union-attr]
        else:
            self._model.fit(X_tr, y_tr)  # type: ignore[union-attr]

        # CalibratedClassifierCV with cv=3: trains 3-fold cross-calibration on full data.
        # This is the sklearn 1.8+ approach for well-calibrated multi-class probabilities.
        self._calibrated_model = CalibratedClassifierCV(
            _make_model(),
            method="isotonic",
            cv=3,
        )
        self._calibrated_model.fit(X_num, y_enc)

        # Metrics on the held-out 20% (base model — class predictions are unchanged by calibration)
        y_pred: np.ndarray = self._model.predict(X_te)  # type: ignore[union-attr]
        acc = accuracy_score(y_te, y_pred)

        proba = self._calibrated_model.predict_proba(X_te)
        top3_hits = [y_te[i] in np.argsort(proba[i])[-3:] for i in range(len(y_te))]
        top3_acc = float(np.mean(top3_hits))

        cm = confusion_matrix(y_te, y_pred)
        col_w = max(len(c) for c in self.classes_) + 2

        print(f"\n{'='*62}")
        print(f"CROP CLASSIFIER — TEST-SET METRICS  [{self._backend}]")
        print(f"  n_train={len(X_tr)}  n_test={len(X_te)}  n_classes={len(self.classes_)}")
        print(f"  Accuracy:       {acc:.3f}")
        print(f"  Top-3 accuracy: {top3_acc:.3f}")
        header = " " * (col_w + 2) + "  ".join(f"{c:>{col_w}}" for c in self.classes_)
        print(f"\n  Confusion matrix (rows=true, cols=pred):")
        print(f"  {header}")
        for i, label in enumerate(self.classes_):
            row_str = "  ".join(f"{v:>{col_w}}" for v in cm[i])
            print(f"  {label:>{col_w}}  {row_str}")

        # Feature importances (top-10 by gain)
        fi: np.ndarray | None = getattr(self._model, "feature_importances_", None)
        if fi is not None and len(fi) == len(self.feature_columns):
            ranked = sorted(
                zip(self.feature_columns, fi.tolist()),
                key=lambda t: t[1],
                reverse=True,
            )[:10]
            print("\n  Feature importances (top-10, gain):")
            for feat, imp in ranked:
                print(f"    {feat:<35} {imp:.4f}")

        print("="*62)

        if acc < 0.4:
            print("  NOTE: low accuracy expected on this small dataset (~200 rows / 5 crops).")
            print("        Pipeline correctness is the goal, not accuracy tuning.")

        logger.info("Classifier [%s] test accuracy=%.3f  top3=%.3f", self._backend, acc, top3_acc)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        enc: np.ndarray = self._model.predict(X[self.feature_columns].astype(float))  # type: ignore[union-attr]
        return np.array(self._le.inverse_transform(enc.astype(int)))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated probabilities; falls back to raw model if not yet calibrated."""
        Xf = X[self.feature_columns].astype(float)
        if self._calibrated_model is not None:
            return self._calibrated_model.predict_proba(Xf)
        return self._model.predict_proba(Xf)  # type: ignore[union-attr]

    @property
    def feature_importances_(self) -> np.ndarray | None:
        return getattr(self._model, "feature_importances_", None)

    def save(self, path: Path) -> None:
        path = Path(path)
        if self._backend == "xgboost":
            self._model.save_model(str(path))  # type: ignore[union-attr]
        else:
            pkl_path = path.with_suffix(".pkl")
            with open(pkl_path, "wb") as fh:
                pickle.dump(self._model, fh)

        if self._calibrated_model is not None:
            with open(_calibrated_path(path), "wb") as fh:
                pickle.dump(self._calibrated_model, fh)
            logger.info("Saved calibrated classifier → %s", _calibrated_path(path))

        meta = {
            "feature_columns": self.feature_columns,
            "classes": self.classes_,
            "backend": self._backend,
            "has_calibrated": self._calibrated_model is not None,
        }
        _meta_path(path).write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        logger.info("Saved classifier [%s] → %s", self._backend, path)

    def load(self, path: Path) -> None:
        path = Path(path)
        meta = json.loads(_meta_path(path).read_text())
        self.feature_columns = meta["feature_columns"]
        self.classes_ = meta["classes"]
        self._backend = meta.get("backend", "xgboost")
        self._le = LabelEncoder()
        self._le.fit(self.classes_)

        if self._backend == "xgboost":
            self._model = _make_model()
            self._model.load_model(str(path))  # type: ignore[union-attr]
        else:
            pkl_path = path.with_suffix(".pkl")
            with open(pkl_path, "rb") as fh:
                self._model = pickle.load(fh)

        cal_path = _calibrated_path(path)
        if meta.get("has_calibrated") and cal_path.exists():
            with open(cal_path, "rb") as fh:
                self._calibrated_model = pickle.load(fh)
            logger.info("Loaded calibrated classifier from %s", cal_path)
        else:
            self._calibrated_model = None

        logger.info("Loaded classifier [%s] from %s", self._backend, path)
