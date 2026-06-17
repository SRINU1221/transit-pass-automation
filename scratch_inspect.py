import pandas as pd
import glob
from pathlib import Path

files = glob.glob(r"e:\auto_rayalty\*.xlsx")
print("Found Excel files:", files)

for f in files:
    try:
        df = pd.read_excel(f, nrows=2)
        print(f"\nFile: {Path(f).name}")
        print("Columns:", list(df.columns))
        print("First row data:")
        print(df.to_dict(orient='records'))
    except Exception as e:
        print(f"Error reading {f}: {e}")
