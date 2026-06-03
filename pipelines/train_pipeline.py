# pipelines/train_pipeline.py

import logging
from datetime import datetime
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_squared_error

from core.validator import validate, _remove_faulty_rows, check_data_quality

from core.data import load_and_merge, prepare
from core.model import train_grid, evaluate, save_model, XGB_BASE
from core.plots import plot_time_vs_power, plot_gii_vs_power

log = logging.getLogger(__name__)


def run(
    itc_inv:       str,
    inv_filepaths: List,
    wms_filepaths: List,
    remove_faults: bool = True,
    remove_low_days: bool = True,
    remove_oscillations: bool = False,
    use_optuna: bool = False,
    optuna_trials: int = 20,
    promoted_params: dict = None,
) -> dict:
    """
    Full training pipeline.

    Steps:
        1. Load and merge inverter + WMS files
        2. Validate merged DataFrame
        3. Prepare data (filter, time features, window, blocked split)
        4. Train XGBoost (grid search, Optuna, or use promoted params)
        5. Evaluate on val and test
        6. Save model + metadata
        7. Generate both plots on test period
        8. Return results dict for app display
    """
    start = datetime.now()
    log.info("=" * 60)
    log.info(f"Train pipeline - {itc_inv}")
    log.info("=" * 60)

    # -- Step 1: Load and merge --------------------------------------------
    log.info("Step 1: Loading and merging files")
    try:
        raw_df, merge_warnings = load_and_merge(inv_filepaths, wms_filepaths, itc_inv, fill_gaps=False,)
    except Exception as e:
        return {
            "passed":    False,
            "errors":    [str(e)],
            "warnings":  [],
            "date_swap": None,
        }

    # -- Step 2: Validate --------------------------------------------------
    log.info("Step 2: Validating merged data")
    val_result = validate(raw_df)

    if not val_result["passed"]:
        log.error(f"Validation failed: {val_result['errors']}")
        return {
            "passed":    False,
            "errors":    val_result["errors"],
            "warnings":  merge_warnings + val_result["warnings"],
            "date_swap": val_result["date_swap"],
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



    # -- Step 3: Prepare --------------------------------------------------─
    log.info("Step 3: Preparing data")
    try:
        train_df, val_df, test_df, feature_cols = prepare(df)
    except ValueError as e:
        return {
            "passed":    False,
            "errors":    [str(e)],
            "warnings":  merge_warnings + val_result["warnings"], 
            "date_swap": val_result["date_swap"],
        }

    log.info(
        f"Split - train: {len(train_df)} | "
        f"val: {len(val_df)} | "
        f"test: {len(test_df)} | "
        f"features: {len(feature_cols)}"
    )

    X_train = train_df[feature_cols].values
    y_train = train_df["active_power_kw"].values
    X_val   = val_df[feature_cols].values
    y_val   = val_df["active_power_kw"].values
    X_test  = test_df[feature_cols].values
    y_test  = test_df["active_power_kw"].values

    # -- Step 4: Train ------------------------------------------------
    log.info("Step 4: Training")
    
    if promoted_params:
        # Use promoted params directly (no tuning)
        log.info(f"Using promoted params: {promoted_params.get('label', 'N/A')}")
        best_params = promoted_params.get("hyperparams", {})
        model = xgb.XGBRegressor(**XGB_BASE, **best_params, early_stopping_rounds=30)
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    
    elif use_optuna:
        # Optuna hyperparameter optimization
        log.info(f"Optuna tuning ({optuna_trials} trials)")
        import optuna
        from optuna.pruners import MedianPruner
        
        def objective(trial):
            params = {
                "max_depth": trial.suggest_int("max_depth", 4, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                "min_child_weight": trial.suggest_int("min_child_weight", 50, 300),
                "subsample": trial.suggest_float("subsample", 0.7, 0.95),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.7, 0.95),
                "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 5.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 10.0),
            }
            
            m = xgb.XGBRegressor(**XGB_BASE, **params, early_stopping_rounds=30)
            m.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            
            y_pred = m.predict(X_val)
            rmse = float(np.sqrt(mean_squared_error(y_val, y_pred)))
            log.info(f"  Trial RMSE: {rmse:.2f}")
            return rmse
        
        study = optuna.create_study(
            direction="minimize",
            pruner=MedianPruner(),
        )
        study.optimize(objective, n_trials=optuna_trials, show_progress_bar=True)
        
        best_params = study.best_params
        log.info(f"Optuna best RMSE: {study.best_value:.2f}")
        log.info(f"Best params: {best_params}")
        
        model = xgb.XGBRegressor(**XGB_BASE, **best_params, early_stopping_rounds=30)
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    
    else:
        # Grid search (default)
        log.info("Grid search tuning")
        model, best_params = train_grid(X_train, y_train, X_val, y_val)

    # -- Step 5: Evaluate --------------------------------------------------
    log.info("Step 5: Evaluating")
    y_pred_val  = model.predict(X_val)
    y_pred_test = model.predict(X_test)
    val_metrics  = evaluate(y_val,  y_pred_val)
    test_metrics = evaluate(y_test, y_pred_test)

    log.info(
        f"Val  -> MAE={val_metrics['mae']:.2f} "
        f"RMSE={val_metrics['rmse']:.2f} "
        f"R²={val_metrics['r2']:.4f}"
    )
    log.info(
        f"Test -> MAE={test_metrics['mae']:.2f} "
        f"RMSE={test_metrics['rmse']:.2f} "
        f"R²={test_metrics['r2']:.4f}"
    )

    # -- Step 6: Save model ------------------------------------------------
    log.info("Step 6: Saving model")
    save_model(
        model         = model,
        feature_cols  = feature_cols,
        itc_inv       = itc_inv,
        val_metrics   = val_metrics,
        test_metrics  = test_metrics,
        best_params   = best_params,
        y_test        = y_test,
        y_pred_test   = y_pred_test,
        previous_rmse = None,
    )

    # -- Step 7: Plots ----------------------------------------------------─
    log.info("Step 7: Generating plots")
    plot_time = None
    plot_gii  = None
    try:
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
    except Exception as e:
        log.warning(f"Plot generation failed: {e}. Model was saved successfully.")

    duration = (datetime.now() - start).total_seconds()
    log.info(f"Train pipeline complete in {duration:.1f}s")

    return {
        "passed":       True,
        "errors":       [],
        "warnings":     merge_warnings + val_result["warnings"],
        "date_swap":    val_result["date_swap"],
        "val_metrics":  val_metrics,
        "test_metrics": test_metrics,
        "plot_time":    plot_time,
        "plot_gii":     plot_gii,
        "train_rows":   len(train_df),
        "val_rows":     len(val_df),
        "test_rows":    len(test_df),
        "n_features":   len(feature_cols),
        "duration_sec": round(duration, 1),
    }
