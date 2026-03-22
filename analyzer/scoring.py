import logging
from typing import Dict, List

import config

logger = logging.getLogger(__name__)


def _get_role_weight(owners: List[Dict]) -> int:
    """
    Determine the highest role weight among all reporting owners.
    CEO purchases are weighted highest, random officers lowest.
    """
    best_weight = 1

    for owner in owners:
        title = owner.get("officer_title", "").lower()
        roles = owner.get("roles", [])

        if owner.get("is_ten_pct_owner"):
            best_weight = max(best_weight, config.ROLE_WEIGHTS.get("10% owner", 6))

        if owner.get("is_director") and not owner.get("is_officer"):
            best_weight = max(best_weight, config.ROLE_WEIGHTS.get("director", 5))

        for keyword, weight in config.ROLE_WEIGHTS.items():
            if keyword in title:
                best_weight = max(best_weight, weight)
                break

    return best_weight


def _get_size_score(total_value: float) -> int:
    """Score based on the dollar amount of the purchase."""
    if total_value >= config.PURCHASE_SIZE_TIERS["massive"]:
        return 10
    elif total_value >= config.PURCHASE_SIZE_TIERS["large"]:
        return 8
    elif total_value >= config.PURCHASE_SIZE_TIERS["significant"]:
        return 6
    elif total_value >= config.PURCHASE_SIZE_TIERS["moderate"]:
        return 4
    else:
        return 2


def _get_cluster_score(ticker: str, recent_purchases: List[Dict]) -> int:
    """
    Score based on how many other insiders at the same company
    have purchased recently (cluster buying).
    """
    same_company = [p for p in recent_purchases if p.get("ticker") == ticker]
    unique_owners = set()
    for p in same_company:
        for owner in p.get("owners", []):
            unique_owners.add(owner.get("name", ""))

    count = len(unique_owners)
    if count >= 4:
        return 10
    elif count >= 3:
        return 8
    elif count >= 2:
        return 5
    else:
        return 0


def score_filing(parsed_filing: Dict, recent_purchases: List[Dict]) -> Dict:
    """
    Score an insider purchase filing on a scale of 1-10.

    Returns the filing dict enriched with:
      - confidence_score (int 1-10)
      - confidence_label (str)
      - score_reasons (list of strings explaining the score)
    """
    owners = parsed_filing.get("owners", [])
    total_value = parsed_filing.get("total_value", 0)
    ticker = parsed_filing.get("ticker", "")

    role_weight = _get_role_weight(owners)
    size_score = _get_size_score(total_value)
    cluster_score = _get_cluster_score(ticker, recent_purchases)

    raw_score = (role_weight * 0.40) + (size_score * 0.40) + (cluster_score * 0.20)
    confidence_score = max(1, min(10, round(raw_score)))

    # Build human-readable reasons
    reasons = []

    owner_names = [o["name"] for o in owners]
    owner_titles = []
    for o in owners:
        if o.get("officer_title"):
            owner_titles.append(o["officer_title"])
        elif o.get("is_director"):
            owner_titles.append("Director")
        elif o.get("is_ten_pct_owner"):
            owner_titles.append("10% Owner")

    title_str = ", ".join(owner_titles) if owner_titles else "Insider"
    reasons.append(f"{title_str} purchase (role weight: {role_weight}/10)")

    if total_value >= config.PURCHASE_SIZE_TIERS["massive"]:
        reasons.append(f"Massive purchase: ${total_value:,.0f}")
    elif total_value >= config.PURCHASE_SIZE_TIERS["large"]:
        reasons.append(f"Large purchase: ${total_value:,.0f}")
    elif total_value >= config.PURCHASE_SIZE_TIERS["significant"]:
        reasons.append(f"Significant purchase: ${total_value:,.0f}")
    elif total_value >= config.PURCHASE_SIZE_TIERS["moderate"]:
        reasons.append(f"Moderate purchase: ${total_value:,.0f}")
    else:
        reasons.append(f"Small purchase: ${total_value:,.0f}")

    if cluster_score > 0:
        same_company = [p for p in recent_purchases if p.get("ticker") == ticker]
        unique_count = len(set(
            o.get("name", "") for p in same_company for o in p.get("owners", [])
        ))
        reasons.append(f"Cluster signal: {unique_count} insiders bought recently")

    if confidence_score >= 8:
        label = "VERY HIGH"
    elif confidence_score >= 6:
        label = "HIGH"
    elif confidence_score >= 4:
        label = "MEDIUM"
    else:
        label = "LOW"

    return {
        **parsed_filing,
        "confidence_score": confidence_score,
        "confidence_label": label,
        "score_reasons": reasons,
        "role_weight": role_weight,
        "size_score": size_score,
        "cluster_score": cluster_score,
    }
