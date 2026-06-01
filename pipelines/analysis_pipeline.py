# pipelines/analysis_pipeline.py

import logging
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from core.validator import validate, check_data_quality
from core.data import load_and_merge, prepare_analysis
from core.model import load_model
from core.analysis import run_analysis
from core.explainer import explain_anomalies
from core.plots import (
    plot_analysis_time_vs_power,
    plot_analysis_gii_vs_power,
    plot_analysis_residual_timeline,
)

log = logging.getLogger(__name__)


def run(
    itc_inv:       str,
    inv_filepaths: List,
    wms_filepaths: List,
) -> dict:
    """
    Full analysis pipeline.

    Steps:
        1. Load and merge inverter + WMS files
        2. Validate merged DataFrame
        3. Load saved model + feature cols
        4. Prepare analysis data
        5. Run analysis (predict, residuals, classify, report)
        6. Run SHAP explainability on anomalies
        7. Generate all three plots
        8. Return results dict for app display
    """
    start = datetime.now()
    log.info("=" * 60)
    log.info(f"analysis pipeline - {itc_inv}")
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

    # -- Step 2b: Data quality check (informational only) -----------------
    log.info("Step 2b: Checking data quality")
    quality = check_data_quality(df)
    if not quality["passed"]:
        log.warning(f"Data quality noted: {quality['message']}")

    # -- Step 3: Load model ------------------------------------------------
    log.info("Step 3: Loading model")
    try:
        model, feature_cols, metadata = load_model(itc_inv)
    except FileNotFoundError as e:
        return {
            "passed":    False,
            "errors":    [str(e)],
            "warnings":  merge_warnings + val_result["warnings"],
            "date_swap": val_result["date_swap"],
        }

    log.info(
        f"Model loaded - trained: {metadata.get('saved_at', 'unknown')} | "
        f"test RMSE: {metadata['test_metrics']['rmse']:.2f} kW"
    )

    # -- Step 4: Prepare analysis data ------------------------------------
    log.info("Step 4: Preparing analysis data")
    try:
        df = prepare_analysis(df, feature_cols)
    except ValueError as e:
        return {
            "passed":    False,
            "errors":    [str(e)],
            "warnings":  merge_warnings + val_result["warnings"],
            "date_swap": val_result["date_swap"],
        }

    log.info(f"analysis rows after filtering: {len(df)}")

    if len(df) == 0:
        return {
            "passed":  False,
            "errors":  [
                "No rows remaining after GII and time filters. "
                "Check your data."
            ],
            "warnings":  merge_warnings + val_result["warnings"],
            "date_swap": val_result["date_swap"],
        }

    # -- Step 5: Run analysis --------------------------------------------─
    log.info("Step 5: Running analysis")
    df_result, report, report_path = run_analysis(
        model        = model,
        df           = df,
        feature_cols = feature_cols,
        itc_inv      = itc_inv,
    )

    log.info(
        f"analysis complete - "
        f"normal: {report['normal_count']} | "
        f"warning: {report['warning_count']} | "
        f"anomaly: {report['anomaly_count']}"
    )

    # -- Step 6: SHAP explainability --------------------------------------─
    log.info("Step 6: Running SHAP explainability")
    shap_results = explain_anomalies(
        model        = model,
        df_result    = df_result,
        feature_cols = feature_cols,
        itc_inv      = itc_inv,
    )

    # -- Step 7: Plots ----------------------------------------------------─
    log.info("Step 7: Generating plots")
    date_min = pd.to_datetime(df_result["timestamp"]).dt.date.min()
    date_max = pd.to_datetime(df_result["timestamp"]).dt.date.max()

    log.info("Step 7: Generating plots")
    plot_time    = None
    plot_gii     = None
    plot_anomaly = None
    try:
        plot_time = plot_analysis_time_vs_power(
            df      = df_result,
            itc_inv = itc_inv,
            title   = f"{itc_inv} -- Time vs Power | analysis | {date_min} to {date_max}",
        )
        plot_gii = plot_analysis_gii_vs_power(
            df      = df_result,
            itc_inv = itc_inv,
            title   = f"{itc_inv} -- GII vs Power | analysis | {date_min} to {date_max}",
        )
        plot_anomaly = plot_analysis_residual_timeline(
            df      = df_result,
            itc_inv = itc_inv,
            title   = f"{itc_inv} -- Residual Timeline | analysis",
        )
    except Exception as e:
        log.warning(f"Plot generation failed: {e}")

    duration = (datetime.now() - start).total_seconds()
    log.info(f"analysis pipeline complete in {duration:.1f}s")

    return {
        "passed":       True,
        "errors":       [],
        "warnings":     merge_warnings + val_result["warnings"],
        "date_swap":    val_result["date_swap"],
        "report":       report,
        "report_path":  report_path,
        "shap_results": shap_results,
        "plot_time":    plot_time,
        "plot_gii":     plot_gii,
        "plot_anomaly": plot_anomaly,
        "total_rows":   len(df_result),
        "duration_sec": round(duration, 1),
        "quality_report": quality if not quality["passed"] else None,
    }