# config/settings.py

from pathlib import Path

# -- ITC-INV Registry ----------------------------------------------------------
ITC_INV_LIST = [
    "ITC1_INV1",
    "ITC1_INV2",
    "ITC2_INV1",
    "ITC2_INV2",
    "ITC3_INV1",
    "ITC3_INV2",
    "ITC3_INV3",
    "ITC3_INV4",
]

# -- Inverter Specs (AC capacity per ITC-INV) ----------------------------------
AC_CAPACITY = {
    "ITC1_INV1": 4400,
    "ITC1_INV2": 4400,
    "ITC2_INV1": 4400,
    "ITC2_INV2": 4400,
    "ITC3_INV1": 3300,
    "ITC3_INV2": 3300,
    "ITC3_INV3": 3300,
    "ITC3_INV4": 3300,
}

DC_KWP = {
    "ITC1_INV1": 7257.6,
    "ITC1_INV2": 6955.2,
    "ITC2_INV1": 7087.6,
    "ITC2_INV2": 7223.32,
    "ITC3_INV1": 5368.48,
    "ITC3_INV2": 5368.48,
    "ITC3_INV3": 5368.48,
    "ITC3_INV4": 5353.4,
}
DC_LOADING = {
    "ITC1_INV1": 1.64945455,
    "ITC1_INV2": 1.58072727,
    "ITC2_INV1": 1.61081818,
    "ITC2_INV2": 1.64166364,
    "ITC3_INV1": 1.62681212,
    "ITC3_INV2": 1.62681212,
    "ITC3_INV3": 1.62681212,
    "ITC3_INV4": 1.62224242,

}

# -- Data Filtering ------------------------------------------------------------
GII_FILTER  = 20
TIME_START  = 6
TIME_END    = 19
GAP_ROWS    = 200
VAL_DAYS    = 7
TEST_DAYS   = 7

# -- Anomaly Thresholds --------------------------------------------------------
WARNING_SIGMA = 2
ANOMALY_SIGMA = 3

# -- Model --------------------------------------------------------------------─
RANDOM_SEED = 42
MODEL_TYPE  = "xgboost"      # swap to lgbm if needed

GRID_PARAMS = {
    "n_estimators":      [300, 500, 800],
    "max_depth":         [4, 5, 6],         # 6 is the absolute maximum
    "learning_rate":     [0.01, 0.05],
    "subsample":         [0.7, 0.85],
    "colsample_bytree":  [0.7, 0.85],
    "min_child_weight":  [150, 300],        # Requires 2.5 to 5 hours of data per leaf
    "gamma":             [0.5, 2.0],        # Aggressive pruning for large datasets
    "reg_alpha":         [1.0, 5.0],
    "reg_lambda":        [5.0, 10.0],
}
# LGBM_GRID_PARAMS = {
#     "num_leaves":        [31, 45, 63],
#     "max_depth":         [4, 5, 6],
#     "learning_rate":     [0.01, 0.05],
#     "subsample":         [0.7, 0.85],
#     "colsample_bytree":  [0.7, 0.85],
#     "min_child_samples": [200, 500],        # Extremely strict sample requirements
#     "min_split_gain":    [0.5, 2.0],
#     "reg_alpha":         [1.0, 5.0],
#     "reg_lambda":        [5.0, 10.0],

# }


XGB_BASE = {
    "objective":    "reg:squarederror",
    "tree_method":  "hist",
    "random_state": RANDOM_SEED,
    "n_jobs":       -1,
    "verbosity":    0,
}

# -- Column Mapping ------------------------------------------------------------
# standard name -> possible variants in raw CSVs
COLUMN_MAP = {
    # -- Timestamp --------------------------------------------------------─
    "timestamp":             ["Time Stamp", "time stamp", "timestamp", "time", "datetime"],

    # -- Inverter specs (not in files - will be injected from settings) ----
    "dc_kwp":                ["dc_kwp", "DC KWP", "dc peak", "DC Peak"],
    "ac_kw":                 ["ac_kw", "AC KW", "ac capacity", "AC Capacity"],
    "dc_loading":            ["dc_loading", "DC Loading", "dc load"],

    # -- AC electrical ------------------------------------------------------
    "ry_voltage":            ["RY Voltage", "ry voltage", "ry_voltage", "VRY"],
    "yb_voltage":            ["YB Voltage", "yb voltage", "yb_voltage", "VYB"],
    "br_voltage":            ["BR Voltage", "br voltage", "br_voltage", "VBR"],
    "ir_current":            ["IR Current", "ir current", "ir_current", "IR"],
    "iy_current":            ["IY Current", "iy current", "iy_current", "IY"],
    "ib_current":            ["IB Current", "ib current", "ib_current", "IB"],
    "active_power_kw":       ["Active Power", "active power", "active_power_kw", "P_ac"],
    "reactive_power_kvar":   ["Reactive Power", "reactive power", "reactive_power_kvar"],
    "apparent_power_kva":    ["Apperent\nPower", "Apparent Power", "apparent power", "apparent_power_kva"],
    "power_factor":          ["Power\nFactor", "Power Factor", "power factor", "power_factor", "PF"],
    "frequency_hz":          ["Frequency", "frequency", "frequency_hz", "Hz"],

    # -- Energy / operational (excluded from features) --------------------─
    "today_energy":          ["Today Energy", "today energy"],
    "monthly_energy":        ["Monthly Energy", "monthly energy"],
    "total_energy":          ["Total Energy", "total energy"],
    "today_run_hour":        ["Today Run Hour", "today run hour"],
    "yest_kwh":              ["Yest KWH", "yest kwh"],
    "peak_kw":               ["Peak KW", "peak kw", "peak_kw"],
    "pr":                    ["PR", "pr"],
    "cpr":                   ["CPR", "cpr"],
    "availability":          ["AVAILABILITY", "availability"],
    "brkdwn_loss":           ["BRKDWN LOSS", "brkdwn loss", "brkdown_loss"],
    "brkdwn_mnt":            ["BRKDWN MNT", "brkdwn mnt", "brkdown_mnt"],

    # -- DC strings --------------------------------------------------------
    "mod1_dc_v":             ["MOD1 DC V", "mod1 dc v", "mod1_dc_v", "MPPT1 Voltage"],
    "mod1_dc_a":             ["MOD1 DC A", "mod1 dc a", "mod1_dc_a", "MPPT1 Current"],
    "mod1_dc_kw":            ["MOD1 DC KW", "mod1 dc kw", "mod1_dc_kw", "MPPT1 Power"],
    "mod2_dc_v":             ["MOD2 DC V", "mod2 dc v", "mod2_dc_v", "MPPT2 Voltage"],
    "mod2_dc_a":             ["MOD2 DC A", "mod2 dc a", "mod2_dc_a", "MPPT2 Current"],
    "mod2_dc_kw":            ["MOD2 DC KW", "mod2 dc kw", "mod2_dc_kw", "MPPT2 Power"],
    "mod3_dc_v":             ["MOD3 DC V", "mod3 dc v", "mod3_dc_v", "MPPT3 Voltage"],
    "mod3_dc_a":             ["MOD3 DC A", "mod3 dc a", "mod3_dc_a", "MPPT3 Current"],
    "mod3_dc_kw":            ["MOD3 DC KW", "mod3 dc kw", "mod3_dc_kw", "MPPT3 Power"],
    "mod4_dc_v":             ["MOD4 DC V", "mod4 dc v", "mod4_dc_v", "MPPT4 Voltage"],
    "mod4_dc_a":             ["MOD4 DC A", "mod4 dc a", "mod4_dc_a", "MPPT4 Current"],
    "mod4_dc_kw":            ["MOD4 DC KW", "mod4 dc kw", "mod4_dc_kw", "MPPT4 Power"],

    # -- WMS / weather ----------------------------------------------------─
    "ghi":                   ["GHI", "ghi", "global horizontal"],
    "gii":                   ["GII", "gii", "global inclined"],
    "ghi_acc":               ["GHI_ACC", "ghi_acc", "GHI ACC"],
    "gii_acc":               ["GII ACC.", "GII ACC", "gii_acc", "gii acc"],
    "albedo_up":             ["ALBEDO UP", "albedo up", "albedo_up"],
    "albedo_down":           ["ALBEDO DOWN", "albedo down", "albedo_down"],
    "mod_temp1":             ["MOD TEMP.1", "mod temp.1", "mod_temp1", "Module Temp 1"],
    "mod_temp2":             ["MOD TEMP.2", "mod temp.2", "mod_temp2", "Module Temp 2"],
    "mod_temp3":             ["MOD TEMP.3", "mod temp.3", "mod_temp3", "Module Temp 3"],
    "amb_temp1":             ["AMB TEMP.1", "amb temp.1", "amb_temp1", "Ambient Temp"],
    "rain":                  ["RAIN", "rain", "rainfall"],
    "wind_speed":            ["WIND\nSPEED", "Wind Speed", "wind speed", "wind_speed", "WS"],
    "humidity":              ["HUMIDITY", "humidity"],
    "cloud_cover":           ["CLOUD COVER", "cloud cover", "cloud_cover"],
    "air_press":             ["AIR PRESS", "air press", "air_press", "Air Pressure"],
    "direct":                ["DIRECT RADIATION", "direct radiation", "direct", "DNI"],
    "diffuse":               ["DIFFUSE RADIATION", "diffuse radiation", "diffuse", "DHI"],
}

# -- Timestamp Formats --------------------------------------------------------─
TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",    # train:   2026-01-02 00:01:00
    "%Y-%m-%d %H:%M",       # train:   2026-01-02 00:01
    "%m/%d/%Y %I:%M:%S %p", # retrain: 5/9/2026 12:00:00 AM
    "%m/%d/%Y %I:%M %p",    # retrain: 5/9/2026 12:00 AM
]

# -- Paths --------------------------------------------------------------------─
BASE_DIR        = Path(__file__).resolve().parent.parent
DATA_DIR        = BASE_DIR / "data"
TRAIN_UPLOADS   = DATA_DIR / "train_uploads"
analysis_UPLOADS = DATA_DIR / "analysis_uploads"
RETRAIN_UPLOADS = DATA_DIR / "retrain_uploads"
OUTPUTS_DIR     = BASE_DIR / "outputs"
LOGS_DIR        = BASE_DIR / "logs"

# auto-create all directories on import
for _dir in [
    TRAIN_UPLOADS, analysis_UPLOADS, RETRAIN_UPLOADS,
    LOGS_DIR,
    *[OUTPUTS_DIR / inv for inv in ITC_INV_LIST],
]:
    _dir.mkdir(parents=True, exist_ok=True)

# -- Features to exclude from model ------------------------------------------─
EXCLUDE_FROM_FEATURES = {
    "active_power_kw",
    "timestamp",
    "inverter_id",
    "ghi_acc",
    "gii_acc",
    "apparent_power_kva",
    "reactive_power_kvar",
    "dc_kwp",
    "ac_kw",
    "dc_loading",
    "today_energy",
    "monthly_energy",
    "total_energy",
    "today_run_hour",
    "yest_kwh",
    "pr",
    "cpr",
    "availability",
    "brkdwn_loss",
    "brkdwn_mnt",
    "wind_speed",
    "wind_direction",
}

#  Retraining window Strategy
ROLLING_WINDOW_TRIGGER_MONTHS = 12
ROLLING_WINDOW_DAYS = 120

# Sheet name mapping - file naming -> system naming
SHEET_NAME_MAP = {
    "ITC1_INV1": "ICR-1_INV-1",
    "ITC1_INV2": "ICR-1_INV-2",
    "ITC2_INV1": "ICR-2_INV-1",
    "ITC2_INV2": "ICR-2_INV-2",
    "ITC3_INV1": "ICR-3_INV-1",
    "ITC3_INV2": "ICR-3_INV-2",
    "ITC3_INV3": "ICR-3_INV-3",
    "ITC3_INV4": "ICR-3_INV-4",
}

# Row offsets for each file type
INVERTER_REPORT_HEADER_ROW = 11   # 0-indexed = 10
WMS_REPORT_HEADER_ROW      = 6    # 0-indexed = 5