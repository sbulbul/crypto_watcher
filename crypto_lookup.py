import time

from config import MIN_BUY_SCORE, MIN_SELL_SCORE
from market_flow import fetch_market_flow
from scanner import fetch_market_data, get_ticker_frame, score_from_history
from storage import fetch_latest_price, save_ticker_lookup
from universe import get_crypto_universe

NOT_FOUND_WARNING = 'We couldn\'t find a ticker called "{ticker}". Check the symbol and try again.'
UNAVAILABLE_WARNING = "We couldn't reach the market data source. Please try again in a moment."
EMPTY_TICKER_WARNING = "Enter a ticker symbol to look up."
SAVE_FAILED_WARNING = "This result may not have been saved to your lookup history."


def normalize_ticker(raw_ticker):
    """Uppercase, trim, and append the app's canonical "-USD" suffix if
    missing, matching the ticker format universe.py/scanner.py already use
    everywhere else (FR-002; data-model.md)."""
    ticker = str(raw_ticker or "").strip().upper()
    if not ticker:
        return ""

    if not ticker.endswith("-USD"):
        ticker = f"{ticker}-USD"

    return ticker


def _find_universe_coin(ticker):
    """A recommendation can only be produced for a ticker the scanner itself
    would ever score — this app's tracked universe (research.md). A ticker
    outside it is treated as not-found rather than faked with a placeholder
    coin, since calculate_score() needs a real name/rank/24h-volume."""
    for coin in get_crypto_universe():
        if coin.get("ticker") == ticker:
            return coin

    return None


def fetch_crypto_price(ticker):
    """Return {"price": float, "price_type": "live"|"delayed"} using the
    app's existing multi-source price fetch, or None if every source failed
    (FR-003, FR-011; research.md's price-retrieval decision)."""
    quote = fetch_latest_price(ticker)
    if not quote or not quote.get("price") or quote["price"] <= 0:
        return None

    price_type = "live" if quote.get("source") == "Binance spot" else "delayed"
    return {"price": float(quote["price"]), "price_type": price_type}


def compute_recommendation(ticker, coin):
    """Derive Buy/Sell/Hold from the app's real scanner scoring
    (scanner.score_from_history(), fed by market_flow's Binance data), using
    the same MIN_BUY_SCORE/MIN_SELL_SCORE thresholds the scanner uses to pick
    candidates (FR-004, FR-005; research.md's recommendation decision).
    Returns None if the scanner itself couldn't produce a score (e.g. too
    little history, or 24h volume below the scanner's own floor)."""
    downloaded = fetch_market_data([ticker])
    hist = get_ticker_frame(downloaded, ticker)
    if hist.empty:
        return None

    close = hist["Close"].dropna() if "Close" in hist.columns else hist.iloc[0:0]
    if close.empty:
        return None

    current_price = float(close.iloc[-1])
    market_flow = fetch_market_flow(ticker, current_price)

    score_result = score_from_history(coin, hist, market_flow)
    if not score_result:
        return None

    if score_result["long_term_score"] >= MIN_SELL_SCORE:
        signal = "Sell"
    elif score_result["quick_win_score"] >= MIN_BUY_SCORE:
        signal = "Buy"
    else:
        signal = "Hold"

    return {"signal": signal}


def lookup_ticker(ticker):
    """Perform one on-demand lookup and return a JSON-ready dict matching
    contracts/crypto-lookup-endpoint.md's response shapes."""
    normalized = normalize_ticker(ticker)

    if not normalized:
        return {
            "status": "not_found",
            "ticker": normalized,
            "warning": EMPTY_TICKER_WARNING,
        }

    try:
        coin = _find_universe_coin(normalized)
        price_info = fetch_crypto_price(normalized) if coin else None
        recommendation_info = compute_recommendation(normalized, coin) if price_info else None
    except Exception:
        return {
            "status": "unavailable",
            "ticker": normalized,
            "warning": UNAVAILABLE_WARNING,
        }

    if not coin or not price_info or not recommendation_info:
        return {
            "status": "not_found",
            "ticker": normalized,
            "warning": NOT_FOUND_WARNING.format(ticker=normalized),
        }

    looked_up_at = time.time()
    result = {
        "status": "ok",
        "ticker": normalized,
        "price": price_info["price"],
        "price_type": price_info["price_type"],
        "recommendation": recommendation_info["signal"],
        "looked_up_at": looked_up_at,
    }

    try:
        save_ticker_lookup(
            ticker=normalized,
            price=result["price"],
            price_type=result["price_type"],
            recommendation=result["recommendation"],
            looked_up_at=looked_up_at,
        )
    except Exception:
        result["warning"] = SAVE_FAILED_WARNING

    return result
