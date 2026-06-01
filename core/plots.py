# core/plots.py

import json
import logging
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config.settings import OUTPUTS_DIR, AC_CAPACITY, DC_KWP

log = logging.getLogger(__name__)

STC_IRRADIANCE = 1000.0


# ── Colours ───────────────────────────────────────────────────────────────────
STATUS_COLORS_MPL = {
    "normal":  "#2196F3",
    "warning": "#FF9800",
    "anomaly": "#F44336",
}

STATUS_COLORS_PLOTLY = {
    "normal":  "#2196F3",
    "warning": "#FF9800",
    "anomaly": "#F44336",
}


# ── Output path helpers ───────────────────────────────────────────────────────

def _latest_dir(itc_inv: str) -> Path:
    """Always overwrites — latest analysis run only."""
    p = OUTPUTS_DIR / itc_inv / "latest"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _static_dir(itc_inv: str) -> Path:
    """For train/retrain static plots."""
    p = OUTPUTS_DIR / itc_inv
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Envelope helper ───────────────────────────────────────────────────────────

def _compute_envelope(gii: np.ndarray, itc_inv: str) -> np.ndarray:
    ac_kw           = AC_CAPACITY[itc_inv]
    dc_kwp          = DC_KWP[itc_inv]
    gii_full_output = STC_IRRADIANCE / (dc_kwp / ac_kw)
    return np.clip(ac_kw * (gii / gii_full_output), 0, ac_kw)


# ══════════════════════════════════════════════════════════════════════════════
# MATPLOTLIB — TRAIN AND RETRAIN PLOTS (static PNG)
# ══════════════════════════════════════════════════════════════════════════════

def plot_time_vs_power(
    df:      pd.DataFrame,
    itc_inv: str,
    title:   str = None,
    days:    int = 3,
) -> Path:
    """
    Static matplotlib line plot for train/retrain.
    Saves to outputs/ITC_INV/ (not latest/).
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    sample_dates = sorted(df["timestamp"].dt.date.unique())[:days]
    df = df[df["timestamp"].dt.date.isin(sample_dates)].reset_index(drop=True)

    ts       = df["timestamp"]
    actual   = pd.to_numeric(df["active_power_kw"], errors="coerce").values
    gii      = pd.to_numeric(df["gii"], errors="coerce").values
    envelope = _compute_envelope(gii, itc_inv)

    has_pred   = "predicted_power" in df.columns
    has_status = "status" in df.columns

    if has_pred:
        df["predicted_power"] = pd.to_numeric(
            df["predicted_power"], errors="coerce"
        )

    fig, ax1 = plt.subplots(figsize=(16, 5))
    ax2      = ax1.twinx()

    ax2.fill_between(ts, gii, alpha=0.12, color="gold", label="GII")
    ax2.set_ylabel("GII (W/m2)", color="goldenrod", fontsize=10)
    ax2.tick_params(axis="y", labelcolor="goldenrod")
    ax2.set_ylim(0, max(float(np.nanmax(gii)), 1) * 2.5)

    ax1.plot(ts, envelope, "--", color="#9E9E9E",
             linewidth=1.2, label="Max envelope", zorder=2)

    if has_status:
        for status, color in STATUS_COLORS_MPL.items():
            mask = df["status"] == status
            if mask.any():
                ax1.scatter(
                    ts[mask], actual[mask],
                    s=6, color=color, alpha=0.7,
                    label=f"Actual ({status})", zorder=3,
                )
    else:
        ax1.plot(ts, actual, color="#2196F3",
                 linewidth=1.4, label="Actual", zorder=3)

    if has_pred:
        ax1.plot(ts, df["predicted_power"].values,
                 color="#FF5722", linewidth=1.2,
                 label="Predicted", alpha=0.85, zorder=4)

    ax1.set_ylabel("Active Power (kW)", fontsize=10)
    ax1.set_xlabel("Time", fontsize=10)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
    ax1.xaxis.set_major_locator(mdates.DayLocator())

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2,
               loc="upper left", fontsize=8)

    ax1.set_title(title or f"{itc_inv} -- Time vs Power", fontsize=11)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()

    out_path = _static_dir(itc_inv) / "time_vs_power.png"
    plt.savefig(out_path, dpi=350)
    plt.close()
    log.info(f"Plot saved -> {out_path}")
    return out_path


def plot_gii_vs_power(
    df:      pd.DataFrame,
    itc_inv: str,
    title:   str = None,
) -> Path:
    """
    Static matplotlib scatter for train/retrain.
    Saves to outputs/ITC_INV/.
    """
    df  = df.copy()
    gii = pd.to_numeric(df["gii"], errors="coerce").values

    gii_line = np.linspace(
        float(np.nanmin(gii)), float(np.nanmax(gii)), 300
    )
    env_line = _compute_envelope(gii_line, itc_inv)

    fig, ax = plt.subplots(figsize=(10, 6))

    if "status" in df.columns:
        for status, color in STATUS_COLORS_MPL.items():
            mask = df["status"] == status
            if mask.any():
                ax.scatter(
                    gii[mask],
                    pd.to_numeric(
                        df["active_power_kw"], errors="coerce"
                    ).values[mask],
                    s=4, alpha=0.35, color=color,
                    label=f"Actual ({status})", rasterized=True,
                )
    else:
        ax.scatter(
            gii,
            pd.to_numeric(df["active_power_kw"], errors="coerce").values,
            s=4, alpha=0.3, color="#2196F3",
            label="Actual", rasterized=True,
        )

    if "predicted_power" in df.columns:
        ax.scatter(
            gii,
            pd.to_numeric(df["predicted_power"], errors="coerce").values,
            s=4, alpha=0.2, color="#FF5722",
            label="Predicted", rasterized=True,
        )

    ax.plot(gii_line, env_line, "--", color="#9E9E9E",
            linewidth=1.5, label="Max envelope")

    ax.set_xlabel("GII (W/m2)", fontsize=10)
    ax.set_ylabel("Active Power (kW)", fontsize=10)
    ax.legend(fontsize=9, markerscale=4)
    ax.set_title(title or f"{itc_inv} -- GII vs Power", fontsize=11)

    plt.tight_layout()
    out_path = _static_dir(itc_inv) / "gii_vs_power.png"
    plt.savefig(out_path, dpi=350)
    plt.close()
    log.info(f"Plot saved -> {out_path}")
    return out_path


def plot_anomaly_timeline(
    df:      pd.DataFrame,
    itc_inv: str,
    title:   str = None,
) -> Path:
    """
    Static matplotlib residual timeline for train/retrain.
    Saves to outputs/ITC_INV/.
    Only called when residual and status columns exist.
    """
    if "residual" not in df.columns or "status" not in df.columns:
        raise ValueError("DataFrame must have residual and status columns.")

    df  = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df  = df.sort_values("timestamp").reset_index(drop=True)
    ts  = df["timestamp"]
    res = pd.to_numeric(df["residual"], errors="coerce").values

    fig, ax = plt.subplots(figsize=(16, 4))

    for status, color in STATUS_COLORS_MPL.items():
        mask = df["status"] == status
        if mask.any():
            ax.scatter(ts[mask], res[mask], s=5,
                       color=color, alpha=0.6,
                       label=status.capitalize(), zorder=3)

    ax.axhline(0, color="black", linewidth=0.8,
               linestyle="-", alpha=0.5)

    meta_path = OUTPUTS_DIR / itc_inv / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        p = meta.get("residual_percentiles", {})
        w = p.get("p5")
        a = p.get("p1")
        if w:
            ax.axhline(w, color="#FF9800", linewidth=1.0,
                       linestyle="--", alpha=0.7,
                       label="Warning threshold (p5)")
        if a:
            ax.axhline(a, color="#F44336", linewidth=1.0,
                       linestyle="--", alpha=0.7,
                       label="Anomaly threshold (p1)")

    ax.set_ylabel("Residual (kW)", fontsize=10)
    ax.set_xlabel("Time", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.legend(fontsize=9)
    ax.set_title(title or f"{itc_inv} -- Residual Timeline", fontsize=11)

    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()

    out_path = _static_dir(itc_inv) / "anomaly_timeline.png"
    plt.savefig(out_path, dpi=350)
    plt.close()
    log.info(f"Plot saved -> {out_path}")
    return out_path


# ══════════════════════════════════════════════════════════════════════════════
# PLOTLY — analysis PLOTS (interactive HTML, saved to latest/)
# ══════════════════════════════════════════════════════════════════════════════

def plot_analysis_time_vs_power(
    df:      pd.DataFrame,
    itc_inv: str,
    title:   str = None,
) -> Path:
    """
    Interactive Plotly time vs power plot for analysis.
    Features:
    - Hover: timestamp, actual, predicted, residual, status, GII
    - Actual points coloured by status
    - Predicted as continuous line
    - Envelope as dashed line
    - GII as shaded area on secondary axis
    - Anomaly/warning markers flagged
    - Range slider + 1D/3D/1W/Full buttons
    Saves to outputs/ITC_INV/latest/time_vs_power.html
    """
    df = df.copy()
    df["timestamp"]      = pd.to_datetime(df["timestamp"])
    df["active_power_kw"] = pd.to_numeric(df["active_power_kw"], errors="coerce")
    df["predicted_power"] = pd.to_numeric(df["predicted_power"], errors="coerce")
    df["gii"]            = pd.to_numeric(df["gii"], errors="coerce")
    df["residual"]       = pd.to_numeric(df["residual"], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)

    envelope = _compute_envelope(df["gii"].values, itc_inv)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # ── GII shaded area (secondary axis) ─────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x         = df["timestamp"],
            y         = df["gii"],
            name      = "GII (W/m2)",
            fill      = "tozeroy",
            fillcolor = "rgba(255, 215, 0, 0.12)",
            line      = dict(color="rgba(255, 215, 0, 0.3)", width=1),
            hovertemplate = (
                "<b>GII</b>: %{y:.1f} W/m2<br>"
                "<b>Time</b>: %{x}<extra></extra>"
            ),
        ),
        secondary_y=True,
    )

    # ── Envelope (primary axis) ───────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x         = df["timestamp"],
            y         = envelope,
            name      = "Max Envelope",
            line      = dict(color="#9E9E9E", width=1.5, dash="dash"),
            hovertemplate = (
                "<b>Max Envelope</b>: %{y:.1f} kW<br>"
                "<b>Time</b>: %{x}<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    # ── Predicted (primary axis) ──────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x         = df["timestamp"],
            y         = df["predicted_power"],
            name      = "Predicted",
            line      = dict(color="#FF5722", width=1.5),
            opacity   = 0.85,
            hovertemplate = (
                "<b>Predicted</b>: %{y:.1f} kW<br>"
                "<b>Time</b>: %{x}<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    # ── Actual coloured by status ─────────────────────────────────────────
    for status, color in STATUS_COLORS_PLOTLY.items():
        mask = df["status"] == status
        if not mask.any():
            continue
        sub = df[mask]
        fig.add_trace(
            go.Scatter(
                x    = sub["timestamp"],
                y    = sub["active_power_kw"],
                name = f"Actual ({status.capitalize()})",
                mode = "markers",
                marker = dict(color=color, size=4, opacity=0.8),
                customdata = np.stack([
                    sub["predicted_power"].values,
                    sub["residual"].values,
                    sub["gii"].values,
                    sub["status"].values,
                ], axis=-1),
                hovertemplate = (
                    "<b>Time</b>: %{x}<br>"
                    "<b>Actual</b>: %{y:.1f} kW<br>"
                    "<b>Predicted</b>: %{customdata[0]:.1f} kW<br>"
                    "<b>Residual</b>: %{customdata[1]:.1f} kW<br>"
                    "<b>GII</b>: %{customdata[2]:.1f} W/m2<br>"
                    "<b>Status</b>: %{customdata[3]}<extra></extra>"
                ),
            ),
            secondary_y=False,
        )

    # ── Anomaly flag markers ──────────────────────────────────────────────
    anomalies = df[df["status"] == "anomaly"]
    if not anomalies.empty:
        fig.add_trace(
            go.Scatter(
                x      = anomalies["timestamp"],
                y      = anomalies["active_power_kw"],
                name   = "Anomaly Flag",
                mode   = "markers",
                marker = dict(
                    symbol = "triangle-down",
                    size   = 12,
                    color  = "#F44336",
                    line   = dict(color="darkred", width=1),
                ),
                hovertemplate = (
                    "<b>ANOMALY</b><br>"
                    "<b>Time</b>: %{x}<br>"
                    "<b>Actual</b>: %{y:.1f} kW<extra></extra>"
                ),
            ),
            secondary_y=False,
        )

    # ── Layout ────────────────────────────────────────────────────────────
    date_min = df["timestamp"].dt.date.min()
    date_max = df["timestamp"].dt.date.max()

    fig.update_layout(
        title       = title or f"{itc_inv} -- Time vs Power | analysis",
        height      = 500,
        hovermode   = "x unified",
        legend      = dict(
            orientation = "h",
            yanchor     = "bottom",
            y           = 1.02,
            xanchor     = "right",
            x           = 1,
        ),
        xaxis = dict(
            rangeselector = dict(
                buttons = [
                    dict(count=1, label="1D", step="day",  stepmode="backward"),
                    dict(count=3, label="3D", step="day",  stepmode="backward"),
                    dict(count=7, label="1W", step="day",  stepmode="backward"),
                    dict(label="Full", step="all"),
                ],
            ),
            rangeslider = dict(visible=True),
        ),
        yaxis  = dict(title="Active Power (kW)"),
        yaxis2 = dict(title="GII (W/m2)", showgrid=False),
        plot_bgcolor  = "white",
        paper_bgcolor = "white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#F0F0F0")
    fig.update_yaxes(showgrid=True, gridcolor="#F0F0F0")

    out_path = _latest_dir(itc_inv) / "time_vs_power.html"
    fig.write_html(str(out_path), include_plotlyjs=True)
    log.info(f"Interactive plot saved -> {out_path}")
    return out_path


def plot_analysis_gii_vs_power(
    df:      pd.DataFrame,
    itc_inv: str,
    title:   str = None,
    time_period: str = "all",
    

) -> Path:
    """
    Interactive Plotly GII vs Power scatter for analysis.
    Features:
    - Hover: timestamp, actual, predicted, GII, status, residual
    - Actual points coloured by status
    - Predicted points as orange line + dots
    - Envelope line
    - Anomaly flags
    - Time period selection (1d, 3d, 1w, all)
    Saves to outputs/ITC_INV/latest/gii_vs_power.html
    """
    df = df.copy()
    df["gii"]             = pd.to_numeric(df["gii"], errors="coerce")
    df["active_power_kw"] = pd.to_numeric(df["active_power_kw"], errors="coerce")
    df["predicted_power"] = pd.to_numeric(df["predicted_power"], errors="coerce")
    df["residual"]        = pd.to_numeric(df["residual"], errors="coerce")
    df["timestamp"]       = pd.to_datetime(df["timestamp"])
    df = df.dropna(subset=["gii", "active_power_kw"]).reset_index(drop=True)
    gii_min = float(df["gii"].min())
    gii_max = float(df["gii"].max())

    # filter by time period
    if time_period != "all":
        from datetime import timedelta
        max_time = df["timestamp"].max()
        if time_period == "1d":
            min_time = max_time - timedelta(days=1)
        elif time_period == "3d":
            min_time = max_time - timedelta(days=3)
        elif time_period == "1w":
            min_time = max_time - timedelta(weeks=1)
        else:
            min_time = df["timestamp"].min()
        df = df[(df["timestamp"] >= min_time) & (df["timestamp"] <= max_time)].reset_index(drop=True)

    # envelope line
    gii_line = np.linspace(float(df["gii"].min()), float(df["gii"].max()), 300)
    env_line = _compute_envelope(gii_line, itc_inv)

    fig = go.Figure()

    # ── Actual coloured by status ─────────────────────────────────────────
    for status, color in STATUS_COLORS_PLOTLY.items():
        mask = df["status"] == status
        if not mask.any():
            continue
        sub = df[mask]
        fig.add_trace(go.Scatter(
            x    = sub["gii"],
            y    = sub["active_power_kw"],
            name = f"Actual ({status.capitalize()})",
            mode = "markers",
            marker = dict(color=color, size=4, opacity=0.6),
            customdata = np.stack([
                sub["timestamp"].dt.strftime("%Y-%m-%d %H:%M").values,
                sub["predicted_power"].values,
                sub["residual"].values,
                sub["status"].values,
            ], axis=-1),
            hovertemplate = (
                "<b>Time</b>: %{customdata[0]}<br>"
                "<b>GII</b>: %{x:.1f} W/m2<br>"
                "<b>Actual</b>: %{y:.1f} kW<br>"
                "<b>Predicted</b>: %{customdata[1]:.1f} kW<br>"
                "<b>Residual</b>: %{customdata[2]:.1f} kW<br>"
                "<b>Status</b>: %{customdata[3]}<extra></extra>"
            ),
        ))

    # ── Predicted as line + dots ─────────────────────────────────────────
    df_pred = df.dropna(subset=["predicted_power"]).sort_values("gii")
    fig.add_trace(go.Scatter(
        x         = df_pred["gii"],
        y         = df_pred["predicted_power"],
        name      = "Predicted",
        mode      = "lines+markers",
        line      = dict(color="#FF5722", width=1.5),
        marker    = dict(color="#FF5722", size=3, opacity=0.5),
        customdata = np.stack([
            df_pred["timestamp"].dt.strftime("%Y-%m-%d %H:%M").values,
            df_pred["status"].values,
        ], axis=-1),
        hovertemplate = (
            "<b>Time</b>: %{customdata[0]}<br>"
            "<b>GII</b>: %{x:.1f} W/m2<br>"
            "<b>Predicted</b>: %{y:.1f} kW<br>"
            "<b>Status</b>: %{customdata[1]}<extra></extra>"
        ),
    ))

    # ── Envelope ──────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x         = gii_line,
        y         = env_line,
        name      = "Max Envelope",
        mode      = "lines",
        line      = dict(color="#9E9E9E", width=1.5, dash="dash"),
        hovertemplate = (
            "<b>Envelope</b>: %{y:.1f} kW<br>"
            "<b>GII</b>: %{x:.1f} W/m2<extra></extra>"
        ),
    ))

    # ── Anomaly flag markers ──────────────────────────────────────────────
    anomalies = df[df["status"] == "anomaly"]
    if not anomalies.empty:
        fig.add_trace(go.Scatter(
            x      = anomalies["gii"],
            y      = anomalies["active_power_kw"],
            name   = "Anomaly Flag",
            mode   = "markers",
            marker = dict(
                symbol = "triangle-down",
                size   = 12,
                color  = "#F44336",
                line   = dict(color="darkred", width=1),
            ),
            customdata = anomalies["timestamp"].dt.strftime("%Y-%m-%d %H:%M").values,
            hovertemplate = (
                "<b>ANOMALY</b><br>"
                "<b>Time</b>: %{customdata}<br>"
                "<b>GII</b>: %{x:.1f} W/m2<br>"
                "<b>Actual</b>: %{y:.1f} kW<extra></extra>"
            ),
        ))

    # time period label
    period_label = {
        "1d": "Last 24h",
        "3d": "Last 3 days",
        "1w": "Last 1 week",
        "all": "All time"
    }.get(time_period, "")
    
    fig.update_layout(
        title        = (title or f"{itc_inv} -- GII vs Power | analysis") + f" ({period_label})",
        height       = 500,
        hovermode    = "closest",
        xaxis        = dict(
            title="GII (W/m2)", 
            showgrid=True, 
            gridcolor="#F0F0F0",
            rangeslider=dict(visible=True),
            type="linear",
        ),
        yaxis        = dict(title="Active Power (kW)", showgrid=True, gridcolor="#F0F0F0"),
        legend       = dict(
            orientation = "h",
            yanchor     = "bottom",
            y           = 1.02,
            xanchor     = "right",
            x           = 1,
        ),
        plot_bgcolor  = "white",
        paper_bgcolor = "white",
    )

    out_path = _latest_dir(itc_inv) / "gii_vs_power.html"
    fig.write_html(str(out_path), include_plotlyjs=True)
    log.info(f"Interactive plot saved -> {out_path}")
    return out_path


def plot_analysis_residual_timeline(
    df:      pd.DataFrame,
    itc_inv: str,
    title:   str = None,
) -> Path:
    """
    Interactive Plotly residual timeline for analysis.
    Features:
    - Hover: timestamp, residual, status, actual, predicted
    - Points coloured by status
    - Threshold bands from metadata percentiles
    - Zero line
    - Range slider
    Saves to outputs/ITC_INV/latest/anomaly_timeline.html
    """
    if "residual" not in df.columns or "status" not in df.columns:
        raise ValueError("DataFrame must have residual and status columns.")

    df = df.copy()
    df["timestamp"]       = pd.to_datetime(df["timestamp"])
    df["residual"]        = pd.to_numeric(df["residual"], errors="coerce")
    df["active_power_kw"] = pd.to_numeric(df["active_power_kw"], errors="coerce")
    df["predicted_power"] = pd.to_numeric(df["predicted_power"], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)

    # load thresholds from metadata
    warning_threshold = None
    anomaly_threshold = None
    meta_path = OUTPUTS_DIR / itc_inv / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        p = meta.get("residual_percentiles", {})
        warning_threshold = p.get("p5")
        anomaly_threshold = p.get("p1")

    fig = go.Figure()

    # ── Residual points coloured by status ────────────────────────────────
    for status, color in STATUS_COLORS_PLOTLY.items():
        mask = df["status"] == status
        if not mask.any():
            continue
        sub = df[mask]
        fig.add_trace(go.Scatter(
            x    = sub["timestamp"],
            y    = sub["residual"],
            name = status.capitalize(),
            mode = "markers",
            marker = dict(color=color, size=5, opacity=0.7),
            customdata = np.stack([
                sub["active_power_kw"].values,
                sub["predicted_power"].values,
                sub["status"].values,
            ], axis=-1),
            hovertemplate = (
                "<b>Time</b>: %{x}<br>"
                "<b>Residual</b>: %{y:.1f} kW<br>"
                "<b>Actual</b>: %{customdata[0]:.1f} kW<br>"
                "<b>Predicted</b>: %{customdata[1]:.1f} kW<br>"
                "<b>Status</b>: %{customdata[2]}<extra></extra>"
            ),
        ))

    # ── Zero line ─────────────────────────────────────────────────────────
    fig.add_hline(
        y           = 0,
        line_color  = "black",
        line_width  = 0.8,
        line_dash   = "solid",
        opacity     = 0.5,
    )

    # ── Threshold lines ───────────────────────────────────────────────────
    if warning_threshold is not None:
        fig.add_hline(
            y              = warning_threshold,
            line_color     = "#FF9800",
            line_width     = 1.2,
            line_dash      = "dash",
            annotation_text = f"Warning (p5): {warning_threshold:.1f} kW",
            annotation_position = "bottom right",
        )
    if anomaly_threshold is not None:
        fig.add_hline(
            y              = anomaly_threshold,
            line_color     = "#F44336",
            line_width     = 1.2,
            line_dash      = "dash",
            annotation_text = f"Anomaly (p1): {anomaly_threshold:.1f} kW",
            annotation_position = "bottom right",
        )

    fig.update_layout(
        title   = title or f"{itc_inv} -- Residual Timeline | analysis",
        height  = 400,
        hovermode = "x unified",
        xaxis = dict(
            rangeselector = dict(
                buttons = [
                    dict(count=1, label="1D", step="day",  stepmode="backward"),
                    dict(count=3, label="3D", step="day",  stepmode="backward"),
                    dict(count=7, label="1W", step="day",  stepmode="backward"),
                    dict(label="Full", step="all"),
                ],
            ),
            rangeslider = dict(visible=True),
            type        = "date",
        ),
        yaxis = dict(
            title     = "Residual (kW)",
            showgrid  = True,
            gridcolor = "#F0F0F0",
        ),
        legend = dict(
            orientation = "h",
            yanchor     = "bottom",
            y           = 1.02,
            xanchor     = "right",
            x           = 1,
        ),
        plot_bgcolor  = "white",
        paper_bgcolor = "white",
    )

    out_path = _latest_dir(itc_inv) / "anomaly_timeline.html"
    fig.write_html(str(out_path), include_plotlyjs=True)
    log.info(f"Interactive plot saved -> {out_path}")
    return out_path