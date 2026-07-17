# deduplicate.py
# ─────────────────────────────────────────────────────────────
# Deduplication logic for ShopStream customer pipeline.
#
# Strategy:
#   Pass 1 → exact email match (catches ~80% of duplicates)
#   Pass 2 → exact phone match (catches remaining ~10%)
#
# Source priority (lower = more trusted):
#   CRM > Website > ERP
#
# Merge rules:
#   - Take first non-null value from highest priority source
#   - opt_out: if ANY source says opted out → mark as opted out
#   - Track which sources contributed to each record
# ─────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np
import logging

from config import CONFIG

logger = logging.getLogger(__name__)

def assign_source_priority(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a numeric priority column based on source.
    Lower number = more trusted source.

    CRM=1, Website=2, ERP=3
    """
    df["source_priority"] = df["source"].map(
        CONFIG["source_priority"]
    ).fillna(99)

    logger.info("  Source priority assigned:")
    for source, priority in CONFIG["source_priority"].items():
        count = (df["source"] == source).sum()
        logger.info(f"    {source} (priority {priority}): {count} records")

    return df

def merge_duplicate_group(group: pd.DataFrame) -> pd.Series:
    """
    Merge a group of duplicate records into one golden record.

    Rules:
    1. Sort by source priority — most trusted first
    2. For each field take first non-null value
    3. opt_out: if ANY record is opted out → True (GDPR)
    4. Track all contributing sources
    """
    # sort by priority — most trusted first
    group = group.sort_values("source_priority")

    # start with the most trusted record
    golden = group.iloc[0].copy()

    # for each field fill nulls from lower priority sources
    fields_to_merge = [
        "first_name",
        "last_name",
        "phone",
        "region",
        "registration_date"
    ]

    for field in fields_to_merge:
        if field in group.columns and pd.isna(golden.get(field)):
            non_null = group[field].dropna()
            if len(non_null) > 0:
                golden[field] = non_null.iloc[0]

    # GDPR rule — opt_out from ANY source = opted out
    if "opt_out" in group.columns:
        golden["opt_out"] = (
            group["opt_out"]
            .fillna(0)
            .astype(bool)
            .any()
        )

    # track provenance — which sources contributed
    golden["sources"]       = ",".join(group["source"].unique())
    golden["source_count"]  = len(group["source"].unique())

    return golden

def dedupe_by_email(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pass 1: Deduplicate records with valid emails.
    Groups by email and merges duplicates.

    Records with invalid/null emails are set aside
    and cannot be deduplicated by email.
    """
    logger.info("  Pass 1: Deduplicating by email...")

    # split valid and invalid email records
    valid_mask   = df["email_valid"] == True
    valid_df     = df[valid_mask].copy()
    invalid_df   = df[~valid_mask].copy()

    before = len(valid_df)

    # group by email and merge each group
    deduped = (
        valid_df
        .groupby("email", sort=False)
        .apply(merge_duplicate_group, include_groups=False)
        .reset_index()
    )

    after    = len(deduped)
    removed  = before - after

    logger.info(f"    Valid email records before: {before}")
    logger.info(f"    Valid email records after:  {after}")
    logger.info(f"    Duplicates removed:         {removed}")
    logger.info(f"    Invalid email records kept: {len(invalid_df)}")

    return deduped, invalid_df

def dedupe_by_phone(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pass 2: Deduplicate remaining records by phone number.
    Only runs on records that were not matched by email.

    Catches cases where same customer has different emails
    but same phone number.
    """
    logger.info("  Pass 2: Deduplicating by phone...")

    # only deduplicate records that have a phone number
    has_phone    = df["phone"].notna()
    phone_df     = df[has_phone].copy()
    no_phone_df  = df[~has_phone].copy()

    before = len(phone_df)

    deduped = (
        phone_df
        .groupby("phone", sort=False)
        .apply(merge_duplicate_group, include_groups=False)
        .reset_index(drop=True)
    )

    after   = len(deduped)
    removed = before - after

    logger.info(f"    Phone records before: {before}")
    logger.info(f"    Phone records after:  {after}")
    logger.info(f"    Duplicates removed:   {removed}")

    # combine phone deduped + records with no phone
    result = pd.concat([deduped, no_phone_df], ignore_index=True)
    return result

def deduplicate_customers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run full deduplication pipeline.
    Called from pipeline.py
    """
    logger.info("=" * 60)
    logger.info("DEDUPLICATION — Merging duplicate records")
    logger.info("=" * 60)
    logger.info(f"Records entering deduplication: {len(df)}")

    # Step 1 — assign source priority
    df = assign_source_priority(df)

    # Step 2 — sort by priority so CRM always wins
    df = df.sort_values("source_priority").reset_index(drop=True)

    # Step 3 — Pass 1: deduplicate by email
    deduped_df, invalid_df = dedupe_by_email(df)

    # Step 4 — Pass 2: deduplicate invalid records by phone
    invalid_deduped = dedupe_by_phone(invalid_df)

    # Step 5 — combine results
    final = pd.concat(
        [deduped_df, invalid_deduped],
        ignore_index=True
    )

    # Summary
    removed_total = len(df) - len(final)
    multi_source  = (final.get("source_count", pd.Series([1])) > 1).sum()

    logger.info("=" * 60)
    logger.info("DEDUPLICATION COMPLETE")
    logger.info(f"  Records before: {len(df)}")
    logger.info(f"  Records after:  {len(final)}")
    logger.info(f"  Duplicates removed:       {removed_total}")
    logger.info(f"  Multi-source records:     {multi_source}")
    logger.info(f"  Opted out (GDPR flagged): {final['opt_out'].sum()}")
    logger.info("=" * 60)

    return final