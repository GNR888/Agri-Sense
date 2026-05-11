"""Yield regressor — XGBoost with transparent sklearn fallback.

See crop_classifier.py for the libomp / fallback rationale.
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)

def _try_import_xgboost_regressor(timeout: float = 3.0) -> type | None:
    """Import XGBRegressor in a daemon thread; return None if it hangs or fails."""
    import threading  # noqa: PLC0415

    result: list[type | None] = [None]
    done = threading.Event()

    def _do_import() -> None:
        try:
            from xgboost import XGBRegressor  # noqa: PLC0415
            result[0] = XGBRegressor
        except Exception:  # noqa: BLE001
            pass
        finally:
            done.set()

    t = threading.Thread(target=_do_import, daemon=True)
    t.start()
    done.wait(timeout=timeout)
    return result[0]


_XGBRegressor = _try_import_xgboost_regressor()
if _XGBRegressor is not None:
    _BACKEND = "xgboost"
else:
    _BACKEND = "sklearn"
    logger.warning(
        "XGBoost could not be loaded. Falling back to HistGradientBoostingRegressor."
    )

if _BACKEND == "xgboost":
    def _make_model() -> object:
        return _XGBRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.1,
            eval_metric="rmse",
            random_state=42,
            verbosity=0,
        )
else:
    from sklearn.ensemble import HistGradientBoostingRegressor as _HGBR

    def _make_model() -> object:  # type: ignore[misc]
        return _HGBR(
            max_iter=300,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
        )


def _meta_path(model_path: Path) -> Path:
    return model_path.with_name(model_path.stem + "_meta.json")


class YieldRegressor:
    """Predicts yield (t/ha) given crop + environment features."""

    def __init__(self) -> None:
        self._model: object = _make_model()
        self._backend: str = _BACKEND
        self.feature_columns: list[str] = []

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        crop_labels: pd.Series | None = None,
    ) -> None:
        """Train on (X, y); log RMSE/MAE/R² and per-crop RMSE on held-out test."""
        self.feature_columns = list(X.columns)
        X_num = X.astype(float)

        X_tr, X_te, y_tr, y_te = train_test_split(
            X_num, y, test_size=0.2, random_state=42
        )
        crop_te = crop_labels.loc[X_te.index] if crop_labels is not None else None

        if self._backend == "xgboost":
            self._model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)  # type: ignore[union-attr]
        else:
            self._model.fit(X_tr, y_tr)  # type: ignore[union-attr]

        y_pred: np.ndarray = self._model.predict(X_te)  # type: ignore[union-attr]
        rmse = float(np.sqrt(mean_squared_error(y_te, y_pred)))
        mae = float(mean_absolute_error(y_te, y_pred))
        r2 = float(r2_score(y_te, y_pred))

        print(f"\n{'='*62}")
        print(f"YIELD REGRESSOR — TEST-SET METRICS  [{self._backend}]")
        print(f"  n_train={len(X_tr)}  n_test={len(X_te)}")
        print(f"  RMSE: {rmse:.3f} t/ha")
        print(f"  MAE:  {mae:.3f} t/ha")
        print(f"  R²:   {r2:.3f}")

        if crop_te is not None:
            print("\n  Per-crop RMSE (t/ha):")
            y_te_arr = np.array(y_te)
            for crop in sorted(crop_te.unique()):
                mask = (crop_te == crop).values
                n = int(mask.sum())
                if n < 2:
                    print(f"    {crop:<20} — insufficient test samples (n={n})")
                    continue
                crop_rmse = float(np.sqrt(mean_squared_error(y_te_arr[mask], y_pred[mask])))
                print(f"    {crop:<20} RMSE={crop_rmse:.3f} t/ha  (n={n})")
        print("="*62)

        logger.info("Regressor [%s] test RMSE=%.3f t/ha  MAE=%.3f  R²=%.3f",
                    self._backend, rmse, mae, r2)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self._model.predict(X[self.feature_columns].astype(float))  # type: ignore[union-attr]

    def save(self, path: Path) -> None:
        path = Path(path)
        if self._backend == "xgboost":
            self._model.save_model(str(path))  # type: ignore[union-attr]
        else:
            pkl_path = path.with_suffix(".pkl")
            with open(pkl_path, "wb") as fh:
                pickle.dump(self._model, fh)

        meta = {
            "feature_columns": self.feature_columns,
            "backend": self._backend,
        }
        _meta_path(path).write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        logger.info("Saved regressor [%s] → %s", self._backend, path)

    def load(self, path: Path) -> None:
        path = Path(path)
        meta = json.loads(_meta_path(path).read_text())
        self.feature_columns = meta["feature_columns"]
        self._backend = meta.get("backend", "xgboost")

        if self._backend == "xgboost":
            self._model = _make_model()
            self._model.load_model(str(path))  # type: ignore[union-attr]
        else:
            pkl_path = path.with_suffix(".pkl")
            with open(pkl_path, "rb") as fh:
                self._model = pickle.load(fh)

        logger.info("Loaded regressor [%s] from %s", self._backend, path)
