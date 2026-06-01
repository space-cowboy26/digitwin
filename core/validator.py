# core/validator.py
import logging
log = logging.getLogger(__name__)
import pandas as pd
import numpy as np
from config.settings import COLUMN_MAP, TIMESTAMP_FORMATS


# -- Required columns for the pipeline to function ----------------------------
REQUIRED_COLUMNS = [
    "timestamp",
    "active_power_kw",
    "gii",
    "ghi",
    "mod1_dc_v", "mod1_dc_a", "mod1_dc_kw",
    "mod2_dc_v", "mod2_dc_a", "mod2_dc_kw",
    "mod3_dc_v", "mod3_dc_a", "mod3_dc_kw",
    "mod4_dc_v", "mod4_dc_a", "mod4_dc_kw",
]

OPTIONAL_COLUMNS = [
    # "dc_kwp", "ac_kw", "dc_loading",
    "power_factor", "frequency_hz",
    "ghi_acc", "gii_acc",
    "albedo_up", "albedo_down",
    "mod_temp1", "mod_temp2", "mod_temp3",
    "amb_temp1", "rain", "humidity",
    "cloud_cover", "air_press",
    "direct", "diffuse",
    "reactive_power_kvar", "apparent_power_kva",
    "wind_speed",
"wind_direction",
"ry_voltage", "yb_voltage", "br_voltage",
"ir_current", "iy_current", "ib_current",
"peak_kw",
]


# -- Column normalisation ------------------------------------------------------

def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    # build lookup maps
    col_exact_map    = {c: c for c in df.columns}
    col_stripped_map = {c.strip().lower(): c for c in df.columns}

    for standard_name, variants in COLUMN_MAP.items():
        for variant in variants:
            # 1. exact match
            if variant in col_exact_map:
                rename[variant] = standard_name
                break
            # 2. stripped lowercase match - catches ALL CAPS, extra spaces, mixed case
            if variant.strip().lower() in col_stripped_map:
                actual_col = col_stripped_map[variant.strip().lower()]
                rename[actual_col] = standard_name
                break

    return df.rename(columns=rename)


# -- Timestamp parsing --------------------------------------------------------─

def parse_timestamp(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """
    Tries each format in TIMESTAMP_FORMATS.
    Returns df with parsed timestamp and the format that worked.
    Raises ValueError if none work.
    """
    col = "timestamp"

    # already datetime
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        return df, "already parsed"

    for fmt in TIMESTAMP_FORMATS:
        try:
            parsed = pd.to_datetime(df[col], format=fmt, errors="raise")
            df = df.copy()
            df[col] = parsed
            return df, fmt
        except Exception:
            continue

    # last resort - pandas analysis
    try:
        df = df.copy()
        df[col] = pd.to_datetime(df[col], infer_datetime_format=True)
        return df, "inferred"
    except Exception:
        raise ValueError(
            f"Could not parse timestamp column. "
            f"Tried formats: {TIMESTAMP_FORMATS}. "
            f"Sample values: {df[col].head(3).tolist()}"
        )


# -- Month/day swap detection --------------------------------------------------

def detect_date_swap(df: pd.DataFrame) -> dict:
    """
    Checks if month and day might be swapped.
    Returns a dict with:
        - suspicious: bool
        - sample: list of 3 raw timestamp strings for operator confirmation
        - reason: explanation string
    """
    col = "timestamp"
    months = df[col].dt.month
    days   = df[col].dt.day

    # if all months are <= 12 but days are also <= 12,
    # swap is ambiguous - show operator a sample
    ambiguous = (months <= 12) & (days <= 12)
    all_ambiguous = ambiguous.all()

    # strong signal: if day values are all low (1-12) but month values
    # are spread across 1-12, likely swapped
    unique_months = months.nunique()
    unique_days   = days.nunique()

    suspicious = all_ambiguous and (unique_days < unique_months)

    return {
        "suspicious": suspicious,
        "sample":     df[col].dt.strftime("%Y-%m-%d %H:%M:%S").head(3).tolist(),
        "reason":     "Day and month values are both ≤ 12. Please confirm the date format."
                      if suspicious else "Timestamps look correct.",
    }


# -- Required column check ----------------------------------------------------─

def check_required_columns(df: pd.DataFrame) -> dict:
    """
    Checks which required columns are present or missing.
    Returns dict with missing list and a pass/fail bool.
    """
    present = set(df.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    optional_missing = [c for c in OPTIONAL_COLUMNS if c not in present]

    return {
        "passed":           len(missing) == 0,
        "missing_required": missing,
        "missing_optional": optional_missing,
    }


# -- Duplicate timestamp check ------------------------------------------------─

def check_duplicates(df: pd.DataFrame) -> dict:
    dupes = df["timestamp"].duplicated().sum()
    return {
        "passed": dupes == 0,
        "duplicate_count": int(dupes),
        "message": f"{dupes} duplicate timestamps found." if dupes > 0 else "No duplicates.",
    }


# -- Missing value report ------------------------------------------------------

def check_missing_values(df: pd.DataFrame) -> dict:
    total   = len(df)
    missing = df[REQUIRED_COLUMNS].isnull().sum()
    missing = missing[missing > 0]

    report = {
        col: {"count": int(n), "pct": round(n / total * 100, 2)}
        for col, n in missing.items()
    }
    return {
        "passed":  len(report) == 0,
        "details": report,
        "message": "No missing values in required columns."
                   if len(report) == 0
                   else f"Missing values found in: {list(report.keys())}",
    }


# -- Master validate function --------------------------------------------------

def validate(df: pd.DataFrame) -> dict:
    """
    Runs all checks in sequence.
    Returns a single result dict the app and pipelines consume.

    result = {
        "passed":       bool,        ← False means block the pipeline
        "warnings":     list[str],   ← non-blocking issues to show operator
        "errors":       list[str],   ← blocking issues
        "df":           DataFrame,   ← cleaned df if passed
        "date_swap":    dict,        ← for operator confirmation in app
    }
    """
    errors   = []
    warnings = []

    # step 1 - normalise columns
    df = normalise_columns(df)
    df = df.dropna(how="all").reset_index(drop=True)

    # step 2 - check required columns before anything else
    col_check = check_required_columns(df)
    if not col_check["passed"]:
        return {
            "passed":    False,
            "errors":    [f"Missing required columns: {col_check['missing_required']}"],
            "warnings":  [],
            "df":        None,
            "date_swap": None,
        }
    if col_check["missing_optional"]:
        warnings.append(f"Missing optional columns (will be skipped): {col_check['missing_optional']}")

    # step 3 - parse timestamp
    try:
        df, fmt_used = parse_timestamp(df)
        warnings.append(f"Timestamp parsed using format: {fmt_used}")
    except ValueError as e:
        return {
            "passed":    False,
            "errors":    [str(e)],
            "warnings":  warnings,
            "df":        None,
            "date_swap": None,
        }

    # step 4 - date swap detection
    date_swap = detect_date_swap(df)
    if date_swap["suspicious"]:
        warnings.append(date_swap["reason"])

    # step 5 - duplicates
    dupe_check = check_duplicates(df)
    if not dupe_check["passed"]:
        warnings.append(dupe_check["message"])
        df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

    # step 6 - missing values
    missing_check = check_missing_values(df)
    if not missing_check["passed"]:
        warnings.append(missing_check["message"])

    return {
        "passed":    True,
        "errors":    errors,
        "warnings":  warnings,
        "df":        df,
        "date_swap": date_swap,
    }
def check_data_quality(df: pd.DataFrame) -> dict:
    """
    Checks for suspicious rows that should be removed before training.
    Returns a report dict with details for operator review.
    Only relevant for train and retrain — not analysis.
    """
    issues = []

    if "gii" not in df.columns or "active_power_kw" not in df.columns:
        return {"issues": [], "passed": True, "message": "Skipped — required columns missing."}

    gii    = pd.to_numeric(df["gii"], errors="coerce")
    power  = pd.to_numeric(df["active_power_kw"], errors="coerce")

    # ── Inverter trips — high GII but zero/near-zero power ────────────────
    trips = df[(gii > 300) & (power < 100)].copy()
    if len(trips) > 0:
        issues.append({
            "type":        "Inverter Trip / Zero Power at High GII",
            "count":       len(trips),
            "description": (
                f"{len(trips)} rows where GII > 300 W/m2 but power < 100 kW. "
                f"Likely inverter trips, protection relay events, or communication loss."
            ),
            "sample": trips[["timestamp", "gii", "active_power_kw"]].head(10).to_dict("records"),
            "date_range": (
                f"{trips['timestamp'].min()} to {trips['timestamp'].max()}"
            ),
        })

    # ── Oscillating power — high variance within 10-minute window ─────────
    df_sorted = df.sort_values("timestamp").copy()
    df_sorted["power_numeric"] = pd.to_numeric(df_sorted["active_power_kw"], errors="coerce")
    df_sorted["rolling_std"]   = (
        df_sorted["power_numeric"]
        .rolling(window=10, min_periods=5)
        .std()
    )
    oscillating = df_sorted[
        (gii > 300) &
        (df_sorted["rolling_std"] > 500)
    ].copy()
    if len(oscillating) > 0:
        issues.append({
            "type":        "Oscillating / Unstable Power",
            "count":       len(oscillating),
            "description": (
                f"{len(oscillating)} rows where power fluctuated > 500 kW "
                f"May be cloud edge effects (legitimate) or MPPT instability (fault)."
                f"Likely MPPT instability or protection relay hunting."
                f"Enable 'remove oscillations' checkbox only if confirmed as faults."
            ),
            "sample": oscillating[["timestamp", "gii", "active_power_kw"]].head(10).to_dict("records"),
            "date_range": (
                f"{oscillating['timestamp'].min()} to {oscillating['timestamp'].max()}"
            ),
        })

    # ── Sustained low power — full day below 10% of max observed ──────────
    max_power  = float(power.quantile(0.95))
    low_thresh = max_power * 0.10
    day_col    = pd.to_datetime(df["timestamp"]).dt.date
    daily_max  = df.groupby(day_col)["active_power_kw"].apply(
        lambda x: pd.to_numeric(x, errors="coerce").max()
    )
    low_days = daily_max[daily_max < low_thresh].index.tolist()
    if low_days:
        issues.append({
            "type":        "Sustained Low Output Days",
            "count":       len(low_days),
            "description": (
                f"{len(low_days)} day(s) where max power was below "
                f"10% of normal ({low_thresh:.1f} kW). "
                f"Likely full-day outage or maintenance period."
            ),
            "sample": [str(d) for d in low_days],
            "date_range": (
                f"{min(low_days)} to {max(low_days)}"
            ),
        })

    return {
        "issues":  issues,
        "passed":  len(issues) == 0,
        "message": (
            "No data quality issues detected."
            if len(issues) == 0
            else f"{len(issues)} issue type(s) found. Please review before training."
        ),
    }

def _remove_faulty_rows(df: pd.DataFrame, remove_low_days: bool = True, remove_oscillations: bool = False,) -> pd.DataFrame:
    """
    Remove rows identified in the quality report.
    Removes trip rows and oscillating rows by timestamp.
    Removes full low-output days entirely.
    """
    df = df.copy()
    original_len = len(df)

    gii   = pd.to_numeric(df["gii"], errors="coerce")
    power = pd.to_numeric(df["active_power_kw"], errors="coerce")

    # remove trip rows
    trip_mask = (gii > 300) & (power < 100)
    df = df[~trip_mask].reset_index(drop=True)

    # remove oscillating rows
    if remove_oscillations:

        df_sorted = df.sort_values("timestamp").copy()
        df_sorted["power_numeric"] = pd.to_numeric(
            df_sorted["active_power_kw"], errors="coerce"
        )
        df_sorted["rolling_std"] = (
            df_sorted["power_numeric"]
            .rolling(window=10, min_periods=5)
            .std()
        )
        gii2 = pd.to_numeric(df_sorted["gii"], errors="coerce")
        oscillating_mask = (gii2 > 300) & (df_sorted["rolling_std"] > 500)
        df = df_sorted[~oscillating_mask].reset_index(drop=True)

    # remove low output days
    day_col   = pd.to_datetime(df["timestamp"]).dt.date
    max_power = float(pd.to_numeric(df["active_power_kw"], errors="coerce").quantile(0.95))
    low_thresh = max_power * 0.10
    daily_max  = df.groupby(day_col)["active_power_kw"].apply(
        lambda x: pd.to_numeric(x, errors="coerce").max()
    )
    low_days = set(daily_max[daily_max < low_thresh].index.tolist())
    if remove_low_days:
        low_days = set(daily_max[daily_max < low_thresh].index.tolist())
        if low_days:
            df = df[~day_col.isin(low_days)].reset_index(drop=True)

    removed = original_len - len(df)
    log.info(f"Fault removal: {removed} rows removed, {len(df)} rows remaining.")
    df = df.drop(columns=["power_numeric", "rolling_std"], errors="ignore")

    return df