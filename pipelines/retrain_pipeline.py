# pipelines/retrain_pipeline.py

import logging
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from core.validator import validate, _remove_faulty_rows, check_data_quality
from core.data import load_and_merge, prepare
from core.model import train_grid, evaluate, save_model, load_model
from core.plots import plot_time_vs_power, plot_gii_vs_power

log = logging.getLogger(__name__)

RMSE_DEGRADATION_LIMIT = 1.5


def run(
    itc_inv:       str,
    inv_filepaths: List,
    wms_filepaths: List,
    remove_faults: bool = False,
    remove_low_days: bool = True,
    remove_oscillations: bool = False,
) -> dict:
    """
    Monthly retrain pipeline.

    Steps:
        1. Load and merge inverter + WMS files
        2. Validate merged DataFrame
        3. Load previous model to get previous RMSE
        4. Prepare data (filter, time features, window, blocked split)
        5. Retrain using same grid params
        6. Evaluate and compare against previous RMSE
        7. Save model only if new RMSE <= 1.5x previous RMSE
        8. Regenerate plots
        9. Return results dict for app display
    """
    start = datetime.now()
    log.info("=" * 60)
    log.info(f"Retrain pipeline - {itc_inv}")
    log.info("=" * 60)

    # -- Step 1: Load and merge --------------------------------------------
    log.info("Step 1: Loading and merging files")
    try:
        raw_df, merge_warnings = load_and_merge(inv_filepaths, wms_filepaths, itc_inv,fill_gaps=False,)
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


    # -- Step 2b: Data quality check ---------------------------------------
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
            log.info("Removing faulty rows and proceeding with retraining.")
            df = _remove_faulty_rows(df, remove_low_days=remove_low_days, remove_oscillations= remove_oscillations)
            log.info(f"Rows after fault removal: {len(df)}")

    # -- Step 3: Load previous model --------------------------------------─
    log.info("Step 3: Loading previous model")
    try:
        _, _, prev_metadata = load_model(itc_inv)
        previous_rmse       = prev_metadata["test_metrics"]["rmse"]
        previous_val_rmse = prev_metadata["val_metrics"]["rmse"]
        prev_feature_cols   = prev_metadata["feature_cols"]
        log.info(f"Previous test RMSE: {previous_rmse:.2f} kW")
    except FileNotFoundError:
        log.warning(f"No existing model found for {itc_inv} - treating as first train")
        previous_rmse     = None
        previous_val_rmse = None
        prev_feature_cols = None

    # -- Step 4: Prepare --------------------------------------------------─
    log.info("Step 4: Preparing data")
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

    # -- Feature set change detection --------------------------------------
    feature_warnings = []
    if prev_feature_cols is not None:
        old_features = set(prev_feature_cols)
        new_features = set(feature_cols)
        added        = new_features - old_features
        removed      = old_features - new_features
        if added:
            msg = f"New features added in retrain: {sorted(added)}"
            log.warning(msg)
            feature_warnings.append(msg)
        if removed:
            msg = f"Features removed in retrain: {sorted(removed)}"
            log.warning(msg)
            feature_warnings.append(msg)

    X_train = train_df[feature_cols].values
    y_train = train_df["active_power_kw"].values
    X_val   = val_df[feature_cols].values
    y_val   = val_df["active_power_kw"].values
    X_test  = test_df[feature_cols].values
    y_test  = test_df["active_power_kw"].values

    months_available = (
        df["timestamp"].max() - df["timestamp"].min()
    ).days / 30.0

    window_mode = (
        "Rolling 120-day window"
        if months_available >= 12
        else f"Expanding window ({months_available:.1f} months)"
    )
    log.info(f"Data window: {window_mode}")

    # -- Step 5: Retrain --------------------------------------------------─
    log.info("Step 5: Retraining - grid search")
    model, best_params = train_grid(X_train, y_train, X_val, y_val)

    # -- Step 6: Evaluate --------------------------------------------------
    log.info("Step 6: Evaluating")
    y_pred_val  = model.predict(X_val)
    y_pred_test = model.predict(X_test)
    val_metrics  = evaluate(y_val,  y_pred_val)
    test_metrics = evaluate(y_test, y_pred_test)
    new_rmse     = test_metrics["rmse"]
    new_val_rmse = val_metrics["rmse"]

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

    if previous_rmse is not None:
        rmse_change_pct = round(
            (new_rmse - previous_rmse) / previous_rmse * 100, 2
        )
        log.info(
            f"RMSE change: {rmse_change_pct:+.2f}% "
            f"vs previous {previous_rmse:.2f} kW"
        )
    else:
        rmse_change_pct = None

    # -- Step 7: Save with safety check -----------------------------------
    log.info("Step 7: Saving model")
    save_blocked_reason = None
    model_saved         = False

    if (
        previous_rmse is not None
        and new_rmse > previous_rmse * RMSE_DEGRADATION_LIMIT
    ):
        save_blocked_reason = (
            f"New RMSE ({new_rmse:.2f} kW) is more than "
            f"{int((RMSE_DEGRADATION_LIMIT - 1) * 100)}% worse than "
            f"previous ({previous_rmse:.2f} kW). "
            f"Model not saved - please review data quality."
        )
        log.warning(save_blocked_reason)
    else:
        save_model(
            model         = model,
            feature_cols  = feature_cols,
            itc_inv       = itc_inv,
            val_metrics   = val_metrics,
            test_metrics  = test_metrics,
            best_params   = best_params,
            y_test        = y_test,
            y_pred_test   = y_pred_test,
            previous_rmse = previous_rmse,
            previous_val_rmse= previous_val_rmse,
        )
        model_saved = True
        log.info("Model saved successfully.")

    # title_str must be before try block
    if rmse_change_pct is not None:
        direction = "↑" if rmse_change_pct > 0 else "↓"
        title_str = (
            f"{itc_inv} - Retrain Test Period | "
            f"RMSE={new_rmse:.1f} kW "
            f"({direction}{abs(rmse_change_pct):.1f}%)"
        )
    else:
        title_str = f"{itc_inv} - Retrain Test Period | RMSE={new_rmse:.1f} kW"

    # --Step 8: Plots ----------------------------------

    log.info("Step 8: Generating plots")
    plot_time = None
    plot_gii  = None
    try:
        test_df = test_df.copy()
        test_df["predicted_power"] = y_pred_test
        plot_time = plot_time_vs_power(
            df      = test_df,
            itc_inv = itc_inv,
            title   = title_str,
        )
        plot_gii = plot_gii_vs_power(
            df      = test_df,
            itc_inv = itc_inv,
            title   = f"{itc_inv} - GII vs Power | Retrain",
        )
    except Exception as e:
        log.warning(f"Plot generation failed: {e}. Model was saved successfully.")
    duration = (datetime.now() - start).total_seconds()
    log.info(f"Retrain pipeline complete in {duration:.1f}s")

    return {
        "passed":               True,
        "errors":               [],
        "warnings":             merge_warnings + val_result["warnings"] + feature_warnings,
        "date_swap":            val_result["date_swap"],
        "val_metrics":          val_metrics,
        "test_metrics":         test_metrics,
        "previous_rmse":        previous_rmse,
        "new_rmse":             new_rmse,
        "previous_val_rmse": previous_val_rmse,
        "new_val_rmse": new_val_rmse,
        "rmse_change_pct":      rmse_change_pct,
        "model_saved":          model_saved,
        "save_blocked_reason":  save_blocked_reason,
        "plot_time":            plot_time,
        "plot_gii":             plot_gii,
        "train_rows":           len(train_df),
        "val_rows":             len(val_df),
        "test_rows":            len(test_df),
        "months_available":     round(months_available, 1),
        "window_mode":          window_mode,
        "duration_sec":         round(duration, 1),
    }