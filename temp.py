import pandas as pd
import joblib
from core.data import load_and_merge, filter_data, add_time_features
from core.validator import validate

from pathlib import Path

inv_files = list(Path(r"C:\Users\dhruv\Desktop\Continuum\retrain\INVERTER_REPORT-29-4-26").glob("*.xlsx"))
wms_files = list(Path(r"C:\Users\dhruv\Desktop\Continuum\retrain\wms\wms").glob("*.xlsx"))

print(f"Inverter files found: {len(inv_files)}")
print(f"WMS files found: {len(wms_files)}")

raw_df, warnings = load_and_merge(inv_files, wms_files, "ITC1_INV1")
val_result = validate(raw_df)
df = val_result["df"]
df = filter_data(df)

# check suspicious rows — high GII but low power
suspicious = df[(df["gii"] > 300) & (df["active_power_kw"] < 500)]
print(f"Suspicious rows: {len(suspicious)}")
print(suspicious[["timestamp", "gii", "active_power_kw", "mod1_dc_a", "mod1_dc_kw"]].head(20))

# check power distribution at high GII
high_gii = df[df["gii"] > 500]
print(f"\nHigh GII rows: {len(high_gii)}")
print(f"Power at high GII:")
print(high_gii["active_power_kw"].describe())