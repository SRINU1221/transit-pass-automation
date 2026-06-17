"""
excel_processor.py — Reads and validates the Transit Pass Excel file.

Expected columns (flexible header matching):
  - Vehicle No, Driver, License, Phone  (existing)
  - Aggregator                           (new)
  - Dispatch Qty / Dispatch Quantity     (new)
  - Stationary No / Stationery No        (new)
  - Sales Value                          (new)
"""
from __future__ import annotations

import pandas as pd


# ── Flexible column aliases ──────────────────────────────────────────────────
COLUMN_ALIASES: dict[str, str] = {
    # Vehicle Number
    "VEHICLE.NO":   "vehicle_no",
    "VEHICLE NO":   "vehicle_no",
    "VEHICLE_NO":   "vehicle_no",
    "VEHICLENO":    "vehicle_no",
    "VEHICLE NUMBER": "vehicle_no",

    # Vehicle Type
    "VEHICLE TYPE": "vehicle_type",
    "VEHICLE_TYPE": "vehicle_type",
    "VEHICLE.TYPE": "vehicle_type",
    "VEHICLETYPE":  "vehicle_type",

    # Driver Name
    "DRIVER":            "driver",
    "DRIVER NAME":       "driver",
    "DRIVERNAME":        "driver",
    "DRIVER4":           "driver",
    "DRIVER NAME1":      "driver",

    # License Number
    "LICENSE":           "license",
    "LICENCE":           "license",
    "LICENSE NO":        "license",
    "LICENCE NO":        "license",
    "DL NO":             "license",
    "DL.NO":             "license",
    "DLNO":              "license",
    # ✅ Actual Excel header variants
    "DRIVER LICENSE NO": "license",
    "DRIVER LICENSE":    "license",
    "DRIVER LICENCE NO": "license",
    "DRIVER LICENCE":    "license",
    "DRIVER DL NO":      "license",
    "DL NUMBER":         "license",

    # Phone / Mobile
    "PHONE":             "phone",
    "PHONE NO":          "phone",
    "MOBILE":            "phone",
    "MOBILE NO":         "phone",
    "CONTACT":           "phone",
    "CONTACT NO":        "phone",
    # ✅ Actual Excel header variants
    "DRIVER MOBILE":     "phone",
    "DRIVER MOBILE NO":  "phone",
    "DRIVER PHONE":      "phone",
    "DRIVER PHONE NO":   "phone",

    # Aggregator
    "AGGREGATOR":        "aggregator",
    "AGGREGATOR NAME":   "aggregator",
    "AGG":               "aggregator",
    "LESSEE":            "aggregator",
    "LESSEE NAME":       "aggregator",
    # ✅ Actual Excel header variants
    "AGGREGATORS":       "aggregator",   # plural ← your Excel uses this
    "AGGREGATER":        "aggregator",
    "AGGREGATERS":       "aggregator",
    "MINERAL TYPE":      "aggregator",   # sometimes labelled differently
    "GRADE":             "aggregator",

    # Dispatch Quantity
    "DISPATCH QTY":       "dispatch_qty",
    "DISPATCH QUANTITY":  "dispatch_qty",
    "DISPATCH.QTY":       "dispatch_qty",
    "DISPATCHQTY":        "dispatch_qty",
    "QUANTITY":           "dispatch_qty",
    "QTY":                "dispatch_qty",
    "TONNAGE":            "dispatch_qty",
    "TONS":               "dispatch_qty",

    # Stationary / Stationery Number
    "STATIONARY NO":   "stationary_no",
    "STATIONERY NO":   "stationary_no",
    "STATIONARY.NO":   "stationary_no",
    "STATIONERY.NO":   "stationary_no",
    "STATIONARYNO":    "stationary_no",
    "STATIONERYNO":    "stationary_no",
    "ST NO":           "stationary_no",
    "STNO":            "stationary_no",

    # Sales Value
    "SALES VALUE":    "sales_value",
    "SALES.VALUE":    "sales_value",
    "SALESVALUE":     "sales_value",
    "SALES":          "sales_value",
    "VALUE":          "sales_value",
    # ✅ Actual Excel header variants
    "SALE VALUE":     "sales_value",   # singular ← your Excel uses this
    "SALE.VALUE":     "sales_value",
    "SALEVALUE":      "sales_value",
    "SALE AMT":       "sales_value",
    "SALE AMOUNT":    "sales_value",
    "SALES AMOUNT":   "sales_value",
    "AMOUNT":         "sales_value",
    "ROYALTY VALUE":  "sales_value",
}

# Internal field names used by the automation engine
ALL_FIELDS = [
    "vehicle_no",
    "vehicle_type",
    "driver",
    "license",
    "phone",
    "aggregator",
    "dispatch_qty",
    "stationary_no",
    "sales_value",
]


# ── Core loader ──────────────────────────────────────────────────────────────

def load_records(file_path: str) -> tuple[list[dict], list[str]]:
    """
    Load Transit Pass records from an Excel file.
    Returns: (records list, warnings list)
    """
    warnings: list[str] = []
    records:  list[dict] = []

    df = pd.read_excel(file_path, header=0, dtype=str)
    df = df.fillna("").astype(str)

    # Normalise headers: strip whitespace, UPPERCASE
    df.columns = [str(c).strip().upper() for c in df.columns]

    # Build column → field mapping
    col_to_field: dict[str, str] = {}
    for col in df.columns:
        field = COLUMN_ALIASES.get(col)
        if field and field not in col_to_field.values():
            col_to_field[col] = field

    if not col_to_field:
        warnings.append(
            "⚠️  No recognised columns found. Expected headers like: "
            "VEHICLE NO, DRIVER, LICENSE, PHONE, AGGREGATOR, DISPATCH QTY, "
            "STATIONARY NO, SALES VALUE"
        )
        return [], warnings

    # Check for multiple vehicle-no columns (dual-block layout)
    veh_cols = [c for c, f in col_to_field.items() if f == "vehicle_no"]
    if len(veh_cols) > 1:
        blocks = _split_into_blocks(df, veh_cols, col_to_field)
    else:
        blocks = [("MAIN", col_to_field)]

    for block_name, mapping in blocks:
        for idx, row in df.iterrows():
            rec: dict = {"_row": int(idx) + 2, "_side": block_name}
            for col, field in mapping.items():
                rec[field] = str(row.get(col, "")).strip()
            # Skip rows with no vehicle number
            if not rec.get("vehicle_no"):
                continue
            # Ensure all fields present
            for f in ALL_FIELDS:
                rec.setdefault(f, "")
            records.append(rec)

    if not records:
        warnings.append("⚠️  Excel loaded but no valid records found (all vehicle numbers empty).")
    else:
        detected = [f"{col} → {field}" for col, field in list(col_to_field.items())[:10]]
        warnings.append(
            f"ℹ️  Detected {len(col_to_field)} columns: {', '.join(detected)}"
            + (" …and more" if len(col_to_field) > 10 else "")
        )
        # Warn about missing important fields
        found_fields = set(col_to_field.values())
        important = {"aggregator", "dispatch_qty", "stationary_no", "sales_value"}
        missing = important - found_fields
        if missing:
            warnings.append(
                f"⚠️  Missing columns (will be blank): {', '.join(sorted(missing))}. "
                "Add these headers to your Excel for full automation."
            )

    return records, warnings


def _split_into_blocks(
    df: pd.DataFrame,
    veh_cols: list[str],
    col_to_field: dict[str, str],
) -> list[tuple[str, dict[str, str]]]:
    col_list = list(df.columns)
    blocks = []
    for i, veh_col in enumerate(veh_cols):
        veh_idx = col_list.index(veh_col)
        next_veh_idx = col_list.index(veh_cols[i + 1]) if i + 1 < len(veh_cols) else len(col_list)
        block_cols = col_list[veh_idx:next_veh_idx]
        block_map = {c: f for c, f in col_to_field.items() if c in block_cols}
        blocks.append((f"BLOCK{i+1}", block_map))
    return blocks


# ── Display helpers ───────────────────────────────────────────────────────────

def records_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """Convert records list to a clean DataFrame for display."""
    if not records:
        return pd.DataFrame()

    display_cols = [
        "_row", "_side",
        "vehicle_no", "vehicle_type", "driver", "license", "phone",
        "aggregator", "dispatch_qty", "stationary_no", "sales_value",
    ]
    df = pd.DataFrame(records)
    existing = [c for c in display_cols if c in df.columns]
    df = df[existing].copy()
    df.rename(columns={
        "_row":          "Row",
        "_side":         "Block",
        "vehicle_no":    "Vehicle No",
        "vehicle_type":  "Vehicle Type",
        "driver":        "Driver",
        "license":       "License",
        "phone":         "Driver Mobile",
        "aggregator":    "Aggregator",
        "dispatch_qty":  "Dispatch Qty",
        "stationary_no": "Stationary No",
        "sales_value":   "Sales Value",
    }, inplace=True)
    return df


def add_status_column(records: list[dict], file_path: str, output_path: str):
    """Write the original Excel back with a Status column appended."""
    df_orig = pd.read_excel(file_path, header=0, dtype=str)

    status_by_row: dict[int, list[str]] = {}
    for r in records:
        row_num = r.get("_row", 0)
        if row_num not in status_by_row:
            status_by_row[row_num] = []
        status_by_row[row_num].append(r.get("_status", "Pending"))

    statuses = []
    for i in range(len(df_orig)):
        row_num = i + 2
        row_statuses = status_by_row.get(row_num, [""])
        statuses.append(" | ".join(row_statuses))

    df_orig["Automation Status"] = statuses

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df_orig.to_excel(writer, index=False, sheet_name="Records")
        wb = writer.book
        ws = writer.sheets["Records"]
        green = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#276221"})
        red   = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
        last_row   = len(df_orig) + 1
        status_col = len(df_orig.columns) - 1
        ws.conditional_format(1, status_col, last_row, status_col,
            {"type": "text", "criteria": "containing", "value": "✅", "format": green})
        ws.conditional_format(1, status_col, last_row, status_col,
            {"type": "text", "criteria": "containing", "value": "❌", "format": red})
