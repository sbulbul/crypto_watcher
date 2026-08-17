from market_flow import fetch_market_flow


MIN_SIGNAL_SCORE = 62
NEAR_TOP_30M_POSITION = 0.78
BREAKOUT_30M_POSITION = 0.86
BREAKOUT_MIN_SPOT_BUY_RATIO = 0.68
BREAKOUT_MIN_VOLUME_RATIO = 1.80
BREAKOUT_MIN_BOOK_IMBALANCE = 1.60
BREAKOUT_MIN_FUTURES_TAKER_RATIO = 1.18
BREAKOUT_MIN_1M_RETURN = 0.05
BREAKOUT_MAX_5M_RETURN = 1.25


def _fmt_pct(value):
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def evaluate_public_signal(ticker, current_price, behavior, confirmation):
    flow = fetch_market_flow(ticker, current_price)
    score = 0
    reasons = []
    hard_rejects = []

    taker_buy_ratio = flow.get("taker_buy_ratio")
    book_imbalance = flow.get("book_imbalance")
    spread_pct = flow.get("spread_pct")
    futures_taker_ratio = flow.get("futures_taker_buy_sell_ratio")
    funding_rate = flow.get("funding_rate")
    long_short_ratio = flow.get("long_short_ratio")
    top_trader_ratio = flow.get("top_trader_position_ratio")

    if behavior.get("entry_trigger"):
        score += 22
        reasons.append("fresh 1m entry trigger")
    else:
        hard_rejects.append("no fresh 1m entry trigger")

    close_position = behavior.get("close_position_30m")
    ret_1m = behavior.get("return_1m_pct") or 0
    ret_5m = behavior.get("return_5m_pct")
    ret_15m = behavior.get("return_15m_pct")
    volume_ratio = behavior.get("volume_ratio_5m")
    huge_breakout_confirmed = (
        close_position is not None
        and close_position >= BREAKOUT_30M_POSITION
        and behavior.get("entry_trigger")
        and ret_1m >= BREAKOUT_MIN_1M_RETURN
        and (ret_5m is not None and ret_5m <= BREAKOUT_MAX_5M_RETURN)
        and (volume_ratio is not None and volume_ratio >= BREAKOUT_MIN_VOLUME_RATIO)
        and (taker_buy_ratio is not None and taker_buy_ratio >= BREAKOUT_MIN_SPOT_BUY_RATIO)
        and (book_imbalance is not None and book_imbalance >= BREAKOUT_MIN_BOOK_IMBALANCE)
        and (
            futures_taker_ratio is None
            or futures_taker_ratio >= BREAKOUT_MIN_FUTURES_TAKER_RATIO
        )
    )
    if close_position is not None:
        if 0.35 <= close_position <= 0.78:
            score += 14
            reasons.append(f"healthy 30m location {close_position:.2f}")
        elif close_position >= NEAR_TOP_30M_POSITION:
            if huge_breakout_confirmed:
                score += 18
                reasons.append(f"confirmed breakout near 30m high {close_position:.2f}")
            else:
                hard_rejects.append(f"near top without huge breakout confirmation {close_position:.2f}")
        elif close_position < 0.25 and not behavior.get("entry_trigger"):
            hard_rejects.append(f"lower range without turn {close_position:.2f}")

    if ret_5m is not None:
        if -0.20 <= ret_5m <= 0.90:
            score += 10
            reasons.append(f"not chasing 5m {_fmt_pct(ret_5m)}")
        elif ret_5m > 1.25:
            hard_rejects.append(f"5m chase {_fmt_pct(ret_5m)}")
        elif ret_5m < -0.55:
            hard_rejects.append(f"5m rolling over {_fmt_pct(ret_5m)}")

    if ret_15m is not None:
        if -0.15 <= ret_15m <= 2.20:
            score += 8
            reasons.append(f"controlled 15m {_fmt_pct(ret_15m)}")
        elif ret_15m < -0.55:
            hard_rejects.append(f"15m breakdown {_fmt_pct(ret_15m)}")
        elif ret_15m > 4.0:
            hard_rejects.append(f"15m overextended {_fmt_pct(ret_15m)}")

    if volume_ratio is not None:
        if volume_ratio >= 1.15:
            score += 12
            reasons.append(f"1m volume expanding {volume_ratio:.2f}x")
        elif volume_ratio >= 0.75:
            score += 5
            reasons.append(f"1m volume acceptable {volume_ratio:.2f}x")
        elif volume_ratio < 0.45:
            hard_rejects.append(f"1m volume fading {volume_ratio:.2f}x")

    if taker_buy_ratio is not None:
        if taker_buy_ratio >= 0.62:
            score += 16
            reasons.append(f"spot buyers lead {taker_buy_ratio * 100:.0f}%")
        elif taker_buy_ratio >= 0.52:
            score += 6
            reasons.append(f"spot buyers modest {taker_buy_ratio * 100:.0f}%")
        elif taker_buy_ratio < 0.42:
            hard_rejects.append(f"spot sellers lead {(1 - taker_buy_ratio) * 100:.0f}%")

    if book_imbalance is not None:
        if book_imbalance >= 1.25:
            score += 10
            reasons.append(f"bid book support {book_imbalance:.2f}x")
        elif book_imbalance >= 0.75:
            score += 3
            reasons.append(f"book balanced {book_imbalance:.2f}x")
        elif book_imbalance < 0.45:
            hard_rejects.append(f"ask book pressure {book_imbalance:.2f}x")

    if spread_pct is not None:
        if spread_pct <= 0.08:
            score += 6
            reasons.append(f"tight spread {_fmt_pct(spread_pct)}")
        elif spread_pct > 0.30:
            hard_rejects.append(f"wide spread {_fmt_pct(spread_pct)}")

    if futures_taker_ratio is not None:
        if futures_taker_ratio >= 1.10:
            score += 8
            reasons.append(f"futures buyers {futures_taker_ratio:.2f}x")
        elif futures_taker_ratio < 0.82:
            hard_rejects.append(f"futures sellers {futures_taker_ratio:.2f}x")

    if funding_rate is not None:
        if funding_rate > 0.08:
            hard_rejects.append(f"funding crowded {_fmt_pct(funding_rate)}")
        elif funding_rate < -0.02 and behavior.get("entry_trigger"):
            score += 4
            reasons.append(f"possible short squeeze funding {_fmt_pct(funding_rate)}")

    if long_short_ratio is not None and long_short_ratio > 2.8:
        hard_rejects.append(f"crowded longs {long_short_ratio:.2f}x")
    if top_trader_ratio is not None and top_trader_ratio > 3.0:
        hard_rejects.append(f"top traders crowded {top_trader_ratio:.2f}x")

    approved = score >= MIN_SIGNAL_SCORE and not hard_rejects
    return {
        "approved": approved,
        "score": score,
        "threshold": MIN_SIGNAL_SCORE,
        "reasons": reasons,
        "hard_rejects": hard_rejects,
        "flow": flow,
        "summary": "; ".join(reasons + [f"reject: {reason}" for reason in hard_rejects]),
    }
