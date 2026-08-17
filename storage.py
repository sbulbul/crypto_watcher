import json
import sqlite3
import time
from pathlib import Path

import requests
import yfinance as yf

DB_PATH = Path(__file__).resolve().parent / "data" / "crypto_watcher.db"
UNIVERSE_CACHE_PATH = Path(__file__).resolve().parent / "data" / "crypto_universe.json"


def ticker_to_binance_symbol(ticker):
    base = str(ticker).upper().replace("-USD", "").replace("USD", "")
    if not base or not base.replace("_", "").isalnum():
        return None
    return f"{base}USDT"


def fetch_binance_price(ticker):
    symbol = ticker_to_binance_symbol(ticker)
    if not symbol:
        return None

    try:
        response = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=5,
        )
        if response.status_code == 400:
            return None
        response.raise_for_status()
        payload = response.json()
        price = float(payload.get("price") or 0)
        if price > 0:
            return {"price": price, "source": "Binance spot"}
    except Exception:
        return None

    return None


def get_cached_coingecko_id(ticker):
    try:
        if not UNIVERSE_CACHE_PATH.exists():
            return None

        with UNIVERSE_CACHE_PATH.open("r", encoding="utf-8") as file:
            cache = json.load(file)

        ticker_text = str(ticker).upper()
        for coin in cache.get("coins", []):
            if str(coin.get("ticker", "")).upper() == ticker_text:
                return coin.get("id")
    except Exception:
        return None

    return None


def fetch_coingecko_price(ticker):
    coin_id = get_cached_coingecko_id(ticker)
    if not coin_id:
        return None

    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        price = float(payload.get(coin_id, {}).get("usd") or 0)
        if price > 0:
            return {"price": price, "source": "CoinGecko simple price"}
    except Exception:
        return None

    return None


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at REAL NOT NULL,
                completed_at REAL NOT NULL,
                limit_requested INTEGER NOT NULL,
                universe_count INTEGER NOT NULL,
                candidate_count INTEGER NOT NULL,
                status TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL,
                rank INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                signal TEXT NOT NULL,
                long_term_signal TEXT,
                quick_win_score INTEGER,
                long_term_score INTEGER,
                moonshot_score INTEGER NOT NULL,
                momentum_score INTEGER NOT NULL,
                scan_price REAL NOT NULL,
                price_change REAL NOT NULL,
                price_change_5d REAL NOT NULL,
                price_change_20d REAL NOT NULL,
                three_year_return REAL,
                relative_volume REAL NOT NULL,
                dollar_volume REAL NOT NULL,
                headline TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                long_term_reasons_json TEXT,
                checked_price REAL,
                checked_at REAL,
                checked_source TEXT,
                return_pct REAL,
                trade_note TEXT,
                target_price REAL,
                stop_price REAL,
                entry_low REAL,
                entry_high REAL,
                support REAL,
                resistance REAL,
                vwap REAL,
                atr REAL,
                atr_pct REAL,
                range_24h_pct REAL,
                upside_to_high_pct REAL,
                target_profit_pct REAL,
                stop_loss_pct REAL,
                reward_risk REAL,
                target_window TEXT,
                rsi REAL,
                market_flow_json TEXT,
                FOREIGN KEY(scan_id) REFERENCES scans(id)
            )
        """)
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(scan_results)").fetchall()
        }
        new_columns = {
            "trade_note": "TEXT",
            "target_price": "REAL",
            "stop_price": "REAL",
            "entry_low": "REAL",
            "entry_high": "REAL",
            "support": "REAL",
            "resistance": "REAL",
            "vwap": "REAL",
            "atr": "REAL",
            "atr_pct": "REAL",
            "range_24h_pct": "REAL",
            "upside_to_high_pct": "REAL",
            "target_profit_pct": "REAL",
            "stop_loss_pct": "REAL",
            "reward_risk": "REAL",
            "target_window": "TEXT",
            "rsi": "REAL",
            "market_flow_json": "TEXT",
        }
        for column, column_type in new_columns.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE scan_results ADD COLUMN {column} {column_type}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scan_results_scan_id ON scan_results(scan_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scan_results_ticker ON scan_results(ticker)"
        )


def save_scan(limit, universe_count, results, started_at, completed_at=None, status="completed"):
    init_db()
    completed_at = completed_at or time.time()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO scans (
                started_at, completed_at, limit_requested, universe_count,
                candidate_count, status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (started_at, completed_at, limit, universe_count, len(results), status),
        )
        scan_id = cursor.lastrowid

        for rank, item in enumerate(results, start=1):
            conn.execute(
                """
                INSERT INTO scan_results (
                    scan_id, rank, ticker, signal, long_term_signal,
                    quick_win_score, long_term_score, moonshot_score, momentum_score,
                    scan_price, price_change, price_change_5d, price_change_20d,
                    three_year_return, relative_volume, dollar_volume, headline,
                    reasons_json, long_term_reasons_json, trade_note, target_price,
                    stop_price, entry_low, entry_high, support, resistance, vwap,
                    atr, atr_pct, range_24h_pct, upside_to_high_pct,
                    target_profit_pct, stop_loss_pct, reward_risk,
                    target_window, rsi, market_flow_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    rank,
                    item["ticker"],
                    item["signal"],
                    item.get("long_term_signal", ""),
                    item.get("quick_win_score", item["moonshot_score"]),
                    item.get("long_term_score", 0),
                    item["moonshot_score"],
                    item["momentum_score"],
                    item["price"],
                    item["price_change"],
                    item["price_change_5d"],
                    item["price_change_20d"],
                    item.get("three_year_return"),
                    item["relative_volume"],
                    item.get("dollar_volume", 0),
                    item["headline"],
                    json.dumps(item.get("reasons", [])),
                    json.dumps(item.get("long_term_reasons", [])),
                    item.get("trade_note"),
                    item.get("target_price"),
                    item.get("stop_price"),
                    item.get("entry_low"),
                    item.get("entry_high"),
                    item.get("support"),
                    item.get("resistance"),
                    item.get("vwap"),
                    item.get("atr"),
                    item.get("atr_pct"),
                    item.get("range_24h_pct"),
                    item.get("upside_to_high_pct"),
                    item.get("target_profit_pct"),
                    item.get("stop_loss_pct"),
                    item.get("reward_risk"),
                    item.get("target_window"),
                    item.get("rsi"),
                    json.dumps(item.get("market_flow", {})),
                ),
            )

    return scan_id


def row_to_result(row):
    return {
        "ticker": row["ticker"],
        "score": row["moonshot_score"],
        "signal": row["signal"],
        "long_term_signal": row["long_term_signal"],
        "quick_win_score": row["quick_win_score"] if row["quick_win_score"] is not None else row["moonshot_score"],
        "long_term_score": row["long_term_score"] or 0,
        "moonshot_score": row["moonshot_score"],
        "momentum_score": row["momentum_score"],
        "price": row["scan_price"],
        "price_change": row["price_change"],
        "price_change_5d": row["price_change_5d"],
        "price_change_20d": row["price_change_20d"],
        "three_year_return": row["three_year_return"],
        "relative_volume": row["relative_volume"],
        "dollar_volume": row["dollar_volume"],
        "headline": row["headline"],
        "trade_note": row["trade_note"] or row["headline"],
        "target_price": row["target_price"],
        "stop_price": row["stop_price"],
        "entry_low": row["entry_low"],
        "entry_high": row["entry_high"],
        "support": row["support"],
        "resistance": row["resistance"],
        "vwap": row["vwap"],
        "atr": row["atr"],
        "atr_pct": row["atr_pct"],
        "range_24h_pct": row["range_24h_pct"],
        "upside_to_high_pct": row["upside_to_high_pct"],
        "target_profit_pct": row["target_profit_pct"],
        "stop_loss_pct": row["stop_loss_pct"],
        "reward_risk": row["reward_risk"],
        "target_window": row["target_window"],
        "rsi": row["rsi"],
        "market_flow": json.loads(row["market_flow_json"] or "{}"),
        "reasons": json.loads(row["reasons_json"] or "[]"),
        "quick_win_reasons": json.loads(row["reasons_json"] or "[]"),
        "long_term_reasons": json.loads(row["long_term_reasons_json"] or "[]"),
        "checked_price": row["checked_price"],
        "checked_at": row["checked_at"],
        "checked_source": row["checked_source"],
        "return_pct": row["return_pct"],
    }


def get_scan(scan_id):
    init_db()
    with get_connection() as conn:
        scan = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if not scan:
            return None

        rows = conn.execute(
            "SELECT * FROM scan_results WHERE scan_id = ? ORDER BY rank",
            (scan_id,),
        ).fetchall()

    return {
        "scan": dict(scan),
        "results": [row_to_result(row) for row in rows],
    }


def get_latest_scan():
    init_db()
    with get_connection() as conn:
        scan = conn.execute(
            "SELECT id FROM scans ORDER BY completed_at DESC, id DESC LIMIT 1"
        ).fetchone()

    if not scan:
        return None

    return get_scan(scan["id"])


def list_scans(limit=10):
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.*,
                MAX(r.moonshot_score) AS top_score,
                AVG(r.return_pct) AS avg_return_pct,
                MAX(r.return_pct) AS best_return_pct,
                SUM(CASE WHEN r.return_pct >= 25 THEN 1 ELSE 0 END) AS double_count
            FROM scans s
            LEFT JOIN scan_results r ON r.scan_id = s.id
            GROUP BY s.id
            ORDER BY s.completed_at DESC, s.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def delete_scan(scan_id):
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM scan_results WHERE scan_id = ?", (scan_id,))
        conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))


def delete_all_scans():
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM scan_results")
        conn.execute("DELETE FROM scans")


def fetch_latest_price(ticker):
    quote = fetch_binance_price(ticker)
    if quote:
        return quote

    try:
        hist = yf.Ticker(ticker).history(period="1d", interval="1m")
        if not hist.empty:
            close = hist["Close"].dropna()
            if not close.empty:
                return {
                    "price": float(close.iloc[-1]),
                    "source": "Yahoo crypto 1m",
                }
    except Exception:
        pass

    try:
        hist = yf.download(
            tickers=[ticker],
            period="5d",
            interval="1h",
            progress=False,
            auto_adjust=False,
            threads=False,
            timeout=15,
        )
        if hist.empty:
            return None

        close = hist["Close"]
        if hasattr(close, "columns"):
            close = close[ticker] if ticker in close.columns else close.iloc[:, 0]

        close = close.dropna()
        if close.empty:
            return None

        return {
            "price": float(close.iloc[-1]),
            "source": "Yahoo crypto 1h fallback",
        }
    except Exception:
        pass

    return fetch_coingecko_price(ticker)


def update_scan_performance(scan_id, progress_callback=None):
    init_db()
    saved = get_scan(scan_id)
    if not saved:
        return None

    checked_at = time.time()
    updated = 0

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, ticker, scan_price FROM scan_results WHERE scan_id = ?",
            (scan_id,),
        ).fetchall()

        total = len(rows)
        if progress_callback:
            progress_callback(processed=0, total=total, ticker="", updated=0)

        for index, row in enumerate(rows, start=1):
            if progress_callback:
                progress_callback(
                    processed=index,
                    total=total,
                    ticker=row["ticker"],
                    updated=updated,
                )

            quote = fetch_latest_price(row["ticker"])
            if not quote or quote["price"] <= 0:
                continue

            latest_price = quote["price"]
            return_pct = ((latest_price - row["scan_price"]) / row["scan_price"]) * 100
            conn.execute(
                """
                UPDATE scan_results
                SET checked_price = ?, checked_at = ?, checked_source = ?, return_pct = ?
                WHERE id = ?
                """,
                (latest_price, checked_at, quote["source"], return_pct, row["id"]),
            )
            updated += 1

            if progress_callback:
                progress_callback(
                    processed=index,
                    total=total,
                    ticker=row["ticker"],
                    updated=updated,
                )

    return {
        "scan_id": scan_id,
        "updated": updated,
        "checked_at": checked_at,
    }
