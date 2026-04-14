import logging
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import pytz

import config

logger = logging.getLogger(__name__)
ET = pytz.timezone(config.TIMEZONE)


class FilingsDatabase:
    """SQLite database to track processed filings and recent purchases for cluster detection."""

    def __init__(self):
        self.db_path = config.DB_PATH
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_filings (
                    accession TEXT PRIMARY KEY,
                    ticker TEXT,
                    company_name TEXT,
                    file_date TEXT,
                    processed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS insider_purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    accession TEXT,
                    ticker TEXT,
                    company_name TEXT,
                    owner_name TEXT,
                    officer_title TEXT,
                    total_shares REAL,
                    total_value REAL,
                    purchase_date TEXT,
                    confidence_score INTEGER,
                    filed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS company_locations (
                    cik TEXT PRIMARY KEY,
                    ticker TEXT,
                    company_name TEXT,
                    city TEXT,
                    state TEXT,
                    latitude REAL,
                    longitude REAL,
                    geocoded_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_purchases_ticker
                ON insider_purchases(ticker)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_purchases_date
                ON insider_purchases(purchase_date)
            """)

            for col in ("latitude REAL", "longitude REAL", "company_summary TEXT"):
                try:
                    conn.execute(f"ALTER TABLE insider_purchases ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass

            conn.commit()

    def is_processed(self, accession: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_filings WHERE accession = ?",
                (accession,)
            ).fetchone()
            return row is not None

    def mark_processed(self, accession: str, ticker: str = "", company_name: str = "", file_date: str = ""):
        now = datetime.now(ET).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO processed_filings
                   (accession, ticker, company_name, file_date, processed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (accession, ticker, company_name, file_date, now)
            )
            conn.commit()

    def save_purchase(self, scored_filing: Dict):
        now = datetime.now(ET).isoformat()
        owners = scored_filing.get("owners", [])
        owner_name = owners[0].get("name", "") if owners else ""
        officer_title = owners[0].get("officer_title", "") if owners else ""
        purchases = scored_filing.get("purchases", [])
        purchase_date = purchases[0].get("date", "") if purchases else ""

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO insider_purchases
                   (accession, ticker, company_name, owner_name, officer_title,
                    total_shares, total_value, purchase_date, confidence_score,
                    filed_at, latitude, longitude, company_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scored_filing.get("accession", ""),
                    scored_filing.get("ticker", ""),
                    scored_filing.get("company_name", ""),
                    owner_name,
                    officer_title,
                    scored_filing.get("total_shares", 0),
                    scored_filing.get("total_value", 0),
                    purchase_date,
                    scored_filing.get("confidence_score", 0),
                    now,
                    scored_filing.get("latitude"),
                    scored_filing.get("longitude"),
                    scored_filing.get("company_summary", ""),
                )
            )
            conn.commit()

    def get_recent_purchases(self, days: int = None) -> List[Dict]:
        """Get recent insider purchases for cluster detection."""
        if days is None:
            days = config.CLUSTER_LOOKBACK_DAYS

        cutoff = (datetime.now(ET) - timedelta(days=days)).strftime("%Y-%m-%d")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT ticker, company_name, owner_name, officer_title,
                          total_shares, total_value, purchase_date, confidence_score
                   FROM insider_purchases
                   WHERE purchase_date >= ?
                   ORDER BY purchase_date DESC""",
                (cutoff,)
            ).fetchall()

        results = []
        for row in rows:
            results.append({
                "ticker": row["ticker"],
                "company_name": row["company_name"],
                "owners": [{"name": row["owner_name"], "officer_title": row["officer_title"]}],
                "total_value": row["total_value"],
                "purchase_date": row["purchase_date"],
            })

        return results

    # --- Company location cache ---

    def get_company_location(self, cik: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT city, state, latitude, longitude FROM company_locations WHERE cik = ?",
                (cik,)
            ).fetchone()

        if row and row["latitude"] is not None:
            return {
                "city": row["city"],
                "state": row["state"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
            }
        return None

    def save_company_location(self, cik: str, location: Dict, ticker: str = "", company_name: str = ""):
        now = datetime.now(ET).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO company_locations
                   (cik, ticker, company_name, city, state, latitude, longitude, geocoded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cik,
                    ticker,
                    company_name,
                    location.get("city", ""),
                    location.get("state", ""),
                    location.get("latitude"),
                    location.get("longitude"),
                    now,
                )
            )
            conn.commit()

    # --- Map API queries ---

    def get_purchases_for_map(self, days: int = 90) -> List[Dict]:
        """Get purchases with location data for the map frontend."""
        cutoff = (datetime.now(ET) - timedelta(days=days)).strftime("%Y-%m-%d")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT ticker, company_name, owner_name, officer_title,
                          total_shares, total_value, purchase_date,
                          confidence_score, latitude, longitude, filed_at,
                          company_summary
                   FROM insider_purchases
                   WHERE purchase_date >= ?
                     AND latitude IS NOT NULL
                     AND longitude IS NOT NULL
                   ORDER BY filed_at DESC""",
                (cutoff,)
            ).fetchall()

        return [dict(row) for row in rows]

    def cleanup_old_records(self, days: int = 90):
        """Remove records older than the given number of days."""
        cutoff = (datetime.now(ET) - timedelta(days=days)).strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM processed_filings WHERE file_date < ?", (cutoff,))
            conn.execute("DELETE FROM insider_purchases WHERE purchase_date < ?", (cutoff,))
            conn.commit()
        logger.info(f"Cleaned up records older than {days} days")
