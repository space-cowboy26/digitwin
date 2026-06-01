# core/analysis.py

import logging
from pathlib import Path

import numpy as np
import pandas as pd



from config.settings import (
    WARNING_SIGMA,
    ANOMALY_SIGMA,
    OUTPUTS_DIR,
)

log = logging.getLogger(__name__)


# -- Predict ------------------------------------------------------------------─

def predict(
    model,
    df:           pd.DataFrame,
    feature_cols: list[str],
) -> pd.DataFrame:
    """
    Run model analysis on prepared DataFrame.
    Returns df with predicted_power column added.
    """
    df = df.copy()
    df["predicted_power"] = model.predict(df[feature_cols].values)
    return df


# -- Residuals ----------------------------------------------------------------─

def compute_residuals(df: pd.DataFrame) -> pd.DataFrame:
    """
    residual = actual - predicted
    Negative residual = underperformance (actual below expected)
    Positive residual = overperformance (sensor noise / measurement error)
    """
    df = df.copy()
    df["residual"] = df["active_power_kw"] - df["predicted_power"]
    return df


# -- Thresholds ----------------------------------------------------------------

def compute_thresholds(itc_inv: str) -> dict:
    """
    Load training residual stats from metadata and compute
    warning / anomaly thresholds.
    Thresholds are derived from validation residuals - not test.
    """
    import json
    meta_path = OUTPUTS_DIR / itc_inv / "metadata.json"

    if not meta_path.exists():
        raise FileNotFoundError(f"No metadata found for {itc_inv}.")

    with open(meta_path) as f:
        meta = json.load(f)

    # use val RMSE as proxy for residual std
    # negative side matters more - underperformance detection
    percentiles = meta["residual_percentiles"]

    return {
        "warning_threshold": percentiles["p5"],
        "anomaly_threshold": percentiles["p1"],
        "p50":               percentiles ["p50"],
    }


# -- Classify ------------------------------------------------------------------

def classify(
    df:         pd.DataFrame,
    thresholds: dict,
) -> pd.DataFrame:
    """
    Classify each row as normal / warning / anomaly
    based on residual vs thresholds.
    """
    df     = df.copy()
    res    = df["residual"]
    w      = thresholds["warning_threshold"]
    a      = thresholds["anomaly_threshold"]
    

    conditions = [
        res < a,
        res < w,
    ]
    choices = ["anomaly", "warning"]
    df["status"] = np.select(conditions, choices, default="normal")

    return df


# -- Summary report ------------------------------------------------------------

def build_report(df: pd.DataFrame, thresholds: dict) -> dict:
    """
    Builds a summary dict for display in the Streamlit app.
    """
    total   = len(df)
    counts  = df["status"].value_counts().to_dict()
    normal  = counts.get("normal",  0)
    warning = counts.get("warning", 0)
    anomaly = counts.get("anomaly", 0)

    anomaly_rows = df[df["status"] == "anomaly"][[
        "timestamp", "active_power_kw", "predicted_power", "residual", "status"
    ]].reset_index(drop=True)

    warning_rows = df[df["status"] == "warning"][[
        "timestamp", "active_power_kw", "predicted_power", "residual", "status"
    ]].reset_index(drop=True)

    return {
        "total_rows":     total,
        "normal_count":   normal,
        "warning_count":  warning,
        "anomaly_count":  anomaly,
        "normal_pct":     round(normal  / total * 100, 1),
        "warning_pct":    round(warning / total * 100, 1),
        "anomaly_pct":    round(anomaly / total * 100, 1),
        "mean_residual":  round(float(df["residual"].mean()), 2),
        "max_neg_residual": round(float(df["residual"].min()), 2),
        "max_neg_timestamp": str(df.loc[df["residual"].idxmin(), "timestamp"]),
        "thresholds":     thresholds,
        "anomaly_table":  anomaly_rows,
        "warning_table":  warning_rows,
    }


# -- Save report --------------------------------------------------------------─

def save_report(
    df:       pd.DataFrame,
    itc_inv:  str,
    filename: str = "anomaly_report.csv",
) -> Path:
    """
    Save full analysis results to outputs/ITC_INV/anomaly_report.csv
    """
    out_path = OUTPUTS_DIR / itc_inv / filename
    df[[
        "timestamp", "active_power_kw",
        "predicted_power", "residual", "status"
    ]].to_csv(out_path, index=False)
    log.info(f"Report saved -> {out_path}")
    return out_path


# -- Master analysis function ------------------------------------------------─

def run_analysis(
    model,
    df:           pd.DataFrame,
    feature_cols: list[str],
    itc_inv:      str,
) -> tuple[pd.DataFrame, dict, Path]:
    """
    Full analysis pipeline:
    predict -> residuals -> thresholds -> classify -> report -> save

    Returns:
        df_result  : full DataFrame with predictions, residuals, status
        report     : summary dict for app display
        report_path: path to saved CSV
    """
    def apply_persistence_filter(df: pd.DataFrame) -> pd.DataFrame:
        df     = df.copy()
        status = df["status"].values.copy()
        ts     = pd.to_datetime(df["timestamp"]).values
        n      = len(status)
        result = np.array(["normal"] * n, dtype=object)

        i = 0
        while i < n:
            if status[i] in ("warning", "anomaly"):
                # build streak - break if time gap > 2 minutes
                j = i
                while j < n and status[j] in ("warning", "anomaly"):
                    if j > i:
                        gap_minutes = (ts[j] - ts[j-1]) / np.timedelta64(1, "m")
                        if gap_minutes > 2:
                            break   # gap in timestamps - end the streak here
                    j += 1

                streak_len = j - i

                if streak_len >= 10:
                    result[i:j] = "anomaly"
                elif streak_len >= 5:
                    result[i:j] = "warning"

                i = j
            else:
                i += 1

        df["status"] = result
        return df

    thresholds = compute_thresholds(itc_inv)

    df_result = predict(model, df, feature_cols)
    df_result = compute_residuals(df_result)
    df_result = classify(df_result, thresholds)
    df_result = apply_persistence_filter(df_result)

    report      = build_report(df_result, thresholds)
    report_path = save_report(df_result, itc_inv)

    log.info(
        f"{itc_inv} analysis complete - "
        f"normal: {report['normal_count']} | "
        f"warning: {report['warning_count']} | "
        f"anomaly: {report['anomaly_count']}"
    )

    return df_result, report, report_path