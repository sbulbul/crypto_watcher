---

description: "Task list template for feature implementation"
---

# Tasks: Smoke Test Suite

**Input**: Design documents from `/specs/002-smoke-test-suite/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Not a separate layer here — this feature *is* a test suite, so the
Gherkin `.feature` scenarios and their step definitions are the implementation
itself, not something additionally tested. Every scenario created carries the
`@smoke` tag (explicit user request) so the suite can later be filtered with
`npx cucumber-js --tags @smoke`, and every task that produces or extends a scenario
is verified to actually run under Playwright before being marked done.

**Organization**: Tasks are grouped by user story (spec.md: US1 P1, US2 P2, US3 P3).
US1 and US2 both touch the same 3 `.feature` files by design (US1 adds the
text-check half of each scenario, US2 extends the same scenario with its
action-check half) — this is intentional layering, not duplication: after US1 the
suite is already a complete, useful MVP (heading checks only); after US2 the same
scenarios are upgraded in place to also verify each page's primary action.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task includes exact file path(s)

## Path Conventions

New standalone Node/TypeScript project at `smoke-tests/`, alongside (not inside) the
Python app — see plan.md's Project Structure. Paths below are relative to the
repository root (`crypto_watcher/`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the Node/TypeScript project so Cucumber + Playwright can run
at all, including the automatic dependency/driver install (US3's underlying
mechanism — see Phase 5).

- [X] T001 Create `smoke-tests/package.json`: dependencies `@cucumber/cucumber`,
      `playwright`, `typescript`, `ts-node`, `@types/node`; scripts
      `"test": "cucumber-js"` and `"postinstall": "playwright install chromium"`
      (research.md's install-automation decision; FR-007)
- [X] T002 [P] Create `smoke-tests/tsconfig.json` (CommonJS module target
      compatible with `ts-node`'s Cucumber integration)
- [X] T003 [P] Create `smoke-tests/cucumber.cjs`: config pointing at
      `features/**/*.feature` and `step-definitions/**/*.ts`, with
      `requireModule: ['ts-node/register']` so `.ts` step files load directly.
      Dropped the deprecated `publishQuiet` option cucumber-js warned about.
- [X] T004 Run `npm install` inside `smoke-tests/` and confirm it completes with
      exit code 0, `node_modules` populated, and the Playwright Chromium binary
      present afterward (verifies T001-T003's wiring end-to-end; quickstart.md
      section 2) (depends on T001, T002, T003). Confirmed via
      `%LOCALAPPDATA%\ms-playwright`: chromium-1234 installed alongside a
      pre-existing chromium-1228 from something else on this machine — empirically
      resolves the U1 edge case from `/speckit-analyze`: `playwright install`
      correctly fetches whatever version the current `playwright` package needs
      regardless of what's already cached, no extra logic required. `npx
      cucumber-js` runs cleanly with "0 scenarios."

**Checkpoint**: `npx cucumber-js` runs (reporting "0 scenarios" is fine — nothing
written yet) with no missing-dependency errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared World/hooks/step infrastructure every scenario needs — no
feature file can run without this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Create `smoke-tests/step-definitions/world.ts`: custom Cucumber World
      class holding `page`/`browser` (Playwright types) and `baseUrl` (defaults to
      `http://127.0.0.1:5051`, overridable via a `BASE_URL` env var; data-model.md).
      Also exports `DEFAULT_TIMEOUT_MS = 10_000` as the one shared timeout constant
      every step file uses — resolves the A1 ambiguity from `/speckit-analyze`
      (no more per-file ad hoc timeout values).
- [X] T006 Create `smoke-tests/step-definitions/hooks.ts`: `Before` launches a
      Chromium browser + new page onto the World; `After` closes both, even on
      scenario failure (bounded lifecycle — FR-008) (depends on T005)
- [X] T007 [P] Create `smoke-tests/step-definitions/common.steps.ts`: shared steps
      `Given('I am on the {string} page', ...)` (navigates `baseUrl + path` with a
      bounded timeout so an unreachable app fails fast rather than hanging — FR-008)
      and `Then('I should see a heading {string}', ...)` (Playwright
      `getByRole('heading', { name })` assertion) (depends on T005)

**Checkpoint**: Shared step vocabulary exists; any `.feature` file can now use
`Given I am on the "..." page` / `Then I should see a heading "..."`.

---

## Phase 3: User Story 1 - Run a smoke suite that verifies the app's main pages (Priority: P1) 🎯 MVP

**Goal**: Each of the app's 3 covered main pages has an `@smoke`-tagged scenario
confirming it loads with its correct main heading (FR-002, FR-003).

**Independent Test**: With the app running, `npm test` inside `smoke-tests/` reports
3 passing scenarios, each asserting the correct heading for its page
(quickstart.md section 3).

### Implementation for User Story 1

- [X] T008 [P] [US1] Create `smoke-tests/features/home.feature`: `@smoke` scenario
      "Home page loads with its main heading" — Given I am on the "/" page, Then I
      should see a heading "Crypto Hourly Watcher" (contracts/ui-contract.md)
- [X] T009 [P] [US1] Create `smoke-tests/features/crypto-lookup.feature`: `@smoke`
      scenario "Crypto Lookup page loads with its main heading" — Given I am on the
      "/crypto" page, Then I should see a heading "Crypto Lookup"
      (contracts/ui-contract.md)
- [X] T010 [P] [US1] Create `smoke-tests/features/history.feature`: `@smoke`
      scenario "History page loads with its main heading" — Given I am on the
      "/history" page, Then I should see a heading "Scan History"
      (contracts/ui-contract.md)
- [X] T011 [US1] With `python app.py` running, run `npm test` in `smoke-tests/` and
      confirm all 3 scenarios pass (depends on T004, T007, T008, T009, T010).
      Confirmed: 3 scenarios (3 passed), 6 steps (6 passed), 1.6s total.

**Checkpoint**: User Story 1 is fully functional and independently testable — the
suite already delivers real value (catches a broken main page) even before US2.

---

## Phase 4: User Story 2 - Smoke suite exercises each covered page's primary action (Priority: P2)

**Goal**: Each of the 3 already-covered scenarios is extended to also perform and
verify that page's primary action, not just its heading (FR-004).

**Independent Test**: With the app running, `npm test` reports the same 3 scenarios
passing, now with additional steps confirming each page's primary action produced
the expected outcome (quickstart.md section 3).

### Implementation for User Story 2

- [X] T012 [P] [US2] Extend the scenario in `smoke-tests/features/home.feature`:
      add setting the scan limit, clicking "Scan Crypto", and asserting the scan is
      in progress within a bounded wait (research.md — checks "scan started," not
      "scan completed", to stay inside the 3-minute suite budget) (depends on T008).
      **Deviated from the original plan**: the assertion targets
      `#progressPanel.active` instead of literal text "Scanning hourly crypto
      data" — that text is never actually stable (see T013's note). Also added an
      explicit scan-limit-250 step and a final stop-the-scan cleanup step; both
      fixes are documented in contracts/ui-contract.md's "Corrected during
      implementation" section.
- [X] T013 [US2] Create `smoke-tests/step-definitions/home.steps.ts` implementing
      the click and progress-check steps referenced in T012 (depends on T012).
      **Two real bugs found and fixed by actually running this against the live
      app**: (1) `templates/index.html`'s `#progressText` is rewritten by client JS
      through "Preparing crypto universe" then "Scanning N of M" — never the
      static "Scanning hourly crypto data" placeholder — so the assertion now
      checks the stable `#progressPanel.active` class instead of any text; (2) a
      small leftover scan limit could complete in ~4s, racing against Playwright's
      own browser-launch overhead and finishing before the assertion observed it —
      fixed by explicitly setting the limit to 250 before clicking. Also added
      `I stop the scan` (POST `/stop_scan`) so the scenario doesn't leave a
      long-running scan active server-side after it ends. Verified stable across
      4 consecutive full-suite runs.
- [X] T014 [P] [US2] Extend the scenario in
      `smoke-tests/features/crypto-lookup.feature`: add
      `When I look up ticker "BTC"` and
      `Then I should see a result or a warning` within a bounded wait (either
      outcome is a pass per spec's edge-case allowance) (depends on T009)
- [X] T015 [US2] Create `smoke-tests/step-definitions/crypto-lookup.steps.ts`
      implementing the fill-ticker-and-submit step and the result-or-warning-visible
      assertion referenced in T014, using `getByLabel('Ticker symbol')`,
      `getByRole('button', { name: 'Look Up' })`, and the `#resultState` /
      `#warningState` containers (contracts/ui-contract.md) (depends on T014).
      Uses `Promise.any` (not `.race`) so a warning appearing first can't
      spuriously fail the check if the result locator's own timeout happens to
      elapse first.
- [X] T016 [P] [US2] Extend the scenario in `smoke-tests/features/history.feature`:
      add `Then I should see the history list or the empty state` (depends on T010)
- [X] T017 [US2] Create `smoke-tests/step-definitions/history.steps.ts`
      implementing the either/or assertion referenced in T016, checking for
      `.history-table` OR a heading "No saved scans yet" (contracts/ui-contract.md)
      (depends on T016)
- [X] T018 [US2] With `python app.py` running, run `npm test` in `smoke-tests/` and
      confirm all 3 scenarios pass their full heading-and-action checks (depends on
      T013, T015, T017). Confirmed: 3 scenarios (3 passed), 13 steps (13 passed),
      ~3.4s — stable across 4 consecutive runs.
      Along the way, also fixed two Cucumber/TypeScript wiring issues unrelated to
      the app itself: `tsconfig.json`'s `target` needed to be `ES2021` (not
      `ES2020`) for `Promise.any` to type-check, and Cucumber's own default 5s
      step timeout needed raising via `setDefaultTimeout()` in `hooks.ts` since it
      was shorter than `DEFAULT_TIMEOUT_MS` (10s) and would kill a step before
      Playwright's own wait inside it ever got the chance to time out.

**Checkpoint**: User Stories 1 AND 2 both work — the suite now verifies real
functionality per page, not just rendering.

---

## Phase 5: User Story 3 - Suite is runnable without manual environment troubleshooting (Priority: P3)

**Goal**: Confirm the automated setup mechanism built in Phase 1 (T001's
`postinstall` script) genuinely delivers a zero-manual-step first run (FR-007).

**Independent Test**: On a clone with `smoke-tests/node_modules` never installed,
running only `npm install` is sufficient for `npm test` to then succeed
(quickstart.md section 2).

### Implementation for User Story 3

- [X] T019 [US3] Verify zero-manual-setup end-to-end: delete
      `smoke-tests/node_modules`, run `npm install` alone, confirm the Playwright
      Chromium binary is present afterward, and confirm `npm test` then succeeds
      with no additional commands (quickstart.md section 2) (depends on T001, T004,
      T011, T018). Confirmed: fresh install (168 packages, ~5s) followed immediately
      by `npm test` → 3 scenarios (3 passed), no manual steps beyond `npm install`.
- [X] T020 [US3] Run `npm install` a second time immediately after T019 and confirm
      it completes quickly without a full reinstall (quickstart.md section 6)
      (depends on T019). Confirmed: "up to date, audited 169 packages in 2s" — 2.6s
      total, no re-download of the Chromium binary.

**Checkpoint**: All user stories are independently functional; the suite is usable
by someone who has never run it before with a single command.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the suite actually behaves correctly under failure conditions,
and that this session's explicit `@smoke` tagging requirement was applied
consistently.

- [X] T021 [P] Confirm every scenario across `smoke-tests/features/*.feature`
      carries the `@smoke` tag — e.g. one `@smoke` line immediately above each
      `Scenario:` line in all 3 files (this session's explicit request). Confirmed:
      `grep -c "@smoke"` and `grep -c "Scenario:"` both return exactly 1 per file;
      `npx cucumber-js --tags "@smoke"` selects and passes all 3.
- [X] T022 Run quickstart.md section 4: temporarily break
      `templates/index.html`'s `<h1>Crypto Hourly Watcher</h1>`, restart the app,
      run `npm test`, confirm only the Home scenario fails with a clear message,
      then revert the change and restart the app (SC-004 — proves the suite
      actually detects regressions, not just always passing).
      **Found and fixed a real gap on the first attempt**: appending a "z"
      (`Crypto Hourly Watcherz`) did NOT fail the suite — Playwright's
      `getByRole`/`getByText` name matching is substring-based by default, so the
      broken heading still satisfied a search for the correct one. Added
      `exact: true` to both matchers in `common.steps.ts`; re-ran and confirmed the
      Home scenario now fails with a precise "waiting for ... exact: true" message
      while the other two still pass, then reverted the template edit and restarted
      the app, then confirmed all 3 pass again. Removed the now-unused generic
      `Then('I should see {string}')` step (superseded by the more specific
      `#progressPanel.active` check from T013).
- [X] T023 Run quickstart.md section 5: stop `python app.py`, run `npm test`,
      confirm it fails quickly and clearly (not hanging) within its configured
      timeout, then restart the app (FR-008). Confirmed: all 3 scenarios fail
      immediately with `net::ERR_CONNECTION_REFUSED` naming the exact URL — no
      hanging, ~7s for all 3 combined (far under any timeout). App restarted
      afterward and confirmed serving normally again.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (T005 needs `tsconfig.json`/Cucumber
  config to be loadable) — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational
- **User Story 2 (Phase 4)**: Depends on User Story 1 (extends the same 3 feature
  files US1 creates) — not independent of US1 the way US1/US2 usually are in other
  features, by design (see Organization note above)
- **User Story 3 (Phase 5)**: Depends on Setup's `postinstall` wiring (T001) and on
  a working suite to confirm against (T011, T018) — verification only, no new
  scenario code
- **Polish (Phase 6)**: Depends on US1, US2, and US3 all being complete

### Within Each User Story

- Each page's `.feature` scenario (US1) before that same page's action extension
  (US2) — T008→T012→T013, T009→T014→T015, T010→T016→T017
- A "run and confirm passing" verification task closes out both US1 and US2
- Foundational step vocabulary (T005-T007) before any feature file references it

### Parallel Opportunities

- T002, T003 (Setup) — different files, no dependency on each other
- T007 (Foundational) — different file from T006, both depend only on T005
- T008, T009, T010 (US1) — three independent feature files
- T012, T014, T016 (US2) — three independent scenario extensions (each still
  sequential with its own paired step-definition task: T013, T015, T017)
- T021 (Polish) — independent of T022/T023, which share the single running app
  instance and are kept sequential with each other for that reason

---

## Parallel Example: User Story 1

```bash
Task: "Create smoke-tests/features/home.feature with an @smoke heading-check scenario"
Task: "Create smoke-tests/features/crypto-lookup.feature with an @smoke heading-check scenario"
Task: "Create smoke-tests/features/history.feature with an @smoke heading-check scenario"
```

## Parallel Example: User Story 2 (scenario extensions)

```bash
Task: "Extend home.feature's scenario with a Scan Crypto action check"
Task: "Extend crypto-lookup.feature's scenario with a ticker-lookup action check"
Task: "Extend history.feature's scenario with a list-or-empty-state check"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: `npm test` reports 3 passing heading-check scenarios
5. This alone is a demoable MVP — a genuinely useful smoke suite that catches a
   fully broken main page, before any action-checking exists

### Incremental Delivery

1. Setup + Foundational → Cucumber/Playwright plumbing works, 0 scenarios yet
2. Add User Story 1 → validate independently → MVP demoable (heading checks)
3. Add User Story 2 → validate independently → scenarios upgraded in place with
   action checks
4. Add User Story 3 → validate independently → zero-manual-setup confirmed
5. Polish → confirm `@smoke` tagging, prove the suite fails when it should, prove
   it fails cleanly when the app is down

---

## Notes

- [P] tasks touch different files with no ordering dependency between them
- Tasks that edit the same `.feature` file across phases (e.g., T008 then T012) are
  intentionally sequential — that's the US1→US2 layering, not a conflict
- `@smoke` is applied to every scenario at creation time (T008-T010), not added
  retroactively — T021 is a verification pass, not the tagging step itself
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently before continuing
