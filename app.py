# app.py

import logging
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st

from config.settings import ITC_INV_LIST, OUTPUTS_DIR, AC_CAPACITY
from core.model import model_status
from pipelines.batch_pipeline import  run_batch_train, run_batch_analysis

from pipelines.experiments_pipeline import run_experiment
from experiments.registry import get_registry
import json


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
    st.session_state["selected_itc_inv"] = ITC_INV_LIST
if "batch_analysis_results" not in st.session_state:
    st.session_state["batch_analysis_results"] = None
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
if "experiment_results" not in st.session_state:
    st.session_state["experiment_results"] = None
if "experiment_inv_paths" not in st.session_state:
    st.session_state["experiment_inv_paths"] = []
if "experiment_wms_paths" not in st.session_state:
    st.session_state["experiment_wms_paths"] = []
if "experiment_blocked" not in st.session_state:
    st.session_state["experiment_blocked"] = False
if "experiment_results" not in st.session_state:
    st.session_state["experiment_results"] = None
if "experiment_inv_paths" not in st.session_state:
    st.session_state["experiment_inv_paths"] = []
if "experiment_wms_paths" not in st.session_state:
    st.session_state["experiment_wms_paths"] = []

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
            f"Possible month/day swap in timestamps.\n\n"
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
    """For analysis - Plotly HTML files."""
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
st.sidebar.markdown("---")
with st.sidebar.expander("RESET"):
    st.warning("This will delete all trained models, metadata, and experiment results.")
    confirm = st.text_input(
        "Type RESET to confirm",
        key="reset_confirm",
    )
    if st.button("Delete All Models", key="btn_reset", type="primary"):
        if confirm == "RESET":
            import shutil
            # delete production models
            for itc_inv in ITC_INV_LIST:
                inv_dir = OUTPUTS_DIR / itc_inv
                if inv_dir.exists():
                    shutil.rmtree(inv_dir)
            # delete experiments
            exp_dir = OUTPUTS_DIR / "experiments"
            if exp_dir.exists():
                shutil.rmtree(exp_dir)
            # delete promoted params
            params_dir = OUTPUTS_DIR / "promoted_params"
            if params_dir.exists():
                shutil.rmtree(params_dir)
            # clear session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("All models deleted. Ready for fresh training.")
            st.rerun()
        else:
            st.error("Type RESET exactly to confirm.")


# --- Tabs ---------------------------------------------------------------------------------------------------------

tab_analysis, tab_experiments, tab_train, tab_manual = st.tabs([
    "ANALYSIS",
    "EXPERIMENTS",
    "TRAIN",
    "MANUAL",
])


# ----------------------------------------------------------------
# TAB 1 - BATCH TRAIN
# ----------------------------------------------------------------

with tab_train:
    st.header("Train Models")
    st.markdown(
        "Upload all daily Inverter Report and WMS Report files "
        "covering the full training period (3-6 months). "
        "Models will be trained for all ITC-INV sheets found in the files."
    )

    col1, col2 = st.columns(2)
    with col1:
        overwrite = st.checkbox(
            "Overwrite existing models",
            value=False,
            help="If unchecked, already trained inverters are skipped.",
        )
    with col2:
        tuning_method = st.radio(
            "Tuning method",
            ["Grid Search", "Optuna"],
            horizontal=True,
            help="Grid Search: exhaustive parameter combinations. Optuna: Bayesian optimization.",
        )
    
    if tuning_method == "Optuna":
        optuna_trials = st.slider(
            "Optuna trials",
            min_value=10,
            max_value=100,
            value=20,
            step=5,
            help="Number of hyperparameter combinations to evaluate",
        )
    else:
        optuna_trials = None
    
    # Check for promoted params
    promoted_params_dir = OUTPUTS_DIR / "promoted_params"
    promoted_params_files = list(promoted_params_dir.glob("*.json")) if promoted_params_dir.exists() else []
    promoted_params_files = [f for f in promoted_params_files if f.name != "active_params.json"]
    
    use_promoted = st.checkbox(
        "Use promoted model params",
        value=False,
        help="Use parameters from experiments tab instead of tuning",
    )
    
    if use_promoted and promoted_params_files:
        st.markdown("**Select promoted params to apply:**")
        col1, col2 = st.columns(2)
        
        with col1:
            selected_params_file = st.selectbox(
                "Available promoted params",
                options=promoted_params_files,
                format_func=lambda f: f.stem,
                key="promoted_params_select",
            )
            
            with open(selected_params_file) as f:
                promoted_params_data = json.load(f)
            
            st.info(
                f"**Label:** {promoted_params_data.get('label', 'N/A')}\n"
                f"**From:** {promoted_params_data.get('promoted_from', 'N/A')}\n"
                f"**Date:** {promoted_params_data.get('promoted_at', 'N/A')[:10]}"
            )
            
            apply_to_all = st.checkbox(
                "Apply to all inverters",
                value=True,
                help="If unchecked, you'll select per inverter after upload",
            )
    else:
        selected_params_file = None
        promoted_params_data = None
        apply_to_all = False
        if not promoted_params_files and use_promoted:
            st.warning("No promoted params available. Training will use tuning method selected above.")

    inv_files = file_collector("Inverter Report Files", "train_inv")
    wms_files = file_collector("WMS Report Files",      "train_wms")

    if st.button("Train", type="primary", key="btn_train"):
        st.session_state["train_inv_paths"] = inv_files
        st.session_state["train_wms_paths"] = wms_files
        st.session_state["train_results"]   = None
        st.session_state["train_blocked"]   = False
        st.session_state["train_tuning_method"] = tuning_method
        st.session_state["train_optuna_trials"] = optuna_trials
        st.session_state["train_promoted_params"] = promoted_params_data if use_promoted and promoted_params_data else None
        st.session_state["train_apply_to_all"] = apply_to_all

        with st.spinner("Training inverters - this may take several minutes..."):
            train_results = run_batch_train(
                inv_filepaths = inv_files,
                wms_filepaths = wms_files,
                overwrite     = overwrite,
                remove_faults = False,
                use_optuna    = (tuning_method == "Optuna"),
                optuna_trials = optuna_trials,
                promoted_params = st.session_state.get("train_promoted_params"),
                apply_to_all_promoted = st.session_state.get("train_apply_to_all", False),
            )
        st.session_state["train_results"] = train_results

        # check if any inverter was blocked
        any_blocked = any(r.get("blocked") for r in train_results.values())
        st.session_state["train_blocked"] = any_blocked

    # ---- Show results if available ----------------------------
    if st.session_state.get("train_results"):
        train_results = st.session_state["train_results"]

        # ---- Quality report for blocked inverters ----------------------------------------------------
        blocked_invs = [
            inv for inv, r in train_results.items() if r.get("blocked")
        ]
        if blocked_invs:
            st.markdown("---")
            st.subheader("Data Quality Issues Found")
            for itc_inv in blocked_invs:
                st.markdown(f"**{itc_inv.replace('_', '-')}**")
                show_quality_report(train_results[itc_inv]["quality_report"])

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
                            new_train_results = run_batch_train(
                                inv_filepaths    = inv_paths,
                                wms_filepaths    = wms_paths,
                                overwrite        = overwrite,
                                remove_faults    = True,
                                remove_low_days  = remove_low_days_train,
                                remove_oscillations_train = remove_oscillations_train,
                            )
                        st.session_state["train_results"] = new_train_results
                        st.session_state["train_blocked"] = False
                        st.rerun()
            else:
                st.info("Please clean your data and re-upload.")

        # ---- Training summary table --------------------------------------------------------------------------------
        non_blocked = {
            inv: r for inv, r in train_results.items() if not r.get("blocked")
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
# TAB 2 - EXPERIMENTS
# ----------------------------------------------------------------

with tab_experiments:
    st.header("Experiments - Find Best Model")
    st.markdown(
        "Train and compare models for a single inverter to find optimal "
        "hyperparameters, model type (XGBoost/LightGBM), and validation strategy. "
        "Save best model to registry for production use."
    )
    
    # --- Inverter selection -----------------------------------------------------------------------------
    selected_inv = st.selectbox(
        "Select Inverter",
        options=ITC_INV_LIST,
        index=0,
        key="experiment_selected_inv",
    )
    
    # --- Model selection --------------------------------------------------------------------------------
    col1, col2 = st.columns(2)
    with col1:
        model_type = st.selectbox(
            "Model Type",
            options=["xgboost", "lgbm"],
            index=0,
            key="experiment_model_type",
        )
    with col2:
        split_strategy = st.selectbox(
            "Split Strategy",
            options=["blocked"],
            index=0,
            key="experiment_split_strategy",
            help="Blocked split is recommended for production (most realistic)",
        )
    
    # --- Walk-forward settings --------------------------------------------------------------------------
    walk_forward = st.checkbox(
        "Walk-forward validation",
        value=True,
        key="experiment_walk_forward",
        help="Use rolling window validation for time-series robustness",
    )
    if walk_forward:
        n_folds = st.number_input(
            "Number of folds",
            min_value=2,
            max_value=10,
            value=5,
            key="experiment_n_folds",
            
        )
    
    # --- Hyperparameter grid ----------------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Hyperparameter Grid")
    
    if model_type == "xgboost":
        xgb_grid_size = st.radio(
            "XGBoost Grid Size",
            options=["Small", "Medium", "Large"],
            index=1,
            key="xgb_grid_size",
            help="Small: 8 combos (~20s) | Medium: 96 combos (~3 min) | Large: 864 combos (~8 min)",
        )
        lgbm_grid_size = "Medium"
    else:
        lgbm_grid_size = st.radio(
            "LightGBM Grid Size",
            options=["Small", "Medium", "Large"],
            index=1,
            key="lgbm_grid_size",
        )
        xgb_grid_size= "Medium"


    

     # --- Tuning method ------------------------------------------------------------------------------------
    st.markdown("---")
    tuning_method = st.radio(
        "Tuning Method",
        ["Grid Search", "Optuna"],
        horizontal=True,
        key="experiment_tuning_method",
        help="Grid Search: exhaustive search. Optuna: Bayesian optimization (faster, more efficient)",
    )
    
    # --- Upload files -----------------------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Upload Files")
    
    inv_files = file_collector(f"Inverter Report Files - {selected_inv}", "experiment_inv")
    wms_files = file_collector(f"WMS Report Files - {selected_inv}", "experiment_wms")
     
   
    
    # --- Run button -------------------------------------------------------------------------------------
    if both_uploaded(inv_files, wms_files):
        st.success(
            f"Received {len(inv_files)} inverter file(s) "
            f"and {len(wms_files)} WMS file(s)."
        )
        
        if st.button(" Run Experiment", type="primary", key="btn_experiment"):
            st.session_state["inv_paths"] = inv_files
            st.session_state["wms_paths"] = wms_files
            st.session_state["experiment_results"]   = None
            st.session_state["experiments_blocked"]   = False
            
            with st.spinner(f"Running experiment for {selected_inv} - this may take several minutes..."):
                exp_results = {selected_inv: run_experiment(
                    itc_inv=selected_inv,
                    inv_filepaths=inv_files,
                    wms_filepaths=wms_files,
                    model_type=model_type,
                    split_strategy=split_strategy,
                    walk_forward= walk_forward,
                    n_walk_folds=n_folds if walk_forward else 1,
                    remove_faults= False,
                    xgb_grid_size=xgb_grid_size,
                    lgbm_grid_size=lgbm_grid_size,
                    use_optuna=(tuning_method == "Optuna"),
                )}
            
            st.session_state["experiment_results"] = exp_results
            st.session_state["experiment_inv_paths"] = inv_files
            st.session_state["experiment_wms_paths"] = wms_files

            any_blocked = any(r.get("blocked") for r in exp_results.values())
            st.session_state["experiments_blocked"] = any_blocked

            
    
    # --- Show results if available ---------------------------------------------------------------------
    exp_results = st.session_state.get("experiment_results")
    if exp_results and selected_inv in exp_results:
        inv_exp_results = exp_results[selected_inv]
        st.caption(f"Result type: {type(inv_exp_results)} | Keys: {list(inv_exp_results.keys()) if isinstance(inv_exp_results, dict) else inv_exp_results}")
        

        blocked_invs = [
            inv for inv, r in exp_results.items() if r.get("blocked")
        ]
        if blocked_invs:
            st.markdown("---")
            st.subheader("Data Quality Issues Found")
            for itc_inv in blocked_invs:
                st.markdown(f"**{itc_inv.replace('_', '-')}**")
                show_quality_report(exp_results[itc_inv]["quality_report"])

            st.markdown("---")
            st.markdown("**What would you like to do?**")
            auto_remove_exp = st.checkbox(
                "Auto-remove faulty rows and proceed with training",
                key="auto_remove_exp",
                help=(
                    "Faulty rows will be removed automatically before training. "
                    "Check the quality report above to understand what will be removed."
                ),
            )
            if auto_remove_exp:
                remove_low_days_exp = st.checkbox(
                    "Also remove full low-output days",
                    value=True,
                    key="remove_low_days_exp",
                    help=(
                        "If checked, entire days where max power was below 10% of normal are removed. "
                        "If unchecked, only individual trip rows and oscillating rows are removed."
                    ),
                )
                remove_oscillations_exp = st.checkbox(
                    "Also remove oscillating/unstable power periods",
                    value=False,
                    key="remove_oscillations_exp",
                    help=(
                        "If checked, periods where power fluctuated rapidly during high GII are removed. "
                        "Note: cloud edge effects can look like oscillations — use with caution."

                    ),
                )

                if st.button(
                    "Proceed with Auto-removal",
                    type="primary",
                    key="btn_train_auto_exp",
                ):
                    inv_paths = st.session_state.get("experiment_inv_paths", [])
                    wms_paths = st.session_state.get("experiment_wms_paths", [])

                    if not inv_paths or not wms_paths:
                        st.error("File paths lost — please re-upload your files and try again.")
                    else:
                        with st.spinner("Removing faulty rows and running experiment..."):
                            new_exp_results = {selected_inv: run_experiment(
                                itc_inv          = selected_inv,
                                inv_filepaths    = inv_paths,
                                wms_filepaths    = wms_paths,
                                remove_faults    = True,
                                remove_low_days  = remove_low_days_exp,
                                walk_forward= walk_forward,
                                n_walk_folds= n_folds if walk_forward else 1,
                                remove_oscillations = remove_oscillations_exp,
                                xgb_grid_size=xgb_grid_size,
                                lgbm_grid_size=lgbm_grid_size,
                                use_optuna=(tuning_method == "Optuna"),
                            )}
                        st.session_state["experiment_results"] = new_exp_results
                        st.session_state["experiment_blocked"] = False
                        st.rerun()
            else:
                st.info("Please clean your data and re-upload.")
        
        st.markdown("---")
        st.subheader("Experiment Results")

        exp_result = inv_exp_results
        if exp_result.get("passed"):
            st.markdown(f"**{model_type.upper()} | {split_strategy.upper()}**")

            col1, col2, col3 = st.columns(3)
            col1.metric("Train RMSE", f"{exp_result['train_metrics']['rmse']:.2f} kW")
            col2.metric("Val RMSE",   f"{exp_result['val_metrics']['rmse']:.2f} kW")
            col3.metric("Test RMSE",  f"{exp_result['test_metrics']['rmse']:.2f} kW")

            ac_capacity = AC_CAPACITY.get(selected_inv, 4400)
            st.caption(
                f"Test RMSE as % of rated capacity: "
                f"{exp_result['test_metrics']['rmse'] / ac_capacity * 100:.2f}%  |  "
                f"Walk-forward RMSE: "
                f"{exp_result['summary'].get('fold_metrics', {}).get('mean', 0) / ac_capacity * 100:.2f}%"
            )

            col4, col5, col6 = st.columns(3)
            col4.metric("Train R²", f"{exp_result['train_metrics']['r2']:.4f}")
            col5.metric("Val R²",   f"{exp_result['val_metrics']['r2']:.4f}")
            col6.metric("Test R²",  f"{exp_result['test_metrics']['r2']:.4f}")

            st.markdown("**Best Hyperparameters**")
            best_params = exp_result.get("best_params", {})
            if best_params:
                params_df = pd.DataFrame(
                    list(best_params.items()),
                    columns=["Parameter", "Value"]
                )
                params_df["Value"] = params_df["Value"].astype(str)
                st.dataframe(params_df, width="stretch")

            st.caption(f"Grid search explored {exp_result.get('grid_search_size', 'N/A')} combinations")

            if exp_result.get("overfitting_issues"):
                st.warning("Potential overfitting detected:")
                for issue in exp_result["overfitting_issues"]:
                    st.caption(f"  - {issue}")

            plots = exp_result.get("plots", {})
            if plots.get("predictions") and Path(plots["predictions"]).exists():
                st.image(plots["predictions"], caption="Predictions vs Actual")
            if plots.get("residuals") and Path(plots["residuals"]).exists():
                st.image(plots["residuals"], caption="Residual Distribution")

            st.markdown("---")
            st.subheader("Save Model")
            
            col_label, col_action = st.columns([3, 1])
            with col_label:
                label = st.text_input(
                    "Label for model", 
                    value=f"{model_type}_v1", 
                    key="experiment_label"
                )
            
            col_save, col_declare = st.columns(2)
            
            with col_save:
                if st.button("Save to Registry", key="btn_save_registry", help="Save model for future comparison"):
                    try:
                        from experiments.selection import promote_model
                        promoted_path = promote_model(
                            experiment_tag = exp_result["experiment_tag"],
                            label          = label,
                            itc_inv        = selected_inv,
                            overwrite      = False,
                        )
                        st.success(f"Model saved to registry: {label}")
                    except Exception as e:
                        st.error(f"Save failed: {e}")
            
            with col_declare:
                if st.button("Declare as Trained", key="btn_declare_trained", help="Move to production as trained model for this inverter"):
                    try:
                        from experiments.selection import promote_model
                        from core.model import save_model as save_prod_model
                        import joblib
                        
                        # Move experimental model to production
                        promoted_path = promote_model(
                            experiment_tag = exp_result["experiment_tag"],
                            label          = label,
                            itc_inv        = selected_inv,
                            overwrite      = True,  # This will be for production
                            declare_as_trained = True,
                        )
                        st.success(f"Model declared as trained for {selected_inv}")
                        st.info(f"Saved to: {promoted_path}")
                    except Exception as e:
                        st.error(f"Declaration failed: {e}")

        elif exp_result.get("blocked"):
            pass  # already handled above

        else:
            st.error("Experiment failed.")
            for err in exp_result.get("errors", []):
                st.error(err)
        
       
# ----------------------------------------------------------------
# TAB 3 - ANALYSIS
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
                analysis_results = run_batch_analysis(
                    inv_filepaths = inv_paths,
                    wms_filepaths = wms_paths
                )

            st.session_state["batch_analysis_results"] = analysis_results

    # --- Summary table --------------------------------------------------------------------------------
    analysis_results = st.session_state.get("batch_analysis_results")
    if analysis_results:
        st.markdown("---")
        st.subheader("Fleet Summary")

        summary_rows = []
        for itc_inv, r in analysis_results.items():
            if not isinstance(r,dict):
                continue
            if r.get("skipped"):
                summary_rows.append({
                    "Inverter": itc_inv.replace("_", "-"),
                    "Status":   " Not trained",
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
            inv for inv, r in analysis_results.items()
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
            r = analysis_results[selected]

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


# - TAB 4 IMPLEMENTATION

with tab_manual:
    st.header("Operational Manual")
    st.markdown("---")

    # ---- System Overview -----------------------------------------------------
    st.subheader("1. Project Overview")
    st.markdown("""
    
    This **Solar Digital Twin** uses Machine Learning to create a "digital twin" of a healthy inverter. By looking at real-time weather data (sunlight and temperature), the model calculates exactly how much electricity the inverter *should* be producing right now if it were perfectly healthy. 
    
    By comparing this **Predicted Power** against the actual **Measured Power**, the application immediately catches underperformance, flags anomalies, and uses AI diagnostics to explain exactly what went wrong.
    """)

    st.markdown("---")

    # ---- Key Concepts Explained ----------------------------------------------
        
    st.markdown("""
    ### Data Quality & Preprocessing Checks
    The model is only as good as the data it trains on. If you train a digital twin on "faulty" data (e.g., a day where an inverter was broken), the model will learn that low power output is "normal" for that weather. To prevent this, the system automatically scans your uploaded files for three common data checks before starting:
    """)

    ### Automated Pre-Cleaning
    st.markdown("""
        To prevent the model from learning "bad behaviors," the training pipeline automatically scans your uploads and blocks training if it finds these common errors:
1. Inverter Trips: Timestamps where the sun is shining brightly ($GII>300\\text{ W/m}^2$) but power output is zero ($<100\\text{ kW}$)
2. Power Oscillations: Periods where the output fluctuates wildly ($>500\\text{ kW}$ in a span of  10 minutes) during steady clear skies.
3.  Low Output Days: Complete days where an inverter was offline or limited below 10% .


    #### Overcoming Blocks
    When the system identifies these patterns, it blocks the training process and flags the specific timestamps for your review. You have two primary options:
    
    1. **Manual Cleanup:** Use the provided timestamp report to identify the exact rows in your Excel sheets, delete them, and re-upload the cleaned files. This is the most accurate method.
    2. **Auto-Removal:** If the error count is small, you can check the **"Auto-remove faulty rows"** box. The system will perform an internal filter—dropping only the specific minutes/days flagged—so you can proceed with training without manual spreadsheet editing.
    3. Cross checking the files manually with the automated quality checks would be more suitable for data quality as, automated oscilalting checks wouldnt be able to identify between cloud cover or genuine failure.

    By removing noise, we force the model to focus purely on the relationship between high irradiance and peak power, making the resulting anomaly detection much more sensitive and accurate.
    """)
    
    


    st.markdown("""
    ### Data Filtering 
    To ensure the model learns from consistent, high-quality solar irradiance data, the system applies these strict filters during load:
    * **Time Window:** Data is pruned to strictly between **06:00 and 19:00**. Outside this range, GII is too low for reliable power-to-irradiance modeling.
    * **Irradiance Threshold:** Rows where **GII ≤ 20 W/m²** are dropped. This removes night-time noise and early-dawn/dusk periods where the inverter is not in an active power-conversion state.
    """)
    st.markdown("""
    ### Data Splitting 
     * **Blocked Split:**
    The Blocked Split divides your dataset into three distinct, chronological chunks: 
                
        **Training (Past) → Validation (Buffer) → Test (Future).**
    
        It mimics how the system will behave tomorrow. It preserves the natural flow of time, ensuring no future data leaks into the past.

   * **Walk-Forward Validation:** 
    Walk-Forward Validation treats timestamps like a sliding window, performing multiple training and testing passes across the timeline.
    
        It trains on a "window" of past data and tests on the immediate next period. Then, it "slides" the window forward, adding the previous test data to the training set, and tests on a new future period.
                
        If a model performs perfectly on a single split but fails during Walk-Forward Validation, it suggests the model is fragile and sensitive to seasonal weather changes.
    """)

    st.markdown("""
    ### Machine Learning Models, Tuners & Tools
    * **XGBoost (Extreme Gradient Boosting):** A highly powerful algorithm that builds an ensemble of decision trees step-by-step to predict inverter power based on weather variables.
    * **LightGBM (Light Gradient Boosting Machine):** A faster, memory-efficient variation of gradient boosting designed to handle massive datasets quickly by growing trees vertically rather than horizontally.
    * **Grid Search:** A traditional tuning method that exhaustively tests a small, manually predefined list of model settings one by one. It is slow but highly predictable.
    * **Optuna:** An intelligent AI tuning engine that automatically runs quick training trials, guesses which hyperparameter settings will look best based on past history, and cuts off bad trials early to save laptop processing power.
    * **Walk-Forward Validation:** A time-series evaluation technique where the model trains on past data and tests on the immediate following weeks, safely simulating real-world production performance without leaking future data.
    
    * **SHAP Explainability:** SHAP Explainability comes under Explainable AI (XAI), it uses SHAPLEY values derived from game theory to break down exactly how much each sensor (like string voltage or temperature) pushed the model's power prediction up or down, allowing you to pinpoint the root cause of a performance drop.
    """)
    
    
    # Error Metrics Definitions
    st.markdown("""
    ### Performance & Accuracy Metrics
    * **RMSE (Root Mean Square Error):** The average prediction error of the model in kW. Because it squares errors before averaging, it penalizes large, sudden misses heavily.
        * *RMSE as % of Rated Capacity:* Compared against the **4,400 kW** inverters, an RMSE of 44 kW is exactly **1% of capacity** (Excellent). Errors under 110 kW (2.5%) are highly reliable. Values over 200 kW mean the data used was too messy or filled with old faults.
    * **MAE (Mean Absolute Error):** The average absolute error between predicted and actual power. Unlike RMSE, it treats all errors linearly without heavily penalizing single large spikes.
    * **MAPE (Mean Absolute Percentage Error):** Measures error as a percentage of the actual value. However, it breaks down or goes to infinity when actual solar power output drops close to zero (like during early mornings or evenings).
    * **sMAPE (Symmetric Mean Absolute Percentage Error):** The modified percentage metric **used in this project**. It binds percentage errors between 0% and 200%, preventing zero-power calculations from breaking your metrics during low-light hours.
    * **R² (R-Squared / Coefficient of Determination):** Explains how much of the inverter's power variance is successfully captured by the weather data. It scales from 0.0 to 1.0, where **1.0 is a perfect fit**. A value above 0.95 means your digital twin is incredibly accurate.
    """)
    
    # Thresholds Explanation
    st.markdown("""
    ### Anomaly Tracking Thresholds            
    When a model is trained on clean data, it still makes tiny, random prediction errors. We take these healthy past errors and sort them into percentiles to set our alarm boundaries for the **Residual** (Actual Power minus Predicted Power).
    
    * **p50 (50th Percentile / Median):** The mid-point baseline error of a perfectly normal day. Actual output matches expectations smoothly.
    * **p5 (5th Percentile — Warning Boundary):** Only 5% of healthy historical data had errors this low. If the inverter falls below this line for **10 consecutive minutes**, it triggers a **🟠 Warning**. Indicates minor losses like dust buildup, partial tree/structure shadows, or a single degrading string.
    * **p1 (1st Percentile — Anomaly Boundary):** An extreme error that should almost never happen on a healthy day (only 1% of the cleanest data touches this). If the inverter drops past this line for **5 consecutive minutes**, it triggers a **🔴 Anomaly**. This means a serious fault has occurred, such as a blown string fuse, a complete string dropout, or an inverter trip.
    """)

    

                
    st.markdown("---")

    # ---- Tab 1: Analysis -----------------------------------------------------
    with st.expander(" 2. ANALYSIS TAB  ", expanded=False):
        st.markdown("""
        ### Purpose
        Upload recent data (1-2 weeks or a single day) to let the system score your current operations and look for faults.

        ### What to Upload
        1. **Inverter Report Files:** Daily Excel sheets containing the inverter's electrical measurements (DC string currents, AC grid voltages, power output).
        2. **WMS Report Files:** Daily Excel sheets from the Weather Monitoring Station containing sunlight levels (GHI, GII) and ambient temperatures.

        ### Summary Table
        Once executed, the dashboard grades your assets using a simple grid:
        * **Status:** Shows a quick status badge (**🟢 Normal**, **🟠 Warning**, or **🔴 Anomaly**) based on the threshold rules explained above.
        * **Normal / Warning / Anomaly Columns:** Shows the exact number of minutes the inverter spent in each state during the uploaded period.
        * **Mean Residual:** The average power loss over the entire period. For example, a Mean Residual of `-15 kW` means that, on average, the inverter produced 15 kW less than it was fully capable of across the week.

        ### Charts & Plots
        * **Time vs Power Plot:** A timeline graph. Look for sudden drops to red lines (trips/fuses) vs gradual downward trends over days (dirt buildup).
        * **GII vs Power Scatter Plot:** Shows how power behaves at different sunlight levels. If the output drops below the prediction line *only* during peak afternoon sun, the inverter is likely overheating (thermal derating) or clipping power.
        * **SHAP Diagnosis Panel:** Breaks down the source of the issue. If the AI points to **DC Strings**, send a technician to check string cards, fuses, or panels. If it highlights **AC Electrical**, the issue is a grid voltage imbalance or terminal connection problem.
        """)

    # ---- Tab 2: Experiments --------------------------------------------------
    with st.expander(" 3. EXPERIMENTS TAB ", expanded=False):
        st.markdown("""
        ### Purpose
        An engineering workspace to test different settings, tuning methods, and models on a single inverter before pushing them to the live sidebar.

        ### Hyperparameter Tuning Frameworks
        * **Grid Search:** Runs through a predefined combinations list. Safe, consistent, but slow.
        * **Optuna:** An intelligent AI tuning engine. It evaluates trial metrics, hooks them directly into active trial pruning, and cuts off bad runs instantly using a `MedianPruner` loop to save processing time.

        ### Pushing to Production
        * **Save to Registry:** Saves the model as a backup candidate under a custom version name.
        * **Declare as Trained:** Finalizes your work. It copies the model weights into the active system slot, updates the sidebar state, and sets up the new `metadata.json` boundaries.
        """)

    # ---- Tab 3: Train --------------------------------------------------------
    # app.py — TRAIN TAB MANUAL SECTION

    with st.expander(" 4. TRAIN TAB", expanded=False):
        st.markdown("""
        ### Purpose
        Builds the initial digital twin for new inverters. Use this to establish a performance baseline using 3-6 months of historical data.

        ### Control Panel Reference
        | Control | Function | Technical Purpose |
        | :--- | :--- | :--- |
        | **Data Source Input** | Text box for folder paths or drag-and-drop file uploader. | Aggregates and merges Inverter and WMS weather reports for training. |
        | **Overwrite Models** | Checkbox toggle. | If unchecked, the system ignores inverters that already have a model. If checked, it forces a hard re-train, replacing existing binaries. |
        | **Tuning Method** | Radio selector: **Grid Search** vs **Optuna**. | Selects the hyperparameter optimization engine. |
        | **Optuna Trials** | Slider (10-100). | Sets the optimization budget. |
        | **Promoted Params** | Selector for `.json` files. | Injects a pre-verified configuration from the Experiments tab. |
        | **Apply to All** | Checkbox toggle. | When checked, forces the selected **Promoted Params** file to be used for *every* inverter in the batch, skipping individual tuning loops. |
        | **Train Button** | Execution trigger. | Starts data cleaning, filtering, and the training search engine. |

        ---

        ### Operational Logic & Workflow Rules

        * **Applying Promoted Parameters:** If you have developed a "Champion" configuration in the *Experiments* tab, select the parameter file in the **Promoted Params** dropdown. By checking **"Apply to all"**, you bypass the time-consuming tuning loop for the entire batch, forcing all inverters to adopt that verified configuration immediately.

        * **Analysis Tab Dependency:**  **CRITICAL:** The Analysis tab exclusively uses inverters with a **"Trained"** status. 
            If an inverter is not found in the production registry (or shows "-- Not trained yet" in the sidebar), the Analysis tab will ignore it. This prevents confusion and stops the system from attempting to infer data for uninitialized assets.

        * **Sidebar Synchronization:** Upon successful training, the system updates the production registry (`outputs/ITC_INV/model.joblib`) and generates the required `metadata.json`. The sidebar status badge will automatically shift to green, signaling that the asset is now eligible for global fleet analysis.

        
        """)

    # ---- System Maintenance --------------------------------------------------
    with st.expander(" 5. SIDEBAR STATUS & SYSTEM MAINTENANCE", expanded=False):
        st.markdown("""
        ### Sidebar Status Meanings
        * **Trained | Last: 2026-06-02 | RMSE: 32.1 kW:** The digital twin is active, highly accurate (under 1.1% capacity error), and actively protecting that inverter.
        * **-- Not trained yet:** No model exists for this asset. It will be ignored during global analysis loops until initialized in the Train tab.

        ### The RESET Button
        Located at the bottom of the sidebar under a strict confirmation toggle. Typing **RESET** and clicking the button completely deletes all trained model files, cleans out the dashboard cache, and clears the registry for a fresh setup. Use with extreme caution.
                    """)                       


        
