# Implementation Plan: Crypto Ticker Lookup

**Branch**: `001-stock-ticker-lookup` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-stock-ticker-lookup/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a new page to the existing Flask app where a user types a cryptocurrency ticker,
submits it, and sees that coin's current (or delayed) price plus a Buy/Sell/Hold
recommendation — reached via a new button on the main page. This plan **replaces** the
earlier stock-ticker version of this feature: an initial implementation was built
against equities, but since this app (`crypto_watcher`) already has a full crypto
evaluation pipeline that equities could never use, the feature is being re-scoped to
crypto and the existing stock-specific code (`stock_lookup.py`, `/stock` routes,
`templates/stock.html`) will be reworked into a crypto version rather than kept
alongside it (see spec.md's pivot note).

Unlike the stock version — which had to invent a new scoring approach because the
app's real scorer needs crypto-only order-book/funding-rate data — this version
**genuinely reuses the app's existing evaluation criteria**: `scanner.py`'s
`score_from_history()` (which calls `scorer.py`'s `calculate_score()`) is the same
function the scanner already runs for every coin it scans, fed by the same
`market_flow.py` Binance data and the same `storage.py` multi-source price fetch. This
resolves the earlier gap between what FR-005 claimed and what was actually
implemented (see `research.md`).

## Technical Context

**Language/Version**: Python (matches existing codebase; no per-feature language
choice). No version is pinned anywhere in the repo's `requirements.txt`; developed
against the interpreter already installed locally (Python 3.14.6).

**Primary Dependencies**: Flask (existing), `yfinance` (existing — used for the
single-ticker hourly OHLCV history `score_from_history()` needs), `requests`
(existing — Binance/CoinGecko calls already in `storage.py`/`market_flow.py`),
`sqlite3` (stdlib, via `storage.py`), `pytest` (added during the stock version, kept).
No new third-party dependencies are introduced.

**Storage**: The existing SQLite database at `data/crypto_watcher.db`. The
`ticker_lookups` table added during the stock version is reused as-is (its schema —
ticker/price/price_type/recommendation/looked_up_at — is already asset-agnostic); only
the *meaning* of `price_type`'s values changes (see Constraints below and
research.md).

**Testing**: `pytest` (already adopted). Existing stock-specific tests
(`tests/test_stock_lookup.py`) will be reworked to test the crypto module instead of
being kept as a second, parallel suite.

**Target Platform**: Same as the existing app — local Flask development server
(`app.py`), single-user, no deployment/hosting target defined in the repo.

**Project Type**: Web application — server-rendered HTML (Jinja2 templates) with a
small vanilla-JS `fetch()` call for the in-progress/result update behavior, matching
the existing app's architecture and reusing the same interaction pattern the stock
version already validated (see research.md — this part carries over unchanged).

**Performance Goals**: Matches SC-002 — price and recommendation displayed within 5
seconds for at least 95% of lookups of an actively traded ticker. The dominant cost is
now a single-ticker `yfinance` hourly-history fetch (for `score_from_history()`) plus
one `fetch_latest_price()` call (Binance-first, with fallbacks) — both bounded,
single-ticker operations already used elsewhere in the app for individual coins.

**Constraints**: Crypto markets trade continuously, so there is no "market closed"
case the way there was for stocks. `price_type` is redefined around *data-source
freshness* instead: `"live"` when `fetch_latest_price()`'s fastest source (Binance
spot ticker) answered, `"delayed"` when it had to fall back to a slower source (Yahoo
1m/1h or CoinGecko simple price), per FR-011's updated wording. Each lookup makes a
bounded number of real network calls (price fetch, hourly history, market-flow); all
must have explicit timeouts so a slow/unreachable response degrades to the FR-008
warning rather than hanging.

**Scale/Scope**: Single-user local app (no auth, no multi-tenancy). The
`ticker_lookups` history table only needs to comfortably hold personal usage volume;
no scale-out concerns.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this feature complies |
|---|---|
| I. Zero Loophole Execution | Every branch is explicit and required by a spec FR: not-found ticker (FR-007), unreachable/erroring data source (FR-008), empty submission (FR-009), history-write failure (FR-014). The lookup orchestration function returns one of a closed set of outcomes (`ok` / `not_found` / `unavailable`) — no branch falls through undefined. |
| II. Mandatory Failure Warnings (NON-NEGOTIABLE) | All failure branches surface a visible warning in the page UI (not just server logs), via the JSON contract in `contracts/` and a warning element in the crypto lookup template. |
| III. Process Visibility | The client-side `fetch()` shows a loading state immediately on submit and replaces it with either the result or a warning when the response arrives (FR-006) — carried over unchanged from the stock version. |
| IV. UI Text Integrity | The template reuses the same CSS conventions validated during the stock version (`.error-state`, card/stat-row patterns, explicit `overflow-wrap`/`min-width:0` rules) which already wrap/contain dynamic text; must be re-verified per quickstart.md once ticker/price/recommendation values are crypto-shaped (FR-012). |
| V. Live API Integrity | Price, history, and market-flow data all come from live calls to Binance/Yahoo/CoinGecko via the app's existing `storage.py`/`market_flow.py`/`scanner.py` functions; responses are validated before being shown as a result, never substituted with placeholder data (FR-003, FR-011). |
| VI. Data Durability | Every completed lookup is written to `ticker_lookups` before being considered "saved"; a write failure produces the FR-014 warning rather than silently dropping the record. |

No violations requiring justification — this feature reuses existing app
architecture, dependencies, and (now, genuinely) existing scoring logic rather than
introducing new patterns. Complexity Tracking is not needed.

**Post-Phase 1 re-check**: The table above already reflects the finished design
(`research.md`'s reuse decisions, `data-model.md`'s `ticker_lookups` table with its
redefined `price_type` values, and `contracts/crypto-lookup-endpoint.md`'s explicit
success/not_found/unavailable/save-failure response shapes). No new gate violations
were introduced during Phase 1 design.

## Project Structure

### Documentation (this feature)

```text
specs/001-stock-ticker-lookup/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command) — crypto-lookup-endpoint.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan;
                          #   must be regenerated to reflect the rename/rework below)
```

### Source Code (repository root)

```text
app.py                   # Flask routes — rework GET /stock -> GET /crypto (page) and
                          #   GET /stock_lookup -> GET /crypto_lookup (JSON)
crypto_lookup.py          # RENAME/REWORK of stock_lookup.py: orchestrates
                           #   storage.fetch_latest_price() + scanner.fetch_market_data()
                           #   + scanner.score_from_history() + market_flow.fetch_market_flow()
                           #   for one on-demand ticker
storage.py                # ticker_lookups table / save_ticker_lookup() / list_ticker_lookups()
                           #   already exist and are reused as-is (asset-agnostic schema);
                           #   fetch_latest_price() (already crypto-native) is now called
                           #   directly instead of being reimplemented
scanner.py                # existing score_from_history()/fetch_market_data()/get_ticker_frame()
                           #   reused directly, unchanged
market_flow.py            # existing fetch_market_flow() reused directly, unchanged
scorer.py                 # existing calculate_score() reused directly (via score_from_history()),
                           #   unchanged
config.py                 # existing MIN_BUY_SCORE / MIN_SELL_SCORE thresholds reused, now
                           #   applied to the real quick_win_score/long_term_score outputs

templates/
├── index.html            # nav button already added during the stock version; only its
│                          #   label/target may need updating (Stock Lookup -> Crypto Lookup,
│                          #   url_for('stock_page') -> url_for('crypto_page'))
└── crypto.html            # RENAME/REWORK of stock.html: same structure (input, loading,
                            #   warning, result states), crypto-appropriate copy/examples

static/
└── style.css               # existing lookup-page styles from the stock version are reused
                             #   as-is (asset-agnostic — ticker/price/recommendation/warning
                             #   containers, no stock-specific styling exists)

tests/
├── conftest.py              # existing temp-DB fixture reused as-is
├── test_crypto_lookup.py    # RENAME/REWORK of test_stock_lookup.py: same test shapes
│                             #   (recommendation mapping, not-found/unavailable detection,
│                             #   ok+save-failure), fed by mocked scanner/market_flow/storage
│                             #   calls instead of a mocked yfinance.Ticker
└── test_storage_ticker_lookups.py  # unchanged — already asset-agnostic
```

**Structure Decision**: Same flat, single-application Flask layout the stock version
established — no new structural pattern is introduced. The change is a rename +
rework of the feature-specific files (`stock_lookup.py` → `crypto_lookup.py`,
`stock.html` → `crypto.html`, their routes and tests) plus new direct calls into
`scanner.py`/`market_flow.py`/`scorer.py`, which were already present in the codebase
and are now wired into the on-demand lookup path instead of only the batch scanner
path. `storage.py`'s `ticker_lookups` table, `save_ticker_lookup()`,
`list_ticker_lookups()`, and `fetch_latest_price()` all carry over unchanged.

## Complexity Tracking

Not applicable — the Constitution Check above found no violations to justify.
