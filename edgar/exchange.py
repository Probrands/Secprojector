import logging
from typing import Dict, Optional

import requests

import config

logger = logging.getLogger(__name__)

EXCHANGE_DATA_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


class ExchangeLookup:
    """Looks up which exchange a company trades on using SEC data."""

    def __init__(self):
        self._by_ticker: Dict[str, str] = {}
        self._by_cik: Dict[int, str] = {}
        self._loaded = False

    def load(self):
        try:
            resp = requests.get(
                EXCHANGE_DATA_URL,
                headers={"User-Agent": config.SEC_USER_AGENT},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for row in data.get("data", []):
                if len(row) >= 4 and row[3]:
                    cik, name, ticker, exchange = row[0], row[1], row[2], row[3]
                    self._by_ticker[ticker.upper()] = exchange
                    self._by_cik[int(cik)] = exchange

            self._loaded = True
            logger.info(f"Loaded exchange data for {len(self._by_ticker)} tickers")
        except Exception as e:
            logger.error(f"Failed to load exchange data: {e}")

    def get_exchange(self, ticker: str = "", cik: str = "") -> Optional[str]:
        if not self._loaded:
            self.load()

        if ticker:
            result = self._by_ticker.get(ticker.upper())
            if result:
                return result

        if cik:
            try:
                result = self._by_cik.get(int(cik))
                if result:
                    return result
            except (ValueError, TypeError):
                pass

        return None

    def is_nyse(self, ticker: str = "", cik: str = "") -> bool:
        return self.get_exchange(ticker, cik) == "NYSE"
