# clean.py
# ─────────────────────────────────────────────────────────────
# Cleaning and standardisation functions for ShopStream
# customer data pipeline.
#
# Each function handles ONE specific problem:
#   - clean_emails()    → standardise + validate
#   - clean_names()     → fix casing and encoding
#   - clean_phones()    → standardise 15+ formats
#   - clean_regions()   → map all variants to US/EU/APAC
#   - clean_nulls()     → handle missing values
#   - clean_dataframe() → runs ALL cleaning in order
# ─────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np
import re
import logging

from config import CONFIG

logger = logging.getLogger(__name__)


def clean_emails(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardise and validate email addresses.

    Problems fixed:
    - Mixed case → evans@GMAIL.com → evans@gmail.com
    - Leading/trailing spaces → ' evans@gmail.com '
    - Internal spaces → 'evans @gmail.com'
    - Empty strings and placeholder values → NaN
    - Invalid format flagged in email_valid column
    """
    logger.info("   Cleaning email addresses...")
    
    # Save original for audit/logging
    df["email_raw"] = df["email"].copy()
    
    # Standardise: strip spaces and lowercase
    df["email"] = (
        df["email"]
        .astype(str) # Ensure all entries are strings
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "", regex=True)  # Remove all internal spaces
    )
    
    df["email"] = df["email"].replace({"nan": np.nan, "none": np.nan, "":np.nan})  # Convert common placeholders to NaN
    
    # Validate format
    df["email_valid"] = df["email"].str.match(
        CONFIG["email_regex"],
        na=False
    )
    
    # Summary logging
    total = len(df)
    null_emails = df["email"].isna().sum()
    invalid_email = (~df["email_valid"]).sum()
    valid_emails = df["email_valid"].sum()
    
    logger.info(f"      Total records: {total}")
    logger.info(f"      Valid emails: {valid_emails}")
    logger.info(f"      Invalid emails: {invalid_email}")
    logger.info(f"      Null emails: {null_emails}")
    
    return df
    
def clean_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardise first_name and last_name columns.

    Problems fixed:
    - UPPERCASE names → 'EVANS' → 'Evans'
    - lowercase names → 'evans' → 'Evans'
    - Extra whitespace → 'Evans  Mensah' → 'Evans Mensah'
    - Placeholder strings → 'nan', 'none' → NaN
    """
    logger.info("   Cleaning names...")
    
    for col in ["first_name", "last_name"]:
        df[col] = (
            df[col]
            .astype(str) # Ensure all entries are strings
            .str.strip()
            .str.title()
            .str.replace(r"\s+", " ", regex=True)  # Replace multiple spaces with single
        )
        
        df[col] = df[col].replace({"nan": np.nan, "none": np.nan, "": np.nan})  # Convert common placeholders to NaN
        
        null_first = df["first_name"].isna().sum()
        null_last = df["last_name"].isna().sum()
        logger.info(f"      {col}: Null values after cleaning: {null_first})")
        logger.info(f"      {col}: Null values after cleaning: {null_last})")
        
        return df
    
    
def clean_phones(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardise phone numbers from 15+ formats.

    Problems fixed:
    - '+1 (555) 123-4567' → '+15551234567'
    - '555.123.4567'      → '5551234567'
    - '+44 20 7946 0958'  → '+442079460958'
    - 'invalid-phone'     → NaN
    - Too short numbers   → NaN

    Rule:
    - Preserve leading + for international numbers
    - Remove all non-digit characters
    - If less than 7 digits → NaN (not a real number)
    """
    logger.info("   Cleaning phone numbers...")
    
    def standardise_phone(phone):
        if pd.isna(phone) or str(phone).strip() in ("", "nan", "none", "None"):
            return np.nan
        
        phone = str(phone).strip()
        has_plus = phone.startswith("+")
        digits = re.sub(r"[^\d]", "", phone)  # Remove all non-digit characters
        
        if len(digits) < 7:  # Too short to be valid
            return np.nan
        
        return f"+{digits}" if has_plus else digits
    
    df["phone"] = df["phone"].apply(standardise_phone)
    
    null_phones = df["phone"].isna().sum()
    logger.info(f"      Null/invalid phones after cleaning: {null_phones}")
            
    
    return df

def clean_regions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map all region variants to one of 3 valid values:
    US, EU, or APAC.

    Problems fixed:
    - 'us', 'USA', 'united states', 'North America' → 'US'
    - 'eu', 'Europe', 'EMEA'                        → 'EU'
    - 'apac', 'Asia Pacific', 'Asia'                → 'APAC'
    - Anything not in the map                       → NaN
    """
    logger.info("  Cleaning regions...")

    REGION_MAP = {
        # US variants
        "us":            "US",
        "usa":           "US",
        "united states": "US",
        "north america": "US",
        "na":            "US",
        "amer":          "US",
        "america":       "US",
        "u.s.":          "US",
        "u.s.a.":        "US",
        # EU variants
        "eu":             "EU",
        "europe":         "EU",
        "emea":           "EU",
        "eur":            "EU",
        "european union": "EU",
        # APAC variants
        "apac":          "APAC",
        "asia":          "APAC",
        "asia pacific":  "APAC",
        "ap":            "APAC",
        "asia-pacific":  "APAC",
    }

    # save original for audit
    df["region_raw"] = df["region"].copy()

    df["region"] = (
        df["region"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(REGION_MAP)
    )

    # summary
    null_regions  = df["region"].isna().sum()
    mapped        = df["region"].notna().sum()

    logger.info(f"    Successfully mapped: {mapped}")
    logger.info(f"    Unmapped (null):     {null_regions}")
    logger.info("    Region distribution:")
    for region, count in df["region"].value_counts().items():
        logger.info(f"      {region}: {count}")

    return df

def clean_nulls(df: pd.DataFrame) -> pd.DataFrame:
    """
    Handle remaining null values after standardisation.

    Rules:
    - email is null   → drop the row (cannot be contacted)
    - first_name null → fill with 'Unknown'
    - last_name null  → fill with 'Unknown'
    - phone null      → acceptable, keep as NaN
    - region null     → acceptable, AI will infer later
    """
    logger.info("  Handling null values...")

    before = len(df)

    # drop rows with no email — unusable for campaign
    df = df.dropna(subset=["email"]).copy()
    dropped = before - len(df)
    logger.info(f"    Dropped {dropped} rows with null email")

    # fill name nulls
    df["first_name"] = df["first_name"].fillna("Unknown")
    df["last_name"]  = df["last_name"].fillna("Unknown")

    logger.info(f"    Remaining null phones:  {df['phone'].isna().sum()}")
    logger.info(f"    Remaining null regions: {df['region'].isna().sum()}")

    return df

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run all cleaning functions in the correct order.
    This is the only function called from pipeline.py
    """
    logger.info("=" * 60)
    logger.info("CLEANING — Standardising all fields")
    logger.info("=" * 60)
    logger.info(f"Records entering cleaning: {len(df)}")

    df = clean_emails(df)
    df = clean_names(df)
    df = clean_phones(df)
    df = clean_regions(df)
    df = clean_nulls(df)

    logger.info("=" * 60)
    logger.info("CLEANING COMPLETE")
    logger.info(f"  Records after cleaning: {len(df)}")
    logger.info(f"  Valid emails:   {df['email_valid'].sum()}")
    logger.info(f"  Null regions:   {df['region'].isna().sum()}")
    logger.info(f"  Null phones:    {df['phone'].isna().sum()}")
    logger.info("=" * 60)

    return df