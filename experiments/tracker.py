# experiments/tracker.py

import json
import logging
from datetime import datetime
from pathlib import Path
import matplotlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config.settings import OUTPUTS_DIR

log = logging.getLogger(__name__)


# -- Paths ----------------------------------------------------------------------

EXPERIMENTS_DIR = OUTPUTS_DIR / "experiments"
PLOTS_DIR = EXPERIMENTS_DIR / "plots"


# -- Metrics --------------------------------------------------------------------

METRIC_KEYS = ["rmse", "mae", "r2", "smape"]


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute standard regression metrics."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
        "smape": float(np.mean(np.abs(y_true - y_pred) / ((np.abs(y_true) + np.abs(y_pred)) / 2)) * 100),
    }


# -- Tracker --------------------------------------------------------------------

class ExperimentTracker:
    """Track experiment metrics, save plots, log progress."""
    
    def __init__(self, itc_inv: str, experiment_tag: str):
        self.itc_inv = itc_inv
        self.experiment_tag = experiment_tag
        self.log_dir = EXPERIMENTS_DIR / itc_inv / experiment_tag / "logs"
        self.plot_dir = PLOTS_DIR / itc_inv / experiment_tag
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.plot_dir.mkdir(parents=True, exist_ok=True)
        
        self._metrics_history = []
        self._params_history = []
        self._fold_rmse_history = []
    
    def __repr__(self) -> str:
        return f"ExperimentTracker({self.itc_inv}, {self.experiment_tag})"
    
    # -- Metric tracking --------------------------------------------------------
    
    def record_metrics(self, stage: str, metrics: dict, params: dict = None):
        """Record metrics for a training stage."""
        record = {
            "stage": stage,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "params": params,
        }
        self._metrics_history.append(record)
        return record
    
    def record_fold(self, fold: int, metrics: dict):
        """Record metrics for a walk-forward fold."""
        record = {
            "fold": fold,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
        }
        self._fold_rmse_history.append(record)
        return record
    
    # -- Grid search tracking ---------------------------------------------------
    
    def log_grid_search(self, params: dict, val_metrics: dict, best: bool = False):
        """Log grid search iteration."""
        log_data = {
            "params": params,
            "val_rmse": val_metrics.get("rmse"),
            "val_mae": val_metrics.get("mae"),
            "is_best": best,
            "timestamp": datetime.now().isoformat(),
        }
        self._params_history.append(log_data)
        return log_data
    
    # -- Plotting ---------------------------------------------------------------
    
    def plot_training_history(self, history: dict, show: bool = False) -> Path:
        """Plot training loss (XGBoost/LightGBM eval results)."""
        if not history:
            return None
        
        plt.figure(figsize=(10, 6))
        
        # Plot train and val loss
        for key, values in history.items():
            if "eval" in key.lower() or "val" in key.lower():
                plt.plot(values, label=f"Val - {key}")
            else:
                plt.plot(values, label=f"Train - {key}")
        
        plt.xlabel("Iteration")
        plt.ylabel("Loss")
        plt.title(f"Training History - {self.itc_inv}")
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Save
        save_path = self.plot_dir / "training_history.png"
        plt.savefig(save_path, dpi=350, bbox_inches="tight")
        if show:
            plt.show()
        plt.close()
        
        log.info(f"Training history saved: {save_path}")
        return save_path
    
    def plot_predictions(self, y_true: np.ndarray, y_pred: np.ndarray, show: bool = False) -> Path:
        """Plot predicted vs actual values."""
        plt.figure(figsize=(10, 6))
        plt.scatter(y_true, y_pred, alpha=0.5, s=20)
        
        # Perfect prediction line
        min_val = min(y_true.min(), y_pred.min())
        max_val = max(y_true.max(), y_pred.max())
        plt.plot([min_val, max_val], [min_val, max_val], "r--", linewidth=2, label="Perfect fit")
        
        plt.xlabel("Actual Power (kW)")
        plt.ylabel("Predicted Power (kW)")
        plt.title(f"Predictions vs Actual - {self.itc_inv}")
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        save_path = self.plot_dir / "predictions.png"
        plt.savefig(save_path, dpi=350, bbox_inches="tight")
        if show and matplotlib.get_backend() != "agg":
            plt.show()
        plt.close()
        
        log.info(f"Predictions plot saved: {save_path}")
        return save_path
    
    def plot_residuals(self, y_true: np.ndarray, y_pred: np.ndarray, show: bool = False) -> Path:
        """Plot residual distribution."""
        residuals = y_true - y_pred
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        
        # Residual histogram
        axes[0].hist(residuals, bins=50, edgecolor="black", alpha=0.7)
        axes[0].axvline(0, color="red", linestyle="--", linewidth=2)
        axes[0].set_xlabel("Residual (Actual - Predicted)")
        axes[0].set_ylabel("Frequency")
        axes[0].set_title(f"Residual Distribution - {self.itc_inv}")
        axes[0].grid(True, alpha=0.3)
        
        # Residual vs Predicted
        axes[1].scatter(range(len(residuals)), residuals, alpha=0.3, s=10)
        axes[1].axhline(0, color="red", linestyle="--", linewidth=2)
        axes[1].set_xlabel("Sample Index")
        axes[1].set_ylabel("Residual (kW)")
        axes[1].set_title("Residuals over Samples")
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        save_path = self.plot_dir / "residuals.png"
        plt.savefig(save_path, dpi=350, bbox_inches="tight")
        if show and matplotlib.get_backend() != "agg":
            plt.show()
        plt.close()
        
        log.info(f"Residuals plot saved: {save_path}")
        return save_path
    
    def plot_walk_forward_folds(self, show: bool = False) -> Path:
        """Plot walk-forward validation fold metrics."""
        if not self._fold_rmse_history:
            return None
        
        folds = [r["fold"] for r in self._fold_rmse_history]
        rmse_vals = [r["metrics"]["rmse"] for r in self._fold_rmse_history]
        
        plt.figure(figsize=(12, 6))
        plt.plot(folds, rmse_vals, marker="o", linewidth=2, markersize=6)
        plt.fill_between(folds, rmse_vals, alpha=0.3)
        
        # Mean line
        mean_rmse = np.mean(rmse_vals)
        plt.axhline(mean_rmse, color="red", linestyle="--", linewidth=2, label=f"Mean RMSE: {mean_rmse:.2f}")
        
        plt.xlabel("Fold")
        plt.ylabel("RMSE (kW)")
        plt.title(f"Walk-Fold Validation - {self.itc_inv}")
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        save_path = self.plot_dir / "walk_forward_folds.png"
        plt.savefig(save_path, dpi=350, bbox_inches="tight")
        if show:
            plt.show()
        plt.close()
        
        log.info(f"Walk-forward folds plot saved: {save_path}")
        return save_path
    
    def plot_grid_search_results(self, top_n: int = 20, show: bool = False) -> Path:
        """Plot grid search results (scatter of params vs RMSE)."""
        if not self._params_history:
            return None
        
        # Filter best N to avoid clutter
        sorted_params = sorted(self._params_history, key=lambda x: x["val_rmse"])
        plot_data = sorted_params[:top_n]
        
        rmse_vals = [p["val_rmse"] for p in plot_data]
        
        plt.figure(figsize=(12, 6))
        plt.scatter(range(len(rmse_vals)), rmse_vals, c=rmse_vals, cmap="viridis", s=100, alpha=0.8)
        plt.colorbar(label="RMSE")
        
        plt.xlabel("Grid Search Iteration")
        plt.ylabel("Validation RMSE (kW)")
        plt.title(f"Grid Search Results - Top {top_n} - {self.itc_inv}")
        plt.grid(True, alpha=0.3)
        
        save_path = self.plot_dir / "grid_search_results.png"
        plt.savefig(save_path, dpi=350, bbox_inches="tight")
        if show:
            plt.show()
        plt.close()
        
        log.info(f"Grid search results saved: {save_path}")
        return save_path
    
    # -- Summary ----------------------------------------------------------------
    
    def get_summary(self) -> dict:
        """Get experiment summary."""
        summary = {
            "itc_inv": self.itc_inv,
            "experiment_tag": self.experiment_tag,
            "timestamp": datetime.now().isoformat(),
            "num_grid_search_iterations": len(self._params_history),
            "num_walk_forward_folds": len(self._fold_rmse_history),
        }
        
        # Last recorded metrics
        if self._metrics_history:
            last = self._metrics_history[-1]
            summary["metrics"] = last["metrics"]
            summary["stage"] = last["stage"]
        
        # Fold metrics
        if self._fold_rmse_history:
            rmse_vals = [r["metrics"]["rmse"] for r in self._fold_rmse_history]
            summary["fold_metrics"] = {
                "mean": float(np.mean(rmse_vals)),
                "std": float(np.std(rmse_vals)),
                "min": float(np.min(rmse_vals)),
                "max": float(np.max(rmse_vals)),
            }
        
        return summary
    
    def save_summary(self) -> Path:
        """Save experiment summary to JSON."""
        summary = self.get_summary()
        save_path = self.plot_dir / "summary.json"
        
        with open(save_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        
        return save_path
