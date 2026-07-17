# export.py
# ─────────────────────────────────────────────────────────────
# Export functions for ShopStream customer pipeline.
#
# Delivers 3 outputs:
#   1. golden_customers.parquet  → analytics & pipelines
#   2. golden_customers.csv      → marketing team upload
#   3. quality_report.csv        → data governance proof
#   4. customer_quality_report.png 6-chart EDA visualization
# ─────────────────────────────────────────────────────────────

import pandas as pd
import logging
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

from config import CONFIG
from utils import file_size

logger = logging.getLogger(__name__)


def export_golden_parquet(df: pd.DataFrame) -> Path:
    """
    Export golden customer records as Parquet.
    Used by downstream pipelines and analytics tools.

    Why Parquet:
    - 70-90% smaller than CSV
    - Preserves data types
    - Fast columnar reads
    """
    path = CONFIG["output_dir"] / "golden_customers.parquet"

    df.to_parquet(
        path,
        index=False,
        engine="pyarrow",
        compression="gzip"
    )

    size_kb = file_size(path)
    logger.info(f"  Parquet export: {path} ({size_kb:.1f} KB)")
    return path


def export_golden_csv(df: pd.DataFrame) -> Path:
    """
    Export golden customer records as CSV.
    Used by marketing team for campaign upload.

    Why UTF-8 BOM:
    - encoding='utf-8-sig' adds BOM marker
    - Makes Excel open accented characters correctly
    - François stays François not FranÃ§ois
    """
    path = CONFIG["output_dir"] / "golden_customers.csv"

    df.to_csv(
        path,
        index=False,
        encoding="utf-8-sig"    # BOM for Excel compatibility
    )

    size_kb = file_size(path)
    logger.info(f"  CSV export: {path} ({size_kb:.1f} KB)")
    return path


def export_quality_report(report: pd.DataFrame) -> Path:
    """
    Export quality validation report as CSV.
    Used by data governance team as proof of quality.
    """
    path = CONFIG["output_dir"] / "quality_report.csv"

    report.to_csv(path, index=False)

    logger.info(f"  Quality report: {path}")
    return path


def export_campaign_ready(df: pd.DataFrame) -> Path:
    """
    Export ONLY campaign-ready customers:
    - Valid email
    - Not opted out
    - Has a region assigned

    This is the FINAL file the marketing team uploads
    to their email platform.
    """
    campaign_df = df[
        (df["email_valid"] == True) &
        (df["opt_out"]     == False) &
        (df["region"].notna())
    ].copy()

    # keep only columns marketing team needs
    campaign_columns = [
        "email",
        "first_name",
        "last_name",
        "region",
        "sources"
    ]

    campaign_df = campaign_df[campaign_columns]

    path = CONFIG["output_dir"] / "campaign_customers.csv"
    campaign_df.to_csv(path, index=False, encoding="utf-8-sig")

    size_kb = path.stat().st_size / 1024
    logger.info(f"  Campaign file: {path} ({size_kb:.1f} KB)")
    logger.info(f"  Campaign ready customers: {len(campaign_df)}")

    # breakdown by region
    for region, count in campaign_df["region"].value_counts().items():
        logger.info(f"    {region}: {count} customers")

    return path


def generate_eda_report(df: pd.DataFrame):
    """Generate a professional 6-chart EDA and quality visualization."""
    logger.info("STEP 5: Generating EDA visualization...")
    
    output_dir = CONFIG["output_dir"]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("ShopStream Customer Data Quality Report", fontsize=16, fontweight="bold")
    colors = ["#2196F3", "#4CAF50", "#FF9800", "#F44336", "#9C27B0", "#00BCD4"]

    # 1. Customer Count by Region
    region_counts = df["region"].value_counts()
    axes[0, 0].bar(region_counts.index, region_counts.values, color=colors[:len(region_counts)])
    axes[0, 0].set_title("Customers by Region")
    axes[0, 0].set_ylabel("Count")
    axes[0, 0].set_xlabel("Region")
    for i, (r, c) in enumerate(region_counts.items()):
        axes[0, 0].text(i, c + 50, f"{c:,}", ha="center", fontweight="bold", fontsize=9)

    # 2. Registration Trend
    monthly = df.dropna(subset=["registration_date"]).set_index("registration_date").resample("ME").size()
    axes[0, 1].plot(monthly.index, monthly.values, color=colors[0], linewidth=2)
    axes[0, 1].fill_between(monthly.index, monthly.values, alpha=0.2, color=colors[0])
    axes[0, 1].set_title("Monthly Registration Trend")
    axes[0, 1].set_ylabel("New Customers")
    axes[0, 1].tick_params(axis="x", rotation=45)

    # 3. Source Contribution
    if "sources" in df.columns:
        source_counts = df["sources"].str.split(",").explode().value_counts()
    else:
        source_counts = df["source"].value_counts()
    axes[0, 2].pie(source_counts.values, labels=source_counts.index,
                   autopct="%1.1f%%", colors=colors[:len(source_counts)], startangle=90)
    axes[0, 2].set_title("Records by Source System")

    # 4. Field Completeness
    fields = ["email", "first_name", "last_name", "phone", "region"]
    completeness = df[fields].notna().mean().sort_values()
    bar_colors = ["#F44336" if v < 0.9 else "#4CAF50" for v in completeness.values]
    axes[1, 0].barh(completeness.index, completeness.values, color=bar_colors)
    axes[1, 0].set_xlim(0, 1.1)
    axes[1, 0].axvline(x=CONFIG["quality_threshold"], color="red",
                       linestyle="--", label=f"{CONFIG['quality_threshold']:.0%} threshold")
    axes[1, 0].set_title("Field Completeness Rate")
    axes[1, 0].legend(fontsize=8)
    for i, v in enumerate(completeness.values):
        axes[1, 0].text(v + 0.01, i, f"{v:.1%}", va="center", fontsize=9)

    # 5. Email Validity Breakdown
    if "email_valid" in df.columns:
        valid_counts = df["email_valid"].value_counts()
        labels = ["Valid", "Invalid"]
        values = [valid_counts.get(True, 0), valid_counts.get(False, 0)]
        wedge_colors = [colors[1], colors[3]]
        axes[1, 1].pie(values, labels=labels, autopct="%1.1f%%",
                       colors=wedge_colors, startangle=90)
        axes[1, 1].set_title("Email Validity")

    # 6. Opt-Out Rate by Region
    if "opt_out" in df.columns:
        opt_out_rate = df.groupby("region")["opt_out"].mean().sort_values()
        axes[1, 2].bar(opt_out_rate.index, opt_out_rate.values,
                       color=[colors[3] if v > 0.2 else colors[1] for v in opt_out_rate.values])
        axes[1, 2].set_title("Opt-Out Rate by Region")
        axes[1, 2].set_ylabel("Opt-Out Rate")
        axes[1, 2].axhline(y=0.2, color="red", linestyle="--", label="20% threshold")
        for i, (region, rate) in enumerate(opt_out_rate.items()):
            axes[1, 2].text(i, rate + 0.005, f"{rate:.1%}", ha="center", fontsize=9)

    plt.tight_layout()
    output_path = output_dir / "customer_quality_report.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"  EDA report saved: {output_path}")


def export_all(
    df: pd.DataFrame,
    quality_report: pd.DataFrame
) -> dict:
    """
    Run all exports and return paths.
    Called from pipeline.py
    """
    logger.info("=" * 60)
    logger.info("EXPORT — Delivering outputs")
    logger.info("=" * 60)

    paths = {}
    paths["parquet"]  = export_golden_parquet(df)
    paths["csv"]      = export_golden_csv(df)
    paths["report"]   = export_quality_report(quality_report)
    paths["campaign"] = export_campaign_ready(df)
    paths["visual"]  = generate_eda_report(df)

    logger.info("=" * 60)
    logger.info("EXPORT COMPLETE")
    logger.info(f"  All files saved to: {CONFIG['output_dir']}")
    logger.info("=" * 60)

    return paths