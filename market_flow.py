import time

import requests

BINANCE_SPOT_BASE = "https://api.binance.com"
BINANCE_FUTURES_BASE = "https://fapi.binance.com"
REQUEST_TIMEOUT = 6

_symbol_cache = {}
_futures_symbol_cache = {}


def to_usdt_symbol(ticker):
    base = str(ticker).upper().replace("-USD", "").replace("USD", "")
    if not base or not base.replace("_", "").isalnum():
        return None
    return f"{base}USDT"


def get_json(url, params=None):
    response = requests.get(url, params=params or {}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def load_spot_symbols():
    now = time.time()
    cached = _symbol_cache.get("symbols")
    if cached and now - _symbol_cache.get("created_at", 0) < 3600:
        return cached

    payload = get_json(f"{BINANCE_SPOT_BASE}/api/v3/exchangeInfo")
    symbols = {
        item["symbol"]
        for item in payload.get("symbols", [])
        if item.get("status") == "TRADING"
    }
    _symbol_cache.update({"symbols": symbols, "created_at": now})
    return symbols


def load_futures_symbols():
    now = time.time()
    cached = _futures_symbol_cache.get("symbols")
    if cached and now - _futures_symbol_cache.get("created_at", 0) < 3600:
        return cached

    payload = get_json(f"{BINANCE_FUTURES_BASE}/fapi/v1/exchangeInfo")
    symbols = {
        item["symbol"]
        for item in payload.get("symbols", [])
        if item.get("status") == "TRADING"
    }
    _futures_symbol_cache.update({"symbols": symbols, "created_at": now})
    return symbols


def fetch_order_book(symbol, current_price):
    payload = get_json(
        f"{BINANCE_SPOT_BASE}/api/v3/depth",
        params={"symbol": symbol, "limit": 100},
    )
    bids = payload.get("bids") or []
    asks = payload.get("asks") or []
    if not bids or not asks or current_price <= 0:
        return {}

    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    book_mid = (best_bid + best_ask) / 2
    lower = book_mid * 0.99
    upper = book_mid * 1.01
    bid_depth = sum(float(price) * float(qty) for price, qty in bids if float(price) >= lower)
    ask_depth = sum(float(price) * float(qty) for price, qty in asks if float(price) <= upper)
    spread_pct = ((best_ask - best_bid) / book_mid) * 100 if book_mid else None
    imbalance = bid_depth / ask_depth if ask_depth else None

    return {
        "bid_depth_usd": bid_depth,
        "ask_depth_usd": ask_depth,
        "book_imbalance": imbalance,
        "spread_pct": spread_pct,
    }


def fetch_trade_flow(symbol):
    trades = get_json(
        f"{BINANCE_SPOT_BASE}/api/v3/aggTrades",
        params={"symbol": symbol, "limit": 500},
    )
    if not trades:
        return {}

    buy_notional = 0
    sell_notional = 0
    for trade in trades:
        notional = float(trade["p"]) * float(trade["q"])
        if trade.get("m"):
            sell_notional += notional
        else:
            buy_notional += notional

    total = buy_notional + sell_notional
    buy_ratio = buy_notional / total if total else None
    return {
        "taker_buy_ratio": buy_ratio,
        "taker_buy_usd": buy_notional,
        "taker_sell_usd": sell_notional,
    }


def fetch_klines(symbol, interval="5m", limit=48):
    candles = get_json(
        f"{BINANCE_SPOT_BASE}/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
    )
    parsed = []
    for candle in candles:
        parsed.append({
            "open_time": candle[0],
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": float(candle[5]),
        })
    return parsed


def ema(values, period):
    if not values:
        return None
    multiplier = 2 / (period + 1)
    current = values[0]
    for value in values[1:]:
        current = (value * multiplier) + (current * (1 - multiplier))
    return current


def pct_change(current, previous):
    if not previous:
        return 0
    return ((current - previous) / previous) * 100


def analyze_klines(candles):
    if not candles or len(candles) < 24:
        return {"confirmed": False, "reason": "not enough 5m candles"}

    closes = [candle["close"] for candle in candles]
    volumes = [candle["volume"] for candle in candles]
    current = closes[-1]
    ema9 = ema(closes[-24:], 9)
    ema21 = ema(closes[-24:], 21)
    ret_15m = pct_change(closes[-1], closes[-4])
    ret_30m = pct_change(closes[-1], closes[-7])
    recent_high = max(closes[-13:-1])
    recent_low = min(closes[-13:-1])
    recent_volume = sum(volumes[-3:]) / 3
    base_volume = sum(volumes[-24:-3]) / max(len(volumes[-24:-3]), 1)
    volume_ratio = recent_volume / base_volume if base_volume else 0
    range_1h_pct = pct_change(max(closes[-12:]), min(closes[-12:]))
    near_breakout = current >= recent_high * 0.998
    reclaiming = current > ema9 and ema9 >= ema21
    not_chasing = ret_15m <= 4.5 and range_1h_pct <= 9
    not_breaking_down = current > recent_low * 1.01 and ret_30m > -1.2
    volume_active = volume_ratio >= 0.90

    confirmed = reclaiming and not_chasing and not_breaking_down and volume_active and (
        near_breakout or ret_15m >= 0.15 or ret_30m >= 0.35
    )

    reasons = []
    if reclaiming:
        reasons.append("5m trend above EMA")
    if near_breakout:
        reasons.append("near 5m breakout")
    if ret_15m >= 0.15:
        reasons.append(f"15m lift {ret_15m:.2f}%")
    if volume_active:
        reasons.append(f"5m volume {volume_ratio:.2f}x")

    if not confirmed:
        if not reclaiming:
            reasons.append("5m trend not reclaimed")
        if not not_chasing:
            reasons.append("5m move too extended")
        if not not_breaking_down:
            reasons.append("5m structure breaking down")
        if not volume_active:
            reasons.append(f"5m volume quiet {volume_ratio:.2f}x")

    return {
        "confirmed": confirmed,
        "reason": "; ".join(reasons) if reasons else "5m confirmation unavailable",
        "price": current,
        "ema9": ema9,
        "ema21": ema21,
        "return_15m_pct": ret_15m,
        "return_30m_pct": ret_30m,
        "volume_ratio": volume_ratio,
        "range_1h_pct": range_1h_pct,
    }


def analyze_one_minute_behavior(candles):
    if not candles or len(candles) < 30:
        return {
            "approved": False,
            "score": 0,
            "reason": "not enough 1m candles",
        }

    recent = candles[-60:] if len(candles) >= 60 else candles
    last_30 = recent[-30:]
    last_15 = recent[-15:]
    closes = [candle["close"] for candle in recent]
    highs = [candle["high"] for candle in recent]
    lows = [candle["low"] for candle in recent]
    volumes = [candle["volume"] for candle in recent]
    current = closes[-1]

    high_60 = max(highs)
    low_60 = min(lows)
    high_30 = max(candle["high"] for candle in last_30)
    low_30 = min(candle["low"] for candle in last_30)
    high_15 = max(candle["high"] for candle in last_15)
    low_15 = min(candle["low"] for candle in last_15)
    prev_high_30 = max(candle["high"] for candle in last_30[:-1])
    ema7 = ema(closes[-30:], 7)
    prior_ema7 = ema(closes[-31:-1], 7) if len(closes) >= 31 else ema(closes[:-1], 7)
    ema20 = ema(closes[-45:], 20) if len(closes) >= 45 else ema(closes, 20)

    ret_5m = pct_change(closes[-1], closes[-6]) if len(closes) >= 6 else 0
    ret_1m = pct_change(closes[-1], closes[-2]) if len(closes) >= 2 else 0
    ret_2m = pct_change(closes[-1], closes[-3]) if len(closes) >= 3 else 0
    ret_15m = pct_change(closes[-1], closes[-16]) if len(closes) >= 16 else 0
    ret_30m = pct_change(closes[-1], closes[-31]) if len(closes) >= 31 else 0
    range_30_pct = pct_change(high_30, low_30)
    range_60_pct = pct_change(high_60, low_60)
    pullback_from_high_15_pct = pct_change(high_15, current)
    pullback_from_high_30_pct = pct_change(high_30, current)
    lift_from_low_30_pct = pct_change(current, low_30)
    close_position_30 = (current - low_30) / (high_30 - low_30) if high_30 > low_30 else 0.5
    green_count_15 = sum(1 for candle in last_15 if candle["close"] >= candle["open"])
    red_count_5 = sum(1 for candle in recent[-5:] if candle["close"] < candle["open"])
    recent_volume = sum(volumes[-5:]) / min(len(volumes), 5)
    base_volume_slice = volumes[-35:-5] if len(volumes) >= 35 else volumes[:-5]
    base_volume = sum(base_volume_slice) / max(len(base_volume_slice), 1)
    volume_ratio = recent_volume / base_volume if base_volume else 0
    breakout_now = current >= prev_high_30 * 0.998
    trend_up = bool(ema7 and ema20 and current > ema7 and ema7 >= ema20)
    last_candle_green = recent[-1]["close"] > recent[-1]["open"]
    previous_candle_green = recent[-2]["close"] > recent[-2]["open"] if len(recent) >= 2 else False
    turn_confirmed = bool(
        ema7
        and last_candle_green
        and ret_1m >= 0.02
        and ret_2m >= -0.12
        and current >= ema7 * 0.998
    )
    pullback_reclaim = bool(
        ema7
        and prior_ema7
        and last_candle_green
        and current >= ema7
        and closes[-2] <= prior_ema7 * 1.001
        and -0.55 <= ret_5m <= 0.85
        and 0.20 <= close_position_30 <= 0.78
        and volume_ratio >= 0.65
    )
    entry_trigger = turn_confirmed or pullback_reclaim
    early_reclaim = (
        turn_confirmed
        and 0.35 <= close_position_30 <= 0.78
        and ret_5m <= 0.85
        and pullback_from_high_15_pct <= 1.2
    )
    controlled_pullback = (
        -0.45 <= ret_5m < 0
        and ret_15m >= 0.65
        and ret_30m >= 0.60
        and volume_ratio >= 1.20
        and close_position_30 >= 0.55
        and entry_trigger
    )

    score = 0
    reasons = []
    if trend_up:
        score += 24
        reasons.append("1m trend stacked")
    else:
        score -= 18
        reasons.append("1m trend not stacked")

    if 0.15 <= ret_5m <= 2.2:
        score += 18
        reasons.append(f"5m lift {ret_5m:.2f}%")
    elif controlled_pullback:
        score += 8
        reasons.append(f"controlled 5m pullback {ret_5m:.2f}%")
    elif ret_5m < -0.25:
        score -= 20
        reasons.append(f"5m fade {ret_5m:.2f}%")
    elif ret_5m > 3.0:
        score -= 10
        reasons.append("5m spike chase risk")

    if 0.25 <= ret_15m <= 4.5:
        score += 18
        reasons.append(f"15m lift {ret_15m:.2f}%")
    elif ret_15m < -0.45:
        score -= 22
        reasons.append(f"15m breakdown {ret_15m:.2f}%")
    elif ret_15m > 6:
        score -= 12
        reasons.append("15m overextended")

    if -0.60 <= ret_30m <= 7.5:
        score += 8
        reasons.append(f"30m controlled {ret_30m:.2f}%")
    elif ret_30m < -1.2:
        score -= 20
        reasons.append(f"30m weak {ret_30m:.2f}%")
    elif ret_30m > 10:
        score -= 14
        reasons.append("30m too vertical")

    if volume_ratio >= 1.35:
        score += 14
        reasons.append(f"1m volume rising {volume_ratio:.2f}x")
    elif volume_ratio >= 0.80:
        score += 5
        reasons.append(f"1m volume steady {volume_ratio:.2f}x")
    else:
        score -= 12
        reasons.append(f"1m volume fading {volume_ratio:.2f}x")

    if turn_confirmed:
        score += 14
        reasons.append(f"1m turn confirmed {ret_1m:.2f}%")
    elif pullback_reclaim:
        score += 16
        reasons.append("1m pullback reclaimed EMA")
    else:
        score -= 18
        reasons.append("no fresh 1m entry trigger")

    if early_reclaim:
        score += 16
        reasons.append("early reclaim zone")

    if breakout_now and volume_ratio >= 1.35 and ret_1m >= 0.04:
        score += 6
        reasons.append("active breakout push")
    elif breakout_now:
        score -= 8
        reasons.append("near 30m high without fresh push")

    if close_position_30 >= 0.82:
        score -= 12
        reasons.append("upper-range chase risk")
    elif close_position_30 >= 0.62:
        score += 2
        reasons.append("holding upper 30m range")
    elif close_position_30 <= 0.35:
        if turn_confirmed:
            score += 8
            reasons.append("lower-range rebound attempt")
        else:
            score -= 14
            reasons.append("near lower 30m range")

    if pullback_from_high_15_pct > 2.2 and red_count_5 >= 3:
        score -= 22
        reasons.append("spike rejection in last 15m")
    elif pullback_from_high_15_pct > 1.2:
        score -= 8
        reasons.append("pulling back from 15m high")

    if green_count_15 >= 9 and ret_15m > 0:
        score += 6
        reasons.append("15m candles mostly green")

    hard_reject = (
        (ret_5m < -0.35 and not controlled_pullback)
        or ret_15m < -0.65
        or volume_ratio < 0.55
        or pullback_from_high_15_pct > 1.35
        or pullback_from_high_30_pct > 3.5
        or not entry_trigger
        or (range_30_pct > 9 and close_position_30 < 0.45)
    )
    approved = (score >= 58 or controlled_pullback) and not hard_reject

    return {
        "approved": approved,
        "score": score,
        "reason": "; ".join(reasons),
        "return_5m_pct": ret_5m,
        "return_1m_pct": ret_1m,
        "return_2m_pct": ret_2m,
        "return_15m_pct": ret_15m,
        "return_30m_pct": ret_30m,
        "range_30m_pct": range_30_pct,
        "range_60m_pct": range_60_pct,
        "pullback_from_high_15m_pct": pullback_from_high_15_pct,
        "pullback_from_high_30m_pct": pullback_from_high_30_pct,
        "lift_from_low_30m_pct": lift_from_low_30_pct,
        "close_position_30m": close_position_30,
        "volume_ratio_5m": volume_ratio,
        "green_count_15m": green_count_15,
        "red_count_5m": red_count_5,
        "controlled_pullback": controlled_pullback,
        "turn_confirmed": turn_confirmed,
        "pullback_reclaim": pullback_reclaim,
        "entry_trigger": entry_trigger,
        "trend_up": trend_up,
        "early_reclaim": early_reclaim,
        "last_candle_green": last_candle_green,
        "previous_candle_green": previous_candle_green,
        "current": current,
        "high_30m": high_30,
        "low_30m": low_30,
    }


def fetch_one_minute_behavior(ticker):
    symbol = to_usdt_symbol(ticker)
    if not symbol:
        return {"approved": False, "score": 0, "reason": "no Binance symbol"}
    try:
        spot_symbols = load_spot_symbols()
        if symbol not in spot_symbols:
            return {"approved": False, "score": 0, "reason": "no Binance spot pair"}
        return analyze_one_minute_behavior(fetch_klines(symbol, interval="1m", limit=60))
    except Exception as error:
        return {"approved": False, "score": 0, "reason": f"1m behavior failed: {error}"}


def fetch_short_term_confirmation(ticker):
    symbol = to_usdt_symbol(ticker)
    if not symbol:
        return {"confirmed": False, "reason": "no Binance symbol"}
    try:
        spot_symbols = load_spot_symbols()
        if symbol not in spot_symbols:
            return {"confirmed": False, "reason": "no Binance spot pair"}
        return analyze_klines(fetch_klines(symbol, interval="5m", limit=48))
    except Exception as error:
        return {"confirmed": False, "reason": f"5m confirmation failed: {error}"}


def fetch_market_regime():
    checks = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        try:
            analysis = analyze_klines(fetch_klines(symbol, interval="5m", limit=48))
            checks.append((symbol, analysis))
        except Exception as error:
            checks.append((symbol, {"confirmed": False, "reason": str(error)}))

    if not checks:
        return {"tradable": False, "reason": "market regime unavailable"}

    weak = []
    for symbol, analysis in checks:
        if analysis.get("return_30m_pct", 0) <= -0.75:
            weak.append(f"{symbol} 30m {analysis.get('return_30m_pct', 0):.2f}%")
        if analysis.get("ema9") and analysis.get("ema21") and analysis["ema9"] < analysis["ema21"] * 0.998:
            weak.append(f"{symbol} below 5m trend")

    if len(weak) >= 2:
        return {"tradable": False, "reason": "; ".join(weak)}

    return {"tradable": True, "reason": "BTC/ETH regime acceptable"}


def fetch_futures(symbol):
    futures_symbols = load_futures_symbols()
    if symbol not in futures_symbols:
        return {}

    data = {}
    try:
        open_interest = get_json(
            f"{BINANCE_FUTURES_BASE}/fapi/v1/openInterest",
            params={"symbol": symbol},
        )
        data["open_interest"] = float(open_interest.get("openInterest") or 0)
    except Exception:
        pass

    try:
        premium = get_json(
            f"{BINANCE_FUTURES_BASE}/fapi/v1/premiumIndex",
            params={"symbol": symbol},
        )
        data["funding_rate"] = float(premium.get("lastFundingRate") or 0) * 100
    except Exception:
        pass

    try:
        ratios = get_json(
            f"{BINANCE_FUTURES_BASE}/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": "1h", "limit": 2},
        )
        if ratios:
            latest = ratios[-1]
            data["long_short_ratio"] = float(latest.get("longShortRatio") or 0)
    except Exception:
        pass

    try:
        taker = get_json(
            f"{BINANCE_FUTURES_BASE}/futures/data/takerlongshortRatio",
            params={"symbol": symbol, "period": "5m", "limit": 3},
        )
        if taker:
            latest = taker[-1]
            data["futures_taker_buy_sell_ratio"] = float(latest.get("buySellRatio") or 0)
            data["futures_taker_buy_volume"] = float(latest.get("buyVol") or 0)
            data["futures_taker_sell_volume"] = float(latest.get("sellVol") or 0)
    except Exception:
        pass

    try:
        top_positions = get_json(
            f"{BINANCE_FUTURES_BASE}/futures/data/topLongShortPositionRatio",
            params={"symbol": symbol, "period": "5m", "limit": 3},
        )
        if top_positions:
            latest = top_positions[-1]
            data["top_trader_position_ratio"] = float(latest.get("longShortRatio") or 0)
    except Exception:
        pass

    return data


def fetch_market_flow(ticker, current_price):
    symbol = to_usdt_symbol(ticker)
    if not symbol:
        return {"source": "No Binance symbol"}

    try:
        spot_symbols = load_spot_symbols()
    except Exception as error:
        return {"source": f"Binance unavailable: {error}"}

    if symbol not in spot_symbols:
        return {"source": "No Binance spot pair", "binance_symbol": symbol}

    flow = {"source": "Binance public market data", "binance_symbol": symbol}

    try:
        flow.update(fetch_order_book(symbol, current_price))
    except Exception as error:
        flow["book_error"] = str(error)

    try:
        flow.update(fetch_trade_flow(symbol))
    except Exception as error:
        flow["trade_flow_error"] = str(error)

    try:
        flow.update(fetch_futures(symbol))
    except Exception:
        pass

    return flow
