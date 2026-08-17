import pandas as pd
import pytest

import crypto_lookup
from config import MIN_BUY_SCORE, MIN_SELL_SCORE
from crypto_lookup import compute_recommendation, lookup_ticker


def _build_hist():
    index = pd.date_range("2024-01-01", periods=40, freq="h")
    return pd.DataFrame(
        {"Close": [100.0 + i for i in range(40)], "Volume": [1_000_000] * 40},
        index=index,
    )


def _coin(ticker="BTC-USD"):
    return {"ticker": ticker, "name": "Bitcoin", "rank": 1, "volume_24h": 5_000_000_000}


def test_compute_recommendation_sell_when_long_term_score_high(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "fetch_market_data", lambda tickers: _build_hist())
    monkeypatch.setattr(crypto_lookup, "get_ticker_frame", lambda downloaded, ticker: downloaded)
    monkeypatch.setattr(crypto_lookup, "fetch_market_flow", lambda ticker, price: {})
    monkeypatch.setattr(
        crypto_lookup,
        "score_from_history",
        lambda coin, hist, market_flow: {
            "quick_win_score": 10,
            "long_term_score": MIN_SELL_SCORE,
        },
    )

    result = compute_recommendation("BTC-USD", _coin())

    assert result["signal"] == "Sell"


def test_compute_recommendation_buy_when_quick_win_score_high(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "fetch_market_data", lambda tickers: _build_hist())
    monkeypatch.setattr(crypto_lookup, "get_ticker_frame", lambda downloaded, ticker: downloaded)
    monkeypatch.setattr(crypto_lookup, "fetch_market_flow", lambda ticker, price: {})
    monkeypatch.setattr(
        crypto_lookup,
        "score_from_history",
        lambda coin, hist, market_flow: {
            "quick_win_score": MIN_BUY_SCORE,
            "long_term_score": 10,
        },
    )

    result = compute_recommendation("BTC-USD", _coin())

    assert result["signal"] == "Buy"


def test_compute_recommendation_hold_when_between_thresholds(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "fetch_market_data", lambda tickers: _build_hist())
    monkeypatch.setattr(crypto_lookup, "get_ticker_frame", lambda downloaded, ticker: downloaded)
    monkeypatch.setattr(crypto_lookup, "fetch_market_flow", lambda ticker, price: {})
    monkeypatch.setattr(
        crypto_lookup,
        "score_from_history",
        lambda coin, hist, market_flow: {
            "quick_win_score": MIN_BUY_SCORE - 1,
            "long_term_score": MIN_SELL_SCORE - 1,
        },
    )

    result = compute_recommendation("BTC-USD", _coin())

    assert result["signal"] == "Hold"


def test_compute_recommendation_none_when_scanner_rejects_coin(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "fetch_market_data", lambda tickers: _build_hist())
    monkeypatch.setattr(crypto_lookup, "get_ticker_frame", lambda downloaded, ticker: downloaded)
    monkeypatch.setattr(crypto_lookup, "fetch_market_flow", lambda ticker, price: {})
    monkeypatch.setattr(crypto_lookup, "score_from_history", lambda coin, hist, market_flow: None)

    result = compute_recommendation("BTC-USD", _coin())

    assert result is None


def test_lookup_ticker_not_found_when_outside_tracked_universe(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "get_crypto_universe", lambda: [_coin("ETH-USD")])
    monkeypatch.setattr(
        crypto_lookup, "fetch_latest_price",
        lambda ticker: pytest.fail("should not fetch a price for an untracked ticker"),
    )

    result = lookup_ticker("ZZZZZZ")

    assert result["status"] == "not_found"
    assert result["ticker"] == "ZZZZZZ-USD"
    assert "warning" in result
    assert "price" not in result


def test_lookup_ticker_not_found_when_price_unavailable(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "get_crypto_universe", lambda: [_coin()])
    monkeypatch.setattr(crypto_lookup, "fetch_latest_price", lambda ticker: None)

    result = lookup_ticker("BTC")

    assert result["status"] == "not_found"
    assert result["ticker"] == "BTC-USD"


def test_lookup_ticker_not_found_when_scanner_has_no_score(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "get_crypto_universe", lambda: [_coin()])
    monkeypatch.setattr(
        crypto_lookup, "fetch_latest_price",
        lambda ticker: {"price": 63000.0, "source": "Binance spot"},
    )
    monkeypatch.setattr(crypto_lookup, "fetch_market_data", lambda tickers: pd.DataFrame())
    monkeypatch.setattr(crypto_lookup, "get_ticker_frame", lambda downloaded, ticker: pd.DataFrame())

    result = lookup_ticker("BTC")

    assert result["status"] == "not_found"


def test_lookup_ticker_unavailable_on_unexpected_exception(monkeypatch):
    def boom():
        raise ConnectionError("network down")

    monkeypatch.setattr(crypto_lookup, "get_crypto_universe", boom)

    result = lookup_ticker("BTC")

    assert result["status"] == "unavailable"
    assert result["ticker"] == "BTC-USD"
    assert "warning" in result


def test_lookup_ticker_empty_input_is_not_found_without_any_calls(monkeypatch):
    def fail_if_called():
        raise AssertionError("should not fetch the universe for an empty ticker")

    monkeypatch.setattr(crypto_lookup, "get_crypto_universe", fail_if_called)

    result = lookup_ticker("   ")

    assert result["status"] == "not_found"
    assert result["ticker"] == ""


def test_lookup_ticker_ok_normalizes_and_saves(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "get_crypto_universe", lambda: [_coin()])
    monkeypatch.setattr(
        crypto_lookup, "fetch_latest_price",
        lambda ticker: {"price": 63000.5, "source": "Binance spot"},
    )
    monkeypatch.setattr(crypto_lookup, "fetch_market_data", lambda tickers: _build_hist())
    monkeypatch.setattr(crypto_lookup, "get_ticker_frame", lambda downloaded, ticker: downloaded)
    monkeypatch.setattr(crypto_lookup, "fetch_market_flow", lambda ticker, price: {})
    monkeypatch.setattr(
        crypto_lookup, "score_from_history",
        lambda coin, hist, market_flow: {"quick_win_score": 10, "long_term_score": 10},
    )

    saved = {}

    def fake_save(**kwargs):
        saved.update(kwargs)
        return 1

    monkeypatch.setattr(crypto_lookup, "save_ticker_lookup", fake_save)

    result = lookup_ticker("  btc ")

    assert result["status"] == "ok"
    assert result["ticker"] == "BTC-USD"
    assert result["price"] == pytest.approx(63000.5)
    assert result["price_type"] == "live"
    assert result["recommendation"] == "Hold"
    assert saved["ticker"] == "BTC-USD"


def test_lookup_ticker_delayed_price_type_on_fallback_source(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "get_crypto_universe", lambda: [_coin()])
    monkeypatch.setattr(
        crypto_lookup, "fetch_latest_price",
        lambda ticker: {"price": 63000.5, "source": "CoinGecko simple price"},
    )
    monkeypatch.setattr(crypto_lookup, "fetch_market_data", lambda tickers: _build_hist())
    monkeypatch.setattr(crypto_lookup, "get_ticker_frame", lambda downloaded, ticker: downloaded)
    monkeypatch.setattr(crypto_lookup, "fetch_market_flow", lambda ticker, price: {})
    monkeypatch.setattr(
        crypto_lookup, "score_from_history",
        lambda coin, hist, market_flow: {"quick_win_score": 10, "long_term_score": 10},
    )
    monkeypatch.setattr(crypto_lookup, "save_ticker_lookup", lambda **kwargs: 1)

    result = lookup_ticker("BTC")

    assert result["price_type"] == "delayed"


def test_lookup_ticker_ok_but_save_failure_still_returns_result(monkeypatch):
    monkeypatch.setattr(crypto_lookup, "get_crypto_universe", lambda: [_coin()])
    monkeypatch.setattr(
        crypto_lookup, "fetch_latest_price",
        lambda ticker: {"price": 63000.5, "source": "Binance spot"},
    )
    monkeypatch.setattr(crypto_lookup, "fetch_market_data", lambda tickers: _build_hist())
    monkeypatch.setattr(crypto_lookup, "get_ticker_frame", lambda downloaded, ticker: downloaded)
    monkeypatch.setattr(crypto_lookup, "fetch_market_flow", lambda ticker, price: {})
    monkeypatch.setattr(
        crypto_lookup, "score_from_history",
        lambda coin, hist, market_flow: {"quick_win_score": 10, "long_term_score": 10},
    )

    def failing_save(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(crypto_lookup, "save_ticker_lookup", failing_save)

    result = lookup_ticker("BTC")

    assert result["status"] == "ok"
    assert result["warning"] == crypto_lookup.SAVE_FAILED_WARNING
