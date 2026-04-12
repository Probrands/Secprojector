import logging
import time
from typing import Dict, Optional, Tuple

import requests

import config

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def get_company_location(cik: str, db=None) -> Optional[Dict]:
    """
    Get lat/lng for a company. Checks the DB cache first, then
    fetches the address from SEC EDGAR and geocodes via Nominatim.
    """
    if db:
        cached = db.get_company_location(cik)
        if cached:
            return cached

    address = _fetch_sec_address(cik)
    if not address:
        return None

    coords = _geocode(address)
    if not coords:
        return None

    result = {
        "city": address.get("city", ""),
        "state": address.get("state", ""),
        "latitude": coords[0],
        "longitude": coords[1],
    }

    if db:
        db.save_company_location(cik, result)

    return result


def _fetch_sec_address(cik: str) -> Optional[Dict]:
    """Fetch business address from SEC EDGAR submissions endpoint."""
    try:
        padded_cik = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        resp = requests.get(
            url,
            headers={"User-Agent": config.SEC_USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        biz = data.get("addresses", {}).get("business", {})
        city = biz.get("city", "")
        state = biz.get("stateOrCountry", "")

        if not city and not state:
            return None

        return {
            "city": city,
            "state": state,
            "zip": biz.get("zipCode", ""),
            "street": biz.get("street1", ""),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch SEC address for CIK {cik}: {e}")
        return None


def _geocode(address: Dict) -> Optional[Tuple[float, float]]:
    """Geocode a US address using Nominatim (OpenStreetMap)."""
    try:
        parts = []
        if address.get("city"):
            parts.append(address["city"])
        if address.get("state"):
            parts.append(address["state"])
        parts.append("USA")

        resp = requests.get(
            NOMINATIM_URL,
            params={
                "q": ", ".join(parts),
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            headers={"User-Agent": config.SEC_USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()

        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
        return None
    except Exception as e:
        logger.warning(f"Geocoding failed for {address}: {e}")
        return None
    finally:
        time.sleep(1.1)
