import threading
import time

from market_flow import fetch_market_regime, fetch_one_minute_behavior, fetch_short_term_confirmation
from scanner import scan_market
from signal_engine import evaluate_public_signal
from storage import fetch_latest_price, get_connection, init_db

STARTING_CASH = 5000.0
MAX_HOLD_SECONDS = 60 * 60
STALE_EXIT_SECONDS = 25 * 60
FAST_FAIL_SECONDS = 4 * 60
SCAN_INTERVAL_SECONDS = 2 * 60
PRICE_POLL_SECONDS = 5
WATCHLIST_TTL_SECONDS = 15 * 60
WATCHLIST_CHECK_SECONDS = 10
WATCHLIST_BATCH_SIZE = 6
MAX_WATCHLIST_SIZE = 30
POSITION_BEHAVIOR_SECONDS = 15
MAX_OPEN_POSITIONS = 30
MAX_POSITION_USD = 300.0
MIN_POSITION_USD = 300.0
CASH_RESERVE_USD = 250.0
MAX_ACCOUNT_DRAWDOWN_PCT = 2.0
WEALTHSIMPLE_CLIENT_TIER = "Flat 0.20%"
WEALTHSIMPLE_BASELINE_FEES = {
    "Core": 2.0,
    "Premium": 1.0,
    "Generation": 0.5,
    "Flat 0.20%": 0.20,
}
WEALTHSIMPLE_VOLUME_FEES = [
    (10_000_000, 0.05),
    (5_000_000, 0.10),
    (1_000_000, 0.15),
    (500_000, 0.25),
    (100_000, 0.50),
    (50_000, 0.75),
    (10_000, 1.00),
    (1_000, 1.50),
    (0, 2.00),
]
MARKET_SPREAD_SLIPPAGE_PCT = 0.20
BUY_MIN_SCORE = 65
MIN_TARGET_PROFIT_PCT = 1.25
MIN_REWARD_RISK = 0.80
MIN_24H_RANGE_PCT = 4
MAX_RSI = 90
MAX_BUY_SELL_SCORE = 45
MIN_TAKER_BUY_RATIO = 0.50
MIN_BOOK_IMBALANCE = 0.45
MAX_SCALP_LOSS_PCT = 1.65
SUCCESS_RETURN_PCT = 0.80
QUICK_PROFIT_EXIT_PCT = 0.70
MICRO_PROFIT_TRAIL_PCT = 0.40
BREAKEVEN_TRAIL_BUFFER_PCT = 0.05
PROFIT_CAPTURE_MIN_AGE_SECONDS = 45
PROFIT_LOCK_NET_PCT = 0.25
MOMENTUM_EXIT_MIN_PEAK_NET_PCT = 0.70
MOMENTUM_EXIT_MIN_NET_PCT = 0.20
WIN_ONLY_EXIT_MODE = False
COOLDOWN_AFTER_LOSS_SECONDS = 6 * 60 * 60
COOLDOWN_AFTER_EXIT_SECONDS = 20 * 60
MIN_ENTRY_PRICE_CHANGE_1H = 0.15
MIN_ENTRY_RELATIVE_VOLUME = 0.65
DEFAULT_SCAN_LIMIT = 1000
MIN_DESIRED_OPEN_POSITIONS = 10
FILL_BUY_MIN_SCORE = 45
FILL_MAX_SELL_SCORE = 65
FILL_MIN_REWARD_RISK = 0.80
FILL_MIN_24H_RANGE_PCT = 4
FILL_MAX_RSI = 90
FILL_MIN_HOURLY_LIQUIDITY_USD = 10_000
ENTRY_DECISION_MIN_SCORE = 45
WEAK_MARKET_ENTRY_MIN_SCORE = 60
SETUP_INVALIDATION_NET_PCT = -1.00
FAST_FAILURE_NET_PCT = -1.40
HARD_REJECT_30M_DROP_PCT = -2.50
HARD_REJECT_VOLUME_RATIO = 0.30
MIN_BEHAVIOR_SCORE = -25
MIN_BEHAVIOR_VOLUME_RATIO = 0.15
MAX_BEHAVIOR_PULLBACK_15M_PCT = 3.25
EXTREME_RSI = 95
HARD_MIN_TAKER_BUY_RATIO = 0.35
LOW_VOLUME_RATIO = 0.75
LOW_VOLUME_MIN_BEHAVIOR_SCORE = 10
STRONG_BEHAVIOR_SCORE = 50
STRONG_BEHAVIOR_VOLUME_RATIO = 0.80
FALLBACK_MIN_TAKER_BUY_RATIO = 0.45
ELITE_BEHAVIOR_SCORE = 100
ELITE_BEHAVIOR_VOLUME_RATIO = 1.50
CHASE_5M_RETURN_PCT = 1.25
NEAR_HIGH_BUYER_FLOW_PCT = 0.68
NEAR_HIGH_MIN_VOLUME_RATIO = 1.80
NEAR_HIGH_MIN_BOOK_IMBALANCE = 1.60
NEAR_HIGH_MIN_FUTURES_TAKER_RATIO = 1.18
MAX_ENTRY_30M_POSITION = 0.78
BREAKOUT_ENTRY_30M_POSITION = 0.86
BREAKOUT_ENTRY_MIN_1M_RETURN = 0.05
BREAKOUT_ENTRY_MAX_5M_RETURN = 1.25

_lock = threading.Lock()
_stop_event = threading.Event()
_worker = None
_watchlist = {}
_watch_cursor = 0
_last_watch_check = 0
_position_behavior_cache = {}
_state = {
    "running": False,
    "last_scan_at": None,
    "last_tick_at": None,
    "next_scan_at": None,
    "scan_limit": DEFAULT_SCAN_LIMIT,
    "status": "Idle",
    "error": "",
    "last_candidates": 0,
    "last_eligible": 0,
    "last_rejections": {},
    "watching": 0,
    "market_regime": {},
}


def init_paper_db():
    init_db()
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                starting_cash REAL NOT NULL,
                cash REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                status TEXT NOT NULL,
                opened_at REAL NOT NULL,
                closed_at REAL,
                entry_price REAL NOT NULL,
                quantity REAL NOT NULL,
                invested REAL NOT NULL,
                latest_price REAL,
                highest_price REAL,
                target_price REAL,
                stop_price REAL,
                trailing_stop REAL,
                buy_score INTEGER,
                sell_score INTEGER,
                target_profit_pct REAL,
                target_window TEXT,
                reward_risk REAL,
                open_reason TEXT,
                close_reason TEXT,
                realized_pnl REAL,
                realized_return_pct REAL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_positions_ticker ON paper_positions(ticker)"
        )
        position_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(paper_positions)").fetchall()
        }
        new_position_columns = {
            "entry_pattern": "TEXT",
            "entry_decision_score": "INTEGER",
            "public_signal_score": "INTEGER",
            "behavior_score": "INTEGER",
            "max_net_return_pct": "REAL",
        }
        for column, column_type in new_position_columns.items():
            if column not in position_columns:
                conn.execute(f"ALTER TABLE paper_positions ADD COLUMN {column} {column_type}")
        account = conn.execute("SELECT id FROM paper_account WHERE id = 1").fetchone()
        if not account:
            now = time.time()
            conn.execute(
                """
                INSERT INTO paper_account (
                    id, starting_cash, cash, realized_pnl, created_at, updated_at
                )
                VALUES (1, ?, ?, 0, ?, ?)
                """,
                (STARTING_CASH, STARTING_CASH, now, now),
            )


def get_account():
    init_paper_db()
    with get_connection() as conn:
        account = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
        open_positions = conn.execute(
            "SELECT * FROM paper_positions WHERE status = 'open' ORDER BY opened_at"
        ).fetchall()
        closed_positions = conn.execute(
            """
            SELECT * FROM paper_positions
            WHERE status = 'closed'
            ORDER BY closed_at DESC, id DESC
            LIMIT 50
            """
        ).fetchall()
        all_closed = conn.execute(
            "SELECT realized_pnl, realized_return_pct FROM paper_positions WHERE status = 'closed'"
        ).fetchall()
        current_fee_pct, rolling_volume = wealthsimple_trading_fee_pct(conn)

    positions = [dict(row) for row in open_positions]
    closed = [dict(row) for row in closed_positions]
    estimated_sell_cost_pct = current_fee_pct + MARKET_SPREAD_SLIPPAGE_PCT
    open_value = sum(
        (pos.get("latest_price") or pos["entry_price"])
        * pos["quantity"]
        * (1 - (estimated_sell_cost_pct / 100))
        for pos in positions
    )
    unrealized_pnl = sum(
        (
            (pos.get("latest_price") or pos["entry_price"])
            * pos["quantity"]
            * (1 - (estimated_sell_cost_pct / 100))
            - pos["invested"]
        )
        for pos in positions
    )
    equity = account["cash"] + open_value
    total_return_pct = ((equity - account["starting_cash"]) / account["starting_cash"]) * 100
    closed_count = len(all_closed)
    wins = [row for row in all_closed if (row["realized_pnl"] or 0) > 0]
    losses = [row for row in all_closed if (row["realized_pnl"] or 0) <= 0]
    successful_trades = [
        row for row in all_closed
        if (row["realized_return_pct"] or 0) >= SUCCESS_RETURN_PCT
    ]
    avg_return = (
        sum(row["realized_return_pct"] or 0 for row in all_closed) / closed_count
        if closed_count else 0
    )
    best_return = max([row["realized_return_pct"] or 0 for row in all_closed], default=0)
    worst_return = min([row["realized_return_pct"] or 0 for row in all_closed], default=0)
    win_rate = (len(wins) / closed_count) * 100 if closed_count else 0

    with _lock:
        state = dict(_state)

    return {
        "account": dict(account),
        "positions": positions,
        "closed_positions": closed,
        "open_value": open_value,
        "unrealized_pnl": unrealized_pnl,
        "equity": equity,
        "total_return_pct": total_return_pct,
        "stats": {
            "closed_count": closed_count,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "successful_trades": len(successful_trades),
            "success_rate": (len(successful_trades) / closed_count) * 100 if closed_count else 0,
            "avg_return": avg_return,
            "best_return": best_return,
            "worst_return": worst_return,
        },
        "state": state,
        "rules": {
            "starting_cash": STARTING_CASH,
            "max_hold_minutes": int(MAX_HOLD_SECONDS / 60),
            "stale_exit_minutes": int(STALE_EXIT_SECONDS / 60),
            "fast_fail_minutes": int(FAST_FAIL_SECONDS / 60),
            "scan_interval_minutes": int(SCAN_INTERVAL_SECONDS / 60),
            "price_poll_seconds": PRICE_POLL_SECONDS,
            "max_open_positions": MAX_OPEN_POSITIONS,
            "min_desired_open_positions": MIN_DESIRED_OPEN_POSITIONS,
            "focused_universe": True,
            "broker": "Flat fee crypto venue",
            "wealthsimple_tier": WEALTHSIMPLE_CLIENT_TIER,
            "wealthsimple_trading_fee_pct": current_fee_pct,
            "market_spread_slippage_pct": MARKET_SPREAD_SLIPPAGE_PCT,
            "estimated_round_trip_cost_pct": (current_fee_pct + MARKET_SPREAD_SLIPPAGE_PCT) * 2,
            "rolling_30d_crypto_volume": rolling_volume,
            "max_position_usd": MAX_POSITION_USD,
            "min_position_usd": MIN_POSITION_USD,
            "cash_reserve_usd": CASH_RESERVE_USD,
            "max_account_drawdown_pct": MAX_ACCOUNT_DRAWDOWN_PCT,
            "buy_min_score": BUY_MIN_SCORE,
            "min_target_profit_pct": MIN_TARGET_PROFIT_PCT,
            "max_scalp_loss_pct": MAX_SCALP_LOSS_PCT,
            "success_return_pct": SUCCESS_RETURN_PCT,
            "quick_profit_exit_pct": QUICK_PROFIT_EXIT_PCT,
            "micro_profit_trail_pct": MICRO_PROFIT_TRAIL_PCT,
            "profit_capture_min_age_seconds": PROFIT_CAPTURE_MIN_AGE_SECONDS,
            "profit_lock_net_pct": PROFIT_LOCK_NET_PCT,
            "win_only_exit_mode": WIN_ONLY_EXIT_MODE,
            "entry_confirmation": "Fee-aware 1m trigger plus reclaimed 5m trend, volume, flow, spread, and BTC/ETH regime",
        },
    }


def update_state(**kwargs):
    with _lock:
        _state.update(kwargs)


def refresh_watchlist(items):
    now = time.time()
    existing = open_tickers()
    with _lock:
        for ticker in list(_watchlist):
            if ticker in existing or _watchlist[ticker]["expires_at"] <= now:
                _watchlist.pop(ticker, None)
        for item in items[:MAX_WATCHLIST_SIZE]:
            if item["ticker"] not in existing:
                _watchlist[item["ticker"]] = {
                    "item": item,
                    "expires_at": now + WATCHLIST_TTL_SECONDS,
                }
        _state["watching"] = len(_watchlist)


def evaluate_watchlist(regime=None, force=False):
    global _last_watch_check, _watch_cursor
    now = time.time()
    if not force and now - _last_watch_check < WATCHLIST_CHECK_SECONDS:
        return 0, {}
    _last_watch_check = now

    existing = open_tickers()
    with _lock:
        for ticker in list(_watchlist):
            if ticker in existing or _watchlist[ticker]["expires_at"] <= now:
                _watchlist.pop(ticker, None)
        tickers = list(_watchlist)
        if not tickers:
            _state["watching"] = 0
            return 0, {}
        start = _watch_cursor % len(tickers)
        ordered = tickers[start:] + tickers[:start]
        selected = ordered[:WATCHLIST_BATCH_SIZE]
        _watch_cursor = (start + len(selected)) % len(tickers)
        items = [_watchlist[ticker]["item"] for ticker in selected]

    opened = 0
    rejections = {}
    regime = regime or fetch_market_regime()
    for item in items:
        if open_position_count() >= min(MAX_OPEN_POSITIONS, MIN_DESIRED_OPEN_POSITIONS):
            break
        result = buy_candidate(item, regime=regime)
        if result is True:
            opened += 1
            with _lock:
                _watchlist.pop(item["ticker"], None)
        else:
            key = result or "buy rejected"
            rejections[key] = rejections.get(key, 0) + 1

    with _lock:
        _state["watching"] = len(_watchlist)
    return opened, rejections


def wealthsimple_volume_fee_pct(volume):
    for threshold, fee_pct in WEALTHSIMPLE_VOLUME_FEES:
        if volume >= threshold:
            return fee_pct
    return WEALTHSIMPLE_VOLUME_FEES[-1][1]


def wealthsimple_trading_fee_pct(conn, now=None):
    now = now or time.time()
    cutoff = now - (30 * 24 * 60 * 60)
    opened = conn.execute(
        """
        SELECT COALESCE(SUM(invested), 0) AS volume
        FROM paper_positions
        WHERE opened_at >= ?
        """,
        (cutoff,),
    ).fetchone()
    closed = conn.execute(
        """
        SELECT COALESCE(SUM(COALESCE(latest_price, entry_price) * quantity), 0) AS volume
        FROM paper_positions
        WHERE status = 'closed' AND closed_at >= ?
        """,
        (cutoff,),
    ).fetchone()
    volume = (opened["volume"] or 0) + (closed["volume"] or 0)
    baseline_fee = WEALTHSIMPLE_BASELINE_FEES.get(WEALTHSIMPLE_CLIENT_TIER, 2.0)
    volume_fee = wealthsimple_volume_fee_pct(volume)
    return min(baseline_fee, volume_fee), volume


def total_trade_cost_pct(conn, now=None):
    fee_pct, volume = wealthsimple_trading_fee_pct(conn, now=now)
    return fee_pct + MARKET_SPREAD_SLIPPAGE_PCT, fee_pct, volume


def open_position_count():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM paper_positions WHERE status = 'open'"
        ).fetchone()
    return row["count"]


def open_tickers():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ticker FROM paper_positions WHERE status = 'open'"
        ).fetchall()
    return {row["ticker"] for row in rows}


def recent_loss_count(conn, ticker=None, lookback_seconds=COOLDOWN_AFTER_LOSS_SECONDS):
    cutoff = time.time() - lookback_seconds
    if ticker:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count FROM paper_positions
            WHERE ticker = ? AND status = 'closed'
              AND closed_at >= ? AND COALESCE(realized_pnl, 0) <= 0
            """,
            (ticker, cutoff),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count FROM paper_positions
            WHERE status = 'closed'
              AND closed_at >= ? AND COALESCE(realized_pnl, 0) <= 0
            """,
            (cutoff,),
        ).fetchone()
    return row["count"] if row else 0


def ticker_loss_count(conn, ticker, lookback_seconds=24 * 60 * 60):
    return recent_loss_count(conn, ticker=ticker, lookback_seconds=lookback_seconds)


def recent_exit_count(conn, ticker, lookback_seconds=COOLDOWN_AFTER_EXIT_SECONDS):
    cutoff = time.time() - lookback_seconds
    row = conn.execute(
        """
        SELECT COUNT(*) AS count FROM paper_positions
        WHERE ticker = ? AND status = 'closed' AND closed_at >= ?
        """,
        (ticker, cutoff),
    ).fetchone()
    return row["count"] if row else 0


def adaptive_entry_penalty(conn, sample_size=8):
    rows = conn.execute(
        """
        SELECT realized_return_pct FROM paper_positions
        WHERE status = 'closed'
        ORDER BY closed_at DESC, id DESC
        LIMIT ?
        """,
        (sample_size,),
    ).fetchall()
    clustered_losses = recent_loss_count(conn, lookback_seconds=30 * 60)
    if len(rows) < 5:
        return 12 if clustered_losses >= 3 else 0
    returns = [row["realized_return_pct"] or 0 for row in rows]
    average_return = sum(returns) / len(returns)
    loss_count = sum(1 for value in returns if value <= 0)
    if average_return <= -0.30 or loss_count >= 5:
        return 16
    if average_return < 0 or loss_count >= 4:
        return 8
    return 12 if clustered_losses >= 3 else 0


def liquidation_equity(conn):
    account = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
    positions = conn.execute(
        """
        SELECT invested, latest_price, entry_price, quantity
        FROM paper_positions WHERE status = 'open'
        """
    ).fetchall()
    sell_cost_pct, _, _ = total_trade_cost_pct(conn)
    open_value = sum(
        (row["latest_price"] or row["entry_price"])
        * row["quantity"]
        * (1 - (sell_cost_pct / 100))
        for row in positions
    )
    return account["cash"] + open_value


def entry_structure(confirmation, behavior, flow, huge_breakout_confirmed=False):
    price = confirmation.get("price")
    ema9 = confirmation.get("ema9")
    ema21 = confirmation.get("ema21")
    five_min_trend = bool(price and ema9 and ema21 and price >= ema9 and ema9 >= ema21)
    ret_5m = behavior.get("return_5m_pct") or 0
    ret_15m = behavior.get("return_15m_pct") or 0
    active_volume = max(
        behavior.get("volume_ratio_5m") or 0,
        confirmation.get("volume_ratio") or 0,
    )
    taker_buy_ratio = flow.get("taker_buy_ratio")
    book_imbalance = flow.get("book_imbalance")
    buyer_confirmed = taker_buy_ratio is not None and taker_buy_ratio >= 0.52
    book_confirmed = book_imbalance is not None and book_imbalance >= 0.75

    trend_continuation = (
        five_min_trend
        and behavior.get("approved")
        and behavior.get("trend_up")
        and behavior.get("entry_trigger")
        and -0.20 <= ret_5m <= 0.90
        and -0.15 <= ret_15m <= 2.50
        and (behavior.get("volume_ratio_5m") or 0) >= 0.75
        and (confirmation.get("volume_ratio") or 0) >= 0.75
        and buyer_confirmed
        and book_confirmed
    )

    if huge_breakout_confirmed:
        return True, "confirmed_breakout", "huge breakout confirmation"
    if trend_continuation:
        return True, "trend_continuation", "1m trigger aligned with reclaimed 5m trend"
    missing = []
    if not five_min_trend:
        missing.append("5m trend not reclaimed")
    if not behavior.get("trend_up") and not behavior.get("pullback_reclaim"):
        missing.append("1m trend not aligned")
    if active_volume < 0.75:
        missing.append(f"volume only {active_volume:.2f}x")
    if not behavior.get("approved"):
        missing.append("1m behavior not approved")
    if (confirmation.get("volume_ratio") or 0) < 0.75:
        missing.append("5m volume below 0.75x")
    if behavior.get("pullback_reclaim") and not behavior.get("trend_up"):
        missing.append("early pullback entries disabled")
    if not buyer_confirmed:
        missing.append("buyer flow below 52%")
    if not book_confirmed:
        missing.append("bid book not supportive")
    return False, "unconfirmed", "; ".join(missing) or "entry structure incomplete"


def adaptive_buy_min_score(conn):
    losses = recent_loss_count(conn, lookback_seconds=30 * 60)
    if losses < 3:
        return FILL_BUY_MIN_SCORE
    return BUY_MIN_SCORE + min(14, (losses - 2) * 4)


def rejection_reason(item, fill_mode=False):
    score = item.get("quick_win_score", 0)
    target_profit = item.get("target_profit_pct") or 0
    reward_risk = item.get("reward_risk") or 0
    min_score = FILL_BUY_MIN_SCORE if fill_mode else BUY_MIN_SCORE
    max_sell_score = FILL_MAX_SELL_SCORE if fill_mode else MAX_BUY_SELL_SCORE
    min_reward_risk = FILL_MIN_REWARD_RISK if fill_mode else MIN_REWARD_RISK
    min_24h_range = FILL_MIN_24H_RANGE_PCT if fill_mode else MIN_24H_RANGE_PCT
    max_rsi = FILL_MAX_RSI if fill_mode else MAX_RSI
    min_hourly_liquidity = FILL_MIN_HOURLY_LIQUIDITY_USD if fill_mode else 25_000

    if score < min_score:
        return "buy score too low"
    if fill_mode and score < BUY_MIN_SCORE:
        return "fill score too low"
    if item.get("long_term_score", 0) > max_sell_score:
        return "sell risk too high"
    if target_profit < MIN_TARGET_PROFIT_PCT:
        return "target too small"
    if reward_risk < min_reward_risk:
        return "reward/risk too low"
    if (item.get("range_24h_pct") or 0) < min_24h_range:
        return "24h range too small"
    if item.get("rsi") is not None and item["rsi"] > max_rsi:
        return "RSI too hot"
    if (item.get("dollar_volume") or 0) < min_hourly_liquidity:
        return "hourly liquidity too thin"
    if item.get("price_change", 0) < (-0.8 if fill_mode else -1.5):
        return "hourly price falling"
    if not fill_mode and item.get("price_change", 0) < MIN_ENTRY_PRICE_CHANGE_1H:
        return "no live hourly lift"
    if not fill_mode and (item.get("relative_volume") or 0) < MIN_ENTRY_RELATIVE_VOLUME:
        return "volume not active enough"

    flow = item.get("market_flow") or {}
    if flow.get("source") == "Binance public market data":
        taker_buy_ratio = flow.get("taker_buy_ratio")
        book_imbalance = flow.get("book_imbalance")
        spread_pct = flow.get("spread_pct")
        futures_taker_ratio = flow.get("futures_taker_buy_sell_ratio")
        top_trader_ratio = flow.get("top_trader_position_ratio")
        min_taker_buy_ratio = 0.52 if fill_mode else MIN_TAKER_BUY_RATIO
        min_book_imbalance = 0.60 if fill_mode else MIN_BOOK_IMBALANCE
        min_futures_taker_ratio = 0.95 if fill_mode else 0.95
        if taker_buy_ratio is not None and taker_buy_ratio < min_taker_buy_ratio:
            return "seller flow too strong"
        if book_imbalance is not None and book_imbalance < min_book_imbalance:
            return "order book weak"
        if futures_taker_ratio is not None and futures_taker_ratio < min_futures_taker_ratio:
            return "futures taker sellers lead"
        if top_trader_ratio is not None and top_trader_ratio > 2.8:
            return "top traders crowded long"
        if spread_pct is not None and spread_pct > 0.35:
            return "spread too wide"

    if not fill_mode:
        fast_enough = (
            item.get("price_change", 0) >= 1.0
            or (item.get("price_change_5d", 0) >= 3.0 and item.get("relative_volume", 0) >= 1.2)
            or item.get("relative_volume", 0) >= 1.8
            or "1-4h" in str(item.get("target_window") or "")
            or (target_profit >= 20 and item.get("relative_volume", 0) >= 1.5)
        )
        if not fast_enough:
            return "not fast enough"

    return None


def is_buy_candidate(item):
    return rejection_reason(item) is None


def pre_entry_rejection_reason(item):
    if (item.get("dollar_volume") or 0) < FILL_MIN_HOURLY_LIQUIDITY_USD:
        return "hourly liquidity too thin"
    if item.get("long_term_score", 0) > 75:
        return "sell risk too high"
    if (item.get("target_profit_pct") or 0) < MIN_TARGET_PROFIT_PCT:
        return "target too small"
    if item.get("rsi") is not None and item["rsi"] > EXTREME_RSI:
        return "RSI extreme"

    flow = item.get("market_flow") or {}
    if flow.get("source") == "Binance public market data":
        taker_buy_ratio = flow.get("taker_buy_ratio")
        book_imbalance = flow.get("book_imbalance")
        spread_pct = flow.get("spread_pct")
        if book_imbalance is not None and book_imbalance < 0.45:
            return "order book very weak"
        if spread_pct is not None and spread_pct > 0.45:
            return "spread too wide"

    return None


def position_size(cash, item):
    spendable_cash = max(cash - CASH_RESERVE_USD, 0)
    if spendable_cash < MIN_POSITION_USD:
        return 0
    return min(MAX_POSITION_USD, spendable_cash)


def entry_decision(item, confirmation, behavior, regime):
    score = int(item.get("quick_win_score") or 0)
    reasons = [f"base {score}"]
    ret_15m = confirmation.get("return_15m_pct")
    ret_30m = confirmation.get("return_30m_pct")
    volume_ratio = confirmation.get("volume_ratio")
    range_1h = confirmation.get("range_1h_pct")
    ema9 = confirmation.get("ema9")
    ema21 = confirmation.get("ema21")
    price = confirmation.get("price")

    if regime and not regime.get("tradable"):
        score -= 15
        reasons.append(f"weak market: {regime.get('reason', 'unknown')}")

    if confirmation.get("confirmed"):
        score += 18
        reasons.append("5m confirmed")

    if price and ema9 and ema21:
        if price > ema9 and ema9 >= ema21:
            score += 12
            reasons.append("5m trend reclaimed")
        elif price > ema9:
            score += 5
            reasons.append("price above 5m EMA")
        else:
            score -= 10
            reasons.append("below 5m EMA")

    if ret_15m is not None:
        if 0.20 <= ret_15m <= 3.0:
            score += 10
            reasons.append(f"15m lift {ret_15m:.2f}%")
        elif -0.15 <= ret_15m < 0.20:
            score += 2
            reasons.append("15m stabilizing")
        elif ret_15m < -0.45:
            score -= 14
            reasons.append(f"15m fading {ret_15m:.2f}%")
        elif ret_15m > 4.5:
            score -= 10
            reasons.append("15m chase risk")

    if ret_30m is not None:
        if 0.35 <= ret_30m <= 5.0:
            score += 8
            reasons.append(f"30m lift {ret_30m:.2f}%")
        elif ret_30m < -0.90:
            score -= 16
            reasons.append(f"30m weak {ret_30m:.2f}%")

    if volume_ratio is not None:
        if volume_ratio >= 1.25:
            score += 10
            reasons.append(f"5m volume {volume_ratio:.2f}x")
        elif volume_ratio >= 0.65:
            score += 3
            reasons.append(f"5m volume ok {volume_ratio:.2f}x")
        elif volume_ratio < 0.45:
            score -= 10
            reasons.append(f"5m volume thin {volume_ratio:.2f}x")

    if range_1h is not None and range_1h > 9:
        score -= 8
        reasons.append("1h too stretched")

    behavior_score = behavior.get("score")
    behavior_volume_ratio = behavior.get("volume_ratio_5m") or 0
    strong_chart_behavior = (
        (behavior_score or 0) >= STRONG_BEHAVIOR_SCORE
        and behavior_volume_ratio >= STRONG_BEHAVIOR_VOLUME_RATIO
    ) or bool(behavior.get("controlled_pullback"))
    elite_chart_behavior = (
        (behavior_score or 0) >= ELITE_BEHAVIOR_SCORE
        and behavior_volume_ratio >= ELITE_BEHAVIOR_VOLUME_RATIO
        and item.get("rsi", 0) <= MAX_RSI
    )
    if behavior.get("approved"):
        score += min(24, max(6, int((behavior_score or 0) / 3)))
        reasons.append(f"1m behavior ok {behavior_score}: {behavior.get('reason')}")
    else:
        score -= 8
        reasons.append(f"1m behavior rejected {behavior_score}: {behavior.get('reason')}")

    flow = item.get("market_flow") or {}
    taker_buy_ratio = flow.get("taker_buy_ratio")
    spread_pct = flow.get("spread_pct")
    if taker_buy_ratio is not None:
        if taker_buy_ratio >= 0.58:
            score += 7
            reasons.append(f"buyers {taker_buy_ratio * 100:.0f}%")
        elif taker_buy_ratio < 0.46:
            score -= 10
            reasons.append(f"sellers {(1 - taker_buy_ratio) * 100:.0f}%")
    if spread_pct is not None:
        if spread_pct <= 0.08:
            score += 4
            reasons.append("tight spread")
        elif spread_pct > 0.30:
            score -= 12
            reasons.append(f"wide spread {spread_pct:.2f}%")

    hard_reject = False
    if (behavior_score or 0) < MIN_BEHAVIOR_SCORE:
        score -= 8
        reasons.append("penalty: weak 1m behavior score")
    if (
        behavior_volume_ratio < MIN_BEHAVIOR_VOLUME_RATIO
        and (behavior_score or 0) < 75
    ):
        score -= 6
        reasons.append("penalty: 1m volume fading with weak behavior")
    if (
        behavior_volume_ratio < LOW_VOLUME_RATIO
        and (behavior_score or 0) < LOW_VOLUME_MIN_BEHAVIOR_SCORE
    ):
        score -= 6
        reasons.append("penalty: low 1m volume without strong behavior")
    if (
        (behavior.get("pullback_from_high_15m_pct") or 0) > MAX_BEHAVIOR_PULLBACK_15M_PCT
        and (behavior.get("red_count_5m") or 0) >= 3
    ):
        hard_reject = True
        reasons.append("hard reject: spike rejection with red candles")
    if item.get("rsi") is not None and item["rsi"] > EXTREME_RSI:
        hard_reject = True
        reasons.append(f"hard reject: RSI extreme {item['rsi']:.0f}")
    elif (
        item.get("rsi") is not None
        and item["rsi"] > MAX_RSI
        and (behavior_score or 0) < 75
    ):
        score -= 8
        reasons.append(f"penalty: RSI hot without strong 1m behavior {item['rsi']:.0f}")
    if taker_buy_ratio is not None and taker_buy_ratio < HARD_MIN_TAKER_BUY_RATIO:
        hard_reject = True
        reasons.append(f"hard reject: buyer flow very weak {taker_buy_ratio * 100:.0f}%")
    elif taker_buy_ratio is not None and taker_buy_ratio < MIN_TAKER_BUY_RATIO:
        score -= 5
        reasons.append(f"penalty: buyer flow below winner profile {taker_buy_ratio * 100:.0f}%")
    if ret_30m is not None and ret_30m <= HARD_REJECT_30M_DROP_PCT:
        hard_reject = True
        reasons.append("hard reject: 30m dump")
    if volume_ratio is not None and volume_ratio <= HARD_REJECT_VOLUME_RATIO and not strong_chart_behavior:
        score -= 8
        reasons.append("penalty: no short-term volume")

    threshold = WEAK_MARKET_ENTRY_MIN_SCORE if regime and not regime.get("tradable") else ENTRY_DECISION_MIN_SCORE
    approved = score >= threshold and not hard_reject
    return {
        "approved": approved,
        "score": score,
        "threshold": threshold,
        "hard_reject": hard_reject,
        "reason": "; ".join(reasons),
    }


def buy_candidate(item, regime=None):
    regime = regime or fetch_market_regime()
    confirmation = fetch_short_term_confirmation(item["ticker"])
    behavior = fetch_one_minute_behavior(item["ticker"])
    decision = entry_decision(item, confirmation, behavior, regime)
    if not decision["approved"]:
        if decision.get("hard_reject"):
            return f"entry hard reject {decision['score']}/{decision['threshold']}: {decision['reason']}"
        return f"entry score {decision['score']}<{decision['threshold']}: {decision['reason']}"

    quote = fetch_latest_price(item["ticker"])
    if not quote:
        return "no live quote"

    market_entry_price = quote["price"]
    if not market_entry_price or market_entry_price <= 0:
        return "bad live quote"

    public_signal = evaluate_public_signal(item["ticker"], market_entry_price, behavior, confirmation)
    flow = public_signal.get("flow") or item.get("market_flow") or {}
    taker_buy_ratio = flow.get("taker_buy_ratio")
    book_imbalance = flow.get("book_imbalance")
    futures_taker_ratio = flow.get("futures_taker_buy_sell_ratio")
    close_position_30m = behavior.get("close_position_30m") or 0
    huge_breakout_confirmed = (
        close_position_30m >= BREAKOUT_ENTRY_30M_POSITION
        and behavior.get("entry_trigger")
        and (behavior.get("return_1m_pct") or 0) >= BREAKOUT_ENTRY_MIN_1M_RETURN
        and (behavior.get("return_5m_pct") or 0) <= BREAKOUT_ENTRY_MAX_5M_RETURN
        and (behavior.get("volume_ratio_5m") or 0) >= NEAR_HIGH_MIN_VOLUME_RATIO
        and taker_buy_ratio is not None
        and taker_buy_ratio >= NEAR_HIGH_BUYER_FLOW_PCT
        and book_imbalance is not None
        and book_imbalance >= NEAR_HIGH_MIN_BOOK_IMBALANCE
        and (
            futures_taker_ratio is None
            or futures_taker_ratio >= NEAR_HIGH_MIN_FUTURES_TAKER_RATIO
        )
    )
    if not behavior.get("entry_trigger"):
        return "watching: no fresh 1m entry trigger"
    if (behavior.get("return_5m_pct") or 0) >= CHASE_5M_RETURN_PCT:
        return "avoid chasing 5m spike"
    if (
        close_position_30m > MAX_ENTRY_30M_POSITION
        and not huge_breakout_confirmed
    ):
        return "near top without huge breakout confirmation"
    if (
        close_position_30m >= 0.82
        and (
            taker_buy_ratio is None
            or taker_buy_ratio < NEAR_HIGH_BUYER_FLOW_PCT
            or (behavior.get("volume_ratio_5m") or 0) < NEAR_HIGH_MIN_VOLUME_RATIO
        )
    ):
        return "near 30m high without enough buyer pressure"

    if not public_signal["approved"]:
        if public_signal["hard_rejects"]:
            return f"public data reject {public_signal['score']}/{public_signal['threshold']}: {public_signal['summary']}"
        return f"public data score {public_signal['score']}<{public_signal['threshold']}: {public_signal['summary']}"

    structure_approved, entry_pattern, structure_reason = entry_structure(
        confirmation,
        behavior,
        flow,
        huge_breakout_confirmed=huge_breakout_confirmed,
    )
    if not structure_approved:
        return f"watching: structure incomplete - {structure_reason}"

    with get_connection() as conn:
        now = time.time()
        buy_cost_pct, _, _ = total_trade_cost_pct(conn, now=now)
        entry_price = market_entry_price * (1 + (buy_cost_pct / 100))
        sell_cost_pct, _, _ = total_trade_cost_pct(conn, now=now)
        live_range_30m = behavior.get("range_30m_pct") or 0
        live_target_profit_pct = min(
            2.50,
            max(MIN_TARGET_PROFIT_PCT, live_range_30m * 0.55),
        )
        live_target_price = (
            entry_price * (1 + (live_target_profit_pct / 100))
        ) / (1 - (sell_cost_pct / 100))
        live_reward_risk = live_target_profit_pct / MAX_SCALP_LOSS_PCT
        live_stop_price = (
            entry_price * (1 - (MAX_SCALP_LOSS_PCT / 100))
        ) / (1 - (sell_cost_pct / 100))
        initial_net_return_pct = (
            (market_entry_price * (1 - (sell_cost_pct / 100)) / entry_price) - 1
        ) * 100

        if recent_exit_count(conn, item["ticker"]):
            return "ticker exit cooldown"
        if recent_loss_count(conn, ticker=item["ticker"]):
            return "ticker loss cooldown"
        if ticker_loss_count(conn, item["ticker"]) >= 2:
            return "ticker failed twice in 24h"
        entry_penalty = adaptive_entry_penalty(conn)
        if decision["score"] < ENTRY_DECISION_MIN_SCORE + entry_penalty:
            return f"adaptive quality gate {decision['score']}<{ENTRY_DECISION_MIN_SCORE + entry_penalty}"
        if public_signal["score"] < public_signal["threshold"] + (entry_penalty // 2):
            return f"adaptive public gate {public_signal['score']}<{public_signal['threshold'] + (entry_penalty // 2)}"
        account = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
        account_return_pct = (
            (liquidation_equity(conn) - account["starting_cash"])
            / account["starting_cash"]
        ) * 100
        if account_return_pct <= -MAX_ACCOUNT_DRAWDOWN_PCT:
            return f"account drawdown guard {account_return_pct:.2f}%"
        amount = position_size(account["cash"], item)
        if amount <= 0:
            return "position too small"

        quantity = amount / entry_price
        conn.execute(
            """
            INSERT INTO paper_positions (
                ticker, status, opened_at, entry_price, quantity, invested,
                latest_price, highest_price, target_price, stop_price,
                trailing_stop, buy_score, sell_score, target_profit_pct,
                target_window, reward_risk, open_reason, entry_pattern,
                entry_decision_score, public_signal_score, behavior_score,
                max_net_return_pct
            )
            VALUES (?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["ticker"],
                now,
                entry_price,
                quantity,
                amount,
                market_entry_price,
                market_entry_price,
                live_target_price,
                live_stop_price,
                item.get("quick_win_score"),
                item.get("long_term_score"),
                live_target_profit_pct,
                "Live 5-30m adaptive target",
                live_reward_risk,
                (
                    (item.get("trade_note") or item.get("headline") or "Paper buy signal")
                    + f" Entry decision {decision['score']}/{decision['threshold']}: {decision['reason']}."
                    + f" 1m chart memory: {behavior.get('reason')}."
                    + f" Public data signal {public_signal['score']}/{public_signal['threshold']}: {public_signal['summary']}."
                    + f" Entry pattern {entry_pattern}: {structure_reason}."
                ),
                entry_pattern,
                decision["score"],
                public_signal["score"],
                behavior.get("score"),
                initial_net_return_pct,
            ),
        )
        conn.execute(
            "UPDATE paper_account SET cash = cash - ?, updated_at = ? WHERE id = 1",
            (amount, now),
        )
    return True


def close_position(conn, position, price, reason):
    sell_cost_pct, _, _ = total_trade_cost_pct(conn)
    exit_price = price * (1 - (sell_cost_pct / 100))
    proceeds = exit_price * position["quantity"]
    pnl = proceeds - position["invested"]
    return_pct = (pnl / position["invested"]) * 100 if position["invested"] else 0
    max_net_return_pct = max(
        position.get("max_net_return_pct") or -100,
        return_pct,
    )
    now = time.time()
    conn.execute(
        """
        UPDATE paper_positions
        SET status = 'closed', closed_at = ?, latest_price = ?, close_reason = ?,
            realized_pnl = ?, realized_return_pct = ?, max_net_return_pct = ?
        WHERE id = ?
        """,
        (
            now,
            exit_price,
            reason,
            pnl,
            return_pct,
            max_net_return_pct,
            position["id"],
        ),
    )
    conn.execute(
        """
        UPDATE paper_account
        SET cash = cash + ?, realized_pnl = realized_pnl + ?, updated_at = ?
        WHERE id = 1
        """,
        (proceeds, pnl, now),
    )


def estimated_net_return_pct(conn, position, price):
    sell_cost_pct, _, _ = total_trade_cost_pct(conn)
    estimated_exit_price = price * (1 - (sell_cost_pct / 100))
    return ((estimated_exit_price - position["entry_price"]) / position["entry_price"]) * 100


def success_protect_price(conn, position):
    sell_cost_pct, _, _ = total_trade_cost_pct(conn)
    return (position["entry_price"] * (1 + (SUCCESS_RETURN_PCT / 100))) / (1 - (sell_cost_pct / 100))


def protect_price_for_net_return(conn, position, net_return_pct):
    sell_cost_pct, _, _ = total_trade_cost_pct(conn)
    return (position["entry_price"] * (1 + (net_return_pct / 100))) / (1 - (sell_cost_pct / 100))


def update_positions():
    init_paper_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_positions WHERE status = 'open' ORDER BY opened_at"
        ).fetchall()

        for row in rows:
            position = dict(row)
            quote = fetch_latest_price(position["ticker"])
            if not quote or quote["price"] <= 0:
                continue

            price = quote["price"]
            highest_price = max(position.get("highest_price") or position["entry_price"], price)
            net_return_pct = estimated_net_return_pct(conn, position, price)
            highest_net_return_pct = max(
                position.get("max_net_return_pct") or -100,
                estimated_net_return_pct(conn, position, highest_price),
            )
            age_seconds = time.time() - position["opened_at"]
            trailing_stop = position.get("trailing_stop")
            target_profit_pct = position.get("target_profit_pct") or MIN_TARGET_PROFIT_PCT
            success_stop = success_protect_price(conn, position)
            profit_lock_stop = protect_price_for_net_return(conn, position, PROFIT_LOCK_NET_PCT)
            breakeven_stop = protect_price_for_net_return(conn, position, BREAKEVEN_TRAIL_BUFFER_PCT)

            effective_stop = position.get("stop_price") or protect_price_for_net_return(
                conn, position, -MAX_SCALP_LOSS_PCT
            )

            if net_return_pct >= 4:
                trailing_stop = max(
                    trailing_stop or 0,
                    protect_price_for_net_return(conn, position, 2.0),
                    highest_price * 0.985,
                )
            elif net_return_pct >= 2.0:
                trailing_stop = max(trailing_stop or 0, protect_price_for_net_return(conn, position, 1.0), highest_price * 0.993)
            elif net_return_pct >= target_profit_pct:
                trailing_stop = max(trailing_stop or 0, success_stop, highest_price * 0.996)
            elif net_return_pct >= 1.0:
                trailing_stop = max(trailing_stop or 0, protect_price_for_net_return(conn, position, 0.45), highest_price * 0.996)
            elif net_return_pct >= QUICK_PROFIT_EXIT_PCT:
                trailing_stop = max(trailing_stop or 0, profit_lock_stop, highest_price * 0.996)
            elif highest_net_return_pct >= QUICK_PROFIT_EXIT_PCT:
                trailing_stop = max(trailing_stop or 0, protect_price_for_net_return(conn, position, 0.15))
            elif net_return_pct >= MICRO_PROFIT_TRAIL_PCT:
                trailing_stop = max(trailing_stop or 0, breakeven_stop, highest_price * 0.995)
            elif highest_net_return_pct >= MICRO_PROFIT_TRAIL_PCT:
                trailing_stop = max(trailing_stop or 0, breakeven_stop)

            cache = _position_behavior_cache.get(position["id"])
            if not cache or time.time() - cache["checked_at"] >= POSITION_BEHAVIOR_SECONDS:
                behavior = fetch_one_minute_behavior(position["ticker"])
                cache = {"checked_at": time.time(), "behavior": behavior}
                _position_behavior_cache[position["id"]] = cache
            behavior = cache["behavior"]
            momentum_fading = (
                (behavior.get("return_1m_pct") or 0) <= -0.08
                or (
                    not behavior.get("last_candle_green")
                    and (behavior.get("return_2m_pct") or 0) < -0.05
                    and not behavior.get("trend_up")
                )
            )
            setup_invalidated = (
                not behavior.get("trend_up")
                and (behavior.get("return_5m_pct") or 0) <= -0.25
                and (behavior.get("return_15m_pct") or 0) <= 0
            )

            reason = None
            if (
                age_seconds >= PROFIT_CAPTURE_MIN_AGE_SECONDS
                and highest_net_return_pct >= MOMENTUM_EXIT_MIN_PEAK_NET_PCT
                and net_return_pct >= MOMENTUM_EXIT_MIN_NET_PCT
                and momentum_fading
            ):
                reason = "Momentum rollover profit"
            elif trailing_stop and price <= trailing_stop:
                reason = "Profit protection trail" if highest_net_return_pct >= MICRO_PROFIT_TRAIL_PCT else "Trailing stop"
            elif price <= effective_stop:
                reason = "Scalp risk stop"
            elif (
                age_seconds >= 3 * 60
                and net_return_pct <= SETUP_INVALIDATION_NET_PCT
                and setup_invalidated
            ):
                reason = "Setup invalidation exit"
            elif age_seconds >= FAST_FAIL_SECONDS and net_return_pct <= FAST_FAILURE_NET_PCT:
                reason = "Fast failure exit"
            elif age_seconds >= STALE_EXIT_SECONDS and net_return_pct <= -0.25:
                reason = "Stale trade exit"
            elif age_seconds >= MAX_HOLD_SECONDS:
                reason = "Max hold safety exit"

            if reason:
                close_position(conn, position, price, reason)
                _position_behavior_cache.pop(position["id"], None)
            else:
                conn.execute(
                    """
                    UPDATE paper_positions
                    SET latest_price = ?, highest_price = ?, trailing_stop = ?,
                        max_net_return_pct = ?
                    WHERE id = ?
                    """,
                    (
                        price,
                        highest_price,
                        trailing_stop,
                        highest_net_return_pct,
                        position["id"],
                    ),
                )

    update_state(last_tick_at=time.time())


def scan_for_entries(scan_limit):
    update_state(status="Scanning for paper entries", last_scan_at=time.time())
    results = scan_market(limit=scan_limit, should_stop=_stop_event.is_set, focused=True)
    if _stop_event.is_set():
        update_state(status="Stopping")
        return
    existing = open_tickers()
    opened = 0
    rejections = {}
    buy_skips = {}
    starting_open_count = open_position_count()
    regime = fetch_market_regime()
    update_state(market_regime=regime)

    decision_pool = []
    for item in results:
        if item["ticker"] in existing:
            continue
        rejection = pre_entry_rejection_reason(item)
        if rejection:
            rejections[rejection] = rejections.get(rejection, 0) + 1
            continue
        if (item.get("dollar_volume") or 0) < FILL_MIN_HOURLY_LIQUIDITY_USD:
            rejections["hourly liquidity too thin"] = rejections.get("hourly liquidity too thin", 0) + 1
            continue
        if item.get("long_term_score", 0) > 75:
            rejections["sell risk too high"] = rejections.get("sell risk too high", 0) + 1
            continue
        if (item.get("target_profit_pct") or 0) < MIN_TARGET_PROFIT_PCT:
            rejections["target too small"] = rejections.get("target too small", 0) + 1
            continue
        decision_pool.append(item)

    ranked = sorted(
        decision_pool,
        key=lambda item: (
            item.get("quick_win_score", 0),
            item.get("target_profit_pct") or 0,
            item.get("reward_risk") or 0,
            item.get("relative_volume") or 0,
        ),
        reverse=True,
    )

    refresh_watchlist(ranked)
    opened, buy_skips = evaluate_watchlist(regime=regime, force=True)

    now = time.time()
    update_state(
        status=f"Scan complete, opened {opened} positions",
        last_scan_at=now,
        next_scan_at=now + SCAN_INTERVAL_SECONDS,
        last_candidates=len(results),
        last_eligible=len(decision_pool),
        last_live_opened=opened,
        last_live_rejected=sum(buy_skips.values()),
        last_rejections={**rejections, **{f"buy skip: {key}": value for key, value in buy_skips.items()}},
    )


def trading_loop(scan_limit):
    update_state(
        running=True,
        scan_limit=scan_limit,
        status="Paper trader started",
        error="",
        next_scan_at=time.time(),
    )
    next_scan = time.time()

    while not _stop_event.is_set():
        try:
            update_positions()
            opened, watch_rejections = evaluate_watchlist()
            if opened:
                update_state(
                    status=f"Live trigger opened {opened} position(s)",
                    last_live_opened=opened,
                    last_live_rejected=sum(watch_rejections.values()),
                    last_rejections={f"live watch: {key}": value for key, value in watch_rejections.items()},
                )
            if time.time() >= next_scan:
                scan_for_entries(scan_limit)
                next_scan = time.time() + SCAN_INTERVAL_SECONDS
        except Exception as error:
            update_state(error=str(error), status="Error")
        _stop_event.wait(PRICE_POLL_SECONDS)

    update_state(running=False, status="Stopped", next_scan_at=None)


def start_paper_trader(scan_limit=DEFAULT_SCAN_LIMIT):
    global _worker
    init_paper_db()
    with _lock:
        if _state["running"] or (_worker and _worker.is_alive()):
            return False
        _stop_event.clear()
        _worker = threading.Thread(target=trading_loop, args=(scan_limit,), daemon=True)
        _worker.start()
        return True


def stop_paper_trader():
    _stop_event.set()
    return True


def reset_paper_trader():
    global _watch_cursor, _last_watch_check
    stop_paper_trader()
    worker = _worker
    if worker and worker.is_alive():
        worker.join(timeout=20)
    if worker and worker.is_alive():
        update_state(status="Stopping before reset", error="Paper worker did not stop within 20 seconds")
        return False
    init_paper_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM paper_positions")
        now = time.time()
        conn.execute(
            """
            UPDATE paper_account
            SET cash = ?, realized_pnl = 0, updated_at = ?
            WHERE id = 1
            """,
            (STARTING_CASH, now),
        )
    with _lock:
        _watchlist.clear()
        _position_behavior_cache.clear()
        _watch_cursor = 0
        _last_watch_check = 0
        _state.update(
            running=False,
            last_scan_at=None,
            last_tick_at=None,
            next_scan_at=None,
            status="Reset",
            error="",
            last_candidates=0,
            last_eligible=0,
            last_live_opened=0,
            last_live_rejected=0,
            last_rejections={},
            watching=0,
        )
    return True
