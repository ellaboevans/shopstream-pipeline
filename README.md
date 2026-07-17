# ShopStream Customer Data Quality Pipeline

An end-to-end data engineering lab that consolidates customer records from three heterogeneous source systems into a clean, deduplicated, validated **golden customer dataset**.

The pipeline ingests a legacy CSV, nested JSON, and fixed-width text file; standardizes inconsistent customer attributes; resolves duplicates using source-system priority; applies data quality checks; and produces analytics-, governance-, and campaign-ready outputs.

## Business Problem

ShopStream stores customer information across multiple systems, each with a different format and level of reliability:

| Source  | Format           | Example data quality issues                                                     |
| ------- | ---------------- | ------------------------------------------------------------------------------- |
| Website | ISO-8859-1 CSV   | Test accounts, inconsistent column names, malformed emails, mixed region labels |
| CRM     | Nested JSON      | Nested profile fields, inconsistent phone and region formats                    |
| ERP     | Fixed-width text | No headers, combined names, padded fields, legacy status codes                  |

Many customers appear in more than one source. The goal is to create one trustworthy record per customer while preserving consent and source lineage.

## Pipeline Flow

```text
Website CSV ─┐
CRM JSON ────┼─> Ingest ─> Clean ─> Deduplicate ─> Validate ─> Export
ERP Text ────┘                                      │
                                                   ├─ Golden dataset
                                                   ├─ Campaign audience
                                                   ├─ Quality report
                                                   └─ EDA visualization
```

### 1. Ingestion

- Reads each source using the appropriate parser and encoding.
- Flattens nested CRM profile fields.
- Parses the ERP fixed-width layout and splits full names.
- Removes website test accounts.
- Aligns all sources to a common schema:

```text
email, first_name, last_name, phone, region,
registration_date, opt_out, source
```

### 2. Cleaning and standardization

- Trims and lowercases email addresses, removes internal spaces, and flags invalid formats.
- Normalizes name casing and whitespace.
- Converts phone numbers to consistent digit-based formats while preserving an international `+` prefix.
- Maps region variants such as `USA`, `North America`, `EMEA`, and `Asia Pacific` to `US`, `EU`, or `APAC`.
- Drops records without an email address and fills missing names with `Unknown`.
- Retains raw email and region values for auditability.

### 3. Deduplication

The pipeline uses a two-pass strategy:

1. Valid customer emails are matched exactly.
2. Records with invalid emails are matched by normalized phone number where possible.

When duplicate records are merged, the most trusted non-null values are selected using this priority:

```text
CRM > Website > ERP > Marketing
```

Consent is handled conservatively: if **any** contributing source marks a customer as opted out, the golden record remains opted out. The `sources` and `source_count` fields preserve record provenance.

### 4. Data quality validation

Each rule passes when at least 95% of the evaluated records meet its condition. The pipeline checks:

1. Email is not null.
2. First name is not null.
3. Region is not null.
4. Email is unique.
5. Email matches the configured format.
6. Region belongs to the allowed set (`US`, `EU`, `APAC`).
7. Registration date falls between `2010-01-01` and the current date.

Validation results are recorded in the quality report and logs before the export stage.

## Project Structure

```text
shopstream_pipeline/
├── data/
│   ├── raw/                    # Website, CRM, and ERP source files
│   └── processed/              # Generated pipeline outputs
├── logs/
│   └── pipeline.log            # Execution and quality logs
├── clean.py                    # Field cleaning and standardization
├── config.py                   # Paths, validation rules, and source priority
├── data_inspect.py             # Standalone raw-data profiling script
├── deduplicate.py              # Record matching and golden-record merging
├── export.py                   # CSV, Parquet, report, and chart exports
├── ingest.py                   # Source-specific ingestion and schema alignment
├── pipeline.py                 # End-to-end pipeline entry point
├── utils.py                    # Shared utility functions
├── validate.py                 # Reusable data quality validator
└── requirements.txt            # Pinned Python dependencies
```

## Getting Started

### Prerequisites

- Python 3.10 or later
- `pip`

### Installation

Clone the repository, move into the project directory, and create an isolated environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

### Inspect the raw sources

To profile the three input files before processing them:

```bash
python data_inspect.py
```

### Run the pipeline

From the project root, run:

```bash
python pipeline.py
```

Progress is written to both the terminal and `logs/pipeline.log`.

## Generated Outputs

| File                                         | Purpose                                                                                                                        |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `data/processed/golden_customers.parquet`    | Typed, compressed golden dataset for analytics and downstream pipelines                                                        |
| `data/processed/golden_customers.csv`        | Excel-compatible golden dataset encoded with UTF-8 BOM                                                                         |
| `data/processed/campaign_customers.csv`      | Customers with a valid email, an assigned region, and no opt-out flag                                                          |
| `data/processed/quality_report.csv`          | Pass/fail evidence for every data quality rule                                                                                 |
| `data/processed/customer_quality_report.png` | Six-chart overview of region distribution, registrations, source contribution, completeness, email validity, and opt-out rates |

## Current Lab Results

The included sample run produced:

| Metric                      | Result |
| --------------------------- | -----: |
| Raw records ingested        |  1,750 |
| Golden customer records     |    726 |
| Records removed during cleaning and deduplication |  1,024 |
| Multi-source golden records |    374 |
| Campaign-ready customers    |    407 |
| Quality checks passed       |  7 / 7 |

Campaign-ready customers in that run were distributed across EU (166), US (154), and APAC (87).

## Configuration

Pipeline behavior is centralized in `config.py`. It controls:

- Raw, processed, and log directories.
- The email validation regular expression.
- Accepted region values.
- The quality threshold.
- Source-system trust priority.
- Placeholder CRM API settings for future integration.

Paths are relative to the project root, so run commands from this directory.

## Regenerating the Synthetic Source Data

The repository already includes the raw lab files. To replace them with a reproducible synthetic dataset generated with NumPy seed `42`, run:

```bash
python -c "from pipeline import generate_synthetic_data; generate_synthetic_data()"
```

This overwrites the three files in `data/raw/`; run the pipeline again afterward to refresh the processed outputs.

## Key Design Decisions

- **Modular stages:** ingestion, cleaning, deduplication, validation, and export can be understood and tested independently.
- **Configuration over hardcoding:** reusable business rules live in one configuration module.
- **Privacy-aware merging:** an opt-out from any source always wins.
- **Data lineage:** each golden record identifies all contributing systems.
- **Dual delivery formats:** Parquet supports efficient analytics while CSV supports operational users and campaign tools.
- **Observable execution:** record counts, transformations, validation outcomes, and output paths are captured in a persistent log.
