# Implementation Plan: Stock Ticker Lookup

**Branch**: `001-stock-ticker-lookup` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-stock-ticker-lookup/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a new page to the existing Flask app where a user types a stock ticker, submits
it, and sees that ticker's current (or last-close) price plus a Buy/Sell/Hold
recommendation — reached via a new button on the main page. Price data is fetched
live from `yfinance` (already a dependency, already used for market data in
`scanner.py`). Because the app's existing recommendation logic (`scorer.py`) scores
crypto order-book/funding-rate signals that don't exist for equities, the
recommendation for this feature is computed from real, yfinance-sourced technical
signals (price momentum, moving-average trend, volume trend) using the same
score → threshold → signal architecture the app already uses elsewhere (see
`research.md`). Every completed lookup is persisted to a new SQLite table
(`ticker_lookups`) via `storage.py`, following the app's existing
`init_db()`/`save_scan()` pattern.

## Technical Context

**Language/Version**: Python (matches existing codebase; no per-feature language
choice). No version is pinned anywhere in the repo's `requirements.txt`; developed
against the interpreter already installed locally (Python 3.14.6).

**Primary Dependencies**: Flask (existing, server-rendered HTML + routes), `yfinance`
(existing, already used in `scanner.py` for market data — reused here for stock
price/history), `sqlite3` (Python stdlib, already used via `storage.py`). No new
third-party dependencies are introduced.

**Storage**: The existing SQLite database at `data/crypto_watcher.db` (via
`storage.py`'s `get_connection()`/`init_db()`). A new `ticker_lookups` table is added
alongside the existing `scans`/`scan_results` tables.

**Testing**: No test suite exists in the repo today. `pytest` is adopted as the
testing framework — the de facto standard for Python and needed to exercise the
error branches this feature's constitution compliance requires (invalid ticker,
unreachable data source, failed history write) without making live network calls in
every test run.

**Target Platform**: Same as the existing app — local Flask development server
(`app.py`), single-user, no deployment/hosting target defined in the repo.

**Project Type**: Web application — server-rendered HTML (Jinja2 templates) with
small vanilla-JS `fetch()` calls for the in-progress/result update behavior, matching
the existing app's architecture (e.g., the `/start_scan` + `/scan_status` polling
pattern already in `app.py`). No SPA framework, no separate frontend/backend split.

**Performance Goals**: Matches SC-002 — price and recommendation displayed within 5
seconds for at least 95% of lookups of an actively traded ticker. Bounded almost
entirely by `yfinance` network latency for a single ticker (no batch download needed,
unlike the multi-symbol `yf.download` in `scanner.py`).

**Constraints**: One external network call (to Yahoo Finance via `yfinance`) per
lookup, with a bounded timeout so a slow/unreachable response degrades to the FR-008
warning rather than hanging the request indefinitely. No offline mode or response
caching is required by the spec.

**Scale/Scope**: Single-user local app (no auth, no multi-tenancy — matches the rest
of the app). The `ticker_lookups` history table only needs to comfortably hold
personal usage volume (tens to low thousands of rows); no scale-out concerns.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this feature complies |
|---|---|
| I. Zero Loophole Execution | Every branch is explicit and required by a spec FR: not-found ticker (FR-007), unreachable/erroring data source (FR-008), empty submission (FR-009), history-write failure (FR-014). The lookup orchestration function must return one of a closed set of outcomes (success / not-found / unavailable) — no branch is allowed to fall through undefined. |
| II. Mandatory Failure Warnings (NON-NEGOTIABLE) | All failure branches above surface a visible warning in the page UI (not just server logs), via the JSON error contract in `contracts/` and a warning element in `stock.html`. |
| III. Process Visibility | The client-side `fetch()` call shows a loading state immediately on submit and replaces it with either the result or a warning when the response arrives (FR-006). |
| IV. UI Text Integrity | `stock.html` reuses the existing CSS conventions (`.error-state`, card/stat-row patterns) which already wrap/contain dynamic text; the page must be manually verified (per quickstart.md) with long tickers/messages before the feature is done (FR-012). |
| V. Live API Integrity | Price and history data come only from live `yfinance` calls; the response is validated (non-empty history / valid price) before being shown as a result, never substituted with placeholder data (FR-003, FR-011). |
| VI. Data Durability | Every completed lookup is written to the new `ticker_lookups` table before being considered "saved"; a write failure produces the FR-014 warning rather than silently dropping the record. |

No violations requiring justification — this feature reuses the existing app's
architecture, dependencies, and storage conventions rather than introducing new
patterns. Complexity Tracking is not needed.

**Post-Phase 1 re-check**: The table above already reflects the finished design
(`research.md`'s scoring/price/error-detection decisions, `data-model.md`'s
`ticker_lookups` table, and `contracts/stock-lookup-endpoint.md`'s explicit
success/not_found/unavailable/save-failure response shapes). No new gate violations
were introduced during Phase 1 design — the closed set of response `status` values
in the contract is what makes Principle I (Zero Loophole Execution) concretely
checkable at implementation time.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
app.py                  # Flask routes — add GET /stock (page) and GET /stock_lookup (JSON)
stock_lookup.py         # NEW: fetch price + compute recommendation for one ticker
storage.py              # extend: init_db() gains ticker_lookups table; add
                         #   save_ticker_lookup() / list_ticker_lookups()
config.py               # existing MIN_BUY_SCORE / MIN_SELL_SCORE thresholds reused

templates/
├── index.html           # add nav button to the new page (mirrors existing
│                         #   `<a class="reset-button" href="...">` links)
└── stock.html            # NEW: ticker input, loading state, result/warning display

static/
└── style.css             # extend with the new page's styles, reusing existing
                           #   conventions (.error-state, stat-row/card patterns)

tests/                    # NEW — no test directory exists yet in the repo
└── test_stock_lookup.py  # unit tests for stock_lookup.py's branches (found /
                           #   not-found / unavailable) and storage save/read
```

**Structure Decision**: The repository does not use any of the template's
src/tests or backend/frontend split options — it is a flat, single-application
Flask project (`app.py` + feature modules + `templates/` + `static/` +
`storage.py`). This feature follows that existing convention exactly: one new
module (`stock_lookup.py`), one new template, two new routes in `app.py`, and
additive changes to `storage.py`/`style.css`. A `tests/` directory is newly added
since none currently exists, using `pytest` per the Technical Context decision.

## Complexity Tracking

Not applicable — the Constitution Check above found no violations to justify.
