# core/model.py

import json
import logging
from datetime import datetime
from itertools import product
from pathlib import Path

import joblib
import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from config.settings import (
    XGB_BASE, GRID_PARAMS, RANDOM_SEED,
    OUTPUTS_DIR, 
)

log = logging.getLogger(__name__)


# -- Metrics ------------------------------------------------------------------─

def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    d = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    return float(np.mean(np.where(d == 0, 0, np.abs(y_true - y_pred) / d)) * 100)


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "mae":   float(mean_absolute_error(y_true, y_pred)),
        "rmse":  float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2":    float(r2_score(y_true, y_pred)),
        "smape": smape(y_true, y_pred),
    }


# -- Training ------------------------------------------------------------------

def train_grid(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val:   np.ndarray, y_val:   np.ndarray,
) -> tuple[xgb.XGBRegressor, dict]:
    """
    Grid search over GRID_PARAMS.
    Selects best params by val RMSE.
    Returns fitted model and best params.
    """
    # ---------check for promoted params----------
    active_params_path = OUTPUTS_DIR/"promoted_params"/"active_params.json"
    if active_params_path.exists():
        with open(active_params_path) as f:
            active = json.load(f)
        promoted = active.get("params", {})
        if promoted:
            log.info(
                f"Using promoted params: label= '{active.get('label')}'"
                f" from {active.get('promoted_from')}"
                f" on {active.get('promoted_at', '')[:10]}"
            )
            params = {**XGB_BASE, **promoted}
            model = xgb.XGBRegressor(**params, early_stopping_rounds =30)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
            return model, params
    keys   = list(GRID_PARAMS.keys())
    combos = list(product(*[GRID_PARAMS[k] for k in keys]))
    log.info(f"Grid search: {len(combos)} combinations")

    best_rmse   = np.inf
    best_params = None
    best_model  = None

    for i, vals in enumerate(combos):
        params = {**XGB_BASE, **dict(zip(keys, vals))}
        model  = xgb.XGBRegressor(**params, early_stopping_rounds=30)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        rmse = float(np.sqrt(mean_squared_error(y_val, model.predict(X_val))))

        if rmse < best_rmse:
            best_rmse   = rmse
            best_params = params
            best_model  = model
            log.info(f"  [{i+1:>3}/{len(combos)}] * RMSE={rmse:.2f}")

    log.info(f"Grid search complete. Best val RMSE: {best_rmse:.2f}")
    return best_model, best_params


# -- Save ----------------------------------------------------------------------

def save_model(
    model:        xgb.XGBRegressor,
    feature_cols: list[str],
    itc_inv:      str,
    val_metrics:  dict,
    test_metrics: dict,
    best_params:  dict,
    y_test,
    y_pred_test,
    previous_rmse: float | None = None,
    previous_val_rmse : float| None = None
) -> Path:
    """
    Saves model.joblib and metadata.json to outputs/ITC_INV/.
    Returns path to saved model.
    """
    out_dir = OUTPUTS_DIR / itc_inv
    out_dir.mkdir(parents=True, exist_ok=True)

    # model
    model_path = out_dir / "model.joblib"
    joblib.dump({
        "model":        model,
        "feature_cols": feature_cols,
        "itc_inv":      itc_inv,
        "saved_at":     datetime.now().isoformat(),
    }, model_path)

    # Residual Percentiles
    test_residuals = y_test - y_pred_test
    residual_percentiles = {
        "p5":  float(np.percentile(test_residuals, 5)),
        "p1":  float(np.percentile(test_residuals, 1)),
        "p50": float(np.percentile(test_residuals, 50)),
    }

    # metadata
    metadata = {
        "itc_inv":        itc_inv,
        "model_type":     "xgboost",
        "split":          "blocked",
        "tuning":         "grid",
        "saved_at":       datetime.now().isoformat(),
        "best_params":    best_params,
        "val_metrics":    val_metrics,
        "test_metrics":   test_metrics,
        "feature_cols":   feature_cols,
        "previous_rmse":  previous_rmse,
        "previous_val_rmse": previous_val_rmse,
        "residual_percentiles" : residual_percentiles,
        "retrain_history": _load_retrain_history(out_dir) + [{
            "date":      datetime.now().isoformat(),
            "test_rmse": test_metrics["rmse"],
        }],
    }
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    log.info(f"Model saved -> {model_path}")
    return model_path


def _load_retrain_history(out_dir: Path) -> list:
    meta_path = out_dir / "metadata.json"
    if not meta_path.exists():
        return []
    with open(meta_path) as f:
        meta = json.load(f)
    return meta.get("retrain_history", [])


# -- Load ----------------------------------------------------------------------

def load_model(itc_inv: str) -> tuple[xgb.XGBRegressor, list[str], dict]:
    """
    Loads model and metadata for a given ITC-INV.
    Returns model, feature_cols, metadata.
    """
    out_dir    = OUTPUTS_DIR / itc_inv
    model_path = out_dir / "model.joblib"
    meta_path  = out_dir / "metadata.json"

    if not model_path.exists():
        raise FileNotFoundError(
            f"No trained model found for {itc_inv}. "
            f"Please train first using the Train tab."
        )

    payload      = joblib.load(model_path)
    model        = payload["model"]
    feature_cols = payload["feature_cols"]

    with open(meta_path) as f:
        metadata = json.load(f)

    return model, feature_cols, metadata


# -- Model status --------------------------------------------------------------

def model_status(itc_inv: str) -> dict:
    """
    Returns training status for a given ITC-INV.
    Used by the app dropdown to show trained/not trained.
    """
    
    meta_path = Path(OUTPUTS_DIR).resolve() / itc_inv / "metadata.json"

    if not meta_path.exists():
        return {
            "trained":       False,
            "last_trained":  None,
            "test_rmse":     None,
        }

    with open(meta_path) as f:
        meta = json.load(f)

    return {
        "trained":      True,
        "last_trained": meta.get("saved_at", "Unknown"),
        "test_rmse":    meta.get("test_metrics", {}).get("rmse", None),
    }