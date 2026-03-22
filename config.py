import os
from dotenv import load_dotenv

load_dotenv()

# --- Discord ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# --- SEC EDGAR ---
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "InsiderAlertBot admin@example.com")
EDGAR_BASE_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data"
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "10"))
MAX_REQUESTS_PER_SECOND = 8

# --- Confidence Scoring ---
MIN_CONFIDENCE_SCORE = int(os.getenv("MIN_CONFIDENCE_SCORE", "4"))

# Insider role weights (higher = more significant)
ROLE_WEIGHTS = {
    "ceo": 10,
    "chief executive": 10,
    "president": 8,
    "cfo": 8,
    "chief financial": 8,
    "coo": 7,
    "chief operating": 7,
    "cto": 7,
    "chief technology": 7,
    "evp": 6,
    "executive vice president": 6,
    "svp": 5,
    "senior vice president": 5,
    "director": 5,
    "vp": 4,
    "vice president": 4,
    "general counsel": 5,
    "treasurer": 4,
    "secretary": 3,
    "controller": 4,
    "10% owner": 6,
}

# Purchase size thresholds (in USD)
PURCHASE_SIZE_TIERS = {
    "massive": 1_000_000,    # $1M+
    "large": 500_000,        # $500K+
    "significant": 100_000,  # $100K+
    "moderate": 25_000,      # $25K+
    "small": 0,              # Under $25K
}

# Cluster detection: how many days back to look for multiple insider buys
CLUSTER_LOOKBACK_DAYS = 14

# --- System ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DB_PATH = os.getenv("DB_PATH", "filings.db")
TIMEZONE = "US/Eastern"
