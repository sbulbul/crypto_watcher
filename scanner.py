import math
import time

import pandas as pd
import requests
import yfinance as yf

from config import (
    MARKET_DATA_INTERVAL,
    MARKET_DATA_PERIOD,
    MIN_BUY_SCORE,
    MIN_SELL_SCORE,
    TOP_RESULTS,
)
from market_flow import fetch_market_flow, load_spot_symbols, to_usdt_symbol
from scorer import calculate_score
from universe import get_crypto_universe

CHUNK_SIZE = 40
PROGRESS_EVERY = 10
FLOW_SCORE_FLOOR = 25
FOCUSED_UNIVERSE_LIMIT = 400
FOCUSED_MIN_VOLUME_24H = 2_000_000
FOCUSED_MIN_FALLBACK_VOLUME_24H = 750_000
FOCUSED_MAX_RANK = 1000


def is_valid_number(value):
    try:
        return value is not None and not math.isnan(float(value)) and float(value) > 0
    except Exception:
        return False


def chunked(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def number_or_none(value):
    try:
        if value is None or math.isnan(float(value)):
            return None
        return float(value)
    except Exception:
        return None


def focused_universe_score(coin, spot_symbols):
    volume = number_or_none(coin.get("volume_24h")) or 0
    rank = coin.get("rank") or 999999
    change_1h = number_or_none(coin.get("change_1h"))
    change_24h = number_or_none(coin.get("change_24h"))
    symbol = str(coin.get("symbol") or "").upper()

    if not symbol.isascii() or not symbol.replace("_", "").isalnum():
        return None
    if spot_symbols is not None and to_usdt_symbol(coin.get("ticker")) not in spot_symbols:
        return None
    if rank > FOCUSED_MAX_RANK and volume < 12_000_000:
        return None
    if volume < FOCUSED_MIN_VOLUME_24H and not (rank <= 300 and volume >= FOCUSED_MIN_FALLBACK_VOLUME_24H):
        return None
    if len(symbol) > 12:
        return None
    if change_1h is not None and abs(change_1h) > 18:
        return None
    if change_24h is not None and (change_24h < -35 or change_24h > 75):
        return None

    score = 0
    score += min(40, math.log10(max(volume, 1)) * 5)
    if rank <= 100:
        score += 22
    elif rank <= 300:
        score += 14
    elif rank <= FOCUSED_MAX_RANK:
        score += 6

    if change_1h is not None:
        abs_1h = abs(change_1h)
        if 0.25 <= abs_1h <= 4:
            score += 16
        elif abs_1h <= 8:
            score += 8
        else:
            score -= 12

    if change_24h is not None:
        abs_24h = abs(change_24h)
        if 2 <= abs_24h <= 22:
            score += 14
        elif abs_24h <= 35:
            score += 6
        else:
            score -= 10

    return score


def build_focused_universe(coins, limit):
    try:
        spot_symbols = load_spot_symbols()
    except Exception as error:
        print(f"Binance symbol filter unavailable, using liquidity filter only: {error}")
        spot_symbols = None

    ranked = []
    for coin in coins:
        score = focused_universe_score(coin, spot_symbols)
        if score is not None:
            ranked.append((score, coin))

    ranked.sort(key=lambda item: item[0], reverse=True)
    focused_limit = min(limit, FOCUSED_UNIVERSE_LIMIT)
    return [coin for _, coin in ranked[:focused_limit]]


def get_ticker_frame(downloaded, ticker):
    if downloaded is None or downloaded.empty:
        return pd.DataFrame()

    if not isinstance(downloaded.columns, pd.MultiIndex):
        return downloaded.dropna(how="all")

    if ticker in downloaded.columns.get_level_values(0):
        return downloaded[ticker].dropna(how="all")

    if ticker in downloaded.columns.get_level_values(1):
        return downloaded.xs(ticker, axis=1, level=1).dropna(how="all")

    return pd.DataFrame()


def fetch_market_data(tickers):
    try:
        return yf.download(
            tickers=tickers,
            period=MARKET_DATA_PERIOD,
            interval=MARKET_DATA_INTERVAL,
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False,
            timeout=20,
        )
    except Exception as error:
        print(f"Crypto market data chunk failed: {error}")
        return pd.DataFrame()


def fetch_coingecko_history(coin):
    try:
        response = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin['id']}/market_chart",
            params={"vs_currency": "usd", "days": 7, "interval": "hourly"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as error:
        print(f"CoinGecko history failed for {coin['ticker']}: {error}")
        return pd.DataFrame()

    prices = payload.get("prices") or []
    volumes = payload.get("total_volumes") or []
    if len(prices) < 30 or len(volumes) < 30:
        return pd.DataFrame()

    price_frame = pd.DataFrame(prices, columns=["time", "Close"])
    volume_frame = pd.DataFrame(volumes, columns=["time", "Volume"])
    frame = price_frame.merge(volume_frame, on="time", how="inner")
    if frame.empty:
        return pd.DataFrame()

    frame["Datetime"] = pd.to_datetime(frame["time"], unit="ms", utc=True)
    frame = frame.set_index("Datetime")
    frame["Volume"] = frame["Volume"] / frame["Close"]
    frame["Open"] = frame["Close"]
    frame["High"] = frame["Close"]
    frame["Low"] = frame["Close"]
    return frame[["Open", "High", "Low", "Close", "Volume"]].dropna()


def calculate_rsi(close, period=14):
    if len(close) < period + 1:
        return None

    changes = close.diff().dropna()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)
    avg_gain = gains.tail(period).mean()
    avg_loss = losses.tail(period).mean()

    if avg_loss == 0:
        return 100 if avg_gain > 0 else 50

    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def calculate_atr(hist, period=14):
    if len(hist) < period + 1 or not {"High", "Low", "Close"}.issubset(set(hist.columns)):
        return None

    frame = hist.tail(period + 1).copy()
    previous_close = frame["Close"].shift(1)
    ranges = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    )
    atr = ranges.max(axis=1).dropna().tail(period).mean()
    return float(atr) if atr and not math.isnan(float(atr)) else None


def score_from_history(coin, hist, market_flow=None):
    if hist.empty or len(hist) < 30:
        return None

    required_columns = {"Close", "Volume"}
    if not required_columns.issubset(set(hist.columns)):
        return None

    close = hist["Close"].dropna()
    volume = hist["Volume"].dropna()

    if len(close) < 30 or len(volume) < 24:
        return None

    current_price = float(close.iloc[-1])
    previous_hour_close = float(close.iloc[-2])
    close_4h_ago = float(close.iloc[-5]) if len(close) >= 5 else previous_hour_close
    close_24h_ago = float(close.iloc[-25]) if len(close) >= 25 else previous_hour_close
    current_hour_volume = float(volume.iloc[-1])
    avg_hour_volume = float(volume.tail(24).mean())
    recent_high = float(close.tail(24).max())
    recent_low = float(close.tail(24).min())
    support = float(close.tail(12).min())
    resistance = recent_high
    atr = calculate_atr(hist) or current_price * 0.015
    rsi = calculate_rsi(close)

    recent_slice = hist.tail(24).copy()
    recent_turnover = (recent_slice["Close"] * recent_slice["Volume"]).sum()
    recent_volume = recent_slice["Volume"].sum()
    recent_vwap = float(recent_turnover / recent_volume) if recent_volume else current_price

    if not all([
        is_valid_number(current_price),
        is_valid_number(previous_hour_close),
        is_valid_number(close_4h_ago),
        is_valid_number(close_24h_ago),
        is_valid_number(avg_hour_volume),
        is_valid_number(recent_high),
    ]):
        return None

    return calculate_score(
        ticker=coin["ticker"],
        name=coin["name"],
        market_rank=coin.get("rank"),
        current_price=current_price,
        previous_hour_close=previous_hour_close,
        close_4h_ago=close_4h_ago,
        close_24h_ago=close_24h_ago,
        current_hour_volume=current_hour_volume,
        avg_hour_volume=avg_hour_volume,
        recent_high=recent_high,
        recent_low=recent_low,
        recent_vwap=recent_vwap,
        support=support,
        resistance=resistance,
        atr=atr,
        rsi=rsi,
        market_flow=market_flow or {},
        volume_24h=coin.get("volume_24h") or 0,
    )


def scan_market(limit=250, progress_callback=None, should_stop=None, focused=False):
    coins = get_crypto_universe(limit=limit)
    if focused:
        coins = build_focused_universe(coins, limit)
    results = []
    processed = 0
    total = len(coins)
    started = time.time()

    print(f"Starting crypto scan: {total} coins")

    if progress_callback:
        progress_callback(
            processed=processed,
            total=total,
            ticker="",
            candidates=len(results),
            elapsed=0,
        )

    for chunk in chunked(coins, CHUNK_SIZE):
        if should_stop and should_stop():
            print("Crypto scan stopped by user.")
            break

        tickers = [coin["ticker"] for coin in chunk]
        downloaded = fetch_market_data(tickers)

        for coin in chunk:
            if should_stop and should_stop():
                print("Crypto scan stopped by user.")
                break

            processed += 1
            ticker = coin["ticker"]

            if processed == 1 or processed % PROGRESS_EVERY == 0 or processed == total:
                elapsed = time.time() - started
                print(
                    f"Scanning {processed}/{total}: {ticker} "
                    f"({len(results)} candidates, {elapsed:.0f}s)"
                )

            if progress_callback:
                progress_callback(
                    processed=processed,
                    total=total,
                    ticker=ticker,
                    candidates=len(results),
                    elapsed=time.time() - started,
                )

            hist = get_ticker_frame(downloaded, ticker)
            if hist.empty:
                hist = fetch_coingecko_history(coin)

            result = score_from_history(coin, hist)
            if not result:
                continue

            if max(result["quick_win_score"], result["long_term_score"]) >= FLOW_SCORE_FLOOR:
                flow = fetch_market_flow(ticker, result["price"])
                result = score_from_history(coin, hist, market_flow=flow)
                if not result:
                    continue

            if (
                (result["quick_win_score"] >= MIN_BUY_SCORE and result["long_term_score"] < MIN_SELL_SCORE)
                or result["long_term_score"] >= MIN_SELL_SCORE
            ):
                results.append(result)
                if progress_callback:
                    progress_callback(
                        processed=processed,
                        total=total,
                        ticker=ticker,
                        candidates=len(results),
                        elapsed=time.time() - started,
                    )

        if should_stop and should_stop():
            break

    results = sorted(
        results,
        key=lambda item: (
            max(item["quick_win_score"], item["long_term_score"]),
            item.get("target_profit_pct") or 0,
            item.get("reward_risk") or 0,
            item["relative_volume"],
        ),
        reverse=True,
    )

    elapsed = time.time() - started
    print(
        f"Crypto scan complete in {elapsed:.0f}s. "
        f"Found {len(results)} scored coins. Showing top {TOP_RESULTS}."
    )

    return results[:TOP_RESULTS]
