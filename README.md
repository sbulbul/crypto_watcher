# crypto_watcher

A personal Flask web app for scanning crypto markets, scoring candidates for
short-term buy/sell setups, and paper-trading (real or simulated) the results —
no exchange account or real money required.

## What it does

- **Scanner** — pulls the crypto universe, scores each coin using price
  momentum, volume, and market-flow signals (order-book imbalance, taker-buy
  ratio, funding rate), and ranks candidates by a 0–100 buy/sell score.
- **Scalper** — a faster, shorter-horizon variant of the scanner aimed at
  quick setups.
- **Paper Trader** — simulates entering/exiting positions from scan results
  and tracks simulated P&L over time, without placing real trades.
- **History** — every scan is saved and browsable, with per-scan performance
  tracking (did the picks actually move the way the score predicted?).

All scan, scalper, and paper-trading state persists locally in a SQLite
database (`data/crypto_watcher.db`, not committed to this repo).

## Tech stack

- Python + Flask (server-rendered HTML via Jinja2 templates)
- `yfinance` for historical market data, `requests` against Binance/CoinGecko
  for live crypto prices and order-book/funding data
- SQLite (via the standard library `sqlite3`) for local persistence
- No frontend framework — plain HTML/CSS/JS in `templates/` and `static/`

## Getting started

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5051` in a browser.

## Project layout

```text
app.py              # Flask routes
scanner.py           # market scan orchestration
scorer.py             # buy/sell scoring logic
market_flow.py         # Binance order-book / funding-rate signals
scalper.py               # short-horizon scan variant
paper_trader.py           # simulated position tracking
storage.py                 # SQLite persistence layer
universe.py                 # tracked coin universe
config.py                    # thresholds and tunables
templates/, static/            # UI
data/                            # local cache + SQLite DB (gitignored DB)
```

## Development workflow

This repo uses [Spec Kit](https://github.com/github/spec-kit) for planning new
features. The project constitution (non-negotiable reliability/UX principles
this app must follow) lives at `.specify/memory/constitution.md`. In-progress
and completed feature specs, plans, and task breakdowns live under `specs/`.

The **stock ticker lookup** feature (`specs/001-stock-ticker-lookup/`) is
currently specified and planned but not yet implemented.
