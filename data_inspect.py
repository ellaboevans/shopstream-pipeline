# inspect.py
# ─────────────────────────────────────────────────────────────
# Quick inspection of all 3 raw source files
# Run this BEFORE building the pipeline
# so you understand exactly what you're working with
# ─────────────────────────────────────────────────────────────

import pandas as pd
import json
from pathlib import Path
from config import CONFIG

def divider(title):
    print("\n"+ "="* 60)
    print(f" {title}")
    print("="* 60)
    
    
# Source 1: Website CSV
divider("Source 1: Website CSV")

website = pd.read_csv(
    CONFIG['input_dir'] / "website_customers.csv",
    encoding="iso-8859-1"
    )


print(f"\nShape: {website.shape}")
print(f"\n Column names\n:{list(website.columns)}")
print(f"\nData types:\n{website.dtypes}")
print(f"\nFirst 5 rows:\n{website.head()}")
print(f"\nNull counts:\n{website.isna().sum()}")
print(f"\nSample Region values:\n{website['Region'].value_counts().head(10)}")
print(f"\nSample Email values:\n{website['CustomerEmail'].head(10).tolist()}")
print(f"\nTest accounts:\n{website[website['CustomerEmail'].str.contains('test.shopstream', na=False)]}")

# ── SOURCE 2: CRM JSON ────────────────────────────────────────
divider("SOURCE 2: CRM JSON")

with open(CONFIG["input_dir"] / "crm_export.json") as f:
    raw = json.load(f)

print(f"\nTop level keys: {list(raw.keys())}")
print(f"\nTotal records: {len(raw['customers'])}")
print("\nFirst record (raw):")
print(json.dumps(raw['customers'][0], indent=2))
print("\nSecond record (raw):")
print(json.dumps(raw['customers'][1], indent=2))

# flatten it
crm = pd.json_normalize(raw['customers'], sep='_')
print(f"\nAfter flattening — columns:\n{list(crm.columns)}")
print(f"\nShape: {crm.shape}")
print(f"\nNull counts:\n{crm.isna().sum()}")
print(f"\nSample Region values:\n{crm['region'].value_counts().head(10)}")


# ── SOURCE 3: ERP Fixed-Width ─────────────────────────────────
divider("SOURCE 3: ERP Fixed-Width")

with open(CONFIG["input_dir"] / "erp_customers.txt") as f:
    lines = f.readlines()

print(f"\nTotal lines: {len(lines)}")
print("\nFirst raw line (with positions):")
line = lines[0]
print(repr(line))
print("\nManually parsed:")
print(f"  customer_id : '{line[0:10].strip()}'")
print(f"  full_name   : '{line[10:60].strip()}'")
print(f"  email       : '{line[60:120].strip()}'")
print(f"  phone       : '{line[120:140].strip()}'")
print(f"  region_code : '{line[140:145].strip()}'")
print(f"  date        : '{line[145:155].strip()}'")
print(f"  status      : '{line[155:160].strip()}'")

# read it properly
erp = pd.read_fwf(
    CONFIG["input_dir"] / "erp_customers.txt",
    colspecs=[(0,10),(10,60),(60,120),(120,140),(140,145),(145,155),(155,160)],
    names=["customer_id","full_name","email","phone","region_code","registration_date","status"],
    dtype=str
)
print(f"\nAfter parsing — shape: {erp.shape}")
print(f"\nFirst 5 rows:\n{erp.head()}")
print(f"\nNull counts:\n{erp.isna().sum()}")
print(f"\nStatus values:\n{erp['status'].value_counts()}")

# ── SUMMARY ───────────────────────────────────────────────────
divider("SUMMARY — What We Are Dealing With")

print(f"""
SOURCE          RECORDS     FORMAT          KNOWN ISSUES
──────────────────────────────────────────────────────────────
Website CSV     {len(website):<10}  ISO-8859-1 CSV  Bad emails, test accounts,
                                            messy regions, mixed case names

CRM JSON        {len(crm):<10}  Nested JSON     Nested profile fields,
                                            messy regions, messy phones

ERP Text        {len(erp):<10}  Fixed-width     No headers, full_name needs
                                            splitting, old 2019 dates

TOTAL           {len(website)+len(crm)+len(erp):<10}
""")