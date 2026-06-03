# pipelines/batch_pipeline.py

import logging
from datetime import datetime
from pathlib import Path
from typing import List

from config.settings import ITC_INV_LIST, OUTPUTS_DIR
from core.model import model_status
from pipelines.train_pipeline import run as run_train
from pipelines.analysis_pipeline import run as run_analysis

import traceback


log = logging.getLogger(__name__)


def run_batch_train(
    inv_filepaths: List,
    wms_filepaths: List,
    overwrite:     bool = False,
    remove_faults: bool = False,
    remove_low_days: bool = True,
    remove_oscillations_train: bool = False,
    use_optuna: bool = False,
    optuna_trials: int = 20,
    promoted_params: dict = None,
    apply_to_all_promoted: bool = False,
) -> dict:
    """
    Train models for all ITC-INV found in uploaded files.
    Skips already trained models unless overwrite=True.
    
    Logic:
    - If model exists and overwrite=False → skip
    - If model exists and overwrite=True:
      - If promoted_params exist → use them
      - Else if use_optuna=True → Optuna tuning
      - Else → grid search
    - If model doesn't exist:
      - If promoted_params exist → use them
      - Else if use_optuna=True → Optuna tuning
      - Else → grid search

    Returns:
        {
            itc_inv: {
                "skipped"  : bool,
                "reason"   : str,
                "passed"   : bool,
                "errors"   : list,
                "warnings" : list,
                "val_metrics"  : dict,
                "test_metrics" : dict,
                "duration_sec" : float,
            }
        }
    """
    log.info("=" * 60)
    log.info("Batch Train Pipeline")
    log.info("=" * 60)

    results = {}

    for itc_inv in ITC_INV_LIST:
        log.info(f"\n-- {itc_inv} ----------------------------------------")

        # Check for declared trained model from experiments
        label_params_path = OUTPUTS_DIR / "promoted_params" / f"{itc_inv}_*.json"
        labels_from_exp = list(OUTPUTS_DIR.glob(f"promoted_params/{itc_inv}_*.json"))
        labels_from_exp = [f for f in labels_from_exp if f.name != "active_params.json"]
        
        # Check if model exists in production
        status = model_status(itc_inv)
        
        # Handle train logic
        if labels_from_exp and not overwrite:
            # Model exists in experiments but not in production - skip
            log.info(f"  Skipping {itc_inv} - already declared trained from experiments")
            results[itc_inv] = {
                "skipped": True,
                "reason":  f"Already declared trained for {itc_inv}. "
                           f"Enable overwrite to retrain.",
                "passed":  None,
            }
            continue
        elif status["trained"] and not overwrite:
            log.info(f"  Skipping {itc_inv} - already trained")
            results[itc_inv] = {
                "skipped": True,
                "reason":  f"Already trained on {status['last_trained'][:10]}. "
                           f"Enable overwrite to retrain.",
                "passed":  None,
            }
            continue
        try:
            # Check if this inverter has a declared trained model from experiments
            declared_model_path = OUTPUTS_DIR / "models" / itc_inv / "model.pkl"
            if declared_model_path.exists() and not overwrite:
                # This inverter has a declared trained model - skip training
                log.info(f"  Skipping {itc_inv} - has declared trained model from experiments")
                results[itc_inv] = {
                    "skipped": True,
                    "reason":  f"Declared as trained from experiments. "
                               f"Enable overwrite to retrain.",
                    "passed":  None,
                    " declared_trained_from": itc_inv,
                }
                continue
            
            # Determine which promoted params to use (if any)
            inv_promoted_params = None
            if promoted_params:
                if apply_to_all_promoted:
                    inv_promoted_params = promoted_params
                else:
                    # Per-inverter selection would happen in UI (future enhancement)
                    # For now, if not apply_to_all, don't use promoted params
                    inv_promoted_params = None

            result = run_train(
                itc_inv       = itc_inv,
                inv_filepaths = inv_filepaths,
                wms_filepaths = wms_filepaths,
                remove_faults = remove_faults,
                remove_low_days = remove_low_days,
                remove_oscillations = remove_oscillations_train,
                use_optuna = use_optuna,
                optuna_trials = optuna_trials,
                promoted_params = inv_promoted_params,
            )
            result["skipped"] = False
            results[itc_inv]  = result

            if result.get("blocked"):
                log.warning(f"  {itc_inv} blocked - data quality issues found")
            elif result["passed"]:
                log.info(
                    f" {itc_inv} trained -"
                    f"test RMSE: {result['test_metrics']['rmse']:.2f} kW"
                )
            else:
                log.warning(f"  {itc_inv} failed - {result['errors']}\n{result.get('traceback', '')}")
        except Exception as e:
            log.error(f"  {itc_inv} crashed:\n{traceback.format_exc()}")
            results[itc_inv] = {
                "passed":   False,
                "skipped":  False,
                "errors":   [str(e)],
                "warnings": [],
            }

    return results




def run_batch_analysis(
    inv_filepaths: List,
    wms_filepaths: List,
) -> dict:
    """
    Run analysis for all trained ITC-INV.
    Skips untrained inverters.

    Returns:
        {
            itc_inv: {
                "skipped"      : bool,
                "reason"       : str,
                "passed"       : bool,
                "errors"       : list,
                "warnings"     : list,
                "report"       : dict,
                "shap_results" : dict,
                "plot_time"    : Path,
                "plot_gii"     : Path,
                "plot_anomaly" : Path,
                "total_rows"   : int,
                "duration_sec" : float,
            }
        }
    """
    log.info("=" * 60)
    log.info("Batch analysis Pipeline")
    log.info("=" * 60)

    results = {}

    for itc_inv in ITC_INV_LIST:
        log.info(f"\n-- {itc_inv} ---------------------------------------")

        status = model_status(itc_inv)
        if not status["trained"]:
            log.info(f"  Skipping {itc_inv} - not trained yet")
            results[itc_inv] = {
                "skipped": True,
                "reason":  "No trained model found. Train first.",
                "passed":  None,
            }
            continue

        result = run_analysis(
            itc_inv       = itc_inv,
            inv_filepaths = inv_filepaths,
            wms_filepaths = wms_filepaths,
        )
        result["skipped"] = False
        results[itc_inv]  = result

        if result["passed"]:
            log.info(
                f"  {itc_inv} analysis complete - "
                f"anomaly: {result['report']['anomaly_count']} | "
                f"warning: {result['report']['warning_count']}"
            )
        else:
            log.warning(f"  {itc_inv} failed - {result['errors']}")

    return results


