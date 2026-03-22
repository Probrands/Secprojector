import logging
from datetime import datetime
from typing import Dict

import requests
import pytz

import config

logger = logging.getLogger(__name__)
ET = pytz.timezone(config.TIMEZONE)

CONFIDENCE_COLORS = {
    "VERY HIGH": 3066993,   # green
    "HIGH": 3447003,        # blue
    "MEDIUM": 15844367,     # gold
    "LOW": 10038562,        # dark grey
}


class DiscordNotifier:
    def __init__(self):
        self.webhook_url = config.DISCORD_WEBHOOK_URL
        self.enabled = bool(self.webhook_url)

    def _send(self, embeds: list, ping_everyone: bool = True):
        if not self.enabled:
            logger.warning("Discord webhook not configured, skipping notification")
            return
        try:
            payload = {"embeds": embeds}
            if ping_everyone:
                payload["content"] = "@everyone"
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code not in (200, 204):
                logger.warning(f"Discord webhook returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Discord send failed: {e}")

    def send_insider_alert(self, scored_filing: Dict):
        ticker = scored_filing.get("ticker", "???")
        company = scored_filing.get("company_name", "Unknown Company")
        confidence = scored_filing.get("confidence_label", "UNKNOWN")
        score = scored_filing.get("confidence_score", 0)
        total_value = scored_filing.get("total_value", 0)
        total_shares = scored_filing.get("total_shares", 0)
        avg_price = scored_filing.get("avg_price", 0)
        reasons = scored_filing.get("score_reasons", [])
        owners = scored_filing.get("owners", [])
        purchases = scored_filing.get("purchases", [])

        owner_lines = []
        for o in owners:
            name = o.get("name", "Unknown")
            title = o.get("officer_title", "")
            if o.get("is_director") and not title:
                title = "Director"
            elif o.get("is_ten_pct_owner") and not title:
                title = "10% Owner"
            elif not title:
                title = "Insider"
            owner_lines.append(f"{name} ({title})")

        owner_str = "\n".join(owner_lines) if owner_lines else "Unknown Insider"
        reasons_str = "\n".join(f"- {r}" for r in reasons)
        txn_date = purchases[0].get("date", "N/A") if purchases else "N/A"

        color = CONFIDENCE_COLORS.get(confidence, 10038562)

        description = (
            f"**Insider:** {owner_str}\n"
            f"**Purchase Date:** {txn_date}\n"
            f"**Shares Bought:** {total_shares:,.0f}\n"
            f"**Avg Price:** ${avg_price:,.2f}\n"
            f"**Total Value:** ${total_value:,.0f}\n"
            f"\n"
            f"**Confidence:** {confidence} ({score}/10)\n"
            f"\n"
            f"**Reasons:**\n{reasons_str}"
        )

        self._send([{
            "title": f"SEC INSIDER ALERT - {ticker}",
            "description": description,
            "color": color,
            "footer": {"text": f"{company} | Filed {datetime.now(ET).strftime('%m/%d/%Y %I:%M %p ET')}"},
        }])

        logger.info(f"Sent Discord alert for {ticker} - {confidence} confidence")

    def send_startup(self):
        now = datetime.now(ET).strftime("%I:%M %p ET")
        self._send([{
            "title": "SEC Insider Alert Bot Started",
            "description": (
                f"Bot is online and monitoring EDGAR for insider purchases.\n"
                f"**Scan interval:** Every {config.SCAN_INTERVAL_MINUTES} minutes\n"
                f"**Min confidence:** {config.MIN_CONFIDENCE_SCORE}/10\n"
                f"**Time:** {now}"
            ),
            "color": 3066993,
        }])

    def send_scan_summary(self, total_filings: int, purchases_found: int, alerts_sent: int):
        now = datetime.now(ET).strftime("%I:%M %p ET")
        self._send([{
            "title": "Scan Complete",
            "description": (
                f"**Filings scanned:** {total_filings}\n"
                f"**Purchases found:** {purchases_found}\n"
                f"**Alerts sent:** {alerts_sent}\n"
                f"**Time:** {now}"
            ),
            "color": 3447003,
        }])

    def send_error(self, message: str):
        self._send([{
            "title": "Bot Error",
            "description": f"```{message[:1800]}```",
            "color": 15158332,
        }])
