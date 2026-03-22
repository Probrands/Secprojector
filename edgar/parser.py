import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Transaction codes that indicate an open-market purchase
PURCHASE_CODES = {"P"}


def _get_text(element, path: str) -> str:
    """Safely extract text from an XML element path, handling <value> children."""
    value_node = element.find(f"{path}/value")
    if value_node is not None and value_node.text and value_node.text.strip():
        return value_node.text.strip()
    node = element.find(path)
    if node is not None and node.text and node.text.strip():
        return node.text.strip()
    return ""


def _parse_float(text: str) -> float:
    try:
        return float(text.replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def parse_form4_xml(xml_text: str) -> Optional[Dict]:
    """
    Parse a Form 4 XML document and extract insider purchase transactions.

    Returns a dict with filing info and purchase transactions, or None if
    there are no open-market purchases in this filing.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"XML parse error: {e}")
        return None

    # -- Issuer (the company) --
    issuer = root.find(".//issuer")
    company_name = _get_text(issuer, "issuerName") if issuer is not None else ""
    ticker = _get_text(issuer, "issuerTradingSymbol") if issuer is not None else ""
    company_cik = _get_text(issuer, "issuerCik") if issuer is not None else ""

    # -- Reporting Owner (the insider) --
    owners = []
    for owner_elem in root.findall(".//reportingOwner"):
        owner_id = owner_elem.find("reportingOwnerId")
        owner_rel = owner_elem.find("reportingOwnerRelationship")

        owner_name = _get_text(owner_id, "rptOwnerName") if owner_id is not None else ""

        is_director = _get_text(owner_rel, "isDirector") if owner_rel is not None else "0"
        is_officer = _get_text(owner_rel, "isOfficer") if owner_rel is not None else "0"
        is_ten_pct = _get_text(owner_rel, "isTenPercentOwner") if owner_rel is not None else "0"
        officer_title = _get_text(owner_rel, "officerTitle") if owner_rel is not None else ""

        roles = []
        if is_officer in ("1", "true"):
            roles.append(officer_title if officer_title else "Officer")
        if is_director in ("1", "true"):
            roles.append("Director")
        if is_ten_pct in ("1", "true"):
            roles.append("10% Owner")

        owners.append({
            "name": owner_name,
            "roles": roles,
            "officer_title": officer_title,
            "is_director": is_director in ("1", "true"),
            "is_officer": is_officer in ("1", "true"),
            "is_ten_pct_owner": is_ten_pct in ("1", "true"),
        })

    # -- Non-Derivative Transactions (stock purchases/sales) --
    purchases = []
    for txn in root.findall(".//nonDerivativeTransaction"):
        code = _get_text(txn, ".//transactionCoding/transactionCode")
        if code not in PURCHASE_CODES:
            continue

        acq_disp = _get_text(txn, ".//transactionAmounts/transactionAcquiredDisposedCode")
        if acq_disp == "D":
            continue

        security = _get_text(txn, "securityTitle")
        txn_date = _get_text(txn, "transactionDate")
        shares = _parse_float(_get_text(txn, ".//transactionAmounts/transactionShares"))
        price = _parse_float(_get_text(txn, ".//transactionAmounts/transactionPricePerShare"))
        total_value = shares * price

        purchases.append({
            "security": security,
            "date": txn_date,
            "shares": shares,
            "price_per_share": price,
            "total_value": total_value,
        })

    if not purchases:
        return None

    total_shares = sum(p["shares"] for p in purchases)
    total_value = sum(p["total_value"] for p in purchases)
    avg_price = total_value / total_shares if total_shares > 0 else 0

    return {
        "company_name": company_name,
        "ticker": ticker.upper(),
        "company_cik": company_cik,
        "owners": owners,
        "purchases": purchases,
        "total_shares": total_shares,
        "total_value": total_value,
        "avg_price": avg_price,
    }
