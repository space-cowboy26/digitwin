# experiments/registry.py

import json
import shutil
from datetime import datetime
from pathlib import Path

import joblib

from config.settings import OUTPUTS_DIR


# -- Constants ------------------------------------------------------------------

EXPERIMENTS_DIR = OUTPUTS_DIR / "experiments"
MODEL_EXTENSIONS = (".joblib", ".pkl")


# -- Registry -------------------------------------------------------------------

class ModelRegistry:
    """Model registry for experiment results with versioning and labels."""
    
    def __init__(self, itc_inv: str):
        self.itc_inv = itc_inv
        self.exp_dir = EXPERIMENTS_DIR / itc_inv
        
    def __repr__(self) -> str:
        return f"ModelRegistry({self.itc_inv})"
    
    # -- Directory structure ----------------------------------------------------
    
    def get_model_dir(self, experiment_tag: str) -> Path:
        """Get model directory for a specific experiment."""
        return self.exp_dir / experiment_tag
    
    def get_model_path(self, experiment_tag: str) -> Path:
        """Get model file path for a specific experiment."""
        return self.get_model_dir(experiment_tag) / "model.joblib"
    
    def get_metadata_path(self, experiment_tag: str) -> Path:
        """Get metadata file path for a specific experiment."""
        return self.get_model_dir(experiment_tag) / "metadata.json"
    
    # -- Save/Load --------------------------------------------------------------
    
    def save_model(
        self,
        experiment_tag: str,
        model: object,
        feature_cols: list,
        metadata: dict,
    ) -> Path:
        """Save model, metadata, and return path."""
        model_dir = self.get_model_dir(experiment_tag)
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model
        model_path = self.get_model_path(experiment_tag)
        joblib.dump({
            "model": model,
            "feature_cols": feature_cols,
            "itc_inv": self.itc_inv,
            "experiment_tag": experiment_tag,
            "saved_at": datetime.now().isoformat(),
        }, model_path)
        
        # Save metadata
        meta_path = self.get_metadata_path(experiment_tag)
        full_metadata = {
            **metadata,
            "experiment_tag": experiment_tag,
            "itc_inv": self.itc_inv,
            "saved_at": datetime.now().isoformat(),
        }
        with open(meta_path, "w") as f:
            json.dump(full_metadata, f, indent=2, default=str)
        
        return model_path
    
    def load_model(self, experiment_tag: str) -> tuple:
        """Load model, feature_cols, metadata for a specific experiment."""
        model_path = self.get_model_path(experiment_tag)
        meta_path = self.get_metadata_path(experiment_tag)
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {experiment_tag}")
        
        payload = joblib.load(model_path)
        model = payload["model"]
        feature_cols = payload["feature_cols"]
        
        with open(meta_path) as f:
            metadata = json.load(f)
        
        return model, feature_cols, metadata
    
    # -- List/Query -------------------------------------------------------------
    
    def list_experiments(self) -> list:
        """List all experiment tags for this inverter."""
        if not self.exp_dir.exists():
            return []
        
        experiments = []
        for item in self.exp_dir.iterdir():
            if item.is_dir() and (item / "model.joblib").exists():
                experiments.append(item.name)
        
        return sorted(experiments, reverse=True)
    
    def get_experiment_info(self, experiment_tag: str) -> dict:
        """Get metadata for a specific experiment."""
        meta_path = self.get_metadata_path(experiment_tag)
        if not meta_path.exists():
            return {}
        
        with open(meta_path) as f:
            return json.load(f)
    
    def query_models(
        self,
        label: str = None,
        model_type: str = None,
        split: str = None,
        sort_by: str = "rmse",
        ascending: bool = True,
    ) -> list:
        """Query models with optional filters."""
        experiments = self.list_experiments()
        models = []
        
        for exp_tag in experiments:
            info = self.get_experiment_info(exp_tag)
            
            # Apply filters
            if label and info.get("label") != label:
                continue
            if model_type and info.get("model_type") != model_type:
                continue
            if split and info.get("split") != split:
                continue
            
            # Extract metrics
            metrics = info.get("test_metrics", {})
            val_metrics = info.get("val_metrics", {})
            info_dict = {
                "experiment_tag": exp_tag,
                "label": info.get("label"),
                "model_type": info.get("model_type"),
                "split": info.get("split"),
                "saved_at": info.get("saved_at"),
                "train_rows": info.get("train_rows"),
                "val_rows": info.get("val_rows"),
                "test_rows": info.get("test_rows"),
                "train_rmse": val_metrics.get("rmse"),
                "val_rmse": val_metrics.get("rmse"),
                "test_rmse": metrics.get("rmse"),
                "test_mae": metrics.get("mae"),
                "test_r2": metrics.get("r2"),
                "test_smape": metrics.get("smape"),
                **info,
            }
            models.append(info_dict)
        
        # Sort
        if sort_by and sort_by in models[0] if models else False:
            models.sort(key=lambda x: x.get(sort_by, 0), reverse=not ascending)
        
        return models
    
    def get_best_model(self, label: str = None, metric: str = "rmse") -> dict:
        """Get best model by metric (lower is better by default)."""
        models = self.query_models(label=label)
        if not models:
            return None
        
        # Sort by metric (ascending for RMSE, MAE, SMAPE; descending for R²)
        ascending = metric not in ["r2"]
        models.sort(key=lambda x: x.get(metric, float("inf")), reverse=not ascending)
        
        return models[0]
    
    # -- Cleanup ----------------------------------------------------------------
    
    def delete_experiment(self, experiment_tag: str) -> bool:
        """Delete a specific experiment and its files."""
        model_dir = self.get_model_dir(experiment_tag)
        if not model_dir.exists():
            return False
        
        import shutil
        shutil.rmtree(model_dir)
        return True
    
    def prune_versions(self, keep: int = 3) -> list:
        """Keep only the most recent N versions, delete older ones."""
        experiments = self.list_experiments()
        if len(experiments) <= keep:
            return []
        
        # Get oldest experiments to delete
        to_delete = experiments[keep:]
        deleted = []
        
        for exp_tag in to_delete:
            if self.delete_experiment(exp_tag):
                deleted.append(exp_tag)
        
        return deleted


# -- Factory function -----------------------------------------------------------

def get_registry(itc_inv: str) -> ModelRegistry:
    """Get model registry for an inverter."""
    return ModelRegistry(itc_inv)
