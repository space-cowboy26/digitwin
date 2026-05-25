# core/explainer.py

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from config.settings import OUTPUTS_DIR

log = logging.getLogger(__name__)


# -- Build explainer ----------------------------------------------------------─

def build_explainer(model, X_train: np.ndarray) -> shap.TreeExplainer:
    """
    Build SHAP TreeExplainer from trained XGBoost model.
    Called once after training and stored in memory.
    TreeExplainer is fast and exact for tree-based models.
    """
    log.info("Building SHAP TreeExplainer")
    explainer = shap.TreeExplainer(model)
    log.info("SHAP TreeExplainer ready")
    return explainer


# -- Compute SHAP values ------------------------------------------------------─

def compute_shap_values(
    explainer:    shap.TreeExplainer,
    X:            np.ndarray,
    feature_cols: list,
) -> pd.DataFrame:
    """
    Compute SHAP values for given rows.
    Returns DataFrame with one column per feature.
    """
    log.info(f"Computing SHAP values for {len(X)} rows")
    shap_values = explainer.shap_values(X)
    return pd.DataFrame(shap_values, columns=feature_cols)


# -- Feature family grouping --------------------------------------------------─

def get_feature_family(name: str) -> str:
    if any(x in name for x in ["mod1", "mod2", "mod3", "mod4"]) and \
       any(x in name for x in ["_dc_", " dc "]):
        return "DC Strings"
    if name in ("ghi", "gii", "direct", "diffuse",
                "albedo_up", "albedo_down"):
        return "Irradiance"
    if any(x in name for x in ["mod_temp", "amb_temp"]):
        return "Temperature"
    if name in ("rain", "humidity", "cloud_cover",
                "air_press", "wind_speed", "wind_direction"):
        return "Weather"
    if any(x in name for x in ["hour", "month", "doy", "minute"]):
        return "Time"
    if name in ("ry_voltage", "yb_voltage", "br_voltage",
                "ir_current", "iy_current", "ib_current",
                "power_factor", "frequency_hz"):
        return "AC Electrical"
    if name in ("dc_kwp", "ac_kw", "dc_loading", "peak_kw"):
        return "Inverter Spec"
    return "Other"


# -- Plot 1: SHAP summary bar chart ------------------------------------------─

def plot_shap_summary(
    shap_df:      pd.DataFrame,
    feature_cols: list,
    itc_inv:      str,
    label:        str = "anomaly",
) -> Path:
    """
    Horizontal bar chart of mean absolute SHAP value per feature.
    Coloured by feature family.
    Shows top 15 features.
    """
    mean_abs = shap_df.abs().mean().sort_values(ascending=False)
    top15    = mean_abs.head(15)

    family_colors = {
        "DC Strings":    "#1565C0",
        "Irradiance":    "#F9A825",
        "Temperature":   "#E53935",
        "Weather":       "#43A047",
        "Time":          "#8E24AA",
        "AC Electrical": "#00838F",
        "Inverter Spec": "#6D4C41",
        "Other":         "#9E9E9E",
    }

    colors = [
        family_colors.get(get_feature_family(f), "#9E9E9E")
        for f in top15.index
    ]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(
        range(len(top15)),
        top15.values,
        color=colors,
        edgecolor="white",
        height=0.7,
    )
    ax.set_yticks(range(len(top15)))
    ax.set_yticklabels(top15.index, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Mean |SHAP value| (kW impact on prediction)", fontsize=10)
    ax.set_title(
        f"{itc_inv} - Feature Contributions to {label.capitalize()} Predictions",
        fontsize=11,
    )

    # legend for families
    seen = {}
    for f, c in zip(top15.index, colors):
        fam = get_feature_family(f)
        if fam not in seen:
            seen[fam] = c
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=c, label=fam)
        for fam, c in seen.items()
    ]
    ax.legend(handles=handles, fontsize=8, loc="lower right")

    plt.tight_layout()
    out_path = OUTPUTS_DIR / itc_inv / f"shap_summary_{label}.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    log.info(f"SHAP summary plot -> {out_path}")
    return out_path


# -- Plot 2: Waterfall for single anomaly event --------------------------------

def plot_shap_waterfall(
    shap_row:     pd.Series,
    feature_row:  pd.Series,
    base_value:   float,
    predicted:    float,
    actual:       float,
    timestamp:    str,
    itc_inv:      str,
    event_idx:    int,
) -> Path:
    """
    Waterfall chart for a single anomaly row.
    Shows how each feature pushed the prediction up or down
    from the base value to the final prediction.
    Shows top 10 contributing features.
    """
    # sort by absolute contribution, take top 10
    top = shap_row.abs().sort_values(ascending=False).head(10)
    top_shap   = shap_row[top.index]
    top_feats  = feature_row[top.index]

    labels = [
        f"{feat}\n= {val:.2f}"
        for feat, val in zip(top.index, top_feats.values)
    ]

    colors = ["#E53935" if v > 0 else "#1565C0" for v in top_shap.values]

    fig, ax = plt.subplots(figsize=(10, 6))

    # running total for waterfall
    running = base_value
    for i, (shap_val, color, label) in enumerate(
        zip(top_shap.values, colors, labels)
    ):
        ax.barh(i, shap_val, left=running, color=color,
                height=0.6, edgecolor="white")
        running += shap_val

    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(base_value, color="black", linewidth=1.0,
               linestyle="--", alpha=0.5, label=f"Base={base_value:.1f} kW")
    ax.axvline(predicted, color="#FF5722", linewidth=1.5,
               linestyle="-", label=f"Predicted={predicted:.1f} kW")
    ax.axvline(actual, color="#2196F3", linewidth=1.5,
               linestyle="-", label=f"Actual={actual:.1f} kW")

    ax.set_xlabel("Power (kW)", fontsize=10)
    ax.set_title(
        f"{itc_inv} - Anomaly Explanation | {timestamp}\n"
        f"Residual = {actual - predicted:.1f} kW",
        fontsize=11,
    )
    ax.legend(fontsize=9)

    plt.tight_layout()
    out_path = OUTPUTS_DIR / itc_inv / f"shap_waterfall_event{event_idx}.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    log.info(f"SHAP waterfall -> {out_path}")
    return out_path


# -- Plot 3: Family summary pie ------------------------------------------------

def plot_shap_family_summary(
    shap_df:      pd.DataFrame,
    feature_cols: list,
    itc_inv:      str,
    label:        str = "anomaly",
) -> Path:
    """
    Pie chart showing which feature family drove anomaly predictions most.
    """
    mean_abs = shap_df.abs().mean()
    family_totals = {}
    for feat, val in mean_abs.items():
        fam = get_feature_family(feat)
        family_totals[fam] = family_totals.get(fam, 0) + val

    family_colors = {
        "DC Strings":    "#1565C0",
        "Irradiance":    "#F9A825",
        "Temperature":   "#E53935",
        "Weather":       "#43A047",
        "Time":          "#8E24AA",
        "AC Electrical": "#00838F",
        "Inverter Spec": "#6D4C41",
        "Other":         "#9E9E9E",
    }

    labels = list(family_totals.keys())
    values = list(family_totals.values())
    colors = [family_colors.get(l, "#9E9E9E") for l in labels]

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        values,
       
        colors=colors,
        autopct="%1.1f%%",
        startangle=140,
        textprops={"fontsize": 9},
    )
    ax.legend(
        wedges,
        labels,
        title="Feature Family",
        loc="center left",
        bbox_to_anchor=(1,0,0.5,1),
        fontsize=9,
    )
    ax.set_title(
        f"{itc_inv} - Feature Family Contribution to {label.capitalize()}",
        fontsize=11,
    )

    plt.tight_layout()
    out_path = OUTPUTS_DIR / itc_inv / f"shap_family_{label}.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    log.info(f"SHAP family pie -> {out_path}")
    return out_path


# -- Master explain function --------------------------------------------------─

def explain_anomalies(
    model,
    df_result:    pd.DataFrame,
    feature_cols: list,
    itc_inv:      str,
    max_waterfalls: int = 3,
) -> dict:
    """
    Full explainability pipeline for anomaly and warning rows.

    Steps:
        1. Build explainer
        2. Compute SHAP on anomaly rows
        3. Plot summary bar chart
        4. Plot family pie chart
        5. Plot waterfall for top N anomaly events
        6. Generate text explanation per anomaly

    Returns dict with plot paths and text explanations.
    """
    anomaly_df = df_result[df_result["status"] == "anomaly"].reset_index(drop=True)
    warning_df = df_result[df_result["status"] == "warning"].reset_index(drop=True)

    results = {
        "anomaly_count":    len(anomaly_df),
        "warning_count":    len(warning_df),
        "plot_summary":     None,
        "plot_family":      None,
        "waterfall_plots":  [],
        "explanations":     [],
    }

    if len(anomaly_df) == 0 and len(warning_df) == 0:
        log.info("No anomalies or warnings to explain")
        return results

    # use anomaly rows if available, else warning rows
    explain_df = anomaly_df if len(anomaly_df) > 0 else warning_df
    label      = "anomaly" if len(anomaly_df) > 0 else "warning"

    X_explain = explain_df[feature_cols].values

    # -- Build explainer and compute SHAP --------------------------------─
    explainer  = build_explainer(model, X_explain)
    shap_df    = compute_shap_values(explainer, X_explain, feature_cols)
    base_value = float(explainer.expected_value)

    # -- Summary plots ----------------------------------------------------─
    results["plot_summary"] = plot_shap_summary(
        shap_df, feature_cols, itc_inv, label
    )
    results["plot_family"] = plot_shap_family_summary(
        shap_df, feature_cols, itc_inv, label
    )

    # -- Waterfall for top N anomaly events --------------------------------
    n_waterfalls = min(max_waterfalls, len(explain_df))
    for i in range(n_waterfalls):
        row       = explain_df.iloc[i]
        shap_row  = shap_df.iloc[i]
        feat_row  = pd.Series(
            explain_df[feature_cols].iloc[i].values,
            index=feature_cols,
        )

        wf_path = plot_shap_waterfall(
            shap_row    = shap_row,
            feature_row = feat_row,
            base_value  = base_value,
            predicted   = float(row["predicted_power"]),
            actual      = float(row["active_power_kw"]),
            timestamp   = str(row["timestamp"]),
            itc_inv     = itc_inv,
            event_idx   = i + 1,
        )
        results["waterfall_plots"].append(wf_path)

        # -- Text explanation ----------------------------------------------
        explanation = _generate_text_explanation(
            shap_row  = shap_row,
            row       = row,
            base_value= base_value,
            feature_cols = feature_cols,
        )
        results["explanations"].append({
            "timestamp":   str(row["timestamp"]),
            "actual":      float(row["active_power_kw"]),
            "predicted":   float(row["predicted_power"]),
            "residual":    float(row["residual"]),
            "explanation": explanation,
        })

    log.info(f"SHAP explanation complete - {n_waterfalls} waterfalls generated")
    return results


# -- Text explanation generator ------------------------------------------------

def _generate_text_explanation(
    shap_row:     pd.Series,
    row:          pd.Series,
    base_value:   float,
    feature_cols: list,
) -> str:
    """
    Generate a plain English explanation of why the model
    predicted high output but actual was low.
    """
    # top 3 features that pushed prediction UP (positive SHAP)
    # these are the features that caused the model to expect high output
    top_up = shap_row.nlargest(3)

    lines = []
    lines.append(
        f"Model expected {row['predicted_power']:.1f} kW "
        f"but inverter produced {row['active_power_kw']:.1f} kW "
        f"(gap: {row['residual']:.1f} kW)."
    )
    lines.append("Primary reasons the model expected high output:")

    for feat, val in top_up.items():
        family = get_feature_family(feat)
        lines.append(f"  -> {feat} ({family}) contributed +{val:.1f} kW to prediction")

    # fault hypothesis
    families = [get_feature_family(f) for f in top_up.index]
    if "DC Strings" in families:
        lines.append("Likely cause: DC string issue - check string currents and voltages.")
    elif "AC Electrical" in families:
        lines.append("Likely cause: AC side issue - check phase voltages and currents.")
    elif "Irradiance" in families:
        lines.append("Likely cause: Irradiance-driven expectation - check for soiling or shading.")
    else:
        lines.append("Likely cause: Unclear - manual inspection recommended.")

    return " ".join(lines)