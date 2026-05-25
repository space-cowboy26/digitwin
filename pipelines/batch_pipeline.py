# pipelines/batch_pipeline.py

import logging
from datetime import datetime
from pathlib import Path
from typing import List

from config.settings import ITC_INV_LIST
from core.model import model_status
from pipelines.train_pipeline import run as run_train
from pipelines.analysis_pipeline import run as run_inference
from pipelines.retrain_pipeline import run as run_retrain

import traceback


log = logging.getLogger(__name__)


def run_batch_train(
    inv_filepaths: List,
    wms_filepaths: List,
    overwrite:     bool = False,
    remove_faults: bool = False,
    remove_low_days: bool =True,
    remove_oscillations_train: bool = False,
) -> dict:
    """
    Train models for all ITC-INV found in uploaded files.
    Skips already trained models unless overwrite=True.

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

        # check if already trained
        status = model_status(itc_inv)
        if status["trained"] and not overwrite:
            log.info(f"  Skipping {itc_inv} - already trained")
            results[itc_inv] = {
                "skipped": True,
                "reason":  f"Already trained on {status['last_trained'][:10]}. "
                           f"Enable overwrite to retrain.",
                "passed":  None,
            }
            continue
        try:

            result = run_train(
                itc_inv       = itc_inv,
                inv_filepaths = inv_filepaths,
                wms_filepaths = wms_filepaths,
                remove_faults = remove_faults,
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




def run_batch_inference(
    inv_filepaths: List,
    wms_filepaths: List,
) -> dict:
    """
    Run inference for all trained ITC-INV.
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
    log.info("Batch Inference Pipeline")
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

        result = run_inference(
            itc_inv       = itc_inv,
            inv_filepaths = inv_filepaths,
            wms_filepaths = wms_filepaths,
        )
        result["skipped"] = False
        results[itc_inv]  = result

        if result["passed"]:
            log.info(
                f"  {itc_inv} inference complete - "
                f"anomaly: {result['report']['anomaly_count']} | "
                f"warning: {result['report']['warning_count']}"
            )
        else:
            log.warning(f"  {itc_inv} failed - {result['errors']}")

    return results


def run_batch_retrain(
    inv_filepaths: List,
    wms_filepaths: List,
    remove_faults: bool = False,
    remove_low_days: bool = True,
    remove_oscillations: bool = False,
) -> dict:
    """
    Retrain models for all trained ITC-INV.
    Skips untrained inverters.

    Returns:
        {
            itc_inv: {
                "skipped"         : bool,
                "reason"          : str,
                "passed"          : bool,
                "errors"          : list,
                "warnings"        : list,
                "previous_rmse"   : float,
                "new_rmse"        : float,
                "rmse_change_pct" : float,
                "model_saved"     : bool,
                "duration_sec"    : float,
            }
        }
    """
    log.info("=" * 60)
    log.info("Batch Retrain Pipeline")
    log.info("=" * 60)

    results = {}

    for itc_inv in ITC_INV_LIST:
        log.info(f"\n-- {itc_inv} ----------------------------------------")

        status = model_status(itc_inv)
        if not status["trained"]:
            log.info(f"  Skipping {itc_inv} - not trained yet")
            results[itc_inv] = {
                "skipped": True,
                "reason":  "No trained model found. Train first.",
                "passed":  None,
            }
            continue
        try:
            result = run_retrain(
                itc_inv       = itc_inv,
                inv_filepaths = inv_filepaths,
                wms_filepaths = wms_filepaths,
                remove_faults = remove_faults,
            )
            result["skipped"] = False
            results[itc_inv]  = result

            if result.get("blocked"):
                log.warning(f"  {itc_inv} blocked - data quality issues found")
            elif result["passed"]:
                log.info(
                    f"  {itc_inv} retrained - "
                    f"new RMSE: {result['new_rmse']:.2f} kW | "
                    f"saved: {result['model_saved']}"
                )
            else:
                log.warning(f"  {itc_inv} failed - {result['errors']}")

        except Exception as e:
            log.error(f"  {itc_inv} crashed:\n{traceback.format_exc()}")
            results[itc_inv] = {
                "passed":   False,
                "skipped":  False,
                "errors":   [str(e)],
                "warnings": [],
            }

    return results