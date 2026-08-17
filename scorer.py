from config import (
    MIN_24H_VOLUME_USD,
    MIN_HOURLY_VOLUME_USD,
    MIN_PRICE,
)

SHORT_TERM_MIN_TARGET_PROFIT_PCT = 3.0
SHORT_TERM_BASE_MAX_TARGET_PROFIT_PCT = 6.0
SHORT_TERM_EXTENDED_MAX_TARGET_PROFIT_PCT = 4.5


def clamp(value, low=0, high=100):
    return max(low, min(value, high))


def pct_change(current, previous):
    if not previous:
        return 0
    return ((current - previous) / previous) * 100


def format_price(value):
    if value is None:
        return "-"

    value = float(value)
    return f"${value:,.2f}"


def score_market_flow(market_flow, price_change_1h):
    buy_adjustment = 0
    sell_adjustment = 0
    reasons = []
    sell_reasons = []

    imbalance = market_flow.get("book_imbalance")
    if imbalance is not None:
        if imbalance >= 1.8:
            buy_adjustment += 10
            reasons.append(f"Bid wall support: {imbalance:.2f}x ask depth")
        elif imbalance >= 1.25:
            buy_adjustment += 5
            reasons.append(f"Bid depth leads asks: {imbalance:.2f}x")
        elif imbalance <= 0.55:
            buy_adjustment -= 10
            sell_adjustment += 10
            reasons.append(f"Penalty: ask wall pressure: bids only {imbalance:.2f}x asks")
            sell_reasons.append(f"Ask wall pressure: bids only {imbalance:.2f}x asks")
        elif imbalance <= 0.8:
            buy_adjustment -= 5
            sell_adjustment += 5
            reasons.append(f"Penalty: ask depth outweighs bids: {imbalance:.2f}x")
            sell_reasons.append(f"Ask depth outweighs bids: {imbalance:.2f}x")

    spread_pct = market_flow.get("spread_pct")
    if spread_pct is not None:
        if spread_pct > 0.25:
            buy_adjustment -= 8
            sell_adjustment += 4
            reasons.append(f"Penalty: wide spread {spread_pct:.2f}%")
        elif spread_pct <= 0.05:
            buy_adjustment += 3
            reasons.append("Tight spread")

    taker_buy_ratio = market_flow.get("taker_buy_ratio")
    if taker_buy_ratio is not None:
        if taker_buy_ratio >= 0.62:
            buy_adjustment += 12
            reasons.append(f"Aggressive buyers lead: {taker_buy_ratio * 100:.0f}% taker buys")
        elif taker_buy_ratio >= 0.55:
            buy_adjustment += 6
            reasons.append(f"Buyer flow positive: {taker_buy_ratio * 100:.0f}% taker buys")
        elif taker_buy_ratio <= 0.38:
            buy_adjustment -= 12
            sell_adjustment += 12
            reasons.append(f"Penalty: aggressive sellers lead: {(1 - taker_buy_ratio) * 100:.0f}% taker sells")
            sell_reasons.append(f"Aggressive sellers lead: {(1 - taker_buy_ratio) * 100:.0f}% taker sells")
        elif taker_buy_ratio <= 0.45:
            buy_adjustment -= 6
            sell_adjustment += 6
            reasons.append(f"Penalty: seller flow positive: {(1 - taker_buy_ratio) * 100:.0f}% taker sells")
            sell_reasons.append(f"Seller flow positive: {(1 - taker_buy_ratio) * 100:.0f}% taker sells")

    funding_rate = market_flow.get("funding_rate")
    if funding_rate is not None:
        if funding_rate > 0.06:
            buy_adjustment -= 6
            sell_adjustment += 5
            sell_reasons.append(f"Longs crowded: funding {funding_rate:.3f}%")
        elif funding_rate < -0.03 and price_change_1h > 0:
            buy_adjustment += 5
            reasons.append(f"Possible short squeeze: funding {funding_rate:.3f}%")

    long_short_ratio = market_flow.get("long_short_ratio")
    if long_short_ratio is not None:
        if long_short_ratio > 2.2:
            buy_adjustment -= 5
            sell_adjustment += 5
            sell_reasons.append(f"Long side crowded: L/S {long_short_ratio:.2f}")
        elif long_short_ratio < 0.75 and price_change_1h > 0:
            buy_adjustment += 4
            reasons.append(f"Under-owned rebound setup: L/S {long_short_ratio:.2f}")

    futures_taker_ratio = market_flow.get("futures_taker_buy_sell_ratio")
    if futures_taker_ratio is not None:
        if futures_taker_ratio >= 1.35:
            buy_adjustment += 8
            reasons.append(f"Futures taker buyers lead: {futures_taker_ratio:.2f}x")
        elif futures_taker_ratio <= 0.82:
            buy_adjustment -= 8
            sell_adjustment += 8
            reasons.append(f"Penalty: futures taker sellers lead: {futures_taker_ratio:.2f}x")
            sell_reasons.append(f"Futures taker sellers lead: {futures_taker_ratio:.2f}x")

    top_trader_ratio = market_flow.get("top_trader_position_ratio")
    if top_trader_ratio is not None:
        if 0.85 <= top_trader_ratio <= 1.8 and price_change_1h > 0:
            buy_adjustment += 3
            reasons.append(f"Top trader positioning not crowded: {top_trader_ratio:.2f}x")
        elif top_trader_ratio > 2.5:
            buy_adjustment -= 5
            sell_adjustment += 4
            sell_reasons.append(f"Top traders crowded long: {top_trader_ratio:.2f}x")
        elif top_trader_ratio < 0.65 and price_change_1h < 0:
            buy_adjustment -= 4
            sell_adjustment += 4
            sell_reasons.append(f"Top traders leaning short: {top_trader_ratio:.2f}x")

    if market_flow.get("source") and market_flow.get("source") != "Binance public market data":
        buy_adjustment -= 3
        reasons.append(market_flow["source"])

    return buy_adjustment, sell_adjustment, reasons, sell_reasons


def build_trade_plan(
    current_price,
    buy_score,
    sell_score,
    price_change_1h,
    price_change_4h,
    support,
    resistance,
    atr,
    rsi,
    market_flow,
):
    atr = max(float(atr or current_price * 0.015), current_price * 0.003)
    atr_pct = (atr / current_price) * 100 if current_price else 0
    entry_low = max(current_price - (atr * 0.35), 0)
    entry_high = current_price + (atr * 0.15)

    max_target_pct = SHORT_TERM_BASE_MAX_TARGET_PROFIT_PCT
    if rsi is not None and rsi >= 82:
        max_target_pct = 3.5
    elif price_change_4h > 12 or price_change_1h > 6:
        max_target_pct = SHORT_TERM_EXTENDED_MAX_TARGET_PROFIT_PCT

    momentum_target_pct = min(
        max_target_pct,
        max(
            SHORT_TERM_MIN_TARGET_PROFIT_PCT,
            (max(price_change_1h, 0) * 0.55)
            + (max(price_change_4h, 0) * 0.18)
            + (atr_pct * 0.90),
        ),
    )
    capped_resistance_target = min(
        resistance + (atr * 0.35),
        current_price * (1 + (max_target_pct / 100)),
    )
    target = max(
        current_price * (1 + (SHORT_TERM_MIN_TARGET_PROFIT_PCT / 100)),
        current_price * (1 + (momentum_target_pct / 100)),
        capped_resistance_target,
    )
    target = min(target, current_price * (1 + (max_target_pct / 100)))
    stop = min(support - (atr * 0.35), current_price - (atr * 1.1))
    stop = max(stop, current_price * 0.90)
    target_profit_pct = ((target - current_price) / current_price) * 100
    stop_loss_pct = ((current_price - stop) / current_price) * 100

    if price_change_1h >= 3 and price_change_4h >= 8:
        target_window = "30-120m breakout attempt"
    else:
        target_window = "15-90m adaptive target"

    if sell_score >= 65:
        action = "Avoid new buys"
        note = (
            f"{action}. Weakness is active; only consider again above "
            f"{format_price(resistance)}. Risk area below {format_price(support)}."
        )
    elif buy_score >= 75:
        action = "Buy only near the entry zone"
        note = (
            f"{action}: {format_price(entry_low)}-{format_price(entry_high)}. "
            f"Upside target {format_price(target)} ({target_profit_pct:.1f}%) over {target_window}; "
            f"cut risk below {format_price(stop)}."
        )
    elif buy_score >= 55:
        action = "Watch for pullback entry"
        note = (
            f"{action}: {format_price(entry_low)}-{format_price(current_price)}. "
            f"Upside target {format_price(target)} ({target_profit_pct:.1f}%) over {target_window}; "
            f"stop below {format_price(stop)}."
        )
    else:
        action = "Wait"
        note = (
            f"{action}. Needs reclaim above {format_price(resistance)} or stronger buyer flow. "
            f"Risk below {format_price(support)}."
        )

    extra = []
    if rsi is not None and rsi >= 78:
        extra.append(f"RSI {rsi:.0f} is hot, avoid chasing candles")
    elif rsi is not None and rsi <= 35 and price_change_1h > 0:
        extra.append(f"RSI {rsi:.0f} suggests rebound potential")

    taker_buy_ratio = market_flow.get("taker_buy_ratio")
    if taker_buy_ratio is not None:
        extra.append(f"taker buys {taker_buy_ratio * 100:.0f}%")

    if price_change_4h > 12:
        extra.append("4h move is extended")

    if extra:
        note += " " + "; ".join(extra) + "."

    return {
        "trade_note": note,
        "target_price": round(target, 8),
        "stop_price": round(stop, 8),
        "entry_low": round(entry_low, 8),
        "entry_high": round(entry_high, 8),
        "target_profit_pct": round(target_profit_pct, 2),
        "stop_loss_pct": round(stop_loss_pct, 2),
        "target_window": target_window,
    }


def score_buy(
    price_change_1h,
    price_change_4h,
    price_change_24h,
    relative_volume,
    dollar_volume,
    current_price_vs_high,
    current_price_vs_vwap,
    atr_pct,
    range_24h_pct,
    upside_to_high_pct,
    market_rank,
):
    score = 0
    reasons = []

    if 3 <= price_change_1h <= 12:
        score += 24
        reasons.append(f"Strong hourly impulse: {price_change_1h:.2f}%")
    elif 1 <= price_change_1h < 3:
        score += 16
        reasons.append(f"Fresh hourly lift: {price_change_1h:.2f}%")
    elif 0.4 <= price_change_1h < 1:
        score += 6
        reasons.append(f"Small hourly lift: {price_change_1h:.2f}%")
    elif price_change_1h > 12:
        score += 4
        reasons.append(f"Very fast hourly move, chase risk: {price_change_1h:.2f}%")

    if 8 <= price_change_4h <= 30:
        score += 24
        reasons.append(f"Explosive 4-hour acceleration: {price_change_4h:.2f}%")
    elif 3 <= price_change_4h < 8:
        score += 16
        reasons.append(f"4-hour acceleration: {price_change_4h:.2f}%")
    elif 1.5 <= price_change_4h < 3:
        score += 6
        reasons.append(f"Early 4-hour lift: {price_change_4h:.2f}%")
    elif price_change_4h < -3:
        score -= 12
        reasons.append(f"Penalty: weak 4-hour trend: {price_change_4h:.2f}%")

    if 8 <= price_change_24h <= 45:
        score += 14
        reasons.append(f"24-hour expansion: {price_change_24h:.2f}%")
    elif -8 <= price_change_24h < 8:
        score += 3
        reasons.append("24-hour trend is stable but not explosive")
    elif price_change_24h > 60:
        score -= 10
        reasons.append(f"Penalty: 24-hour move may be crowded: {price_change_24h:.2f}%")
    elif price_change_24h < -12:
        score -= 10
        reasons.append(f"Penalty: heavy 24-hour drawdown: {price_change_24h:.2f}%")

    if relative_volume >= 3:
        score += 18
        reasons.append(f"Volume surge: {relative_volume:.2f}x recent hourly average")
    elif relative_volume >= 1.6:
        score += 12
        reasons.append(f"Above-average volume: {relative_volume:.2f}x")
    elif relative_volume < 0.65:
        score -= 10
        reasons.append(f"Penalty: quiet volume: {relative_volume:.2f}x")

    if current_price_vs_high >= 0.985:
        score += 12
        reasons.append("Pressing 24-hour high")
    elif current_price_vs_high < 0.94:
        score -= 6
        reasons.append("Below recent high")

    if current_price_vs_vwap >= 1.002:
        score += 8
        reasons.append("Trading above recent VWAP")
    elif current_price_vs_vwap < 0.99:
        score -= 8
        reasons.append("Below recent VWAP")

    if dollar_volume >= 1_000_000:
        score += 8
        reasons.append("Deep hourly liquidity")
    elif dollar_volume >= MIN_HOURLY_VOLUME_USD:
        score += 4
        reasons.append("Acceptable hourly liquidity")

    if market_rank and market_rank <= 75:
        score += 3
        reasons.append("Large/liquid crypto name")

    if atr_pct >= 4:
        score += 14
        reasons.append(f"High hourly volatility: ATR {atr_pct:.2f}%")
    elif atr_pct >= 2:
        score += 8
        reasons.append(f"Tradable hourly volatility: ATR {atr_pct:.2f}%")
    elif atr_pct < 1:
        score -= 16
        reasons.append(f"Penalty: low hourly volatility for 10% target: ATR {atr_pct:.2f}%")

    if range_24h_pct >= 18:
        score += 12
        reasons.append(f"Wide 24-hour range: {range_24h_pct:.2f}%")
    elif range_24h_pct >= 10:
        score += 6
        reasons.append(f"Enough 24-hour range for 10% setup: {range_24h_pct:.2f}%")
    elif range_24h_pct < 7:
        score -= 18
        reasons.append(f"Penalty: 24-hour range too small for 10% target: {range_24h_pct:.2f}%")

    if upside_to_high_pct >= 10:
        score += 8
        reasons.append(f"Room to recent high: {upside_to_high_pct:.2f}%")
    elif upside_to_high_pct < 3 and price_change_1h < 3:
        score -= 10
        reasons.append("Penalty: near resistance without strong impulse")

    if relative_volume < 1 and price_change_1h < 0.5:
        score = min(score, 42)
        reasons.append("Cap: lacks fresh hourly demand")

    if atr_pct < 1.5 and range_24h_pct < 8 and price_change_1h < 3:
        score = min(score, 48)
        reasons.append("Cap: setup does not fit 10% profit hunt")

    if dollar_volume < MIN_HOURLY_VOLUME_USD:
        score = min(score, 35)
        reasons.append("Cap: thin hourly liquidity")

    return clamp(round(score)), reasons


def score_sell(
    price_change_1h,
    price_change_4h,
    price_change_24h,
    relative_volume,
    current_price_vs_high,
    current_price_vs_vwap,
):
    score = 0
    reasons = []

    if price_change_1h <= -2:
        score += 22
        reasons.append(f"Hourly breakdown: {price_change_1h:.2f}%")
    elif price_change_1h <= -0.8:
        score += 12
        reasons.append(f"Hourly weakness: {price_change_1h:.2f}%")

    if price_change_4h <= -5:
        score += 22
        reasons.append(f"4-hour downtrend: {price_change_4h:.2f}%")
    elif price_change_4h <= -2:
        score += 12
        reasons.append(f"4-hour fade: {price_change_4h:.2f}%")

    if price_change_24h <= -10:
        score += 16
        reasons.append(f"24-hour sell pressure: {price_change_24h:.2f}%")
    elif price_change_24h >= 25 and price_change_1h < 0:
        score += 14
        reasons.append("Taking-profit risk after large 24-hour run")

    if relative_volume >= 2 and price_change_1h < 0:
        score += 14
        reasons.append(f"Selling on active volume: {relative_volume:.2f}x")

    if current_price_vs_high < 0.94:
        score += 10
        reasons.append("Rejected from recent high")

    if current_price_vs_vwap < 0.992:
        score += 12
        reasons.append("Trading below recent VWAP")

    if price_change_1h > 0.5 and price_change_4h > 1:
        score -= 15
        reasons.append("Penalty: short-term trend still rising")

    return clamp(round(score)), reasons


def buy_signal(score):
    if score >= 80:
        return "Prime hourly buy watch"
    if score >= 68:
        return "Strong hourly buy"
    if score >= 55:
        return "Buy watch"
    if score >= 40:
        return "Early setup"
    return "Low priority"


def sell_signal(score):
    if score >= 80:
        return "High-risk sell/avoid"
    if score >= 68:
        return "Strong sell watch"
    if score >= 55:
        return "Sell watch"
    if score >= 40:
        return "Weakening"
    return "No sell signal"


def calculate_score(
    ticker,
    name,
    market_rank,
    current_price,
    previous_hour_close,
    close_4h_ago,
    close_24h_ago,
    current_hour_volume,
    avg_hour_volume,
    recent_high,
    recent_low,
    recent_vwap,
    support,
    resistance,
    atr,
    rsi,
    market_flow,
    volume_24h,
):
    if current_price < MIN_PRICE or volume_24h < MIN_24H_VOLUME_USD:
        return None

    price_change_1h = pct_change(current_price, previous_hour_close)
    price_change_4h = pct_change(current_price, close_4h_ago)
    price_change_24h = pct_change(current_price, close_24h_ago)
    relative_volume = current_hour_volume / avg_hour_volume if avg_hour_volume else 0
    dollar_volume = current_price * current_hour_volume
    current_price_vs_high = current_price / recent_high if recent_high else 0
    current_price_vs_vwap = current_price / recent_vwap if recent_vwap else 1
    atr_pct = (atr / current_price) * 100 if current_price else 0
    range_24h_pct = ((recent_high - recent_low) / current_price) * 100 if current_price else 0
    upside_to_high_pct = ((recent_high - current_price) / current_price) * 100 if current_price else 0
    market_flow = market_flow or {}

    buy_score, buy_reasons = score_buy(
        price_change_1h=price_change_1h,
        price_change_4h=price_change_4h,
        price_change_24h=price_change_24h,
        relative_volume=relative_volume,
        dollar_volume=dollar_volume,
        current_price_vs_high=current_price_vs_high,
        current_price_vs_vwap=current_price_vs_vwap,
        atr_pct=atr_pct,
        range_24h_pct=range_24h_pct,
        upside_to_high_pct=upside_to_high_pct,
        market_rank=market_rank,
    )
    sell_score, sell_reasons = score_sell(
        price_change_1h=price_change_1h,
        price_change_4h=price_change_4h,
        price_change_24h=price_change_24h,
        relative_volume=relative_volume,
        current_price_vs_high=current_price_vs_high,
        current_price_vs_vwap=current_price_vs_vwap,
    )
    flow_buy_adjustment, flow_sell_adjustment, flow_reasons, flow_sell_reasons = score_market_flow(
        market_flow=market_flow,
        price_change_1h=price_change_1h,
    )
    buy_score = clamp(buy_score + flow_buy_adjustment)
    sell_score = clamp(sell_score + flow_sell_adjustment)
    buy_reasons.extend(flow_reasons)
    sell_reasons.extend(flow_sell_reasons)

    if rsi is not None:
        if rsi >= 82:
            buy_score = min(buy_score, 72)
            buy_reasons.append(f"Cap: RSI hot at {rsi:.0f}")
        elif rsi >= 72:
            buy_score -= 4
            buy_reasons.append(f"Penalty: RSI elevated at {rsi:.0f}")
        elif 45 <= rsi <= 68 and price_change_1h > 0:
            buy_score += 4
            buy_reasons.append(f"Healthy RSI range: {rsi:.0f}")
        elif rsi <= 35 and price_change_1h < 0:
            sell_score = min(sell_score, 70)
            sell_reasons.append(f"Downside may be stretched: RSI {rsi:.0f}")

    buy_score = clamp(round(buy_score))
    sell_score = clamp(round(sell_score))
    if sell_score >= 65:
        buy_score = min(buy_score, 35)
        buy_reasons.append("Cap: strong sell signal blocks buy setup")
    elif sell_score >= 55:
        buy_score = min(buy_score, 45)
        buy_reasons.append("Cap: sell watch blocks strong buy setup")
    elif sell_score >= 45:
        buy_score = min(buy_score, 62)
        buy_reasons.append("Cap: elevated sell risk limits buy setup")

    plan = build_trade_plan(
        current_price=current_price,
        buy_score=buy_score,
        sell_score=sell_score,
        price_change_1h=price_change_1h,
        price_change_4h=price_change_4h,
        support=support or recent_low,
        resistance=resistance or recent_high,
        atr=atr,
        rsi=rsi,
        market_flow=market_flow,
    )
    target_profit_pct = plan["target_profit_pct"]
    stop_loss_pct = plan["stop_loss_pct"]
    reward_risk = target_profit_pct / stop_loss_pct if stop_loss_pct else 0

    if target_profit_pct >= SHORT_TERM_MIN_TARGET_PROFIT_PCT:
        buy_score += min(6, int(target_profit_pct))
        buy_reasons.append(f"Reachable short-term target: {target_profit_pct:.1f}%")

    if reward_risk >= 2.5:
        buy_score += 6
        buy_reasons.append(f"Good reward/risk: {reward_risk:.1f}x")
    elif reward_risk < 1.2 and buy_score >= 55:
        buy_score -= 8
        buy_reasons.append(f"Penalty: weak reward/risk: {reward_risk:.1f}x")

    buy_score = clamp(round(buy_score))
    plan = build_trade_plan(
        current_price=current_price,
        buy_score=buy_score,
        sell_score=sell_score,
        price_change_1h=price_change_1h,
        price_change_4h=price_change_4h,
        support=support or recent_low,
        resistance=resistance or recent_high,
        atr=atr,
        rsi=rsi,
        market_flow=market_flow,
    )

    return {
        "ticker": ticker,
        "name": name,
        "score": buy_score,
        "quick_win_score": buy_score,
        "long_term_score": sell_score,
        "moonshot_score": buy_score,
        "momentum_score": max(buy_score, sell_score),
        "signal": buy_signal(buy_score),
        "long_term_signal": sell_signal(sell_score),
        "price": round(current_price, 8),
        "price_change": round(price_change_1h, 2),
        "price_change_5d": round(price_change_4h, 2),
        "price_change_20d": round(price_change_24h, 2),
        "three_year_return": None,
        "support": round(support or recent_low, 8),
        "resistance": round(resistance or recent_high, 8),
        "vwap": round(recent_vwap, 8),
        "atr": round(atr, 8),
        "atr_pct": round(atr_pct, 2),
        "range_24h_pct": round(range_24h_pct, 2),
        "upside_to_high_pct": round(upside_to_high_pct, 2),
        "target_profit_pct": target_profit_pct,
        "stop_loss_pct": stop_loss_pct,
        "reward_risk": round(reward_risk, 2),
        "target_window": plan["target_window"],
        "rsi": round(rsi, 2) if rsi is not None else None,
        "relative_volume": round(relative_volume, 2),
        "dollar_volume": round(dollar_volume, 0),
        "headline": plan["trade_note"],
        "trade_note": plan["trade_note"],
        "target_price": plan["target_price"],
        "stop_price": plan["stop_price"],
        "entry_low": plan["entry_low"],
        "entry_high": plan["entry_high"],
        "market_flow": market_flow,
        "reasons": buy_reasons,
        "quick_win_reasons": buy_reasons,
        "long_term_reasons": sell_reasons,
        "momentum_reasons": buy_reasons + sell_reasons,
    }
