# app.py

import logging
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from config.settings import ITC_INV_LIST, OUTPUTS_DIR
from core.model import model_status
from pipelines.batch_pipeline import (
    run_batch_train,
    run_batch_inference,
    run_batch_retrain,
)

# --- Logging -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/pipeline.log", mode="a"),
    ],
)

# --- Page config ----------------------------------------------------------------------------------------------
st.set_page_config(
    page_title="Solar Digital Twin",
    page_icon="☀️",
    layout="wide",
)

# --- Session state defaults ------------------------------------------------------------------------------
if "selected_itc_inv" not in st.session_state:
    st.session_state["selected_itc_inv"] = ITC_INV_LIST[0]
if "batch_inference_results" not in st.session_state:
    st.session_state["batch_inference_results"] = None
if "train_results" not in st.session_state:
    st.session_state["train_results"] = None
if "train_blocked" not in st.session_state:
    st.session_state["train_blocked"] = False
if "train_inv_paths" not in st.session_state:
    st.session_state["train_inv_paths"] = []
if "train_wms_paths" not in st.session_state:
    st.session_state["train_wms_paths"] = []
if "retrain_results" not in st.session_state:
    st.session_state["retrain_results"] = None
if "retrain_inv_paths" not in st.session_state:
    st.session_state["retrain_inv_paths"] = []
if "retrain_wms_paths" not in st.session_state:
    st.session_state["retrain_wms_paths"] = []

# --- Helpers -----------------------------------------------------------------------------------------------------

# def save_uploads(
#     uploaded_files: List,
#     folder:         Path,
#     itc_inv:        str,
#     prefix:         str,
# ) -> List[Path]:
#     folder.mkdir(parents=True, exist_ok=True)
#     saved    = []
#     date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
#     for i, uf in enumerate(uploaded_files):
#         suffix   = Path(uf.name).suffix
#         out_path = folder / f"{itc_inv}_{prefix}_{date_str}_{i}{suffix}"
#         with open(out_path, "wb") as f:
#             f.write(uf.getbuffer())
#         saved.append(out_path)
#     return saved


# def save_uploads_batch(
#     uploaded_files: List,
#     folder:         Path,
#     prefix:         str,
# ) -> List[Path]:
#     """Save uploads without itc_inv prefix - for batch operations."""
#     folder.mkdir(parents=True, exist_ok=True)
#     saved    = []
#     date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
#     for i, uf in enumerate(uploaded_files):
#         suffix   = Path(uf.name).suffix
#         out_path = folder / f"{prefix}_{date_str}_{i}{suffix}"
#         with open(out_path, "wb") as f:
#             f.write(uf.getbuffer())
#         saved.append(out_path)
#     return saved


def status_badge(itc_inv: str) -> str:
    s = model_status(itc_inv)
    if s["trained"]:
        date = s["last_trained"][:10]
        rmse = s["test_rmse"]
        return f" Trained  |  Last: {date}  |  RMSE: {rmse:.1f} kW"
    return "-- Not trained yet"


def show_warnings(warnings: list):
    for w in warnings:
        st.warning(w)


def show_errors(errors: list):
    for e in errors:
        st.error(e)


def show_date_swap(date_swap: dict):
    if date_swap and date_swap["suspicious"]:
        st.warning(
            f"⚠️ Possible month/day swap in timestamps.\n\n"
            f"Sample: {date_swap['sample']}\n\n"
            f"{date_swap['reason']}\n\n"
            f"If dates look wrong, correct your files and re-upload."
        )


def show_metrics(val_metrics: dict, test_metrics: dict):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Validation Metrics**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("MAE",   f"{val_metrics['mae']:.2f} kW")
        m2.metric("RMSE",  f"{val_metrics['rmse']:.2f} kW")
        m3.metric("R²",    f"{val_metrics['r2']:.4f}")
        m4.metric("sMAPE", f"{val_metrics['smape']:.2f}%")
    with c2:
        st.markdown("**Test Metrics**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("MAE",   f"{test_metrics['mae']:.2f} kW")
        m2.metric("RMSE",  f"{test_metrics['rmse']:.2f} kW")
        m3.metric("R²",    f"{test_metrics['r2']:.4f}")
        m4.metric("sMAPE", f"{test_metrics['smape']:.2f}%")


def show_plots_static(plot_time: Path, plot_gii: Path, plot_anomaly: Path = None):
    """For train and retrain — matplotlib PNGs."""
    st.markdown("---")
    if plot_time and Path(plot_time).exists():
        st.subheader("Time vs Power")
        st.image(str(plot_time), width="stretch")
    else:
        st.warning("Time vs Power plot could not be generated.")

    if plot_gii and Path(plot_gii).exists():
        st.subheader("GII vs Power")
        st.image(str(plot_gii), width="stretch")
    else:
        st.warning("GII vs Power plot could not be generated.")

    if plot_anomaly and Path(plot_anomaly).exists():
        st.subheader("Residual Timeline")
        st.image(str(plot_anomaly), width="stretch")


def show_plots_interactive(plot_time: Path, plot_gii: Path, plot_anomaly: Path = None):
    """For inference - Plotly HTML files."""
    st.markdown("---")
    if plot_time and Path(plot_time).exists():
        st.subheader("Time vs Power")
        with open(plot_time, "r", encoding="utf-8") as f:
            st.components.v1.html(f.read(), height=550, scrolling=False)
    else:
        st.warning("Time vs Power plot could not be generated.")

    if plot_gii and Path(plot_gii).exists():
        st.subheader("GII vs Power")
        with open(plot_gii, "r", encoding="utf-8") as f:
            st.components.v1.html(f.read(), height=550, scrolling=False)
    else:
        st.warning("GII vs Power plot could not be generated.")

    if plot_anomaly and Path(plot_anomaly).exists():
        st.subheader("Residual Timeline")
        with open(plot_anomaly, "r", encoding="utf-8") as f:
            st.components.v1.html(f.read(), height=450, scrolling=False)


def show_anomaly_report(report: dict):
    st.markdown("---")
    st.subheader("Anomaly Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("🟢 Normal",  f"{report['normal_count']}",
              f"{report['normal_pct']}%")
    c2.metric("🟠 Warning", f"{report['warning_count']}",
              f"{report['warning_pct']}%", delta_color="inverse")
    c3.metric("🔴 Anomaly", f"{report['anomaly_count']}",
              f"{report['anomaly_pct']}%", delta_color="inverse")

    st.markdown(
        f"**Mean residual:** {report['mean_residual']:.2f} kW  |  "
        f"**Max underperformance:** {report['max_neg_residual']:.2f} kW "
        f"at {report['max_neg_timestamp']}"
    )

    if report["anomaly_count"] > 0:
        st.markdown("**Anomaly Events**")
        st.dataframe(report["anomaly_table"], width="stretch")

    if report["warning_count"] > 0:
        with st.expander(f"Warning Events ({report['warning_count']})"):
            st.dataframe(report["warning_table"], width="stretch")


def show_shap(shap_results: dict):
    if not shap_results or not shap_results.get("plot_summary"):
        return
    st.markdown("---")
    st.subheader("Why Did These Anomalies Occur?")
    c1, c2 = st.columns(2)
    with c1:
        st.image(str(shap_results["plot_summary"]), width="stretch")
    with c2:
        st.image(str(shap_results["plot_family"]), width="stretch")

    if shap_results.get("waterfall_plots"):
        st.subheader("Event-Level Explanation")
        for i, (wf_path, exp) in enumerate(zip(
            shap_results["waterfall_plots"],
            shap_results["explanations"],
        )):
            with st.expander(
                f"Event {i+1} - {exp['timestamp']} | "
                f"Residual: {exp['residual']:.1f} kW"
            ):
                st.image(str(wf_path), width="stretch")
                st.info(exp["explanation"])


def file_collector(label: str, key: str) -> List[Path]:
    """
    Collects files from:
    - Multiple folder paths (pasted one per line)
    - Individual file uploads
    Deduplicates and returns combined sorted list.
    """
    st.markdown(f"**{label}**")

    # --- Folder paths ---------------------------------------------------------------------------------
    folder_input = st.text_area(
        "Paste folder path(s) - one per line",
        placeholder=(
            "C:/Solar/Data/January/Inverter\n"
            "C:/Solar/Data/February/Inverter"
        ),
        key=f"folders_{key}",
        height=100,
    )

    # --- Individual files ---------------------------------------------------------------------------
    uploaded = st.file_uploader(
        "Or upload individual files",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key=f"files_{key}",
    )

    collected: List[Path] = []
    errors = []

    # --- Process folder paths ---------------------------------------------------------------------
    if folder_input.strip():
        for line in folder_input.strip().splitlines():
            folder = Path(line.strip())
            if not folder.exists():
                errors.append(f"Folder not found: {folder}")
                continue
            if not folder.is_dir():
                errors.append(f"Not a folder: {folder}")
                continue
            xlsx = sorted(folder.glob("*.xlsx")) + sorted(folder.glob("*.xls"))
            if not xlsx:
                errors.append(f"No xlsx/xls files in: {folder}")
                continue
            collected.extend(xlsx)

    # --- Process uploaded files ------------------------------------------------------------------
    if uploaded:
        save_dir = Path("data/temp_uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        for uf in uploaded:
            out = save_dir / uf.name
            with open(out, "wb") as f:
                f.write(uf.getbuffer())
            collected.append(out)

    # --- Deduplicate by filename -----------------------------------------------------------------
    seen  = set()
    dedup = []
    for fp in collected:
        if fp.name not in seen:
            seen.add(fp.name)
            dedup.append(fp)
    collected = sorted(dedup)

    # --- Show errors -----------------------------------------------------------------------------------
    for e in errors:
        st.error(e)

    # --- Show collected file list ---------------------------------------------------------------
    if collected:
        st.success(f"{len(collected)} file(s) ready.")
        with st.expander("View file list"):
            for fp in collected:
                st.caption(f" {fp.name}")

    return collected


def both_uploaded(inv_files, wms_files) -> bool:
    """Returns True only if both file sets have at least one file."""
    return bool(inv_files) and bool(wms_files)

def show_quality_report(quality: dict):
    """Show data quality issues and block training until operator confirms clean."""
    st.error(
        f"Data Quality Issues Found — Training Blocked\n\n"
        f"{quality['message']}\n\n"
        f"Please remove the affected periods from your data and re-upload."
    )
    for issue in quality["issues"]:
        with st.expander(f"{issue['type']} — {issue['count']} rows | {issue['date_range']}"):
            st.warning(issue["description"])
            st.markdown("**Sample rows:**")
            st.dataframe(pd.DataFrame(issue["sample"]), width="stretch")


# --- Sidebar -----------------------------------------------------------------------------------------------------

st.sidebar.image("https://img.icons8.com/emoji/96/sun-emoji.png", width=60)
st.sidebar.title("Solar Digital Twin")
st.sidebar.markdown("---")
st.sidebar.subheader("Inverter Status")
for inv in ITC_INV_LIST:
    st.sidebar.caption(f"{inv.replace('_', '-')} - {status_badge(inv)}")
st.sidebar.markdown("---")
st.sidebar.caption("Locally deployed - Solar Digital Twin PoC")


# --- Tabs ---------------------------------------------------------------------------------------------------------

tab_train, tab_analysis, tab_retrain, tab_manual = st.tabs([
    " Train",
    " Analysis",
    " Retrain",
    "Manual",
])


# ----------------------------------------------------------------
# TAB 1 - BATCH TRAIN
# ----------------------------------------------------------------

with tab_train:
    st.header("Train Models - All Inverters")
    st.markdown(
        "Upload all daily Inverter Report and WMS Report files "
        "covering the full training period (3-6 months). "
        "Models will be trained for all ITC-INV sheets found in the files."
    )

    overwrite = st.checkbox(
        "Overwrite existing models",
        value=False,
        help="If unchecked, already trained inverters are skipped.",
    )

    inv_files = file_collector("Inverter Report Files", "train_inv")
    wms_files = file_collector("WMS Report Files",      "train_wms")

    if st.button("Train All", type="primary", key="btn_train"):
        st.session_state["train_inv_paths"] = inv_files
        st.session_state["train_wms_paths"] = wms_files
        st.session_state["train_results"]   = None
        st.session_state["train_blocked"]   = False

        with st.spinner("Training all inverters - this may take several minutes..."):
            results = run_batch_train(
                inv_filepaths = inv_files,
                wms_filepaths = wms_files,
                overwrite     = overwrite,
                remove_faults = False,
            )
        st.session_state["train_results"] = results

        # check if any inverter was blocked
        any_blocked = any(r.get("blocked") for r in results.values())
        st.session_state["train_blocked"] = any_blocked

    # ── Show results if available ─────────────────────────────────────────
    if st.session_state.get("train_results"):
        results = st.session_state["train_results"]

        # ── Quality report for blocked inverters ──────────────────────────
        blocked_invs = [
            inv for inv, r in results.items() if r.get("blocked")
        ]
        if blocked_invs:
            st.markdown("---")
            st.subheader("Data Quality Issues Found")
            for itc_inv in blocked_invs:
                st.markdown(f"**{itc_inv.replace('_', '-')}**")
                show_quality_report(results[itc_inv]["quality_report"])

            st.markdown("---")
            st.markdown("**What would you like to do?**")
            auto_remove_train = st.checkbox(
                "Auto-remove faulty rows and proceed with training",
                key="auto_remove_train",
                help=(
                    "Faulty rows will be removed automatically before training. "
                    "Check the quality report above to understand what will be removed."
                ),
            )
            if auto_remove_train:
                remove_low_days_train = st.checkbox(
                    "Also remove full low-output days",
                    value=True,
                    key="remove_low_days_train",
                    help=(
                        "If checked, entire days where max power was below 10% of normal are removed. "
                        "If unchecked, only individual trip rows and oscillating rows are removed."
                    ),
                )
                remove_oscillations_train = st.checkbox(
                    "Also remove oscillating/unstable power periods",
                    value=False,
                    key="remove_oscillations_train",
                    help=(
                        "If checked, periods where power fluctuated rapidly during high GII are removed. "
                        "Note: cloud edge effects can look like oscillations — use with caution."

                    ),
                )

                if st.button(
                    "Proceed with Auto-removal",
                    type="primary",
                    key="btn_train_auto_remove",
                ):
                    inv_paths = st.session_state.get("train_inv_paths", [])
                    wms_paths = st.session_state.get("train_wms_paths", [])

                    if not inv_paths or not wms_paths:
                        st.error("File paths lost — please re-upload your files and try again.")
                    else:
                        with st.spinner("Removing faulty rows and training..."):
                            new_results = run_batch_train(
                                inv_filepaths    = inv_paths,
                                wms_filepaths    = wms_paths,
                                overwrite        = overwrite,
                                remove_faults    = True,
                                remove_low_days  = remove_low_days_train,
                                remove_oscillations_train = remove_oscillations_train,
                            )
                        st.session_state["train_results"] = new_results
                        st.session_state["train_blocked"] = False
                        st.rerun()
            else:
                st.info("Please clean your data and re-upload.")

        # ── Training summary table ────────────────────────────────────────
        non_blocked = {
            inv: r for inv, r in results.items() if not r.get("blocked")
        }
        if non_blocked:
            st.markdown("---")
            st.subheader("Training Summary")
            rows = []
            for itc_inv, r in non_blocked.items():
                if r.get("skipped"):
                    rows.append({
                        "Inverter":  itc_inv.replace("_", "-"),
                        "Status":    "Skipped",
                        "Test RMSE": "-",
                        "Val RMSE":  "-",
                        "Duration":  "-",
                    })
                elif not r["passed"]:
                    rows.append({
                        "Inverter":  itc_inv.replace("_", "-"),
                        "Status":    "Failed",
                        "Test RMSE": "-",
                        "Val RMSE":  "-",
                        "Duration":  "-",
                    })
                else:
                    rows.append({
                        "Inverter":  itc_inv.replace("_", "-"),
                        "Status":    "Trained",
                        "Test RMSE": f"{r['test_metrics']['rmse']:.2f} kW",
                        "Val RMSE":  f"{r['val_metrics']['rmse']:.2f} kW",
                        "Duration":  f"{r['duration_sec']}s",
                    })
            st.dataframe(pd.DataFrame(rows), width="stretch")

            for itc_inv, r in non_blocked.items():
                if r.get("warnings"):
                    with st.expander(f"Warnings - {itc_inv.replace('_', '-')}"):
                        show_warnings(r["warnings"])

                if r.get("passed"):
                    show_plots_static(r["plot_time"], r["plot_gii"])

    elif inv_files or wms_files:
        st.warning(
            "Please upload both Inverter Report files and WMS Report files."
        )


# ----------------------------------------------------------------
# TAB 2 - ANALYSIS
# ----------------------------------------------------------------

with tab_analysis:
    st.header("Analysis - All Inverters")
    st.markdown(
        "Upload Inverter Report and WMS Report files for the period "
        "to analyse (1-2 weeks). Results will be shown for all trained inverters."
    )

    inv_files = file_collector("Inverter Report Files", "analysis_inv")
    wms_files = file_collector("WMS Report Files",      "analysis_wms")

    if both_uploaded(inv_files, wms_files):
        st.success(
            f"Received {len(inv_files)} inverter file(s) "
            f"and {len(wms_files)} WMS file(s)."
        )

        if st.button(" Run Analysis", type="primary", key="btn_analysis"):
            inv_paths = inv_files
            wms_paths = wms_files
            

            with st.spinner("Running analysis for all inverters..."):
                results = run_batch_inference(
                    inv_filepaths = inv_paths,
                    wms_filepaths = wms_paths
                )

            st.session_state["batch_inference_results"] = results

    # --- Summary table --------------------------------------------------------------------------------
    results = st.session_state.get("batch_inference_results")
    if results:
        st.markdown("---")
        st.subheader("Fleet Summary")

        summary_rows = []
        for itc_inv, r in results.items():
            if r.get("skipped"):
                summary_rows.append({
                    "Inverter": itc_inv.replace("_", "-"),
                    "Status":   "⏭ Not trained",
                    "Normal":   "-",
                    "Warning":  "-",
                    "Anomaly":  "-",
                    "Mean Residual": "-",
                })
            elif not r["passed"]:
                summary_rows.append({
                    "Inverter": itc_inv.replace("_", "-"),
                    "Status":   " Failed",
                    "Normal":   "-",
                    "Warning":  "-",
                    "Anomaly":  "-",
                    "Mean Residual": "-",
                })
            else:
                rep = r["report"]
                anomaly_flag = "🔴" if rep["anomaly_count"] > 0 else (
                    "🟠" if rep["warning_count"] > 0 else "🟢"
                )
                summary_rows.append({
                    "Inverter": itc_inv.replace("_", "-"),
                    "Status":   anomaly_flag,
                    "Normal":   rep["normal_count"],
                    "Warning":  rep["warning_count"],
                    "Anomaly":  rep["anomaly_count"],
                    "Mean Residual": f"{rep['mean_residual']:.1f} kW",
                })

        st.dataframe(pd.DataFrame(summary_rows), width="stretch")

        # --- Per-inverter detail -----------------------------------------------------------------
        st.markdown("---")
        st.subheader("Inverter Detail")

        trained_invs = [
            inv for inv, r in results.items()
            if not r.get("skipped") and r.get("passed")
        ]

        if trained_invs:
            selected = st.selectbox(
                "Select inverter for detailed view",
                options=trained_invs,
                format_func=lambda x: x.replace("_", "-"),
                index=trained_invs.index(st.session_state["selected_itc_inv"])
                if st.session_state["selected_itc_inv"] in trained_invs
                else 0,
                key="analysis_inv_select",
            )
            st.session_state["selected_itc_inv"] = selected
            r = results[selected]

            show_warnings(r.get("warnings", []))
            show_date_swap(r.get("date_swap"))
            show_anomaly_report(r["report"])
            show_shap(r.get("shap_results", {}))
            show_plots_interactive(
                r["plot_time"],
                r["plot_gii"],
                r["plot_anomaly"],
            )

            # download report
            st.markdown("---")
            report_df = pd.concat([
                r["report"]["anomaly_table"],
                r["report"]["warning_table"],
            ]).sort_values("timestamp")

            if len(report_df) > 0:
                st.download_button(
                    label     = f"⬇ Download Anomaly Report - {selected.replace('_', '-')} (CSV)",
                    data      = report_df.to_csv(index=False),
                    file_name = (
                        f"{selected}_anomaly_report_"
                        f"{datetime.now().strftime('%Y%m%d')}.csv"
                    ),
                    mime="text/csv",
                )

    elif inv_files or wms_files:
        st.warning(
            "Please upload both Inverter Report files and WMS Report files."
        )


# ----------------------------------------------------------------
# TAB 3 - BATCH RETRAIN
# ----------------------------------------------------------------

with tab_retrain:
    st.header("Monthly Retrain - All Inverters")
    st.markdown(
        "Upload Inverter Report and WMS Report files for the latest period. "
        "All trained inverters will be retrained automatically."
    )
    
    inv_files = file_collector("Inverter Report Files", "retrain_inv")
    wms_files = file_collector("WMS Report Files",      "retrain_wms")

    if both_uploaded(inv_files, wms_files):
        st.success(
            f"Received {len(inv_files)} inverter file(s) "
            f"and {len(wms_files)} WMS file(s)."
        )

        if st.button("Retrain All", type="primary", key="btn_retrain"):
            st.session_state["retrain_inv_paths"] = inv_files
            st.session_state["retrain_wms_paths"] = wms_files
            st.session_state["retrain_results"]   = None

            with st.spinner("Retraining all inverters - this may take several minutes..."):
                results = run_batch_retrain(
                    inv_filepaths = inv_files,
                    wms_filepaths = wms_files,
                    remove_faults = False,
                )
            st.session_state["retrain_results"] = results
            st.rerun()

        # ── Show results if available ─────────────────────────────────────────
        if st.session_state.get("retrain_results"):
            results = st.session_state["retrain_results"]

            # ── Quality report for blocked inverters ──────────────────────────
            blocked_invs = [
                inv for inv, r in results.items() if r.get("blocked")
            ]
            if blocked_invs:
                st.markdown("---")
                st.subheader("Data Quality Issues Found")
                for itc_inv in blocked_invs:
                    st.markdown(f"**{itc_inv.replace('_', '-')}**")
                    show_quality_report(results[itc_inv]["quality_report"])

                st.markdown("---")
                st.markdown("**What would you like to do?**")
                auto_remove_retrain = st.checkbox(
                    "Auto-remove faulty rows and proceed with retraining",
                    key="auto_remove_retrain",
                    help=(
                        "Faulty rows will be removed automatically before retraining. "
                        "Check the quality report above to understand what will be removed."
                    ),
                )
                if auto_remove_retrain:
                    remove_low_days_retrain = st.checkbox(
                        "Also remove full low-output days",
                        value=True,
                        key="remove_low_days_retrain",
                        help=(
                            "If checked, entire days where max power was below 10% of normal are removed. "
                            "If unchecked, only individual trip rows and oscillating rows are removed."
                        ),
                    )
                    remove_oscillations_retrain = st.checkbox(
                        "Also remove oscillating/unstable power periods",
                        value=False,
                        key="remove_oscillations_retrain",
                        help=(
                            "If checked, periods where power fluctuated rapidly during high GII are removed. "
                            "Note: cloud edge effects can look like oscillations — use with caution."
                        ),
                    )

                    if st.button(
                        "Proceed with Auto-removal",
                        type="primary",
                        key="btn_retrain_auto_remove",
                    ):
                        inv_paths = st.session_state.get("retrain_inv_paths", [])
                        wms_paths = st.session_state.get("retrain_wms_paths", [])

                        if not inv_paths or not wms_paths:
                            st.error("File paths lost — please re-upload your files and try again.")
                        else:
                            with st.spinner("Removing faulty rows and retraining..."):
                                new_results = run_batch_retrain(
                                    inv_filepaths    = inv_paths,
                                    wms_filepaths    = wms_paths,
                                    overwrite        = overwrite,
                                    remove_faults    = True,
                                    remove_low_days  = remove_low_days_retrain,
                                    remove_oscillations_retrain = remove_oscillations_retrain,
                                )
                            st.session_state["retrain_results"] = new_results
                            st.session_state["retrain_blocked"] = False
                            st.rerun()
                else:
                    st.info("Please clean your data and re-upload.")

            # ── Retrain summary table ─────────────────────────────────────────
            non_blocked = {
                inv: r for inv, r in results.items() if not r.get("blocked")
            }
            if non_blocked:
                st.markdown("---")
                st.subheader("Retrain Summary")
                rows = []
                for itc_inv, r in non_blocked.items():
                    if r.get("skipped"):
                        rows.append({
                            "Inverter":          itc_inv.replace("_", "-"),
                            "Status":            "Skipped",
                            "Previous RMSE":     "-",
                            "New RMSE":          "-",
                            "Prev Val RMSE":     "-",
                            "New Val RMSE":      "-",
                            "Change":            "-",
                            "Saved":             "-",
                            "Duration":          "-",
                        })
                    elif not r["passed"]:
                        rows.append({
                            "Inverter":          itc_inv.replace("_", "-"),
                            "Status":            "Failed",
                            "Previous RMSE":     "-",
                            "New RMSE":          "-",
                            "Prev Val RMSE":     "-",
                            "New Val RMSE":      "-",
                            "Change":            "-",
                            "Saved":             "-",
                            "Duration":          "-",
                        })
                    else:
                        change = (
                            f"{r['rmse_change_pct']:+.1f}%"
                            if r["rmse_change_pct"] is not None else "-"
                        )
                        rows.append({
                            "Inverter":          itc_inv.replace("_", "-"),
                            "Status":            "Done",
                            "Previous RMSE":     f"{r['previous_rmse']:.1f} kW"
                                                if r["previous_rmse"] else "-",
                            "New RMSE":          f"{r['new_rmse']:.1f} kW",
                            "Prev Val RMSE":     f"{r['previous_val_rmse']:.1f} kW"
                                                if r.get("previous_val_rmse") else "-",
                            "New Val RMSE":      f"{r['val_metrics']['rmse']:.1f} kW",
                            "Change":            change,
                            "Saved":             "Yes" if r["model_saved"] else "No",
                            "Duration":          f"{r['duration_sec']}s",
                        })
                st.dataframe(pd.DataFrame(rows), width="stretch")

                for itc_inv, r in non_blocked.items():
                    if not r.get("passed"):
                        continue
                    if not r["model_saved"]:
                        st.error(
                            f"{itc_inv.replace('_', '-')}: "
                            f"{r['save_blocked_reason']}"
                        )
                    if r.get("warnings"):
                        with st.expander(f"Warnings - {itc_inv.replace('_', '-')}"):
                            show_warnings(r["warnings"])
                    st.caption(
                        f"{itc_inv.replace('_', '-')} - "
                        f"{r.get('window_mode', '')} | "
                        f"{r.get('months_available', '')} months available"
                    )
                    show_plots_static(r["plot_time"], r["plot_gii"])
    elif inv_files or wms_files:
        st.warning(
            "Please upload both Inverter Report files and WMS Report files."
        )

# TAB 4 MANUAL -----------------------------------------------------
# Add this as Tab 4 in app.py

with tab_manual:
    st.header("User Manual — Solar Digital Twin")
    st.markdown("---")

    # ── Overview ──────────────────────────────────────────────────────────
    st.subheader("Overview")
    st.markdown("""
    This application monitors solar plant inverter performance using machine learning.
    It predicts expected power output and compares it against actual output to detect
    anomalies, warnings, and underperformance events.

    **Three core operations:**
    - **Train** — build a model for each inverter using historical data
    - **Analysis** — run daily/weekly inference to detect anomalies
    - **Retrain** — update the model monthly with new data
    """)

    st.markdown("---")

    # ── Tab 1: Train ───────────────────────────────────────────────────────
    with st.expander(" Train Tab — Complete Guide", expanded=False):
        st.markdown("""
        ### Purpose
        Build the machine learning model for each inverter for the first time.
        Run this once per inverter using 3-6 months of historical data.

        ---

        ### What to Upload
        **Inverter Report files** — daily Excel files from the inverter monitoring system.
        Each file contains one sheet per inverter with DC string measurements,
        AC electrical data, active power, and operational counters.

        **WMS Report files** — daily Excel files from the weather monitoring station.
        Contains GHI, GII, temperature, humidity, rain, and irradiance data.

        Upload all daily files covering your full historical period.
        You can paste folder paths (one per line) or drag and drop individual files.

        ---

        ### Checkboxes

        **Overwrite existing models**
        - Unchecked (default): if a model already exists for an inverter, it is skipped.
        - Checked: existing models are replaced with newly trained ones.
        - Use this if you want to retrain from scratch with better data.

        ---

        ### Data Quality Check
        Before training, the app automatically checks for three types of issues:

        **Inverter Trip / Zero Power at High GII**
        Rows where irradiance is above 300 W/m² but power output is below 100 kW.
        These are likely inverter trips, protection relay events, or communication dropouts.
        Including these in training teaches the model that zero power at high irradiance
        is normal — which will cause it to miss real faults later.

        **Oscillating / Unstable Power**
        Periods where power fluctuated more than 500 kW within a 10-minute window
        during high irradiance. May be MPPT instability or protection relay hunting.
        Note: cloud edge effects can look similar — use judgment before removing.

        **Sustained Low Output Days**
        Full days where maximum power was below 10% of normal.
        Likely full-day outages, maintenance shutdowns, or inverter offline all day.

        ---

        ### When Quality Issues Are Found
        Training is blocked and the issues are displayed with sample timestamps.
        Two options are presented:

        **Option 1 — Clean manually and re-upload**
        Review the timestamps shown, remove those rows/days from your Excel files,
        and upload the cleaned files.

        **Option 2 — Auto-remove faulty rows and proceed**
        Check this box and click "Proceed with Auto-removal".
        The app removes the faulty rows automatically and trains on the remaining data.

        Sub-options when auto-remove is selected:

        - **Also remove full low-output days** (default: on)
          Removes entire days identified as sustained low output.
          Uncheck if those days represent legitimate partial operation.

        - **Also remove oscillating/unstable power periods** (default: off)
          Removes oscillating power periods.
          Only enable if you are confident these are faults, not cloud effects.

        ---

        ### Training Summary Table
        After training completes, a table shows one row per inverter:

        | Column | Meaning |
        |--------|---------|
        | Status | Trained / Skipped / Failed / Blocked |
        | Test RMSE | Model error on the last 7 days of data (lower is better) |
        | Val RMSE | Model error on the 7 days before test (used during training) |
        | Duration | Time taken to train |

        **What is RMSE?**
        Root Mean Square Error — average difference between predicted and actual power in kW.
        A Test RMSE of 20 kW means on average the model was 20 kW off from actual output.
        Lower is better. For anomaly detection, RMSE under 5% of rated capacity is good.

        ---

        ### Plots After Training
        **Time vs Power** — shows actual vs predicted power over the test period.
        **GII vs Power** — scatter plot of irradiance vs power output.
        These confirm the model learned the correct relationship between
        irradiance and power output.
        """)

    # ── Tab 2: Analysis ────────────────────────────────────────────────────
    with st.expander(" Analysis Tab — Complete Guide", expanded=False):
        st.markdown("""
        ### Purpose
        Upload recent data (1-2 weeks or daily) and the app will predict expected
        power for each inverter, compare against actual, and flag anomalies.

        ---

        ### What to Upload
        Same format as training — Inverter Report and WMS Report files.
        Typically 1-2 weeks of daily files, or a single day's file for daily monitoring.

        ---

        ### Fleet Summary Table
        After running analysis, a summary table shows all inverters at a glance:

        | Column | Meaning |
        |--------|---------|
        | Status | 🟢 Normal / 🟠 Warning / 🔴 Anomaly |
        | Normal | Count of minutes classified as normal |
        | Warning | Count of minutes classified as warning |
        | Anomaly | Count of minutes classified as anomaly |
        | Mean Residual | Average difference between actual and predicted power |

        A negative mean residual means the inverter was consistently producing
        less than expected across the period.

        ---

        ### Selecting an Inverter for Detail
        Click the dropdown below the fleet summary to select any inverter.
        The full analysis — plots, anomaly table, and SHAP explanation — appears below.

        ---

        ### Status Definitions

        **🟢 Normal**
        Residual is within expected range based on the model's training error.
        Inverter is performing as expected.

        **🟠 Warning**
        Residual crossed the warning threshold (5th percentile of training residuals)
        for 5 or more consecutive minutes.
        Inverter is underperforming — monitor closely.
        Possible causes: partial shading, mild soiling, one string slightly degraded.

        **🔴 Anomaly**
        Residual crossed the anomaly threshold (1st percentile of training residuals)
        for 10 or more consecutive minutes.
        Significant underperformance — investigate today.
        Possible causes: string fault, MPPT failure, inverter trip, DC cable issue.

        ---

        ### Plots

        **Time vs Power (Interactive)**
        - Blue points: actual power, classified as normal
        - Orange points: actual power, classified as warning
        - Red points: actual power, classified as anomaly
        - Orange line: predicted power (what model expected)
        - Grey dashed line: max envelope (theoretical ceiling based on irradiance)
        - Gold shaded area: GII irradiance on secondary axis
        - Red triangles: anomaly flag markers

        Controls:
        - 1D / 3D / 1W / Full buttons: zoom to last 1 day, 3 days, 1 week, or full period
        - Range slider at bottom: drag to zoom into any custom time range
        - Hover over any point: shows timestamp, actual, predicted, residual, GII, status
        - Click legend items: show/hide individual traces

        **GII vs Power Scatter (Interactive)**
        - Points coloured by status (blue/orange/red)
        - Orange line: binned mean predicted power per irradiance level
        - Grey dashed: theoretical max envelope
        - Hover: shows timestamp, GII, actual, predicted, residual, status

        Diagnostic use:
        - Points clustering below the orange line at all GII levels → inverter-level fault
        - Points below only at high GII → possible clipping or thermal derating
        - Points below only at low GII → possible minimum power threshold issue

        **Residual Timeline (Interactive)**
        - Points coloured by status
        - Zero line: perfect prediction
        - Orange dashed line: warning threshold
        - Red dashed line: anomaly threshold
        - Hover: timestamp, residual, actual, predicted, status

        Patterns to look for:
        - Sudden deep drop to red → inverter trip or string fault
        - Gradual drift to orange → soiling or slow degradation
        - Periodic orange spikes at same time daily → shading at specific hours
        - Short red spikes → sensor noise or brief communication loss
        - Sustained red → serious fault, schedule inspection

        ---

        ### Anomaly Table
        Lists every anomaly event with exact timestamp, actual power,
        predicted power, residual, and status.
        Use the timestamp to cross-reference with inverter SCADA logs.

        ### Warning Events
        Shown in a collapsible expander below the anomaly table.

        ### Download Anomaly Report
        Downloads a CSV of all anomaly and warning events for record-keeping
        or further analysis.

        ---

        ### SHAP Explanation — Why Did This Anomaly Occur?

        **Feature Summary Bar Chart**
        Shows which sensor features contributed most to the model's prediction
        during anomaly periods. Longer bar = more influence on prediction.

        **Feature Family Pie Chart**
        Groups features by category:
        - DC Strings: mod1-4 DC voltage, current, power
        - AC Electrical: phase voltages, currents, power factor
        - Irradiance: GHI, GII, direct, diffuse radiation
        - Temperature: module and ambient temperature
        - Time: hour of day, month, day of year

        High DC Strings % → model expected high output based on DC string readings
        → investigate string currents and voltages

        High AC Electrical % → model expected high output based on AC measurements
        → investigate phase voltages and grid connection

        **Waterfall Chart (per event)**
        Shows exactly how each feature pushed the prediction up or down
        for a specific anomaly timestamp.

        Red bars → feature pushed prediction up (model expected high output because of this)
        Blue bars → feature pushed prediction down

        The gap between predicted (orange line) and actual (blue line)
        is the residual — the anomaly.

        **Text Explanation**
        Plain English summary of the likely fault cause based on which
        feature family dominated the prediction.

        ---

        ### Data Quality Notes
        If quality issues are detected in inference data, a collapsible note appears.
        This is informational only — analysis runs regardless.
        Anomalies in flagged periods may be genuine faults or data artifacts.
        """)

    # ── Tab 3: Retrain ─────────────────────────────────────────────────────
    with st.expander(" Retrain Tab — Complete Guide", expanded=False):
        st.markdown("""
        ### Purpose
        Update the model monthly with new data so it tracks the inverter's
        current performance baseline rather than its state from months ago.

        ---

        ### When to Retrain
        - Every month on the 1st
        - After a panel cleaning event
        - After a string fault is repaired
        - After an inverter component is replaced
        - If anomaly detection starts generating many false alarms

        ---

        ### What to Upload
        Upload all accumulated historical data including the new month.
        Example: if original training used January-March, upload January-May for May retrain.
        The app automatically applies the correct training window:
        - First 12 months: uses all uploaded data (expanding window)
        - After 12 months: uses only the most recent 120 days (rolling window)

        **Important:** Remove known fault periods from your data before uploading.
        The model should learn healthy normal behaviour only.
        Fault periods in training data will cause the model to treat faults as normal.

        ---

        ### Data Quality Check
        Same as training — the app checks for trips, oscillations, and low-output days.
        Same auto-remove options are available.

        ---

        ### Retrain Summary Table

        | Column | Meaning |
        |--------|---------|
        | Previous RMSE | Test RMSE of the model before retraining |
        | New RMSE | Test RMSE of the newly trained model |
        | Prev Val RMSE | Validation RMSE before retraining |
        | New Val RMSE | Validation RMSE of new model |
        | Change | % change in test RMSE (negative = improvement) |
        | Saved | Whether the new model was saved |

        ---

        ### Safety Check
        The new model is only saved if its test RMSE is within 150% of the previous RMSE.
        If the new model is significantly worse, it is not saved and the old model
        is kept. The reason is shown in the app.

        A large RMSE increase usually means:
        - Fault periods were included in retrain data
        - Too little data was uploaded
        - Data quality issues were not addressed

        ---

        ### Window Mode
        Shown at the bottom of each inverter's retrain result:

        **Expanding window** — all uploaded data is used for training.
        Shown when less than 12 months of data is available.

        **Rolling 120-day window** — only the most recent 4 months are used.
        Shown when more than 12 months of data is available.
        This prevents old data from a different degradation state
        affecting the current model.

        ---

        ### Warnings Section
        Expandable per inverter. Shows:
        - Rows dropped due to missing timestamps
        - New features added since last training
        - Features removed since last training
        - Any data quality issues detected
        """)

    # ── Sidebar ────────────────────────────────────────────────────────────
    with st.expander(" Sidebar — Inverter Status Guide", expanded=False):
        st.markdown("""
        ### Inverter Status Badges

        ** Trained | Last: YYYY-MM-DD | RMSE: XX.X kW**
        Model exists for this inverter. Shows date of last training/retrain
        and current test RMSE.

        **⚪ Not trained yet**
        No model exists. Go to Train tab to train this inverter.

        ---

        ### What is Test RMSE?
        The average prediction error of the model on unseen data.
        Lower is better.

        General guidance for this plant (rated 4400 kW):
        - Under 50 kW (< 1.1% of rated): excellent
        - 50-100 kW (1.1-2.3%): good, suitable for anomaly detection
        - 100-200 kW (2.3-4.5%): acceptable, thresholds will be wider
        - Above 200 kW: consider retraining with more or cleaner data
        """)
    # ── File Upload Guide ──────────────────────────────────────────────────
    with st.expander(" File Upload Guide", expanded=False):
        st.markdown("""
        ### Uploading Files

        **Method 1 — Folder Path**
        Paste the full folder path into the text area.
        All Excel files in that folder are loaded automatically.
        You can paste multiple folder paths, one per line.

        Example:
                C:/Solar/Data/April/Inverter
                C:/Solar/Data/May/Inverter

        **Method 2 — Individual Files**
        Use the file uploader to drag and drop individual Excel files.
        Can be combined with folder paths — all files are merged and deduplicated.

        ---

        ### File Naming
        File names do not need to follow any specific convention.
        The app reads timestamps from inside the files, not from filenames.

        ---

        ### Supported Formats
        .xlsx and .xls files only.

        ---

        ### Common Issues

        **"Folder not found"**
        Check the folder path is correct and the drive letter matches.
        Use forward slashes or raw strings with backslashes.

        **"No xlsx/xls files in folder"**
        The folder exists but contains no Excel files.
        Check you selected the correct subfolder.

        **"No inverter files could be read"**
        The Excel files do not contain the expected sheet names for this inverter.
        Check that the inverter report contains the correct sheet
        (e.g. ICR-1_INV-1 for ITC1-INV1).

        **Timestamp warnings**
        The app detects and reports missing timestamps, filled gaps,
        and dropped rows. These are informational — processing continues automatically.

        ---

        ### SharePoint / Network Drives
        Map your SharePoint library as a network drive (e.g. Z:\\)
        or sync via OneDrive to a local folder.
        Then paste that path into the folder input.
        No internet connection is required once files are locally available.
        """)

    # ── Anomaly Response Guide ─────────────────────────────────────────────
    with st.expander(" Anomaly Response Guide", expanded=False):
        st.markdown("""
        ### What to Do When Anomalies Are Detected

        **Step 1 — Check the Fleet Summary**
        Identify which inverters show 🔴 or 🟠 status.
        Check mean residual — large negative values indicate sustained underperformance.

        **Step 2 — Select the affected inverter**
        Use the dropdown to view detailed analysis.

        **Step 3 — Check the Time vs Power plot**
        - When did the anomaly start and end?
        - Was it sudden or gradual?
        - Does it correlate with a GII drop (cloud) or persist through high GII?

        **Step 4 — Check the SHAP explanation**
        - Which feature family dominated? DC Strings or AC Electrical?
        - DC Strings dominant → check string currents and voltages on SCADA
        - AC Electrical dominant → check phase voltages and grid connection

        **Step 5 — Cross-reference with SCADA**
        Use the exact timestamps from the anomaly table to check
        inverter SCADA logs for alarms, trips, or communication faults.

        **Step 6 — Decision**

        | Situation | Action |
        |-----------|--------|
        | Anomaly during cloud event | Monitor, likely benign |
        | Anomaly with SCADA alarm | Escalate to maintenance |
        | Anomaly with no SCADA alarm | Check string fuse / DC cables |
        | Warning persisting multiple days | Schedule inspection |
        | Mean residual trending negative over weeks | Schedule cleaning |

        ---

        ### False Alarms
        Some anomalies may be false alarms caused by:
        - Sensor calibration drift
        - Communication dropout (data gap filled or dropped)
        - Grid events affecting all inverters simultaneously

        If all inverters show anomaly at the same timestamp → likely grid event, not inverter fault.
        If only one inverter shows anomaly → investigate that inverter specifically.
        """)

    # ── Retraining Guide ──────────────────────────────────────────────────
    with st.expander(" Monthly Maintenance Checklist", expanded=False):
        st.markdown("""
        ### Monthly Tasks

        **1. Run Analysis on latest data**
        Upload the past week's files and check fleet summary.
        Download anomaly report and file for records.

        **2. Review anomaly trends**
        Compare this month's anomaly counts to previous months.
        Increasing warning counts may indicate gradual degradation or soiling.

        **3. Retrain models**
        Upload full accumulated data (all months to date).
        Remove known fault periods before uploading.
        Check retrain summary — confirm RMSE improved or stayed stable.

        **4. Archive important inference results**
        Before running next inference, copy the contents of
        `outputs/ITC_INV/latest/` to `outputs/ITC_INV/archive/YYYY-MM-DD/`
        if you want to preserve plots from a significant anomaly event.

        ---

        ### Annual Tasks

        **Review model architecture**
        At 12 months of data, consider whether the weather-only analytics
        model should be added for soiling and derating detection.

        **Full grid search refresh**
        Re-run full hyperparameter grid search to check if better parameters
        exist for the now-larger dataset.
        """)                        


        