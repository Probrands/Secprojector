import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests
import pytz

import config

logger = logging.getLogger(__name__)
ET = pytz.timezone(config.TIMEZONE)


class EdgarClient:
    """Fetches Form 4 insider transaction filings from SEC EDGAR."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.SEC_USER_AGENT,
            "Accept": "application/json",
        })
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce SEC rate limit of ~8 requests per second."""
        elapsed = time.time() - self._last_request_time
        min_interval = 1.0 / config.MAX_REQUESTS_PER_SECOND
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def get_recent_form4_filings(self, date: Optional[str] = None) -> List[Dict]:
        """
        Fetch Form 4 filings for a given date from the EDGAR full-text search API.
        Returns a list of filing metadata dicts.
        """
        if date is None:
            date = datetime.now(ET).strftime("%Y-%m-%d")

        all_hits = []
        offset = 0
        page_size = 100

        while True:
            self._rate_limit()
            params = {
                "q": '""',
                "forms": "4",
                "dateRange": "custom",
                "startdt": date,
                "enddt": date,
                "from": offset,
                "size": page_size,
            }

            try:
                resp = self.session.get(
                    config.EDGAR_BASE_URL, params=params, timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"EDGAR search failed: {e}")
                break

            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                source = hit.get("_source", {})
                file_type = source.get("file_type", "")
                if file_type not in ("4", "4/A"):
                    continue

                filing_id = hit.get("_id", "")
                if ":" not in filing_id:
                    continue

                accession, xml_filename = filing_id.split(":", 1)
                if not xml_filename.endswith(".xml"):
                    continue

                all_hits.append({
                    "accession": accession,
                    "xml_filename": xml_filename,
                    "display_names": source.get("display_names", []),
                    "ciks": source.get("ciks", []),
                    "file_date": source.get("file_date", ""),
                    "period_ending": source.get("period_ending", ""),
                    "form": source.get("form", "4"),
                })

            total = data.get("hits", {}).get("total", {}).get("value", 0)
            offset += page_size
            if offset >= total:
                break

        logger.info(f"Found {len(all_hits)} Form 4 XML filings for {date}")
        return all_hits

    def fetch_form4_xml(self, filing: Dict) -> Optional[str]:
        """
        Fetch the actual Form 4 XML document for a given filing.
        Tries multiple CIKs since agent-filed forms use different CIK paths.
        Returns the raw XML string or None on failure.
        """
        accession = filing["accession"]
        xml_filename = filing["xml_filename"]
        accession_no_dashes = accession.replace("-", "")

        filer_cik = str(int(accession.split("-")[0]))
        candidate_ciks = [filer_cik]
        for c in filing.get("ciks", []):
            stripped = str(int(c))
            if stripped not in candidate_ciks:
                candidate_ciks.append(stripped)

        for cik in candidate_ciks:
            url = f"{config.EDGAR_ARCHIVE_URL}/{cik}/{accession_no_dashes}/{xml_filename}"
            self._rate_limit()
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    return resp.text
            except Exception as e:
                logger.debug(f"Request failed for {url}: {e}")
                continue

        logger.warning(f"Failed to fetch Form 4 XML for accession {accession} (tried {len(candidate_ciks)} CIKs)")
        return None
