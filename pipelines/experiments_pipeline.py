# pipelines/experiments_pipeline.py

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from sklearn.metrics import mean_squared_error

from config.settings import ITC_INV_LIST, OUTPUTS_DIR, GRID_PARAMS, XGB_BASE
from core.validator import validate, _remove_faulty_rows, check_data_quality
from core.data import load_and_merge, prepare
from core.plots import plot_time_vs_power, plot_gii_vs_power
from experiments.registry import get_registry
from experiments.tracker import ExperimentTracker
from experiments.selection import (
    select_best_model,
    compare_models,
    check_overfitting,
    recommend_hyperparams,
)

log = logging.getLogger(__name__)


# -- Grid Search Params ---------------------------------------------------------

# -- Grid Search Params ---------------------------------------------------------

# XGB_GRID_SMALL = {
#     "n_estimators":      [300, 600],
#     "max_depth":         [4, 6],
#     "learning_rate":     [0.05, 0.1],
#     "subsample":         [0.8],
#     "colsample_bytree":  [0.8],
#     "min_child_samples": [10],
#     "reg_alpha":         [0.0],
#     "reg_lambda":        [1.0],
# }

# XGB_GRID_MEDIUM = {
#     "n_estimators":      [300, 600],
#     "max_depth":         [4, 6, 8],
#     "learning_rate":     [0.05, 0.1],
#     "subsample":         [0.8, 1.0],
#     "colsample_bytree":  [0.8],
#     "min_child_samples": [10, 30],
#     "reg_alpha":         [0.0, 0.1],
#     "min_child_weight":  [1, 5],
#     "reg_lambda":        [1.0, 5.0],
# }

# XGB_GRID_LARGE = {
#     "n_estimators":      [300, 600, 900],
#     "max_depth":         [4, 6, 8],
#     "learning_rate":     [0.01, 0.05, 0.1],
#     "subsample":         [0.8, 1.0],
#     "colsample_bytree":  [0.8, 1.0],
#     "min_child_samples": [10, 30],
#     "reg_alpha":         [0.0, 0.1],
#     "reg_lambda":        [1.0, 5.0],
# }

# LGBM_GRID_SMALL = {
#     "num_leaves":        [31, 63],
#     "max_depth":         [4, 6],
#     "learning_rate":     [0.05, 0.1],
#     "subsample":         [0.8],
#     "colsample_bytree":  [0.8],
#     "reg_alpha":         [0.0],
#     "reg_lambda":        [1.0],
# }

# LGBM_GRID_MEDIUM = {
#     "num_leaves":        [31, 63, 127],
#     "max_depth":         [4, 6, 8],
#     "learning_rate":     [0.05, 0.1],
#     "subsample":         [0.8, 1.0],
#     "colsample_bytree":  [0.8, 1.0],
#     "reg_alpha":         [0.0, 0.1],
#     "reg_lambda":        [1.0],
# }

# LGBM_GRID_LARGE = {
#     "num_leaves":        [31, 63, 127, 255],
#     "max_depth":         [4, 6, 8, 10],
#     "learning_rate":     [0.01, 0.05, 0.1],
#     "subsample":         [0.8, 1.0],
#     "colsample_bytree":  [0.8, 1.0],
#     "reg_alpha":         [0.0, 0.1],
#     "reg_lambda":        [1.0, 5.0],
# }
# -- XGBoost Grids -------------------------------------------------------------

# For Testing/Pipeline Validation (Fast, proves it runs without memorizing)
XGB_GRID_SMALL = {
    "n_estimators":      [150],
    "max_depth":         [3, 4],
    "learning_rate":     [0.1],
    "subsample":         [0.8],
    "colsample_bytree":  [0.8],
    "min_child_weight":  [50],   # ~50 mins of data minimum per leaf
    "reg_alpha":         [0.1],
    "reg_lambda":        [1.0],
}

# For 6 - 12 Months Data (~130k - 260k rows)
XGB_GRID_MEDIUM = {
    "n_estimators":      [200, 400],
    "max_depth":         [4, 5],            # Hard cap at 5
    "learning_rate":     [0.05, 0.1],
    "subsample":         [0.7, 0.8],        # Lowered to 0.7 to force variance
    "colsample_bytree":  [0.7, 0.8],
    "min_child_weight":  [50, 150],         # Forces generalisation across 1-2.5 hours
    "gamma":             [0.1, 1.0],        # New: Requires a loss reduction to split
    "reg_alpha":         [0.1, 1.0],
    "reg_lambda":        [1.0, 5.0],
}

# For 12+ Months Data (260k+ rows)
XGB_GRID_LARGE = {
    "n_estimators":      [300, 500, 800],
    "max_depth":         [4, 5, 6],         # 6 is the absolute maximum
    "learning_rate":     [0.01, 0.05],
    "subsample":         [0.7, 0.85],
    "colsample_bytree":  [0.7, 0.85],
    "min_child_weight":  [150, 300],        # Requires 2.5 to 5 hours of data per leaf
    "gamma":             [0.5, 2.0],        # Aggressive pruning for large datasets
    "reg_alpha":         [1.0, 5.0],
    "reg_lambda":        [5.0, 10.0],
}


# -- LightGBM Grids ------------------------------------------------------------

# For Testing/Pipeline Validation
LGBM_GRID_SMALL = {
    "num_leaves":        [15, 31],
    "max_depth":         [3, 4],
    "learning_rate":     [0.1],
    "subsample":         [0.8],
    "colsample_bytree":  [0.8],
    "min_child_samples": [100],             # ~100 rows/minutes per leaf
    "reg_alpha":         [0.1],
    "reg_lambda":        [1.0],
}

# For 6 - 12 Months Data
LGBM_GRID_MEDIUM = {
    "num_leaves":        [15, 31, 45],      # Kept < 2^max_depth to prevent complex trees
    "max_depth":         [4, 5],
    "learning_rate":     [0.05, 0.1],
    "subsample":         [0.7, 0.8],
    "colsample_bytree":  [0.7, 0.8],
    "min_child_samples": [100, 300],        # 1.5 to 5 hours of data
    "min_split_gain":    [0.1, 1.0],        # LGBM equivalent of XGB's gamma
    "reg_alpha":         [0.1, 1.0],
    "reg_lambda":        [1.0, 5.0],
}

# For 12+ Months Data
LGBM_GRID_LARGE = {
    "num_leaves":        [31, 45, 63],
    "max_depth":         [4, 5, 6],
    "learning_rate":     [0.01, 0.05],
    "subsample":         [0.7, 0.85],
    "colsample_bytree":  [0.7, 0.85],
    "min_child_samples": [200, 500],        # Extremely strict sample requirements
    "min_split_gain":    [0.5, 2.0],
    "reg_alpha":         [1.0, 5.0],
    "reg_lambda":        [5.0, 10.0],
}

GRID_MAP = {
    "xgboost": {"Small": XGB_GRID_SMALL, "Medium": XGB_GRID_MEDIUM, "Large": XGB_GRID_LARGE},
    "lgbm":    {"Small": LGBM_GRID_SMALL, "Medium": LGBM_GRID_MEDIUM, "Large": LGBM_GRID_LARGE},
}


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict:
    """Compute standard regression metrics."""
    from sklearn.metrics import mean_absolute_error, r2_score
    
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def grid_search_xgb(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    tracker: ExperimentTracker,
    early_stopping_rounds: int = 30,
    verbose: bool = False,
    xgb_grid = None
) -> Tuple[xgb.XGBRegressor, Dict, Dict]:
    """
    Grid search for XGBoost hyperparameters.
    
    Returns:
        Tuple of (best_model, best_params, best_metrics)
    """
    from itertools import product
    if xgb_grid is None:
        xgb_grid = XGB_GRID_MEDIUM
    keys = list(xgb_grid.keys())
    combos = list(product(*[xgb_grid[k] for k in keys]))
    log.info(f"XGBoost grid search: {len(combos)} combinations")
    
    best_rmse = np.inf
    best_params = None
    best_model = None
    best_val_metrics = None
    
    for i, vals in enumerate(combos):
        params = {**XGB_BASE, **dict(zip(keys, vals))}
        model = xgb.XGBRegressor(**params, early_stopping_rounds=early_stopping_rounds, verbose=False)
        
        try:
            model.fit(
                x_train, y_train,
                eval_set=[(x_val, y_val)],
                verbose=False,
            )
            y_val_pred = model.predict(x_val)
            val_rmse = float(np.sqrt(mean_squared_error(y_val, y_val_pred)))
            
            if val_rmse < best_rmse:
                best_rmse = val_rmse
                best_params = params
                best_model = model
                best_val_metrics = compute_metrics(y_val, y_val_pred)
                
                if verbose:
                    log.info(f"  [{i+1:>3}/{len(combos)}] * RMSE={val_rmse:.2f}")
            
            # Track grid search
            tracker.log_grid_search(params, compute_metrics(y_val, y_val_pred), best_rmse == val_rmse)
            
        except Exception as e:
            log.warning(f"  [{i+1}] Failed: {e}")
            continue
    
    log.info(f"XGBoost grid search complete. Best RMSE: {best_rmse:.2f}")
    return best_model, best_params, best_val_metrics


def grid_search_lgbm(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    tracker: ExperimentTracker,
    early_stopping_rounds: int = 30,
    verbose: bool = False,
    lgbm_grid = None,
) -> Tuple[lgb.LGBMRegressor, Dict, Dict]:
    """
    Grid search for LightGBM hyperparameters.
    
    Returns:
        Tuple of (best_model, best_params, best_metrics)
    """
    from itertools import product

    if lgbm_grid is None:
        lgbm_grid = LGBM_GRID_MEDIUM
    keys = list(lgbm_grid.keys())
    combos = list(product(*[lgbm_grid[k] for k in keys]))
    log.info(f"LightGBM grid search: {len(combos)} combinations")
    
    best_rmse = np.inf
    best_params = None
    best_model = None
    best_val_metrics = None
    
    for i, vals in enumerate(combos):
        params = dict(zip(keys, vals))
        model = lgb.LGBMRegressor(**params, n_estimators=1000, early_stopping_rounds=early_stopping_rounds, verbose=-1)
        
        try:
            model.fit(
                x_train, y_train,
                eval_set=[(x_val, y_val)],
            )
            y_val_pred = model.predict(x_val)
            val_rmse = float(np.sqrt(mean_squared_error(y_val, y_val_pred)))
            
            if val_rmse < best_rmse:
                best_rmse = val_rmse
                best_params = params
                best_model = model
                best_val_metrics = compute_metrics(y_val, y_val_pred)
                
                if verbose:
                    log.info(f"  [{i+1:>3}/{len(combos)}] * RMSE={val_rmse:.2f}")
            
            # Track grid search
            tracker.log_grid_search(params, compute_metrics(y_val, y_val_pred), best_rmse == val_rmse)
            
        except Exception as e:
            log.warning(f"  [{i+1}] Failed: {e}")
            continue
    
    log.info(f"LightGBM grid search complete. Best RMSE: {best_rmse:.2f}")
    return best_model, best_params, best_val_metrics

def optuna_objective(trial, X_full, y_full):
    params = {
        "max_depth":        trial.suggest_int("max_depth", 4, 6),
        "learning_rate":    trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "min_child_weight": trial.suggest_int("min_child_weight", 50, 300),
        "gamma":            trial.suggest_float("gamma", 0.1, 2.0),
        "reg_alpha":        trial.suggest_float("reg_alpha", 0.1, 5.0),
        "reg_lambda":       trial.suggest_float("reg_lambda", 1.0, 10.0),
    }
    # each trial evaluated on walk-forward, not single val
    wf = walk_forward_validate_with_params(params, X_full, y_full, n_folds=3)
    return wf["mean_rmse"]



def walk_forward_validate(
    model,
    X: np.ndarray,
    y: np.ndarray,
    n_folds: int = 5,
    window_size: int = None,
    step: int = 1,
    tracker: ExperimentTracker = None,
) -> Dict:
    """
    Walk-forward validation with rolling window (expanding window variant).
    
    Args:
        model: Trained model instance
        X: Feature matrix
        y: Target array
        n_folds: Number of validation folds
        window_size: Size of training window (None for expanding)
        step: Step size between folds
        tracker: Experiment tracker for logging
    
    Returns:
        Dictionary with fold metrics and overall metrics
    """
    n_samples = len(X)
    fold_size = n_samples // n_folds
    
    all_preds = []
    all_actual = []
    fold_metrics_list = []
    
    for fold in range(n_folds):
        # Training window (expanding): 0 to (fold * fold_size)
        train_end = (fold + 1) * fold_size
        if window_size:
            train_start = max(0, train_end - window_size)
        else:
            train_start = 0
        
        x_train_fold = X[train_start:train_end]
        y_train_fold = y[train_start:train_end]
        
        # Validation window: train_end to (fold + 1) * fold_size
        val_start = train_end
        val_end = min(val_start + fold_size, n_samples)
        if val_end <= val_start:
            continue
        
        x_val_fold = X[val_start:val_end]
        y_val_fold = y[val_start:val_end]
        
        # Train on fold
        try:
            model.fit(x_train_fold, y_train_fold)
            y_pred = model.predict(x_val_fold)
            
            # Record fold metrics
            fold_metrics = compute_metrics(y_val_fold, y_pred)
            fold_metrics_list.append(fold_metrics)
            
            # Track
            if tracker:
                tracker.record_fold(fold, fold_metrics)
            
            all_preds.extend(y_pred)
            all_actual.extend(y_val_fold)
            
        except Exception as e:
            log.warning(f"Fold {fold} failed: {e}")
            continue
    
    if not all_preds:
        return {"error": "All folds failed"}
    
    # Overall metrics
    overall_metrics = compute_metrics(np.array(all_actual), np.array(all_preds))
    
    # Fold statistics
    fold_ratios = [m["rmse"] for m in fold_metrics_list]
    overall_metrics["fold_std"] = float(np.std(fold_ratios))
    overall_metrics["fold_min"] = float(np.min(fold_ratios))
    overall_metrics["fold_max"] = float(np.max(fold_ratios))
    
    return {
        "overall_metrics": overall_metrics,
        "fold_metrics": fold_metrics_list,
        "n_folds": len(fold_metrics_list),
    }


# -- Main Pipeline --------------------------------------------------------------


def run_experiment(
    itc_inv: str,
    inv_filepaths: List[Path],
    wms_filepaths: List[Path],
    model_type: str = "xgboost",  # "xgboost" or "lgbm"
    split_strategy: str = "blocked",
    walk_forward: bool = True,
    n_walk_folds: int = 5,
    remove_faults: bool = False,
    remove_low_days: bool = True,
    remove_oscillations: bool = False,
    xgb_grid_size: str = "Medium",
    lgbm_grid_size: str = "Medium",
) -> Dict:
    """
    Run a full experiment pipeline for a single inverter.
    
    Steps:
        1. Load and merge files
        2. Validate data
        3. Prepare data (split, filter, features)
        4. Grid search for best hyperparameters
        5. Walk-forward validation (optional)
        6. Save best model with metadata
        7. Generate plots
    
    Returns:
        Dictionary with experiment results
    """
    start_time = datetime.now()
    log.info("=" * 60)
    log.info(f"Experiment Pipeline - {itc_inv} | Model: {model_type}")
    log.info("=" * 60)
    
    # Setup registry and tracker
    experiment_tag = f"{model_type}_grid_{split_strategy}"
    registry = get_registry(itc_inv)
    tracker = ExperimentTracker(itc_inv, experiment_tag)
    
    # -- Step 1: Load and merge --------------------------------------------
    log.info("Step 1: Loading and merging files")
    try:
        raw_df, merge_warnings = load_and_merge(inv_filepaths, wms_filepaths, itc_inv, fill_gaps=False)
    except Exception as e:
        return {
            "passed": False,
            "errors": [str(e)],
            "warnings": [],
            "duration_sec": (datetime.now() - start_time).total_seconds(),
        }
    
    # -- Step 2: Validate --------------------------------------------------
    log.info("Step 2: Validating merged data")
    val_result = validate(raw_df)
    
    if not val_result["passed"]:
        log.error(f"Validation failed: {val_result['errors']}")
        return {
            "passed": False,
            "errors": val_result["errors"],
            "warnings": merge_warnings + val_result["warnings"],
            "duration_sec": (datetime.now() - start_time).total_seconds(),
        }
    
    df = val_result["df"]
    log.info(f"Validation passed. Warnings: {val_result['warnings']}")
    
    # -- Step 2b: Data quality check --------------------------------------
    log.info("Step 2b: Checking data quality")
    quality = check_data_quality(df)

    if not quality["passed"]:
        if not remove_faults:
            log.warning(f"Data quality issues found: {quality['message']}")
            return {
                "passed":         False,
                "errors":         [],
                "warnings":       merge_warnings + val_result["warnings"],
                "date_swap":      val_result["date_swap"],
                "quality_report": quality,
                "blocked":        True,
            }
        else:
            log.info("Removing faulty rows and proceeding with training.")
            df = _remove_faulty_rows(df, remove_low_days=remove_low_days, remove_oscillations = remove_oscillations)
            log.info(f"Rows after fault removal: {len(df)}")
    
    # -- Step 3: Prepare ---------------------------------------------------
    log.info("Step 3: Preparing data")
    try:
        train_df, val_df, test_df, feature_cols = prepare(df)
    except Exception as e:
        return {
            "passed": False,
            "errors": [str(e)],
            "warnings": [],
            "duration_sec": (datetime.now() - start_time).total_seconds(),
        }
    
    log.info(f"Train: {len(train_df)} rows, Val: {len(val_df)} rows, Test: {len(test_df)} rows")
    
    # Extract X and y
    X_train = train_df[feature_cols].values
    y_train = train_df["active_power_kw"].values
    X_val = val_df[feature_cols].values
    y_val = val_df["active_power_kw"].values
    X_test = test_df[feature_cols].values
    y_test = test_df["active_power_kw"].values
    
    # -- Step 4: Grid search -----------------------------------------------
    log.info(f"Step 4: Grid search for {model_type.upper()}")
    
    if model_type.lower() == "xgboost":
        selected_xgb_grid=  GRID_MAP.get(model_type.lower(), {}).get(xgb_grid_size, XGB_GRID_MEDIUM)
        best_model, best_params, best_val_metrics = grid_search_xgb(
            X_train, y_train, X_val, y_val, tracker,
            xgb_grid=selected_xgb_grid,
            early_stopping_rounds= 30,
            verbose=True,
        )
    elif model_type.lower() == "lgbm":
        selected_lgbm_grid =  GRID_MAP.get(model_type.lower(), {}).get(lgbm_grid_size, LGBM_GRID_MEDIUM)
        best_model, best_params, best_val_metrics = grid_search_lgbm(
            X_train, y_train, X_val, y_val, tracker,
            early_stopping_rounds= 30,
            lgbm_grid = selected_lgbm_grid,
            verbose=True,
        )
    else:
        return {
            "passed": False,
            "errors": [f"Unknown model type: {model_type}"],
            "duration_sec": (datetime.now() - start_time).total_seconds(),
        }
    
    if best_model is None:
        return {
            "passed": False,
            "errors": ["Grid search failed to find a valid model"],
            "duration_sec": (datetime.now() - start_time).total_seconds(),
        }
    
    # -- Step 4b: Train final model on combined data -----------------------
    log.info("Step 4b: Training final model on combined train+val data")
    try:
        X_combined = np.vstack([X_train, X_val])
        y_combined = np.append(y_train, y_val)
        best_model.set_params(early_stopping_rounds=None)
        best_model.fit(X_combined, y_combined)
    except Exception as e:
        log.warning(f"Final model training failed: {e}")
        # Use the grid search best model instead
    
    # -- Step 5: Walk-forward validation -----------------------------------
    if walk_forward:
        log.info(f"Step 5: Walk-forward validation ({n_walk_folds} folds)")
        X_full = np.vstack([X_train, X_val, X_test])
        y_full = np.append(np.append(y_train, y_val), y_test)
        wf_result = walk_forward_validate(
            best_model, X_full, y_full,
            n_folds=n_walk_folds, tracker=tracker,
        )
        if wf_result.get("overall_metrics"):
            log.info(f"Walk-forward RMSE: {wf_result['overall_metrics']['rmse']:.2f} kW")
        else: 
            log.warning("walk-forward validation failed.")
    
    # -- Step 6: Evaluate on test set -------------------------------------
    log.info("Step 6: Evaluating on test set")
    y_pred_test = best_model.predict(X_test)
    test_metrics = compute_metrics(y_test, y_pred_test)
    
    log.info(f"Test RMSE: {test_metrics['rmse']:.2f} kW")
    log.info(f"Test R²: {test_metrics['r2']:.3f}")
    
    # -- Step 7: Train-test split check (overfitting) ----------------------
    train_pred = best_model.predict(X_train)
    train_metrics = compute_metrics(y_train, train_pred)
    
    is_overfitting, overfit_issues = check_overfitting(train_metrics, best_val_metrics, test_metrics)
    if is_overfitting:
        log.warning(f"Potential overfitting detected:")
        for issue in overfit_issues:
            log.warning(f"  - {issue}")
    
    # -- Step 8: Generate plots -------------------------------------------
    log.info("Step 8: Generating plots")
    
    # Plot predictions vs actual
    prediction_plot = tracker.plot_predictions(y_test, y_pred_test, show=True)
    
    # Plot residuals
    residual_plot = tracker.plot_residuals(y_test, y_pred_test, show=True)
    test_df = test_df.copy()
    test_df["predicted_power"] = y_pred_test
    plot_time = plot_time_vs_power(
        df      = test_df,
        itc_inv = itc_inv,
        title   = (
            f"{itc_inv} -- Test Period | "
            f"RMSE={test_metrics['rmse']:.1f} kW"
        ),
    )
    plot_gii = plot_gii_vs_power(
        df      = test_df,
        itc_inv = itc_inv,
        title   = f"{itc_inv} -- GII vs Power | Test Period",
    )
    
    # Plot training history (if available)
    if hasattr(best_model, "eval_set") and best_model.evals_result_:
        history_plot = tracker.plot_training_history(best_model.evals_result_, show=False)
    
    # Plot grid search results
    grid_plot = tracker.plot_grid_search_results(top_n=20, show=False)
    
    # -- Step 9: Save model -----------------------------------------------
    log.info("Step 9: Saving model")
    
    model_path = registry.save_model(
        experiment_tag=experiment_tag,
        model=best_model,
        feature_cols=feature_cols,
        metadata={
            "itc_inv": itc_inv,
            "model_type": model_type,
            "split": split_strategy,
            "hyperparams": best_params,
            "train_metrics": train_metrics,
            "val_metrics": best_val_metrics,
            "test_metrics": test_metrics,
            "feature_cols": feature_cols,
            "n_train": len(X_train),
            "n_val": len(X_val),
            "n_test": len(X_test),
            "is_overfitting": is_overfitting,
            "overfit_issues": overfit_issues,
            "grid_search_size": len(tracker._params_history),
        },
    )
    
    # -- Step 10: Save summary --------------------------------------------
    summary_path = tracker.save_summary()
    summary = tracker.get_summary()
    
    # -- Finalize -----------------------------------------------------------
    duration = (datetime.now() - start_time).total_seconds()
    
    log.info("=" * 60)
    log.info(f"Experiment complete in {duration:.1f} seconds")
    log.info(f"Best model saved to: {model_path}")
    log.info("=" * 60)
    
    return {
        "passed": True,
        "model_path": str(model_path),
        "experiment_tag": experiment_tag,
        "summary": summary,
        "train_metrics": train_metrics,
        "val_metrics": best_val_metrics,
        "test_metrics": test_metrics,
        "best_params": best_params,
        "grid_search_size": len(tracker._params_history),
        "overfitting_issues": overfit_issues,
        "duration_sec": duration,
        "plots": {
            "predictions": str(prediction_plot) if prediction_plot else None,
            "residuals": str(residual_plot) if residual_plot else None,
            "TIME VS POWER": str(plot_time) if plot_time else None,
            "GII VS POWER": str(plot_gii) if plot_gii else None,
        },
    }


# # -- Batch experiment runner ----------------------------------------------------


# def run_batch_experiments(
#     itc_inv_list: List[str] = None,
#     inv_filepaths: List[Path] = None,
#     wms_filepaths: List[Path] = None,
#     model_types: List[str] = ["xgboost"],
#     split_strategies: List[str] = ["blocked"],
#     n_walk_folds: int = 5,
#     remove_faults: bool = False,
#     remove_low_days: bool = True,
#     remove_oscillations: bool = False,

# ) -> Dict:
#     """
#     Run experiments for multiple inverters and model types.
    
#     Returns:
#         Dictionary with results for each inverter
#     """
#     if itc_inv_list is None:
#         itc_inv_list = ITC_INV_LIST
    
#     results = {}
    
#     for itc_inv in itc_inv_list:
#         log.info(f"\n{'='*60}")
#         log.info(f"INVERTER: {itc_inv}")
#         log.info(f"{'='*60}")
        
#         ExperimentResults = {}
        
#         for model_type in model_types:
#             for split in split_strategies:
#                 experiment_tag = f"{model_type}_{split}"
                
#                 try:
#                     result = run_experiment(
#                         itc_inv=itc_inv,
#                         inv_filepaths=inv_filepaths or [],
#                         wms_filepaths=wms_filepaths or [],
#                         model_type=model_type,
#                         split_strategy=split,
#                         walk_forward=True,
#                         n_walk_folds=n_walk_folds,
#                         remove_faults=False,
#                         remove_low_days=True,
#                         remove_oscillations=False,
#                     )
#                     ExperimentResults[experiment_tag] = result
                    
#                 except Exception as e:
#                     log.error(f"  {itc_inv} - {experiment_tag} crashed: {e}")
#                     ExperimentResults[experiment_tag] = {
#                         "passed": False,
#                         "errors": [str(e)],
#                         "traceback": str(e),
#                     }
        
#         results[itc_inv] = ExperimentResults
    
#     return results
