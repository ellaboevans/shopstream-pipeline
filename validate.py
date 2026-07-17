# validate.py
# ─────────────────────────────────────────────────────────────
# Data quality validation for ShopStream customer pipeline.
#
# Runs 7 quality checks and produces a pass/fail report.
# Pipeline gates on 95% pass rate per check.
#
# Checks:
#   1. Email not null
#   2. First name not null
#   3. Region not null
#   4. Email uniqueness
#   5. Email format valid
#   6. Region values in valid set
#   7. Registration date in valid range
# ─────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np
import logging
from datetime import datetime

from config import CONFIG

logger = logging.getLogger(__name__)


class DataQualityValidator:
    """
    Runs configurable quality checks and produces
    a pass/fail report.

    Usage:
        v = DataQualityValidator(df, threshold=0.95)
        v.check_not_null("email", "Every customer needs email")
        v.check_unique("email", "No duplicate emails")
        report = v.generate_report()
    """

    def __init__(self, df: pd.DataFrame, threshold: float = 0.95):
        self.df        = df
        self.threshold = threshold
        self.results   = []
        self.n         = len(df)

    def _record(
        self,
        check: str,
        description: str,
        failed: int,
        total: int
    ) -> dict:
        """Record result of one quality check."""
        pass_rate = 1 - (failed / total) if total > 0 else 1.0
        status    = "PASS" if pass_rate >= self.threshold else "FAIL"

        result = {
            "check":       check,
            "description": description,
            "total":       total,
            "passed":      total - failed,
            "failed":      failed,
            "pass_rate":   round(pass_rate, 4),
            "status":      status,
        }

        self.results.append(result)
        return result

    def check_not_null(
        self,
        column: str,
        description: str
    ) -> dict:
        """Check column has no null values."""
        failed = int(self.df[column].isna().sum())
        return self._record(
            f"NOT NULL: {column}",
            description,
            failed,
            self.n
        )

    def check_unique(
        self,
        column: str,
        description: str
    ) -> dict:
        """Check column has no duplicate values."""
        non_null = self.df[column].dropna()
        failed   = int(non_null.duplicated().sum())
        return self._record(
            f"UNIQUE: {column}",
            description,
            failed,
            len(non_null)
        )

    def check_regex(
        self,
        column: str,
        pattern: str,
        description: str
    ) -> dict:
        """Check column values match a regex pattern."""
        non_null = self.df[column].dropna()
        failed   = int((~non_null.str.match(pattern, na=False)).sum())
        return self._record(
            f"REGEX: {column}",
            description,
            failed,
            len(non_null)
        )

    def check_values_in_set(
        self,
        column: str,
        valid_values: list,
        description: str
    ) -> dict:
        """Check column values are within an allowed set."""
        non_null = self.df[column].dropna()
        failed   = int((~non_null.isin(valid_values)).sum())
        return self._record(
            f"VALUES IN SET: {column}",
            description,
            failed,
            len(non_null)
        )

    def check_date_range(
        self,
        column: str,
        min_date: str,
        max_date: str,
        description: str
    ) -> dict:
        """Check date column values fall within a valid range."""
        non_null = self.df[column].dropna()
        in_range = non_null.between(
            pd.Timestamp(min_date),
            pd.Timestamp(max_date)
        )
        failed = int((~in_range).sum())
        return self._record(
            f"DATE RANGE: {column}",
            description,
            failed,
            len(non_null)
        )

    def generate_report(self) -> pd.DataFrame:
        """
        Print quality report to logger and return
        results as a DataFrame.
        """
        report = pd.DataFrame(self.results)

        logger.info("=" * 60)
        logger.info("DATA QUALITY REPORT")
        logger.info(f"Threshold: {self.threshold:.0%}")
        logger.info("=" * 60)

        for r in self.results:
            icon = "✓" if r["status"] == "PASS" else "✗"
            logger.info(
                f"  [{icon}] {r['check']}"
                f"\n        {r['description']}"
                f"\n        {r['pass_rate']:.1%} passed "
                f"({r['failed']} failed of {r['total']}) "
                f"→ {r['status']}"
            )

        # overall result
        all_passed = (report["status"] == "PASS").all()
        passed_count = (report["status"] == "PASS").sum()
        total_checks = len(report)

        logger.info("=" * 60)
        if all_passed:
            logger.info("  OVERALL RESULT: ALL CHECKS PASSED ✓")
            logger.info("  Data is ready for campaign delivery!")
        else:
            failed_checks = report[report["status"] == "FAIL"]["check"].tolist()
            logger.info(f"  OVERALL RESULT: {passed_count}/{total_checks} CHECKS PASSED")
            logger.info(f"  FAILED CHECKS: {failed_checks}")
            logger.info("  Data needs attention before campaign delivery!")
        logger.info("=" * 60)

        return report


def run_quality_checks(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run all 7 quality checks on the golden customer dataset.
    Called from pipeline.py
    """
    logger.info("=" * 60)
    logger.info("VALIDATION — Running quality checks")
    logger.info("=" * 60)
    logger.info(f"Records entering validation: {len(df)}")

    v = DataQualityValidator(
        df,
        threshold=CONFIG["quality_threshold"]
    )

    # Check 1 — email not null
    v.check_not_null(
        "email",
        "Every customer must have an email address"
    )

    # Check 2 — first name not null
    v.check_not_null(
        "first_name",
        "Every customer must have a first name"
    )

    # Check 3 — region not null
    v.check_not_null(
        "region",
        "Every customer must have a region for campaign targeting"
    )

    # Check 4 — email uniqueness
    v.check_unique(
        "email",
        "No duplicate emails after deduplication"
    )

    # Check 5 — email format
    v.check_regex(
        "email",
        CONFIG["email_regex"],
        "All emails must be in valid format"
    )

    # Check 6 — region values
    v.check_values_in_set(
        "region",
        CONFIG["valid_regions"],
        "Region must be US, EU or APAC"
    )

    # Check 7 — registration date range
    v.check_date_range(
        "registration_date",
        "2010-01-01",
        datetime.now().strftime("%Y-%m-%d"),
        "Registration dates must be between 2010 and today"
    )

    return v.generate_report()