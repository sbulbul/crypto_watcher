---

description: "Task list template for feature implementation"
---

# Tasks: Crypto Ticker Lookup

**Input**: Design documents from `/specs/001-stock-ticker-lookup/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present, rewritten for the stock→crypto pivot)

**Tests**: Included — carried over from the stock version's decision to use `pytest`
for this feature's constitution-required failure branches (not-found ticker,
unavailable data source, failed history write).

**Organization**: Tasks are grouped by user story (spec.md: US1 P1, US2 P2, US3 P3).
This is a **rework of an already-implemented feature**, not a from-scratch build: the
prior stock-ticker implementation is being renamed and its lookup logic replaced with
real calls into the app's existing crypto scoring pipeline (`scanner.py`,
`market_flow.py`, `scorer.py`) per `research.md`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task includes exact file path(s)

## Path Conventions

Flat, single Flask application (no `src/`/`backend`/`frontend` split) — see
`plan.md`'s Project Structure. Paths below are relative to the repository root
(`crypto_watcher/`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure.

No new tasks — `pytest` (in `requirements.txt`), `tests/__init__.py`, and
`tests/conftest.py`'s temp-DB fixture were already added during the stock-version
implementation and require no changes for this pivot.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can be
implemented.

No new tasks — the `ticker_lookups` table, `save_ticker_lookup()`,
`list_ticker_lookups()` (`storage.py`), and the lookup page's CSS
(`static/style.css`'s `.lookup-result`/`.recommendation-badge`/`.lookup-stat-row`/
`.save-warning` rules) are already asset-agnostic and are reused unchanged (see
plan.md's Project Structure and data-model.md). Unlike the stock version, this
pivot's route/page cutover is **not** safe to do before the new lookup logic exists
(it would leave the app importing a module that doesn't work yet), so that work is
sequenced inside User Story 1 below instead of Foundational.

**Checkpoint**: Nothing blocks User Story 1 — the existing `/stock` route keeps
working with the old code until US1 explicitly cuts it over.

---

## Phase 3: User Story 1 - Look up a ticker's price and recommendation (Priority: P1) 🎯 MVP

**Goal**: A user enters a valid crypto ticker on the lookup page and sees its current
(or delayed) price and a Buy/Sell/Hold recommendation, derived from the app's real
scanner scoring instead of the stock version's improvised technical-indicator score.

**Independent Test**: Open `/crypto` directly, enter a known valid ticker (e.g.
`BTC`), submit, and confirm a price and a Buy/Sell/Hold recommendation are both
displayed (quickstart.md section 3).

### Tests for User Story 1

- [X] T001 [P] [US1] Write unit tests for the recommendation mapping in
      `tests/test_crypto_lookup.py` (new file): mock `scanner.score_from_history()`'s
      `quick_win_score`/`long_term_score` output and assert the Buy/Sell/Hold mapping
      against `config.py`'s `MIN_BUY_SCORE`/`MIN_SELL_SCORE`, per research.md's
      "Recommendation methodology" decision

### Implementation for User Story 1

- [X] T002 [US1] Create `crypto_lookup.py` (new file) with
      `normalize_ticker(raw_ticker)`: uppercase, trim, and append the `-USD` suffix
      if missing, per data-model.md's normalization rule
- [X] T003 [US1] In `crypto_lookup.py`, implement price retrieval by calling
      `storage.fetch_latest_price(ticker)` directly and mapping its `source` field to
      `price_type` (`"live"` when `source == "Binance spot"`, `"delayed"`
      otherwise), per research.md's price-retrieval decision (same file as T002 —
      sequential)
- [X] T004 [US1] In `crypto_lookup.py`, implement recommendation derivation:
      `scanner.fetch_market_data([ticker])` + `scanner.get_ticker_frame()` for
      hourly history, `market_flow.fetch_market_flow(ticker, current_price)` for
      order-book/funding signals, `scanner.score_from_history(coin, hist,
      market_flow)` for the real dual score, then map `long_term_score`/
      `quick_win_score` to Buy/Sell/Hold via `config.py`'s thresholds (FR-004,
      FR-005; research.md) (same file as T002/T003 — sequential). Also added
      `_find_universe_coin()`, restricting recommendations to tickers in the app's
      tracked universe (`universe.get_crypto_universe()`) since that's the actual
      boundary of what the scanner's evaluation criteria can score (documented in
      code comments; a natural consequence of research.md's reuse decision).
- [X] T005 [US1] Implement `lookup_ticker(ticker)` in `crypto_lookup.py`, combining
      T003 + T004 into one Ticker Lookup Result dict with `status="ok"` on success
      (FR-003, FR-004; data-model.md) (depends on T003, T004)
- [X] T006 [US1] In `lookup_ticker()`, call `save_ticker_lookup()` on every
      `status="ok"` result; if the save call fails, keep the price/recommendation in
      the returned result and add the FR-014 save-failure warning rather than
      discarding it (`save_ticker_lookup()` itself is unchanged from the stock
      version) (depends on T005)
- [X] T007 [US1] Cut over `app.py`: change the import from `stock_lookup` to
      `crypto_lookup`, rename the `stock_page` / `GET /stock` route to `crypto_page`
      / `GET /crypto` (rendering `templates/crypto.html`), and rename
      `stock_lookup_route` / `GET /stock_lookup` to `crypto_lookup_route` /
      `GET /crypto_lookup` calling the new `lookup_ticker()` (depends on T006). Also
      updated `templates/index.html`'s nav link immediately in the same pass (see
      T010 note) — leaving it pointing at the removed `stock_page` endpoint broke
      the home page (`BuildError`), so that update couldn't wait for a later phase.
- [X] T008 [US1] Create `templates/crypto.html` (new file, adapted from
      `templates/stock.html` — the input/loading/warning/result markup and JS are
      asset-agnostic and carry over almost unchanged): update copy ("Stock
      Lookup"→"Crypto Lookup", ticker placeholder "e.g. AAPL"→"e.g. BTC"), and point
      its `fetch()` call at `{{ url_for('crypto_lookup_route') }}` (depends on T007)
- [X] T009 [US1] Delete the now-superseded `stock_lookup.py`, `templates/stock.html`,
      and `tests/test_stock_lookup.py` — fully replaced per the pivot decision, not
      kept alongside the crypto version (depends on T001, T007, T008). Verified via
      a fresh app instance afterward: home page 200 with the new nav button, `/crypto`
      200, old `/stock` correctly 404s, full pytest suite (15/15) still green.

**Checkpoint**: User Story 1 is fully functional and independently testable
(quickstart.md section 3), and quickstart.md section 8 (recommendation consistency
with the scanner) becomes checkable for the first time.

---

## Phase 4: User Story 2 - Reach the lookup page from the main page (Priority: P2)

**Goal**: A user on the main page can find and click a button that takes them to the
crypto lookup page.

**Independent Test**: Load the main page, locate the nav button, click it, and
confirm the user lands on `/crypto` (quickstart.md section 2).

### Implementation for User Story 2

- [X] T010 [US2] Update the nav button in `templates/index.html` (already added
      during the stock version): change its label "Stock Lookup"→"Crypto Lookup" and
      `url_for('stock_page')`→`url_for('crypto_page')` (FR-001) (depends on T007).
      Done as part of T007's cutover rather than as a separate later step — see
      T007's note.

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Get a clear warning when a lookup fails (Priority: P3)

**Goal**: A user who enters a nonexistent ticker, hits an unreachable data source, or
submits an empty ticker always sees a clear, visible warning instead of a blank or
broken result.

**Independent Test**: Submit a ticker that does not exist and confirm a visible
warning appears with no price/recommendation shown (quickstart.md section 4).

### Tests for User Story 3

- [X] T011 [US3] Unit test for `lookup_ticker()`'s not-found detection (every price/
      history source returns no usable data → `status="not_found"`) in
      `tests/test_crypto_lookup.py`, per research.md's not-found decision (same file
      as T001 — sequential). Covers three distinct not-found paths: ticker outside
      the tracked universe, price fetch returns nothing, scanner produces no score.
- [X] T012 [US3] Unit test for `lookup_ticker()`'s unavailable detection (an
      unexpected exception propagates from the pipeline → `status="unavailable"`) in
      `tests/test_crypto_lookup.py`, per research.md's unavailable decision (same
      file as T011 — sequential)

### Implementation for User Story 3

- [X] T013 [US3] Extend `lookup_ticker()` in `crypto_lookup.py` to return
      `status="not_found"` with a warning message when price/history retrieval
      yields no usable data (FR-007) (depends on T005)
- [X] T014 [US3] Extend `lookup_ticker()` in `crypto_lookup.py` to return
      `status="unavailable"` with a warning message when an unexpected exception
      propagates from the pipeline (FR-008) (same file as T013 — sequential)
- [X] T015 [US3] Verify `GET /crypto_lookup` in `app.py` passes through the
      `not_found` / `unavailable` JSON shapes from
      `contracts/crypto-lookup-endpoint.md` unchanged (it already just
      `jsonify()`s `lookup_ticker()`'s return value, per T007) (depends on T013,
      T014, T007). Confirmed live via curl against a running instance — both shapes
      match the contract exactly.
- [X] T016 [US3] Verify `templates/crypto.html`'s JS (carried over from
      `stock.html` in T008) correctly renders the warning-only state and the
      empty-ticker client-side prompt for crypto inputs/messages (FR-007, FR-008,
      FR-009) (depends on T008, T015)

**Checkpoint**: All user stories are independently functional (quickstart.md
sections 3-4).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the constitution-driven, cross-story guarantees that don't
belong to a single user story, re-checked against crypto-shaped data.

- [X] T017 [P] Verify `static/style.css`'s existing lookup-page styles handle
      crypto-shaped values (longer tickers like "BTC-USD", sub-$1 coin price
      formatting) without overlap/cutoff at a narrow (~360px) and a wide desktop
      width (FR-012, SC-005; quickstart.md section 6). Same conclusion as the stock
      version's review (`.recommendation-badge`/`.lookup-stat-row`/`#warningText`
      all use `overflow-wrap: anywhere` and the existing 720px/480px breakpoints
      stack `.card-main` vertically): no overlap risk from the CSS side. Note:
      `formatPrice()` in `crypto.html`'s JS always shows exactly 2 decimal places
      (matching `app.py`'s existing `fmt_price` filter convention elsewhere), so a
      very low-priced altcoin would display as "$0.00" — a precision limitation
      shared with the rest of the app, not an overlap/cutoff defect. As with the
      stock version, this environment's browser automation can't reach this
      sandbox's localhost, so this remains a static/reasoned check, not a
      screenshot — worth a quick look in your own browser.
- [X] T018 Run through all 8 sections of `quickstart.md` end-to-end — including the
      new section 8 (recommendation consistency between a scan and a lookup for the
      same coin) — and fix any discrepancies found. Sections 1-5 and 7 verified via
      curl/pytest/direct calls against running instances (see T007/T009/T015 notes
      and below); section 6 not directly observable here (see T017); section 8 is
      structurally guaranteed rather than spot-checked — `crypto_lookup.py` calls
      `scanner.score_from_history()` directly, the exact function `scan_market()`
      uses, so there is no separate implementation that could drift out of sync.
- [X] T019 [P] Verify rows written to `ticker_lookups` still survive an app restart,
      now with the redefined `price_type` values (`live`/`delayed`) (quickstart.md
      section 5; Constitution Principle VI — Data Durability). Confirmed: BTC/ETH
      lookups written by one process were read back with `price_type: "live"` by a
      separate, later process.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No new tasks — reused as-is
- **Foundational (Phase 2)**: No new tasks — reused as-is; does NOT block User
  Story 1 the way it did in the original build, since there's no new shared infra
  to wait on
- **User Story 1 (Phase 3)**: Can start immediately. Its own internal ordering is
  strict: T001 (test) → T002→T003→T004 (same file, sequential) → T005 → T006 → T007
  (app.py cutover) → T008 (template) → T009 (delete old files)
- **User Story 2 (Phase 4)**: Depends on T007 (the route rename) — cannot update
  `index.html`'s `url_for('crypto_page')` reference before that route exists
- **User Story 3 (Phase 5)**: Depends on T005 (extends the same `lookup_ticker()`)
  and, for T015/T016, on T007/T008 (the cutover) having happened
- **Polish (Phase 6)**: Depends on US1, US2, and US3 all being complete

### Within Each User Story

- Tests before implementation (T001 before T002-T009; T011/T012 before T013/T014)
- `crypto_lookup.py` functions before the `app.py` cutover before the template
- Old stock files are deleted only after their replacements are verified working
  (T009 depends on T001's tests passing against the new module, plus T007/T008)

### Parallel Opportunities

- Nothing in Setup/Foundational (no new tasks)
- T001 has no same-file conflict within Phase 3 at the time it's written (tests
  precede implementation), so it is marked [P]
- T017 and T019 (Polish) — different concerns, independent verification passes

---

## Parallel Example: Polish phase

```bash
Task: "Verify static/style.css handles crypto-shaped values without overlap/cutoff"
Task: "Verify ticker_lookups rows survive an app restart with live/delayed price_type values"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 3: User Story 1 (Phases 1 and 2 have no new work)
2. **STOP and VALIDATE**: run quickstart.md sections 3 and 8 against the running app
3. This alone is a demoable MVP — a user can reach `/crypto` directly, look up a
   ticker, and see a price + recommendation that matches the scanner's own scoring

### Incremental Delivery

1. User Story 1 → validate independently → MVP demoable, old `/stock` route retired
2. Add User Story 2 → validate independently → main-page discoverability updated
3. Add User Story 3 → validate independently → failure warnings verified against the
   new crypto data sources
4. Polish → run full quickstart.md, confirm UI text integrity and data durability
   still hold with crypto-shaped data

---

## Notes

- [P] tasks touch different files with no ordering dependency between them
- Tasks against the same file (`crypto_lookup.py`, or `tests/test_crypto_lookup.py`)
  are intentionally left unmarked/sequential to avoid conflicting edits
- `tests/test_storage_ticker_lookups.py` and `tests/conftest.py` need no changes and
  have no corresponding task — they were already asset-agnostic
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently before continuing
