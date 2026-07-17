# ingest.py
# ─────────────────────────────────────────────────────────────
# Ingestion functions for all 3 source systems.
# Each function handles one source and returns a clean
# standardised DataFrame ready for the cleaning step.
# ─────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np
import json
from pathlib import Path
import logging

from config import CONFIG

logger = logging.getLogger(__name__)

STANDARD_SCHEMA = [
    "email",
    "first_name",
    "last_name",
    "phone",
    "region",
    "registration_date",
    "opt_out",
    "source"
]

def ingest_website_csv(file_path: Path) -> pd.DataFrame:
    """"
    Ingest the website registration CSV export.

    Known issues handled here:
    - ISO-8859-1 encoding (legacy system)
    - Column names have spaces and inconsistent casing
    - Contains test accounts that must be removed
    - Phone stored as number — must stay as string
    """
    logger.info(f"Ingesting website data from: {file_path}")
    
    df = pd.read_csv(
        file_path,
        encoding="iso-8859-1",
        dtype={'Phone': str},  
        parse_dates=['Registration Date'],
        na_values=["", "N/A", "null", "NULL", "none", "NaN"],
    )
    
    # Standardise column names to snake_case
    def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(r"[^\w]", "_", regex=True)
            .str.replace(r"_+", "_", regex=True)
            .str.strip("_")
        )
        return df

    df = df.pipe(clean_column_names)
     
    # Rename to standard schema
    df.rename(columns={
        "customeremail":    "email",
        "registration_date": "registration_date",
        "optout":           "opt_out",
    }, inplace=True)
    
    
    # Remove test accounts (identified by email domain)
    test_mask = df["email"].str.contains(
        r"@test\.shopstream\.com$", 
        case=False, 
        na=False
    )
    
    removed = test_mask.sum()
    df = df[~test_mask].copy()
    logger.info(f"Removed {removed} test accounts from website data.")
    
    # Tag source
    df["source"] = "website"
    
    logger.info(f"Finished ingesting website data. Records ingested: {len(df)}")
    return df

def ingest_crm_json(file_path: Path)-> pd.DataFrame:
    """
    Ingest customer data from the CRM JSON export.

    Known issues handled here:
    - Nested profile fields (profile.first_name, profile.last_name)
    - After flattening → profile_first_name, profile_last_name
    - Same messy region variants as website
    - CRM is SOURCE OF TRUTH for opt_out (GDPR critical)
    """
    logger.info(f"Ingesting CRM data from: {file_path}")
    
    raw = json.loads(file_path.read_text())
    logger.info(f"  Top level keys: {list(raw.keys())}")
    logger.info(f"  Total raw records: {len(raw['customers'])}")
    
    # Flatten nested JSON
    df = pd.json_normalize(
        raw['customers'],
        sep="_"
    )
    
    # Rename to standard schema
    df.rename(columns={
        "profile_first_name": "first_name",
        "profile_last_name":  "last_name",
    }, inplace=True)
    
    # Fix registration_date type
    df["registration_date"] = pd.to_datetime(
        df["registration_date"],
        errors="coerce"
    )
    
    # Tag source
    df["source"] = "crm"
    logger.info(f"Finished ingesting CRM data. Records ingested: {len(df)}")
    
    return df
    
def ingest_erp_fixed_width(file_path: Path)-> pd.DataFrame:
    """
    Ingest the legacy ERP fixed-width text file.
    Column positions defined by ERP system spec.

    Known issues handled here:
    - Region values like 'North America' overflow into date/status
    - full_name needs splitting into first_name and last_name
    - Everything reads as string first — types fixed after
    - Old 2019 dates — valid, just old

    Field layout (corrected):
        [0:10]    customer_id
        [10:60]   full_name
        [60:120]  email
        [120:140] phone
        [140:160] region_code   ← widened from 5 to 20 chars
        [160:170] registration_date
        [170:175] status
    """
    logger.info(f"Ingesting ERP data from: {file_path}")
    
    colspecs = [
        (0,   10),    # customer_id      (10 chars)
        (10,  60),    # full_name        (50 chars)
        (60,  120),   # email            (60 chars)
        (120, 140),   # phone            (20 chars)
        (140, 160),   # region_code      (20 chars) 
        (160, 170),   # registration_date(10 chars)
        (170, 175),   # status           (5  chars)
    ]
    
    col_names = [
       "customer_id",
        "full_name",
        "email",
        "phone",
        "region_code",
        "registration_date",
        "status"
    ]
    
    df = pd.read_fwf(
        file_path,
        colspecs=colspecs,
        names=col_names,
        dtype=str,
        encoding="utf-8",
    )
    
    # Strip whitespaces from all columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
        
    # Split full_name into first_name and last_name
    name_split = df["full_name"].str.split(" ", n=1, expand=True)
    df["first_name"] = name_split[0]
    df["last_name"] = name_split[1] if 1 in name_split.columns else np.nan
    
    # Fix registration_date type
    df["registration_date"] = pd.to_datetime(
        df["registration_date"],
        format="%Y-%m-%d",
        errors="coerce",
    )
    
    # Rename region_code to region for standard schema
    df.rename(columns={"region_code": "region"}, inplace=True)
    
    # Add opt_out column (ERP has status not opt_out)
    # INACT = inactive customer → opt_out = True
    df["opt_out"] = df["status"].str.upper() == "INACT"
    
    # Tag source
    df["source"] = "erp"
    
    return df

def align_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Align a source DataFrame to the standard schema.
    Missing columns are added as NaN.
    Extra columns are dropped.
    """
    for col in STANDARD_SCHEMA:
        if col not in df.columns:
            df[col] = np.nan  
    return df[STANDARD_SCHEMA].copy()

def ingest_all_sources() -> pd.DataFrame:
    """
    Ingest all 3 sources and combine into one raw DataFrame.
    Each source is aligned to the standard schema before combining.
    """
    logger.info("=" * 60)
    logger.info("INGESTION - Pulling all sources into raw DataFrames")
    logger.info("=" * 60)
    
    frames = []
    
    # SOURCE 1: Website CSV 
    website_df = ingest_website_csv(
        CONFIG["input_dir"] / "website_customers.csv"
    )
    frames.append(align_schema(website_df))
    
    # SOURCE 2: CRM JSON
    crm_df = ingest_crm_json(
        CONFIG['input_dir'] / "crm_export.json" 
    )
    frames.append(align_schema(crm_df))
    
    # SOURCE 3: ERP Fixed-Width
    erp_df = ingest_erp_fixed_width(
        CONFIG['input_dir'] / "erp_customers.txt" 
    )
    frames.append(align_schema(erp_df))
    
    # Combine all sources into one raw DataFrame
    combined = pd.concat(frames, ignore_index=True)
   
    # Summary logs
    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE - Summary:\n")
    logger.info(f"  Total records ingested: {len(combined)}")
    logger.info("  By source:")
    for source in combined["source"].unique():
        count = (combined["source"] == source).sum()
        logger.info(f"    {source}: {count} records")
    logger.info("=" * 60)
    
    return combined
   
    
   