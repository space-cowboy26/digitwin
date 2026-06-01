# experiments/selection.py

import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from datetime import datetime

from experiments.registry import ModelRegistry, get_registry
from experiments.tracker import ExperimentTracker, compute_metrics

import json

from config.settings import OUTPUTS_DIR

log = logging.getLogger(__name__)


# -- Constants ------------------------------------------------------------------

PRIORITY_METRICS = ["rmse"]  # Primary metric for ranking
SECONDARY_METRICS = ["mae", "smape", "r2"]  # Used for tie-breaking


# -- Selection Logic ------------------------------------------------------------

def calculate_score(metrics: dict, weights: dict = None) -> float:
    """
    Calculate composite score for model comparison.
    Lower is better for RMSE, MAE, SMAPE; higher is better for R².
    """
    if weights is None:
        weights = {
            "rmse": 1.0,
            "mae": 0.5,
            "smape": 0.5,
            "r2": -0.3,  # Negative because higher R² is better
        }
    
    score = 0
    for metric, weight in weights.items():
        value = metrics.get(metric, 0)
        if metric == "r2":
            score += weight * value  # R²: higher is better, weight is negative
        else:
            score += weight * value  # RMSE/MAE/SMAPE: lower is better
    
    return score


def select_best_model(
    models: List[dict],
    priority_metric: str = "rmse",
    allow_min_drop: float = 0.0,  # Minimum improvement required
) -> Optional[dict]:
    """
    Select best model from list by priority metric.
    
    Args:
        models: List of model info dicts from registry query
        priority_metric: Primary metric (e.g., "rmse")
        allow_min_drop: Minimum improvement required (percentage)
    
    Returns:
        Best model info dict or None
    """
    if not models:
        return None
    
    # Sort by priority metric (ascending for RMSE, MAE, SMAPE)
    ascending = priority_metric not in ["r2"]
    sorted_models = sorted(
        models,
        key=lambda x: x.get(priority_metric, float("inf")),
        reverse=not ascending
    )
    
    best = sorted_models[0]
    
    # Check minimum improvement
    if allow_min_drop > 0 and len(sorted_models) > 1:
        worst = sorted_models[-1]
        if priority_metric in ["rmse", "mae", "smape"]:
            improvement = (worst[priority_metric] - best[priority_metric]) / worst[priority_metric] * 100
            if improvement < allow_min_drop:
                log.warning(
                    f"Best model {best.get('experiment_tag')} only {improvement:.1f}% "
                    f"better than worst - consider collecting more data"
                )
    
    return best


def compare_models(
    models: List[dict],
    metrics_to_compare: List[str] = None,
) -> List[dict]:
    """
    Compare models across multiple metrics and rank them.
    
    Returns list with added 'rank' field.
    """
    if metrics_to_compare is None:
        metrics_to_compare = PRIORITY_METRICS + SECONDARY_METRICS
    
    # Calculate composite score for each model
    for model in models:
        metrics = model.get("test_metrics", {})
        score = calculate_score(metrics)
        model["score"] = score
    
    # Sort by score (lower is better due to negative R² weight)
    models_sorted = sorted(models, key=lambda x: x.get("score", float("inf")))
    
    # Add ranks
    for i, model in enumerate(models_sorted):
        model["rank"] = i + 1
    
    return models_sorted


def check_overfitting(
    train_metrics: dict,
    val_metrics: dict,
    test_metrics: dict,
    thresholds: dict = None,
) -> Tuple[bool, List[str]]:
    """
    Check for overfitting by comparing train, validation, and test performance.
    
    Returns:
        Tuple of (is_overfitting: bool, issues: List[str])
    """
    if thresholds is None:
        thresholds = {
            "val_gap_pct": 50,  # Val vs train gap %
            "test_gap_pct": 100,  # Test vs val gap %
            "r2_min": 0.90,
            "rmse_max_pct": 0.20,  # Max RMSE as % of mean
        }
    
    issues = []
    
    # RMSE thresholds
    train_rmse = train_metrics.get("rmse", 0)
    val_rmse = val_metrics.get("rmse", 0)
    test_rmse = test_metrics.get("rmse", 0)
    
    # Validation vs training gap (overfitting indicator)
    if train_rmse > 0:
        val_gap = (val_rmse - train_rmse) / train_rmse * 100
        if val_gap > thresholds["val_gap_pct"]:
            issues.append(
                f"Validation RMSE {val_gap:.1f}% higher than training - possible overfitting"
            )
    
    # Test vs validation gap (data shift indicator)
    if val_rmse > 0:
        test_gap = (test_rmse - val_rmse) / val_rmse * 100
        if test_gap > thresholds["test_gap_pct"]:
            issues.append(
                f"Test RMSE {test_gap:.1f}% higher than validation - possible data shift"
            )
    
    # R² thresholds
    train_r2 = train_metrics.get("r2", 0)
    if train_r2 < thresholds["r2_min"]:
        issues.append(f"Training R² {train_r2:.3f} below minimum {thresholds['r2_min']}")
    
    # High absolute error
    if train_rmse > 0:
        pass
        # Would need target mean to check RMSE as % of mean - skip for now
    
    is_overfitting = len(issues) > 0
    return is_overfitting, issues


def recommend_hyperparams(
    grid_search_results: List[dict],
    top_n: int = 5,
) -> dict:
    """
    Extract recommended hyperparameters from top grid search results.
    
    Returns dictionary with recommended params and confidence level.
    """
    if not grid_search_results:
        return {}
    
    # Get top N
    top_results = sorted(
        grid_search_results,
        key=lambda x: x.get("val_rmse", float("inf"))
    )[:top_n]
    
    # Count param occurrences
    param_counts = {}
    for result in top_results:
        params = result.get("params", {})
        for key, value in params.items():
            param_key = f"{key}_{value}"
            param_counts[param_key] = param_counts.get(param_key, 0) + 1
    
    # Most common params
    recommended = {}
    for param_key, count in param_counts.items():
        if count >= top_n / 2:  # At least 50% of top N agree
            param_name, param_value = param_key.rsplit("_", 1)
            # Convert back to appropriate type
            try:
                if "." in param_value or "e" in param_value:
                    recommended[param_name] = float(param_value)
                else:
                    recommended[param_name] = int(param_value)
            except ValueError:
                recommended[param_name] = param_value
    
    # Confidence level
    confidence = len(recommended) / len(top_results[0].get("params", {})) if top_results else 0
    
    return {
        "recommended_params": recommended,
        "confidence": confidence,
        "n_agreeing": {k: param_counts.get(f"{k}_{v}") for k, v in recommended.items()},
    }


def find_best_model_for_complexity(
    registry: ModelRegistry,
    complexity_level: str = "standard",
) -> Optional[dict]:
    """
    Find best model considering data complexity.
    
    Complexity levels:
    - "standard": Current production-grade models
    - "enhanced": Models with additional features or hyperparameter tuning
    - "advanced": Complex models (ensembles, DL) - future use
    
    Returns best model for the given complexity threshold.
    """
    models = registry.query_models()
    if not models:
        return None
    
    # Filter by complexity threshold based on metrics
    if complexity_level == "standard":
        # Accept models with RMSE < 30% of mean power
        # This is handled by downstream validation
        pass
    elif complexity_level == "enhanced":
        # Require better R² or lower RMSE
        models = [m for m in models if m.get("test_r2", 0) > 0.95]
    elif complexity_level == "advanced":
        # Future: complex models with ensemble methods
        log.warning("Advanced complexity level not yet implemented")
    
    return select_best_model(models)


# -- Promotion Logic ------------------------------------------------------------

def promote_model(
    experiment_tag: str,
    label: str,
    itc_inv: str,
    overwrite: bool = False,
) -> Path:
    """
    Promote experiment model to production with a label.
    
    Args:
        experiment_tag: Source experiment tag
        label: Label for production model (e.g., "xgb_v1", "lgbm_rolling_best")
        itc_inv: Inverter ID
        overwrite: If True, replace existing model with same label
    
    Returns:
        Path to promoted model
    """
    from config.settings import OUTPUTS_DIR
    from experiments.registry import ModelRegistry
    
    registry = get_registry(itc_inv)
    
    # Check if label already exists
    existing = registry.query_models(label=label)
    if existing and not overwrite:
        raise ValueError(
            f"Label '{label}' already exists for {itc_inv}. "
            f"Set overwrite=True to replace."
        )
    
    # Load experiment model
    model, feature_cols, metadata = registry.load_model(experiment_tag)
    
    # Update label in metadata
    metadata["label"] = label
    metadata["promoted_at"] = datetime.now().isoformat()
    if "is_promoted" not in metadata:
        metadata["is_promoted"] = True
    
    # Save with label as experiment_tag
    promoted_tag = f"label_{label}"
    model_path = registry.save_model(
        experiment_tag=promoted_tag,
        model=model,
        feature_cols=feature_cols,
        metadata=metadata,
    )

    params_dir = OUTPUTS_DIR / "promoted_params"
    params_dir.mkdir(parents=True, exist_ok=True)

    active_params = {
        "model_type":    metadata.get("model_type"),
        "promoted_at":   datetime.now().isoformat(),
        "promoted_from": itc_inv,
        "label":         label,
        "params":        metadata.get("hyperparams", {}),
    }

    # save labelled version
    with open(params_dir / f"{itc_inv}_{label}.json", "w") as f:
        json.dump(active_params, f, indent=2, default=str)

    # overwrite active params
    with open(params_dir / "active_params.json", "w") as f:
        json.dump(active_params, f, indent=2, default=str)

        
    log.info(f"Promoted {itc_inv} model with label '{label}': {model_path}")
    return model_path


def demote_model(itc_inv: str, label: str) -> bool:
    """Demote a labeled model (remove production label)."""
    registry = get_registry(itc_inv)
    
    experiment_tag = f"label_{label}"
    if not (registry.get_model_dir(experiment_tag).exists()):
        log.warning(f"Label '{label}' not found for {itc_inv}")
        return False
    
    # Delete the labeled model
    registry.delete_experiment(experiment_tag)
    log.info(f"Demoted {itc_inv} model with label '{label}'")
    return True
