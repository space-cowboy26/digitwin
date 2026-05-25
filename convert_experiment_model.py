import joblib
import json
import numpy as np
from pathlib import Path
from datetime import datetime

# load experiment model
exp = joblib.load("outputs/ITC1_INV1/blocked__grid__xgb.joblib")

itc_inv    = "ITC1_INV1"
output_dir = Path(f"outputs/{itc_inv}")
output_dir.mkdir(parents=True, exist_ok=True)

# save in app format
joblib.dump({
    "model":        exp["model"],
    "feature_cols": exp["feature_cols"],
    "itc_inv":      itc_inv,
    "saved_at":     datetime.now().isoformat(),
}, output_dir / "model.joblib")

# you need to provide val and test metrics manually
# get these from your experiment JSON files
val_metrics  = {"mae": 30.61, "rmse": 30.61, "r2": 0.9996, "smape": 10.94}
test_metrics = {"mae": 29.79, "rmse": 62.31, "r2": 0.9986, "smape": 17.70}

# compute residual percentiles from test predictions
model        = exp["model"]
# you need X_test and y_test here — load from your processed data
# residuals = y_test - model.predict(X_test)
# for now approximate from test RMSE
residual_percentiles = {
    "p5":  -2.0 * test_metrics["rmse"],   # approximate
    "p1":  -3.0 * test_metrics["rmse"],   # approximate
    "p50": 0.0,
}

metadata = {
    "itc_inv":               itc_inv,
    "model_type":            "xgboost",
    "split":                 "blocked",
    "tuning":                "grid",
    "saved_at":              datetime.now().isoformat(),
    "best_params":           exp["model"].get_params(),
    "val_metrics":           val_metrics,
    "test_metrics":          test_metrics,
    "feature_cols":          exp["feature_cols"],
    "previous_rmse":         None,
    "previous_val_rmse":     None,
    "residual_percentiles":  residual_percentiles,
    "retrain_history":       [],
}

with open(output_dir / "metadata.json", "w") as f:
    json.dump(metadata, f, indent=2, default=str)

print(f"Converted model saved to {output_dir}")