import logging
import sys
import time
import signal
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

import config
from edgar.client import EdgarClient
from edgar.parser import parse_form4_xml
from edgar.exchange import ExchangeLookup
from analyzer.scoring import score_filing
from analyzer.market_context import get_market_context, purchase_vs_market_cap, clear_cache as clear_market_cache
from notifications.discord import DiscordNotifier
from database.filings import FilingsDatabase

ET = pytz.timezone(config.TIMEZONE)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("bot")


class InsiderAlertBot:
    def __init__(self):
        logger.info("Initializing SEC Insider Alert Bot...")
        self.edgar = EdgarClient()
        self.exchange_lookup = ExchangeLookup()
        self.discord = DiscordNotifier()
        self.db = FilingsDatabase()
        self.scheduler = BackgroundScheduler(timezone=ET)
        self.running = True

    def start(self):
        self._setup_schedule()
        self.scheduler.start()
        self.discord.send_startup()

        logger.info("Running initial scan...")
        self._scan()

        logger.info(
            f"Bot is running. Scanning every {config.SCAN_INTERVAL_MINUTES} minutes. "
            f"Press Ctrl+C to stop."
        )

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        while self.running:
            time.sleep(30)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received")
        self.running = False
        self.scheduler.shutdown(wait=False)
        logger.info("Bot stopped.")

    def _setup_schedule(self):
        self.scheduler.add_job(
            self._scan,
            IntervalTrigger(minutes=config.SCAN_INTERVAL_MINUTES),
            id="edgar_scan",
            replace_existing=True,
        )

        self.scheduler.add_job(
            self._daily_cleanup,
            CronTrigger(hour=4, minute=0, day_of_week="mon-fri", timezone=ET),
            id="daily_cleanup",
            replace_existing=True,
        )

        logger.info(f"Scheduled scan every {config.SCAN_INTERVAL_MINUTES} minutes")

    def _scan(self):
        now = datetime.now(ET)
        if now.weekday() >= 5:
            logger.info("Weekend - skipping scan")
            return

        try:
            logger.info("=== EDGAR SCAN ===")
            clear_market_cache()
            today = now.strftime("%Y-%m-%d")
            filings = self.edgar.get_recent_form4_filings(date=today)

            new_filings = []
            for f in filings:
                if not self.db.is_processed(f["accession"]):
                    new_filings.append(f)

            if not new_filings:
                logger.info("No new filings to process")
                return

            logger.info(f"Processing {len(new_filings)} new filings...")

            recent_purchases = self.db.get_recent_purchases()
            purchases_found = 0
            alerts_sent = 0

            for filing in new_filings:
                accession = filing["accession"]

                xml_text = self.edgar.fetch_form4_xml(filing)
                if xml_text is None:
                    self.db.mark_processed(accession)
                    continue

                parsed = parse_form4_xml(xml_text)

                if parsed is None:
                    self.db.mark_processed(accession, file_date=today)
                    continue

                purchases_found += 1
                parsed["accession"] = accession

                scored = score_filing(parsed, recent_purchases)

                ticker = scored.get("ticker", "")
                should_alert = False

                if scored["confidence_score"] >= config.MIN_CONFIDENCE_SCORE:
                    cik = scored.get("company_cik", "")
                    exchange = self.exchange_lookup.get_exchange(ticker=ticker, cik=cik)

                    if exchange and exchange in config.ALLOWED_EXCHANGES:
                        should_alert = True
                        market = get_market_context(ticker)
                        if market:
                            scored["market_context"] = market
                            scored["company_summary"] = market.get("company_summary", "")
                            pct = purchase_vs_market_cap(
                                scored.get("total_value", 0),
                                market.get("market_cap"),
                            )
                            if pct:
                                scored["purchase_pct_of_cap"] = pct

                self.db.save_purchase(scored)
                self.db.mark_processed(
                    accession,
                    ticker=scored.get("ticker", ""),
                    company_name=scored.get("company_name", ""),
                    file_date=today,
                )

                recent_purchases.append(scored)

                if should_alert:
                    self.discord.send_insider_alert(scored)
                    alerts_sent += 1
                    logger.info(
                        f"ALERT: {ticker} ({exchange}) - {scored['confidence_label']} "
                        f"(${scored['total_value']:,.0f})"
                    )
                elif scored["confidence_score"] >= config.MIN_CONFIDENCE_SCORE:
                    logger.info(
                        f"Skipped (exchange={exchange or 'unknown'}): {ticker} - "
                        f"score {scored['confidence_score']}/10"
                    )
                else:
                    logger.info(
                        f"Below threshold: {scored['ticker']} - "
                        f"score {scored['confidence_score']}/10 "
                        f"(${scored['total_value']:,.0f})"
                    )

            logger.info(
                f"Scan complete: {len(new_filings)} processed, "
                f"{purchases_found} purchases, {alerts_sent} alerts"
            )

        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)
            self.discord.send_error(f"Scan failed: {e}")

    def _daily_cleanup(self):
        try:
            self.db.cleanup_old_records(days=90)
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


if __name__ == "__main__":
    bot = InsiderAlertBot()
    bot.start()
