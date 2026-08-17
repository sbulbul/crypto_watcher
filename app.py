import csv
import io
import threading
import time
from datetime import datetime
from urllib.parse import quote_plus

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for

from paper_trader import (
    get_account as get_paper_account,
    reset_paper_trader,
    start_paper_trader,
    stop_paper_trader,
)
from scanner import scan_market
from scalper import (
    get_account as get_scalper_account,
    reset_scalper,
    start_scalper,
    stop_scalper,
)
from crypto_lookup import lookup_ticker
from storage import (
    delete_all_scans,
    delete_scan,
    get_latest_scan,
    get_scan,
    init_db,
    list_scans,
    save_scan,
    update_scan_performance,
)

app = Flask(__name__)
init_db()


@app.template_filter("fmt_time")
def fmt_time(value):
    if not value:
        return "-"

    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


@app.template_filter("fmt_pct")
def fmt_pct(value):
    if value is None:
        return "-"

    return f"{value:.2f}%"


@app.template_filter("fmt_price")
def fmt_price(value):
    if value is None:
        return "-"

    value = float(value)
    return f"${value:,.2f}"


@app.template_filter("fmt_money_exact")
def fmt_money_exact(value):
    if value is None:
        return "-"

    value = float(value)
    if abs(value) < 10:
        return f"${value:,.4f}"
    return f"${value:,.2f}"


def ticker_base(ticker):
    text = str(ticker or "").upper()
    if text.endswith("-USDT"):
        return text[:-5]
    if text.endswith("USDT"):
        return text[:-4]
    if text.endswith("-USD"):
        return text[:-4]
    if text.endswith("USD"):
        return text[:-3]
    return text


@app.template_filter("display_pair")
def display_pair(ticker):
    base = ticker_base(ticker)
    if not base:
        return "-"
    return f"{base}-USDT"


@app.template_filter("tradingview_url")
def tradingview_url(ticker):
    base = ticker_base(ticker)
    if not base:
        return "https://www.tradingview.com/"
    return f"https://www.tradingview.com/chart/?symbol=BINANCE%3A{quote_plus(base)}USDT"


@app.template_filter("binance_url")
def binance_url(ticker):
    base = ticker_base(ticker)
    if not base:
        return "https://www.binance.com/en/markets"
    return f"https://www.binance.com/en/trade/{quote_plus(base)}_USDT"


@app.template_filter("coingecko_url")
def coingecko_url(ticker):
    base = ticker_base(ticker)
    if not base:
        return "https://www.coingecko.com/"
    return f"https://www.coingecko.com/en/search?query={quote_plus(base)}"


CSV_FIELDS = [
    "scan_id",
    "scan_started_at",
    "scan_completed_at",
    "scan_status",
    "limit_requested",
    "universe_count",
    "candidate_count",
    "rank",
    "ticker",
    "buy_signal",
    "sell_signal",
    "buy_score",
    "sell_score",
    "momentum_score",
    "scan_price",
    "entry_low",
    "entry_high",
    "target_price",
    "target_profit_pct",
    "target_window",
    "stop_price",
    "stop_loss_pct",
    "reward_risk",
    "price_change_1h_pct",
    "price_change_4h_pct",
    "price_change_24h_pct",
    "relative_volume",
    "hourly_dollar_volume",
    "rsi",
    "atr_pct",
    "range_24h_pct",
    "upside_to_high_pct",
    "support",
    "resistance",
    "vwap",
    "order_book_imbalance",
    "taker_buy_ratio",
    "funding_rate",
    "long_short_ratio",
    "trade_note",
    "setup_note",
    "buy_reasons",
    "sell_reasons",
    "checked_price",
    "checked_at",
    "checked_source",
    "return_since_scan_pct",
]

PAPER_CSV_FIELDS = [
    "id",
    "ticker",
    "status",
    "opened_at",
    "closed_at",
    "entry_price",
    "latest_price",
    "quantity",
    "invested",
    "target_price",
    "stop_price",
    "trailing_stop",
    "buy_score",
    "sell_score",
    "target_profit_pct",
    "target_window",
    "reward_risk",
    "close_reason",
    "realized_pnl",
    "realized_return_pct",
    "open_reason",
]

scan_lock = threading.Lock()
stop_scan_event = threading.Event()
performance_lock = threading.Lock()
scan_state = {
    "running": False,
    "scanned": False,
    "stop_requested": False,
    "stopped": False,
    "limit": 250,
    "processed": 0,
    "total": 0,
    "remaining": 0,
    "percent": 0,
    "ticker": "",
    "candidates": 0,
    "elapsed": 0,
    "started_at": None,
    "completed_at": None,
    "error": "",
    "results": [],
    "scan_id": None,
    "suppress_latest": False,
}
performance_state = {
    "running": False,
    "scan_id": None,
    "processed": 0,
    "total": 0,
    "remaining": 0,
    "percent": 0,
    "ticker": "",
    "updated": 0,
    "error": "",
}


def parse_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 250

    return max(25, min(limit, 1000))


def parse_paper_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 1000

    return max(1000, min(limit, 1000))


def csv_time(value):
    if not value:
        return ""

    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def scan_to_csv_rows(saved):
    scan = saved["scan"]
    rows = []

    for rank, item in enumerate(saved["results"], start=1):
        rows.append({
            "scan_id": scan["id"],
            "scan_started_at": csv_time(scan["started_at"]),
            "scan_completed_at": csv_time(scan["completed_at"]),
            "scan_status": scan["status"],
            "limit_requested": scan["limit_requested"],
            "universe_count": scan["universe_count"],
            "candidate_count": scan["candidate_count"],
            "rank": rank,
            "ticker": item["ticker"],
            "buy_signal": item["signal"],
            "sell_signal": item.get("long_term_signal"),
            "buy_score": item.get("quick_win_score", item["moonshot_score"]),
            "sell_score": item.get("long_term_score"),
            "momentum_score": item["momentum_score"],
            "scan_price": item["price"],
            "entry_low": item.get("entry_low"),
            "entry_high": item.get("entry_high"),
            "target_price": item.get("target_price"),
            "target_profit_pct": item.get("target_profit_pct"),
            "target_window": item.get("target_window"),
            "stop_price": item.get("stop_price"),
            "stop_loss_pct": item.get("stop_loss_pct"),
            "reward_risk": item.get("reward_risk"),
            "price_change_1h_pct": item["price_change"],
            "price_change_4h_pct": item["price_change_5d"],
            "price_change_24h_pct": item["price_change_20d"],
            "relative_volume": item["relative_volume"],
            "hourly_dollar_volume": item["dollar_volume"],
            "rsi": item.get("rsi"),
            "atr_pct": item.get("atr_pct"),
            "range_24h_pct": item.get("range_24h_pct"),
            "upside_to_high_pct": item.get("upside_to_high_pct"),
            "support": item.get("support"),
            "resistance": item.get("resistance"),
            "vwap": item.get("vwap"),
            "order_book_imbalance": item.get("market_flow", {}).get("book_imbalance"),
            "taker_buy_ratio": item.get("market_flow", {}).get("taker_buy_ratio"),
            "funding_rate": item.get("market_flow", {}).get("funding_rate"),
            "long_short_ratio": item.get("market_flow", {}).get("long_short_ratio"),
            "trade_note": item.get("trade_note"),
            "setup_note": item["headline"],
            "buy_reasons": " | ".join(item.get("reasons", [])),
            "sell_reasons": " | ".join(item.get("long_term_reasons", [])),
            "checked_price": item.get("checked_price"),
            "checked_at": csv_time(item.get("checked_at")),
            "checked_source": item.get("checked_source"),
            "return_since_scan_pct": item.get("return_pct"),
        })

    if rows:
        return rows

    return [{
        "scan_id": scan["id"],
        "scan_started_at": csv_time(scan["started_at"]),
        "scan_completed_at": csv_time(scan["completed_at"]),
        "scan_status": scan["status"],
        "limit_requested": scan["limit_requested"],
        "universe_count": scan["universe_count"],
        "candidate_count": scan["candidate_count"],
    }]


def csv_response(rows, filename):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def paper_csv_response(paper):
    rows = []
    for position in paper["positions"] + paper["closed_positions"]:
        row = dict(position)
        row["opened_at"] = csv_time(row.get("opened_at"))
        row["closed_at"] = csv_time(row.get("closed_at"))
        rows.append(row)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=PAPER_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=crypto_paper_trades.csv"},
    )


def public_scan_state():
    with scan_lock:
        state = dict(scan_state)
        state.pop("results", None)
        return state


def public_performance_state():
    with performance_lock:
        return dict(performance_state)


def update_progress(processed, total, ticker, candidates, elapsed):
    percent = round((processed / total) * 100, 1) if total else 0

    with scan_lock:
        scan_state.update({
            "processed": processed,
            "total": total,
            "remaining": max(total - processed, 0),
            "percent": percent,
            "ticker": ticker,
            "candidates": candidates,
            "elapsed": round(elapsed, 0),
        })


def update_performance_progress(processed, total, ticker, updated):
    percent = round((processed / total) * 100, 1) if total else 0

    with performance_lock:
        performance_state.update({
            "processed": processed,
            "total": total,
            "remaining": max(total - processed, 0),
            "percent": percent,
            "ticker": ticker,
            "updated": updated,
        })


def split_results(results):
    buy_results = sorted(
        [result for result in results if result.get("quick_win_score", 0) >= 55],
        key=lambda result: (
            result.get("quick_win_score", 0),
            result.get("target_profit_pct") or 0,
            result.get("reward_risk") or 0,
            result.get("relative_volume", 0),
        ),
        reverse=True,
    )
    sell_results = sorted(
        [result for result in results if result.get("long_term_score", 0) >= 55],
        key=lambda result: (result.get("long_term_score", 0), abs(result.get("price_change", 0))),
        reverse=True,
    )
    other_results = sorted(
        [
            result for result in results
            if result.get("quick_win_score", 0) < 55 and result.get("long_term_score", 0) < 55
        ],
        key=lambda result: max(result.get("quick_win_score", 0), result.get("long_term_score", 0)),
        reverse=True,
    )
    return buy_results, sell_results, other_results


def run_performance_update(scan_id):
    try:
        summary = update_scan_performance(
            scan_id,
            progress_callback=update_performance_progress,
        )
        saved = get_scan(scan_id)
        saved_results = saved["results"] if saved else []

        with scan_lock:
            if scan_state["scan_id"] == scan_id:
                scan_state["results"] = saved_results

        with performance_lock:
            performance_state.update({
                "running": False,
                "processed": performance_state["total"],
                "remaining": 0,
                "percent": 100,
                "updated": summary["updated"] if summary else performance_state["updated"],
                "error": "",
            })
    except Exception as error:
        with performance_lock:
            performance_state.update({"running": False, "error": str(error)})


def run_scan(limit):
    try:
        with scan_lock:
            started_at = scan_state["started_at"] or time.time()

        results = scan_market(
            limit=limit,
            progress_callback=update_progress,
            should_stop=stop_scan_event.is_set,
        )

        with scan_lock:
            was_stopped = stop_scan_event.is_set()
            completed_at = time.time()
            universe_count = scan_state["total"]

        scan_id = save_scan(
            limit=limit,
            universe_count=universe_count,
            results=results,
            started_at=started_at,
            completed_at=completed_at,
            status="stopped" if was_stopped else "completed",
        )

        with scan_lock:
            scan_state.update({
                "running": False,
                "scanned": True,
                "stop_requested": False,
                "stopped": was_stopped,
                "processed": scan_state["processed"] if was_stopped else scan_state["total"],
                "remaining": scan_state["remaining"] if was_stopped else 0,
                "percent": scan_state["percent"] if was_stopped else 100,
                "candidates": len(results),
                "completed_at": completed_at,
                "error": "",
                "results": results,
                "scan_id": scan_id,
            })
            stop_scan_event.clear()
    except Exception as error:
        with scan_lock:
            scan_state.update({
                "running": False,
                "scanned": True,
                "stop_requested": False,
                "stopped": False,
                "completed_at": time.time(),
                "error": str(error),
                "results": [],
                "scan_id": None,
            })
            stop_scan_event.clear()


@app.route("/")
def home():
    with scan_lock:
        results = list(scan_state["results"])
        limit = scan_state["limit"]
        scanned = scan_state["scanned"]
        running = scan_state["running"]
        stopped = scan_state["stopped"]
        error = scan_state["error"]
        scan_id = scan_state["scan_id"]
        scan_started_at = scan_state["started_at"]
        scan_completed_at = scan_state["completed_at"]
        suppress_latest = scan_state["suppress_latest"]

    if not running and not results and not scanned and not suppress_latest:
        latest = get_latest_scan()
        if latest:
            results = latest["results"]
            limit = latest["scan"]["limit_requested"]
            scanned = True
            stopped = latest["scan"]["status"] == "stopped"
            scan_id = latest["scan"]["id"]
            scan_started_at = latest["scan"]["started_at"]
            scan_completed_at = latest["scan"]["completed_at"]
    elif not running and scan_id:
        saved = get_scan(scan_id)
        if saved:
            results = saved["results"]
            limit = saved["scan"]["limit_requested"]
            scanned = True
            stopped = saved["scan"]["status"] == "stopped"
            scan_started_at = saved["scan"]["started_at"]
            scan_completed_at = saved["scan"]["completed_at"]

    buy_results, sell_results, other_results = split_results(results)

    return render_template(
        "index.html",
        results=results,
        strong_results=buy_results,
        speculative_results=other_results,
        quick_win_results=buy_results,
        long_term_results=sell_results,
        other_results=other_results,
        limit=limit,
        scanned=scanned,
        running=running,
        stopped=stopped,
        error=error,
        scan_id=scan_id,
        scan_started_at=scan_started_at,
        scan_completed_at=scan_completed_at,
        scan_history=list_scans(limit=8),
    )


@app.route("/scan")
def scan():
    limit = parse_limit(request.args.get("limit", 250))

    with scan_lock:
        if scan_state["running"]:
            return redirect(url_for("home"))

    start_scan(limit)
    return redirect(url_for("home"))


@app.route("/start_scan")
def start_scan_route():
    limit = parse_limit(request.args.get("limit", 250))
    started = start_scan(limit)
    status = public_scan_state()
    status["started"] = started
    return jsonify(status)


@app.route("/scan_status")
def scan_status():
    return jsonify(public_scan_state())


@app.route("/performance_status")
def performance_status():
    return jsonify(public_performance_state())


@app.route("/stop_scan", methods=["POST"])
def stop_scan():
    with scan_lock:
        if not scan_state["running"]:
            return jsonify(public_scan_state())

        scan_state["stop_requested"] = True

    stop_scan_event.set()
    return jsonify(public_scan_state())


@app.route("/reset")
def reset():
    with scan_lock:
        if scan_state["running"]:
            return redirect(url_for("home"))

        scan_state.update({
            "scanned": False,
            "stop_requested": False,
            "stopped": False,
            "processed": 0,
            "total": 0,
            "remaining": 0,
            "percent": 0,
            "ticker": "",
            "candidates": 0,
            "elapsed": 0,
            "started_at": None,
            "completed_at": None,
            "error": "",
            "results": [],
            "scan_id": None,
            "suppress_latest": True,
        })

    return redirect(url_for("home"))


@app.route("/crypto")
def crypto_page():
    return render_template("crypto.html")


@app.route("/crypto_lookup")
def crypto_lookup_route():
    return jsonify(lookup_ticker(request.args.get("ticker", "")))


@app.route("/history")
def history():
    return render_template("history.html", scan_history=list_scans(limit=50))


@app.route("/paper")
def paper():
    return render_template("paper.html", paper=get_paper_account())


@app.route("/paper_status")
def paper_status():
    return jsonify(get_paper_account())


@app.route("/scalper")
def scalper():
    return render_template("scalper.html", scalper=get_scalper_account())


@app.route("/scalper_status")
def scalper_status():
    return jsonify(get_scalper_account())


@app.route("/start_scalper", methods=["POST"])
def start_scalper_route():
    start_scalper()
    return redirect(url_for("scalper"))


@app.route("/stop_scalper", methods=["POST"])
def stop_scalper_route():
    stop_scalper()
    return redirect(url_for("scalper"))


@app.route("/reset_scalper", methods=["POST"])
def reset_scalper_route():
    reset_scalper()
    return redirect(url_for("scalper"))


@app.route("/export_paper")
def export_paper():
    return paper_csv_response(get_paper_account())


@app.route("/start_paper", methods=["POST"])
def start_paper():
    scan_limit = parse_paper_limit(request.form.get("scan_limit", 1000))
    start_paper_trader(scan_limit=scan_limit)
    return redirect(url_for("paper"))


@app.route("/stop_paper", methods=["POST"])
def stop_paper():
    stop_paper_trader()
    return redirect(url_for("paper"))


@app.route("/reset_paper", methods=["POST"])
def reset_paper():
    reset_paper_trader()
    return redirect(url_for("paper"))


@app.route("/export_scan/<int:scan_id>")
def export_scan(scan_id):
    saved = get_scan(scan_id)
    if not saved:
        return redirect(url_for("history"))

    return csv_response(scan_to_csv_rows(saved), f"crypto_watcher_scan_{scan_id}.csv")


@app.route("/export_history")
def export_history():
    rows = []

    for scan_item in list_scans(limit=100000):
        saved = get_scan(scan_item["id"])
        if saved:
            rows.extend(scan_to_csv_rows(saved))

    return csv_response(rows, "crypto_watcher_all_history.csv")


@app.route("/scan/<int:scan_id>")
def view_scan(scan_id):
    saved = get_scan(scan_id)
    if not saved:
        return redirect(url_for("history"))

    buy_results, sell_results, other_results = split_results(saved["results"])

    return render_template(
        "index.html",
        results=saved["results"],
        strong_results=buy_results,
        speculative_results=other_results,
        quick_win_results=buy_results,
        long_term_results=sell_results,
        other_results=other_results,
        limit=saved["scan"]["limit_requested"],
        scanned=True,
        running=False,
        stopped=saved["scan"]["status"] == "stopped",
        error="",
        scan_id=scan_id,
        scan_started_at=saved["scan"]["started_at"],
        scan_completed_at=saved["scan"]["completed_at"],
        scan_history=list_scans(limit=8),
        viewing_saved=True,
    )


@app.route("/update_performance/<int:scan_id>", methods=["POST"])
def update_performance(scan_id):
    update_scan_performance(scan_id)
    return redirect(url_for("view_scan", scan_id=scan_id))


@app.route("/start_performance_update/<int:scan_id>", methods=["POST"])
def start_performance_update(scan_id):
    with performance_lock:
        if performance_state["running"]:
            status = dict(performance_state)
            status["started"] = False
            return jsonify(status)

        performance_state.update({
            "running": True,
            "scan_id": scan_id,
            "processed": 0,
            "total": 0,
            "remaining": 0,
            "percent": 0,
            "ticker": "",
            "updated": 0,
            "error": "",
        })

    thread = threading.Thread(target=run_performance_update, args=(scan_id,), daemon=True)
    thread.start()
    status = public_performance_state()
    status["started"] = True
    return jsonify(status)


@app.route("/delete_scan/<int:scan_id>", methods=["POST"])
def delete_scan_route(scan_id):
    delete_scan(scan_id)

    with scan_lock:
        if scan_state["scan_id"] == scan_id:
            scan_state.update({
                "scanned": False,
                "stopped": False,
                "results": [],
                "scan_id": None,
                "error": "",
                "suppress_latest": True,
            })

    return redirect(request.referrer or url_for("history"))


@app.route("/clear_history", methods=["POST"])
def clear_history():
    delete_all_scans()

    with scan_lock:
        scan_state.update({
            "scanned": False,
            "stopped": False,
            "results": [],
            "scan_id": None,
            "error": "",
            "suppress_latest": True,
        })

    return redirect(url_for("history"))


def start_scan(limit):
    with scan_lock:
        if scan_state["running"]:
            return False

        stop_scan_event.clear()
        scan_state.update({
            "running": True,
            "scanned": True,
            "stop_requested": False,
            "stopped": False,
            "limit": limit,
            "processed": 0,
            "total": 0,
            "remaining": 0,
            "percent": 0,
            "ticker": "",
            "candidates": 0,
            "elapsed": 0,
            "started_at": time.time(),
            "completed_at": None,
            "error": "",
            "results": [],
            "scan_id": None,
            "suppress_latest": False,
        })

    thread = threading.Thread(target=run_scan, args=(limit,), daemon=True)
    thread.start()
    return True


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5051, debug=False, use_reloader=False, threaded=True)
