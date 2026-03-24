import logging
from typing import Dict, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# Cache market data within a single scan to avoid duplicate API calls
_cache: Dict[str, Optional[Dict]] = {}


def clear_cache():
    _cache.clear()


def get_market_context(ticker: str) -> Optional[Dict]:
    """
    Fetch price history and market cap for a ticker via yfinance.

    Returns dict with:
      - current_price
      - week_52_high, week_52_low
      - range_position (0-100, where 0 = at 52w low, 100 = at 52w high)
      - range_label (str like "Near Low", "Mid-Range", "Near High")
      - market_cap (int)
      - market_cap_label (str like "$1.2B")
    Or None if the lookup fails.
    """
    if ticker in _cache:
        return _cache[ticker]

    try:
        info = yf.Ticker(ticker).info

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        week_52_high = info.get("fiftyTwoWeekHigh")
        week_52_low = info.get("fiftyTwoWeekLow")
        market_cap = info.get("marketCap")

        if current_price is None:
            logger.warning(f"No price data for {ticker}")
            _cache[ticker] = None
            return None

        result: Dict = {
            "current_price": current_price,
            "week_52_high": week_52_high,
            "week_52_low": week_52_low,
            "market_cap": market_cap,
            "market_cap_label": _format_market_cap(market_cap),
        }

        if week_52_high and week_52_low and week_52_high != week_52_low:
            spread = week_52_high - week_52_low
            position = ((current_price - week_52_low) / spread) * 100
            position = max(0.0, min(100.0, position))
            result["range_position"] = round(position, 1)
            result["range_label"] = _range_label(position)
        else:
            result["range_position"] = None
            result["range_label"] = "Insufficient History"

        _cache[ticker] = result
        return result

    except Exception as e:
        logger.warning(f"Market context lookup failed for {ticker}: {e}")
        _cache[ticker] = None
        return None


def _range_label(position: float) -> str:
    if position >= 85:
        return "Near 52W High"
    elif position >= 60:
        return "Upper Range"
    elif position >= 40:
        return "Mid-Range"
    elif position >= 15:
        return "Lower Range"
    else:
        return "Near 52W Low"


def _format_market_cap(cap) -> str:
    if cap is None:
        return "N/A"
    if cap >= 1_000_000_000_000:
        return f"${cap / 1_000_000_000_000:.1f}T"
    if cap >= 1_000_000_000:
        return f"${cap / 1_000_000_000:.1f}B"
    if cap >= 1_000_000:
        return f"${cap / 1_000_000:.0f}M"
    return f"${cap:,.0f}"


def purchase_vs_market_cap(total_value: float, market_cap) -> Optional[str]:
    """Returns the purchase as a percentage of market cap, or None."""
    if not market_cap or market_cap <= 0:
        return None
    pct = (total_value / market_cap) * 100
    if pct >= 0.01:
        return f"{pct:.2f}%"
    return f"{pct:.4f}%"
