from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

import requests
from requests.adapters import HTTPAdapter

from storage import get_connection, init_db

BINANCE_BASE = "https://api.binance.com"
REQUEST_TIMEOUT = 2
SCAN_WORKERS = 8
STARTING_CASH = 5000.0
WATCHLIST = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "SUIUSDT",
    "PEPEUSDT",
    "WLDUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "TRXUSDT",
    "DOTUSDT",
    "NEARUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "INJUSDT",
    "SEIUSDT",
    "HBARUSDT",
    "FETUSDT",
]
MAX_OPEN_POSITIONS = 6
POSITION_USD = 500.0
CASH_RESERVE_USD = 250.0
POLL_SECONDS = 1
MIN_HOLD_SECONDS = 45
MAX_HOLD_SECONDS = 8 * 60
FEE_PCT = 0.20
SLIPPAGE_PCT = 0.03
ROUND_SIDE_COST_PCT = FEE_PCT + SLIPPAGE_PCT
PROFIT_GATE_NET_PCT = 3.00
TARGET_NET_PCT = PROFIT_GATE_NET_PCT
STOP_GROSS_PCT = -0.28
PANIC_GROSS_PCT = -0.55
TRAIL_AFTER_NET_PCT = PROFIT_GATE_NET_PCT
TRAIL_GIVEBACK_PCT = 0.80
LOSS_COOLDOWN_SECONDS = 6 * 60

_lock = threading.Lock()
_stop_event = threading.Event()
_worker = None
_thread_local = threading.local()
_state = {
    "running": False,
    "status": "Idle",
    "error": "",
    "last_tick_at": None,
    "last_scan_at": None,
    "last_scan_ms": None,
    "last_symbol": "",
    "watchlist_size": len(WATCHLIST),
    "last_decisions": {},
}


def get_session():
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
        session.mount("https://", adapter)
        _thread_local.session = session
    return session


def get_json(path, params=None, timeout=REQUEST_TIMEOUT):
    response = get_session().get(
        f"{BINANCE_BASE}{path}",
        params=params or {},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


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


def init_scalper_db():
    init_db()
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scalper_account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                starting_cash REAL NOT NULL,
                cash REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scalper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
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
                setup_score REAL,
                open_reason TEXT,
                close_reason TEXT,
                realized_pnl REAL,
                realized_return_pct REAL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scalper_positions_status ON scalper_positions(status)"
        )
        account = conn.execute("SELECT id FROM scalper_account WHERE id = 1").fetchone()
        if not account:
            now = time.time()
            conn.execute(
                """
                INSERT INTO scalper_account (
                    id, starting_cash, cash, realized_pnl, created_at, updated_at
                )
                VALUES (1, ?, ?, 0, ?, ?)
                """,
                (STARTING_CASH, STARTING_CASH, now, now),
            )


def update_state(**kwargs):
    with _lock:
        _state.update(kwargs)


def fetch_klines(symbol, interval="1m", limit=30):
    payload = get_json(
        "/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
    )
    return [
        {
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in payload
    ]


def fetch_book_ticker(symbol):
    row = get_json("/api/v3/ticker/bookTicker", params={"symbol": symbol})
    bid = float(row["bidPrice"])
    ask = float(row["askPrice"])
    mid = (bid + ask) / 2
    spread_pct = ((ask - bid) / mid) * 100 if mid else 999
    return {"bid": bid, "ask": ask, "mid": mid, "spread_pct": spread_pct}


def fetch_all_book_tickers():
    rows = get_json("/api/v3/ticker/bookTicker")
    tickers = {}
    for row in rows:
        symbol = row["symbol"]
        if symbol not in WATCHLIST:
            continue
        bid = float(row["bidPrice"])
        ask = float(row["askPrice"])
        mid = (bid + ask) / 2
        spread_pct = ((ask - bid) / mid) * 100 if mid else 999
        tickers[symbol] = {"bid": bid, "ask": ask, "mid": mid, "spread_pct": spread_pct}
    return tickers


def analyze_symbol(symbol, book=None):
    candles = fetch_klines(symbol, limit=30)
    book = book or fetch_book_ticker(symbol)
    if len(candles) < 24:
        return {"approved": False, "score": 0, "reason": "not enough candles"}

    closes = [row["close"] for row in candles]
    volumes = [row["volume"] for row in candles]
    price = book["ask"]
    ema9 = ema(closes[-18:], 9)
    ema21 = ema(closes[-24:], 21)
    ret_1m = pct_change(closes[-1], closes[-2])
    ret_3m = pct_change(closes[-1], closes[-4])
    ret_5m = pct_change(closes[-1], closes[-6])
    recent_high = max(closes[-8:-1])
    recent_low = min(closes[-8:-1])
    recent_volume = sum(volumes[-3:]) / 3
    base_volume = sum(volumes[-24:-3]) / max(len(volumes[-24:-3]), 1)
    volume_ratio = recent_volume / base_volume if base_volume else 0

    score = 0
    reasons = []
    if price > ema9 and ema9 >= ema21:
        score += 28
        reasons.append("1m trend up")
    elif price > ema9:
        score += 12
        reasons.append("price reclaimed EMA9")
    else:
        score -= 20
        reasons.append("below 1m EMA")

    if 0.05 <= ret_1m <= 0.90:
        score += 14
        reasons.append(f"1m lift {ret_1m:.2f}%")
    elif ret_1m < -0.12:
        score -= 16
        reasons.append(f"1m fade {ret_1m:.2f}%")

    if 0.18 <= ret_3m <= 1.80:
        score += 24
        reasons.append(f"3m impulse {ret_3m:.2f}%")
    elif ret_3m > 2.5:
        score -= 14
        reasons.append("3m chase risk")
    elif ret_3m < -0.35:
        score -= 20
        reasons.append(f"3m weak {ret_3m:.2f}%")

    if 0.25 <= ret_5m <= 3.2:
        score += 12
        reasons.append(f"5m trend {ret_5m:.2f}%")
    elif ret_5m < -0.60:
        score -= 18
        reasons.append(f"5m weak {ret_5m:.2f}%")

    if volume_ratio >= 1.6:
        score += 18
        reasons.append(f"volume burst {volume_ratio:.2f}x")
    elif volume_ratio >= 1.05:
        score += 8
        reasons.append(f"volume ok {volume_ratio:.2f}x")
    elif volume_ratio < 0.70:
        score -= 10
        reasons.append(f"volume quiet {volume_ratio:.2f}x")

    if price >= recent_high * 0.999:
        score += 10
        reasons.append("near micro breakout")
    if price <= recent_low * 1.002:
        score -= 12
        reasons.append("near micro low")

    if book["spread_pct"] <= 0.06:
        score += 10
        reasons.append("tight spread")
    elif book["spread_pct"] > 0.18:
        score -= 20
        reasons.append(f"wide spread {book['spread_pct']:.2f}%")

    approved = (
        score >= 92
        and 0.04 <= ret_1m <= 0.70
        and 0.25 <= ret_3m <= 1.60
        and 0.30 <= ret_5m <= 2.60
        and volume_ratio >= 1.05
        and book["spread_pct"] <= 0.08
    )
    return {
        "approved": approved,
        "score": score,
        "reason": "; ".join(reasons),
        "price": price,
        "spread_pct": book["spread_pct"],
        "return_1m_pct": ret_1m,
        "return_3m_pct": ret_3m,
        "return_5m_pct": ret_5m,
        "volume_ratio": volume_ratio,
    }


def market_ok(book_tickers=None):
    try:
        checks = []
        for symbol in ("BTCUSDT", "ETHUSDT"):
            checks.append(analyze_symbol(symbol, (book_tickers or {}).get(symbol)))
    except Exception as error:
        return False, f"market check failed: {error}"
    weak = []
    for row in checks:
        if (
            row.get("return_1m_pct", 0) < -0.03
            or row.get("return_3m_pct", 0) < 0.05
            or row.get("return_5m_pct", 0) < 0.10
        ):
            weak.append(row)
    if weak:
        return False, "BTC/ETH no short-term tailwind"
    return True, "market ok"


def open_symbols():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT symbol FROM scalper_positions WHERE status = 'open'"
        ).fetchall()
    return {row["symbol"] for row in rows}


def recent_loss_symbols():
    cutoff = time.time() - LOSS_COOLDOWN_SECONDS
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT symbol FROM scalper_positions
            WHERE status = 'closed' AND closed_at >= ?
              AND COALESCE(realized_pnl, 0) <= 0
            """,
            (cutoff,),
        ).fetchall()
    return {row["symbol"] for row in rows}


def open_position_count():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM scalper_positions WHERE status = 'open'"
        ).fetchone()
    return row["count"]


def close_position(conn, position, price, reason):
    exit_price = price * (1 - (ROUND_SIDE_COST_PCT / 100))
    proceeds = exit_price * position["quantity"]
    pnl = proceeds - position["invested"]
    return_pct = (pnl / position["invested"]) * 100 if position["invested"] else 0
    now = time.time()
    conn.execute(
        """
        UPDATE scalper_positions
        SET status = 'closed', closed_at = ?, latest_price = ?, close_reason = ?,
            realized_pnl = ?, realized_return_pct = ?
        WHERE id = ?
        """,
        (now, exit_price, reason, pnl, return_pct, position["id"]),
    )
    conn.execute(
        """
        UPDATE scalper_account
        SET cash = cash + ?, realized_pnl = realized_pnl + ?, updated_at = ?
        WHERE id = 1
        """,
        (proceeds, pnl, now),
    )


def update_positions():
    init_scalper_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM scalper_positions WHERE status = 'open' ORDER BY opened_at"
        ).fetchall()
        symbols = {row["symbol"] for row in rows}
        try:
            book_tickers = fetch_all_book_tickers() if len(symbols) > 1 else {}
        except Exception:
            book_tickers = {}
        for row in rows:
            position = dict(row)
            try:
                book = book_tickers.get(position["symbol"]) or fetch_book_ticker(position["symbol"])
                price = book["bid"]
            except Exception:
                continue
            highest_price = max(position.get("highest_price") or position["entry_price"], price)
            gross_return = ((price - position["entry_price"]) / position["entry_price"]) * 100
            net_return = ((price * (1 - (ROUND_SIDE_COST_PCT / 100)) - position["entry_price"]) / position["entry_price"]) * 100
            highest_net_return = ((highest_price * (1 - (ROUND_SIDE_COST_PCT / 100)) - position["entry_price"]) / position["entry_price"]) * 100
            age = time.time() - position["opened_at"]
            trailing_stop = position.get("trailing_stop")
            profit_gate_reached = highest_net_return >= PROFIT_GATE_NET_PCT
            if profit_gate_reached:
                lock_price = position["entry_price"] * (1 + ((PROFIT_GATE_NET_PCT - 0.35) / 100))
                trail_price = highest_price * (1 - (TRAIL_GIVEBACK_PCT / 100))
                trailing_stop = max(trailing_stop or 0, lock_price, trail_price)

            reason = None
            if profit_gate_reached and trailing_stop and price <= trailing_stop:
                reason = "Scalp trail"

            if reason:
                close_position(conn, position, price, reason)
            else:
                conn.execute(
                    """
                    UPDATE scalper_positions
                    SET latest_price = ?, highest_price = ?, trailing_stop = ?
                    WHERE id = ?
                    """,
                    (price, highest_price, trailing_stop, position["id"]),
                )
    update_state(last_tick_at=time.time())


def buy_symbol(symbol, analysis):
    entry_price = analysis["price"] * (1 + (ROUND_SIDE_COST_PCT / 100))
    with get_connection() as conn:
        account = conn.execute("SELECT * FROM scalper_account WHERE id = 1").fetchone()
        spendable = max(account["cash"] - CASH_RESERVE_USD, 0)
        amount = min(POSITION_USD, spendable)
        if amount < POSITION_USD:
            return False
        quantity = amount / entry_price
        now = time.time()
        conn.execute(
            """
            INSERT INTO scalper_positions (
                symbol, status, opened_at, entry_price, quantity, invested,
                latest_price, highest_price, target_price, stop_price,
                trailing_stop, setup_score, open_reason
            )
            VALUES (?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                symbol,
                now,
                entry_price,
                quantity,
                amount,
                entry_price,
                entry_price,
                entry_price * (1 + ((TARGET_NET_PCT + ROUND_SIDE_COST_PCT) / 100)),
                entry_price * (1 + (STOP_GROSS_PCT / 100)),
                analysis["score"],
                analysis["reason"],
            ),
        )
        conn.execute(
            "UPDATE scalper_account SET cash = cash - ?, updated_at = ? WHERE id = 1",
            (amount, now),
        )
    return True


def scan_entries():
    scan_started = time.time()
    try:
        book_tickers = fetch_all_book_tickers()
    except Exception as error:
        update_state(
            status="Price snapshot failed",
            error=str(error),
            last_scan_at=time.time(),
            last_scan_ms=round((time.time() - scan_started) * 1000),
        )
        return

    ok, market_reason = market_ok(book_tickers)
    decisions = {"market": market_reason}
    if not ok:
        update_state(
            status="Market weak",
            last_decisions=decisions,
            last_scan_at=time.time(),
            last_scan_ms=round((time.time() - scan_started) * 1000),
        )
        return

    existing = open_symbols()
    cooldown = recent_loss_symbols()
    candidates = []
    slots_before_scan = max(MAX_OPEN_POSITIONS - len(existing), 0)
    symbols_to_scan = [
        symbol for symbol in WATCHLIST
        if symbol not in existing and symbol not in cooldown and slots_before_scan > 0
    ]

    for symbol in cooldown:
        if symbol in WATCHLIST and symbol not in existing:
            decisions[symbol] = "cooldown after recent loss"

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
        futures = {
            executor.submit(analyze_symbol, symbol, book_tickers.get(symbol)): symbol
            for symbol in symbols_to_scan
        }
        for future in as_completed(futures):
            if _stop_event.is_set():
                break
            symbol = futures[future]
            update_state(last_symbol=symbol)
            try:
                analysis = future.result()
            except Exception as error:
                decisions[symbol] = f"error: {error}"
                continue
            decisions[symbol] = f"{analysis['score']}: {analysis['reason']}"
            if analysis["approved"]:
                candidates.append((analysis["score"], symbol, analysis))

    opened = 0
    available_slots = max(MAX_OPEN_POSITIONS - open_position_count(), 0)
    for _, symbol, analysis in sorted(candidates, reverse=True)[:available_slots]:
        if buy_symbol(symbol, analysis):
            existing.add(symbol)
            opened += 1

    update_state(
        status=f"Scalp scan complete, {len(candidates)} eligible, opened {opened}",
        last_scan_at=time.time(),
        last_scan_ms=round((time.time() - scan_started) * 1000),
        last_decisions=decisions,
    )


def scalper_loop():
    update_state(running=True, status="Scalper started", error="")
    while not _stop_event.is_set():
        try:
            update_positions()
            scan_entries()
        except Exception as error:
            update_state(error=str(error), status="Error")
        _stop_event.wait(POLL_SECONDS)
    update_state(running=False, status="Stopped")


def start_scalper():
    global _worker
    init_scalper_db()
    with _lock:
        if _state["running"]:
            return False
        _stop_event.clear()
        _worker = threading.Thread(target=scalper_loop, daemon=True)
        _worker.start()
        return True


def stop_scalper():
    _stop_event.set()
    return True


def reset_scalper():
    stop_scalper()
    time.sleep(0.2)
    init_scalper_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM scalper_positions")
        now = time.time()
        conn.execute(
            """
            UPDATE scalper_account
            SET cash = ?, realized_pnl = 0, updated_at = ?
            WHERE id = 1
            """,
            (STARTING_CASH, now),
        )
    update_state(status="Reset", error="", last_decisions={})


def get_account():
    init_scalper_db()
    with get_connection() as conn:
        account = conn.execute("SELECT * FROM scalper_account WHERE id = 1").fetchone()
        open_positions = conn.execute(
            "SELECT * FROM scalper_positions WHERE status = 'open' ORDER BY opened_at"
        ).fetchall()
        closed_positions = conn.execute(
            """
            SELECT * FROM scalper_positions
            WHERE status = 'closed'
            ORDER BY closed_at DESC, id DESC
            LIMIT 80
            """
        ).fetchall()
        all_closed = conn.execute(
            "SELECT realized_pnl, realized_return_pct FROM scalper_positions WHERE status = 'closed'"
        ).fetchall()

    positions = [dict(row) for row in open_positions]
    closed = [dict(row) for row in closed_positions]
    open_value = sum((pos.get("latest_price") or pos["entry_price"]) * pos["quantity"] for pos in positions)
    unrealized_pnl = sum(
        (((pos.get("latest_price") or pos["entry_price"]) * pos["quantity"]) - pos["invested"])
        for pos in positions
    )
    equity = account["cash"] + open_value
    closed_count = len(all_closed)
    wins = [row for row in all_closed if (row["realized_pnl"] or 0) > 0]
    avg_return = (
        sum(row["realized_return_pct"] or 0 for row in all_closed) / closed_count
        if closed_count else 0
    )
    with _lock:
        state = dict(_state)

    return {
        "account": dict(account),
        "positions": positions,
        "closed_positions": closed,
        "open_value": open_value,
        "unrealized_pnl": unrealized_pnl,
        "equity": equity,
        "total_return_pct": ((equity - account["starting_cash"]) / account["starting_cash"]) * 100,
        "stats": {
            "closed_count": closed_count,
            "wins": len(wins),
            "losses": closed_count - len(wins),
            "win_rate": (len(wins) / closed_count) * 100 if closed_count else 0,
            "avg_return": avg_return,
            "best_return": max([row["realized_return_pct"] or 0 for row in all_closed], default=0),
            "worst_return": min([row["realized_return_pct"] or 0 for row in all_closed], default=0),
        },
        "state": state,
        "rules": {
            "watchlist": WATCHLIST,
            "poll_seconds": POLL_SECONDS,
            "request_timeout": REQUEST_TIMEOUT,
            "scan_workers": SCAN_WORKERS,
            "min_hold_seconds": MIN_HOLD_SECONDS,
            "max_hold_seconds": MAX_HOLD_SECONDS,
            "max_open_positions": MAX_OPEN_POSITIONS,
            "position_usd": POSITION_USD,
            "profit_gate_net_pct": PROFIT_GATE_NET_PCT,
            "target_net_pct": TARGET_NET_PCT,
            "stop_gross_pct": STOP_GROSS_PCT,
            "panic_gross_pct": PANIC_GROSS_PCT,
            "fee_pct": FEE_PCT,
            "slippage_pct": SLIPPAGE_PCT,
            "round_side_cost_pct": ROUND_SIDE_COST_PCT,
        },
    }
