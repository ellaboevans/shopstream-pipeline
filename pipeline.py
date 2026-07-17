# pipeline.py
# ─────────────────────────────────────────────────────────────
# ShopStream Customer Data Quality Pipeline
# Entry point — runs the full pipeline end to end
#
# Author: Evans
# Run:    python pipeline.py
# ─────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np
import json
import re
import requests
from datetime import datetime
from pathlib import Path
import logging

from config import CONFIG
from ingest import ingest_all_sources
from clean import clean_dataframe
from deduplicate import deduplicate_customers
from validate import run_quality_checks
from export import (
    export_all
    )

# Config Setup
CONFIG['log_dir'].mkdir(parents=True, exist_ok=True)
CONFIG['output_dir'].mkdir(parents=True, exist_ok=True)
CONFIG['input_dir'].mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG['log_dir'] / "pipeline.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Synthetic Data Generator
def generate_synthetic_data():
    """
    Generate 4 source datasets with realistic data quality problems.
    Run this once to create test data files in data/raw/
    """
    
    logger.info("Generating synthetic source data...")
    np.random.seed(42)
    n = 1000
    
    # Shared data pools
    emails_pool = [
        f"customer{i}@{'gmail' if i % 3 == 0 else 'yahoo' if i %3 == 1 else 'company'}.com" 
        for i in range(800)
    ]
    
     # intentional bad emails for cleaning practice
    emails_pool += [
        "not-an-email",
        "missing@",
        "@nodomain.com",
        "",
        "double@@sign.com"
    ]
    
    first_names = [
        "Maria", "José", "André", "Léa", "François",
        "Müller", "O'Brien", "John", "Jane", "Mike",
        "Sarah", "Alex", "Chris", "Ama", "Kofi",
        "Evans", "Abena", "Kwame", "Akosua", "Yaw"
    ] * 60
    
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones",
        "Garcia", "Martínez", "Díaz", "López", "González",
        "Wang", "Kim", "Mensah", "Asante", "Boateng"
    ] * 70
    
     # messy region values — 15+ variants for only 3 valid values
    regions_messy = (
        ["US", "us", "USA", "united states", "North America"] * 150 +
        ["EU", "eu", "Europe", "EMEA", "europe"]              * 150 +
        ["APAC", "apac", "Asia Pacific", "Asia", "AP"]        * 100 +
        [None, "", "N/A"]                                      * 80
    )
    np.random.shuffle(regions_messy)
    
    # messy phone formats — real world problem
    phones_messy = (
        [
            "+1 (555) 123-4567",
            "555.123.4567",
            "5551234567",
            "+44 20 7946 0958",
            "020 7946 0958",
            "+81-3-1234-5678",
            "invalid-phone",
            None
        ] * 125
    )
    np.random.shuffle(phones_messy)
    
    # ── SOURCE 1: Website CSV (ISO-8859-1 encoded) ────────────
    logger.info("  Generating website_customers.csv...")
    website_df = pd.DataFrame({
        "CustomerEmail":     np.random.choice(emails_pool, n),
        "First Name":        [first_names[i % len(first_names)] for i in range(n)],
        "Last Name":         [last_names[i % len(last_names)]   for i in range(n)],
        "Phone":             [phones_messy[i % len(phones_messy)] for i in range(n)],
        "Region":            [regions_messy[i % len(regions_messy)] for i in range(n)],
        "Registration Date": pd.date_range("2020-01-01", periods=n, freq="4h")
                               .strftime("%Y-%m-%d"),
        "OptOut":            np.random.choice([0, 1], n, p=[0.85, 0.15]),
    })

    # add test accounts — should be removed during cleaning
    test_accounts = pd.DataFrame({
        "CustomerEmail":     [f"test{i}@test.shopstream.com" for i in range(20)],
        "First Name":        ["Test"] * 20,
        "Last Name":         ["Account"] * 20,
        "Phone":             [None] * 20,
        "Region":            ["US"] * 20,
        "Registration Date": ["2023-01-01"] * 20,
        "OptOut":            [0] * 20,
    })

    website_df = pd.concat([website_df, test_accounts], ignore_index=True)
    website_df.to_csv(
        CONFIG["input_dir"] / "website_customers.csv",
        index=False,
        encoding="iso-8859-1"
    )
    logger.info(f"  website_customers.csv → {len(website_df)} records")


    # ── SOURCE 2: CRM JSON ────────────────────────────────────
    logger.info("  Generating crm_export.json...")
    crm_records = []
    for i in range(n // 2):
        crm_records.append({
            "id":    f"CRM-{i:06d}",
            "email": np.random.choice(emails_pool),
            "profile": {
                "first_name": first_names[np.random.randint(0, len(first_names))],
                "last_name":  last_names[np.random.randint(0, len(last_names))],
            },
            "phone":             phones_messy[i % len(phones_messy)],
            "region":            regions_messy[i % len(regions_messy)],
            "registration_date": f"202{np.random.randint(0,4)}-{np.random.randint(1,13):02d}-01",
            "opt_out":           bool(np.random.choice([0, 1], p=[0.85, 0.15])),
            "lifetime_value":    round(np.random.uniform(50, 5000), 2),
        })

    crm_path = CONFIG["input_dir"] / "crm_export.json"
    crm_path.write_text(json.dumps({"customers": crm_records}))
    logger.info(f"  crm_export.json → {len(crm_records)} records")


    # ── SOURCE 3: ERP Fixed-Width ─────────────────────────────
    logger.info("  Generating erp_customers.txt...")
    erp_lines = []
    for i in range(n // 4):
        email  = np.random.choice(emails_pool)
        name   = f"{first_names[i % len(first_names)]} {last_names[i % len(last_names)]}"
        phone  = str(phones_messy[i % len(phones_messy)] or "")
        region = str(regions_messy[i % len(regions_messy)] or "")
        date   = f"2019-{np.random.randint(1, 13):02d}-01"
        status = np.random.choice(["ACTIV", "INACT"])

        # fixed-width: pad/truncate each field to exact width
        line = (
            f"{str(i):>10}"       # customer_id    (10 chars)
            f"{name:<50}"         # full_name       (50 chars)
            f"{email:<60}"        # email           (60 chars)
            f"{phone:<20}"        # phone           (20 chars)
            f"{region:<20}"        # region_code     (5  chars)
            f"{date:<10}"         # date            (10 chars)
            f"{status:<5}"        # status          (5  chars)
        )
        erp_lines.append(line)

    (CONFIG["input_dir"] / "erp_customers.txt").write_text("\n".join(erp_lines))
    logger.info(f"  erp_customers.txt → {len(erp_lines)} records")

    logger.info("Synthetic data generation complete!")
    logger.info(f"Files saved to: {CONFIG['input_dir']}")


def run_pipeline():
    """Run the full data pipeline end to end."""
    logger.info("Starting ShopStream Customer Data Quality Pipeline...")
    
    start_time = datetime.now()
    
    # 1. Ingest all sources
    raw = ingest_all_sources()
    input_count = len(raw)
    
    # 2. Clean
    cleaned = clean_dataframe(raw)
    
    # 3. Deduplicate
    deduped = deduplicate_customers(cleaned)
    
    # 4. Quality Validation
    quality_report = run_quality_checks(deduped)
    
    # 5: Export campaign-ready customers & EDA report
    export_all(deduped, quality_report)
    
    # Summary
    duration = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Input records:          {input_count:,}")
    logger.info(f"  Output (golden) records:{len(deduped):,}")
    logger.info(f"  Duplicates removed:     {input_count - len(deduped):,}")
    logger.info(f"  Quality checks passed:  {(quality_report['status'] == 'PASS').sum()}/{len(quality_report)}")
    logger.info(f"  Duration:               {duration:.1f}s")
    logger.info("=" * 60)

if __name__ == "__main__":
    # generate_synthetic_data # uncomment only to create raw data files once
    run_pipeline()
    
