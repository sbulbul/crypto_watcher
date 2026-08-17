---

description: "Task list template for feature implementation"
---

# Tasks: Stock Ticker Lookup

**Input**: Design documents from `/specs/001-stock-ticker-lookup/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Included — `plan.md`'s Technical Context and Project Structure explicitly
adopt `pytest` specifically to exercise this feature's constitution-required failure
branches (not-found ticker, unavailable data source, failed history write).

**Organization**: Tasks are grouped by user story (spec.md: US1 P1, US2 P2, US3 P3)
to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task includes exact file path(s)

## Path Conventions

This repo is a flat, single Flask application (no `src/`/`backend`/`frontend`
split) — see `plan.md`'s Project Structure. Paths below are relative to the
repository root (`crypto_watcher/`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the testing infrastructure this feature needs; nothing else to
initialize since the Flask app/dependencies already exist.

- [ ] T001 [P] Add `pytest` to `requirements.txt`
- [ ] T002 [P] Create `tests/__init__.py` (empty) so `tests/` is a discoverable package
- [ ] T003 [P] Create `tests/conftest.py` with a fixture that points `storage.DB_PATH`
      at a temporary SQLite file for the duration of each test (so the test suite
      never reads/writes `data/crypto_watcher.db`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared page route, template shell, DB schema, and persistence
functions that every user story builds on or links to.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Add the `ticker_lookups` table (per `data-model.md`'s schema) to
      `init_db()` in `storage.py`
- [ ] T005 Add `save_ticker_lookup(ticker, price, price_type, recommendation, looked_up_at)`
      and `list_ticker_lookups(limit=10)` functions to `storage.py` (depends on T004)
- [ ] T006 Add a `GET /stock` route in `app.py` that renders a new
      `templates/stock.html` page shell (ticker input field, submit control, and
      empty result/warning containers — no lookup logic wired up yet)
- [ ] T007 [P] Add base styles for the new page's input, submit control, and
      result/warning containers to `static/style.css`, reusing existing conventions
      (`.error-state`, stat-row/card patterns) so text-wrapping is correct from the
      start (FR-012)

**Checkpoint**: Foundation ready — `/stock` page exists and is reachable directly by
URL; user story implementation can now begin.

---

## Phase 3: User Story 1 - Look up a ticker's price and recommendation (Priority: P1) 🎯 MVP

**Goal**: A user enters a valid stock ticker on the lookup page and sees its current
(or last-close) price and a Buy/Sell/Hold recommendation.

**Independent Test**: Open `/stock` directly, enter a known valid ticker (e.g.
`AAPL`), submit, and confirm a price and a Buy/Sell/Hold recommendation are both
displayed (quickstart.md section 3).

### Tests for User Story 1

- [ ] T008 [P] [US1] Unit tests for `compute_recommendation()`'s score→signal mapping
      (Buy/Sell/Hold boundaries against `config.py`'s `MIN_BUY_SCORE`/`MIN_SELL_SCORE`)
      in `tests/test_stock_lookup.py`
- [ ] T009 [P] [US1] Unit tests for `save_ticker_lookup()` / `list_ticker_lookups()`
      round-trip in `tests/test_storage_ticker_lookups.py`

### Implementation for User Story 1

- [ ] T010 [US1] Implement `fetch_stock_price(ticker)` in `stock_lookup.py` using
      `yfinance` to retrieve the latest price, setting `price_type` to `"live"` or
      `"last_close"` per FR-011 / research.md's price-retrieval decision
- [ ] T011 [US1] Implement `compute_recommendation(ticker)` in `stock_lookup.py`:
      derive a momentum / moving-average-trend / volume-trend score from `yfinance`
      history, and map it to Buy/Sell/Hold using `config.py`'s `MIN_BUY_SCORE` /
      `MIN_SELL_SCORE` thresholds (FR-004, FR-005; research.md's recommendation
      decision) (same file as T010 — sequential)
- [ ] T012 [US1] Implement `lookup_ticker(ticker)` in `stock_lookup.py`, combining
      T010 + T011 into one Ticker Lookup Result dict with `status="ok"` on success
      (FR-003, FR-004; data-model.md) (depends on T010, T011)
- [ ] T013 [US1] In `lookup_ticker()`, call `save_ticker_lookup()` on every
      `status="ok"` result; if the save call fails, keep the price/recommendation in
      the returned result and add the FR-014 save-failure warning rather than
      discarding it (depends on T012, T005)
- [ ] T014 [US1] Implement `GET /stock_lookup?ticker=` in `app.py`, calling
      `lookup_ticker()` and returning the success JSON shape defined in
      `contracts/stock-lookup-endpoint.md` (depends on T013)
- [ ] T015 [US1] Implement the client-side JS in `templates/stock.html`: on submit,
      show a loading state immediately, call `/stock_lookup`, and render the
      price/price_type/recommendation on success; every new submission starts a
      fresh request and its response replaces whatever is currently shown or loading
      (FR-006, FR-010, FR-010a) (depends on T006, T014)

**Checkpoint**: User Story 1 is fully functional and independently testable
(quickstart.md section 3).

---

## Phase 4: User Story 2 - Reach the lookup page from the main page (Priority: P2)

**Goal**: A user on the main page can find and click a button that takes them to
the ticker lookup page.

**Independent Test**: Load the main page, locate the new button, click it, and
confirm the user lands on `/stock` (quickstart.md section 2).

### Implementation for User Story 2

- [ ] T016 [US2] Add a clearly labeled nav button/link to `templates/index.html`
      pointing to `url_for('stock_page')`, mirroring the existing
      `<a class="reset-button" href="...">` links (FR-001) (depends on T006)

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Get a clear warning when a lookup fails (Priority: P3)

**Goal**: A user who enters a nonexistent ticker, hits an unreachable data source,
or submits an empty ticker always sees a clear, visible warning instead of a blank
or broken result.

**Independent Test**: Submit a ticker that does not exist and confirm a visible
warning appears with no price/recommendation shown (quickstart.md section 4).

### Tests for User Story 3

- [ ] T017 [US3] Unit test for `lookup_ticker()`'s not-found detection (empty/missing
      `yfinance` data → `status="not_found"`) in `tests/test_stock_lookup.py`
      (same file as T008 — sequential)
- [ ] T018 [US3] Unit test for `lookup_ticker()`'s unavailable-source detection
      (network error/timeout/malformed response → `status="unavailable"`) in
      `tests/test_stock_lookup.py` (same file as T017 — sequential)

### Implementation for User Story 3

- [ ] T019 [US3] Extend `lookup_ticker()` in `stock_lookup.py` to return
      `status="not_found"` with a warning message when `yfinance` returns no usable
      price/history for the ticker (FR-007; research.md's error-detection decision)
      (depends on T012)
- [ ] T020 [US3] Extend `lookup_ticker()` in `stock_lookup.py` to return
      `status="unavailable"` with a warning message on network error, timeout, or
      malformed response (FR-008; research.md's error-detection decision) (same file
      as T019 — sequential)
- [ ] T021 [US3] Update `GET /stock_lookup` in `app.py` to pass through the
      `not_found` / `unavailable` JSON shapes from
      `contracts/stock-lookup-endpoint.md` (depends on T019, T020, T014)
- [ ] T022 [US3] Update the client-side JS in `templates/stock.html` to render a
      warning-only state (no price/recommendation) for `not_found`/`unavailable`
      responses, and to prompt the user to enter a ticker client-side — without
      calling `/stock_lookup` — when the input is empty (FR-007, FR-008, FR-009)
      (depends on T015, T021)

**Checkpoint**: All user stories are independently functional (quickstart.md
sections 3-4).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the constitution-driven, cross-story guarantees that don't
belong to a single user story.

- [ ] T023 [P] Verify and adjust `static/style.css` so ticker, price, recommendation,
      and warning text never overlap or get cut off at a narrow (~360px) and a wide
      desktop width (FR-012, SC-005; quickstart.md section 6)
- [ ] T024 Run through all 7 sections of `quickstart.md` end-to-end and fix any
      discrepancies found
- [ ] T025 [P] Verify rows written to the `ticker_lookups` table in
      `data/crypto_watcher.db` survive an app restart (quickstart.md section 5;
      Constitution Principle VI — Data Durability)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends only on Foundational
- **User Story 2 (Phase 4)**: Depends only on Foundational (reuses the `/stock`
  route T006 created; does not require US1's lookup logic to work)
- **User Story 3 (Phase 5)**: Depends on Foundational, and extends the
  `lookup_ticker()` / `/stock_lookup` / `stock.html` surfaces US1 created (T012,
  T014, T015) — implement after US1 for a working codebase, though its test cases
  (T017, T018) can be drafted earlier
- **Polish (Phase 6)**: Depends on US1, US2, and US3 all being complete

### Within Each User Story

- Tests before implementation (write T008/T009 and T017/T018 first; confirm they
  fail before the corresponding implementation task)
- `stock_lookup.py` functions before the `/stock_lookup` route before the page's JS
- Story complete and checkpointed before moving to the next priority

### Parallel Opportunities

- T001, T002, T003 (Setup) — different files, no dependencies
- T006 and T007 (Foundational) — different files, no dependency on T004/T005
- T008 and T009 (US1 tests) — different files
- T023 and T025 (Polish) — different concerns, independent verification passes

---

## Parallel Example: Phase 1 (Setup)

```bash
Task: "Add pytest to requirements.txt"
Task: "Create tests/__init__.py (empty)"
Task: "Create tests/conftest.py with a temp-DB fixture for storage.DB_PATH"
```

## Parallel Example: User Story 1 tests

```bash
Task: "Unit tests for compute_recommendation() in tests/test_stock_lookup.py"
Task: "Unit tests for save_ticker_lookup()/list_ticker_lookups() in tests/test_storage_ticker_lookups.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks everything else)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md section 3 against the running app
5. This alone is a demoable MVP — a user can reach `/stock` directly, look up a
   ticker, and see a price + recommendation

### Incremental Delivery

1. Setup + Foundational → `/stock` page exists and is reachable by URL
2. Add User Story 1 → validate independently → MVP demoable
3. Add User Story 2 → validate independently → main-page discoverability shipped
4. Add User Story 3 → validate independently → failure warnings shipped, feature
   considered reliable per the constitution
5. Polish → run full quickstart.md, confirm UI text integrity and data durability

---

## Notes

- [P] tasks touch different files with no ordering dependency between them
- Tasks against the same file (e.g., multiple edits to `stock_lookup.py` or
  `tests/test_stock_lookup.py`) are intentionally left unmarked/sequential to avoid
  conflicting edits
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently before continuing
