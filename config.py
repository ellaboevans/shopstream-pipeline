# config.py
# ─────────────────────────────────────────────────────────────
# All pipeline settings live here.
# Change behaviour by editing this file — never hardcode
# values inside your functions.
# ─────────────────────────────────────────────────────────────


from pathlib import Path

CONFIG = {
    'input_dir': Path("data/raw"),
    'output_dir': Path("data/processed"),
    'log_dir': Path("logs"),
    
    
    "email_regex": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    'valid_regions': ["US", "EU", "APAC"],
    "quality_threshold": 0.95,
    
    "source_priority": {
        "crm":      1,
        "website":  2,
        "erp":      3,
        "marketing": 4
    },
    
    "api_configs": {
        "crm_api_url": "https://api.shopstream.example.com/v2/customers",
        "crm_api_key": "sk-xxxx",
    }
}