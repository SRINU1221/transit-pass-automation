"""
test_excel_mapping.py - Run this to verify Excel column aliases are correct.
Usage: python test_excel_mapping.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"e:\auto_rayalty")

from excel_processor import load_records, records_to_dataframe

EXCEL_PATH = r"e:\auto_rayalty\uploaded_royalty.xlsx"

records, warnings = load_records(EXCEL_PATH)

print("\n=== WARNINGS / INFO ===")
for w in warnings:
    print(w)

print("\n=== RECORDS ===")
for i, r in enumerate(records[:3]):
    print(f"\nRow {i+1}:")
    print(f"  vehicle_no   : {r.get('vehicle_no','')}")
    print(f"  driver       : {r.get('driver','')}")
    print(f"  license      : {r.get('license','')}")
    print(f"  phone        : {r.get('phone','')}")
    print(f"  aggregator   : {r.get('aggregator','')}")
    print(f"  dispatch_qty : {r.get('dispatch_qty','')}")
    print(f"  stationary_no: {r.get('stationary_no','')}")
    print(f"  sales_value  : {r.get('sales_value','')}")
