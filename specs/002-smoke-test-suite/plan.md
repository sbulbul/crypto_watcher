# Implementation Plan: Smoke Test Suite

**Branch**: `002-smoke-test-suite` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-smoke-test-suite/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a Node.js/TypeScript smoke-test suite, in a new `smoke-tests/` directory
alongside the existing Python app, using `@cucumber/cucumber` (Gherkin BDD) as the
test runner and `playwright` for browser automation. The suite drives a locally
running instance of the Flask app in Chromium and covers 3 of the app's 5 main pages
(Home/Scanner, Crypto Lookup, History — see research.md for why these three), each
scenario checking that page's main heading text plus its single primary action. A
single `npm install` installs both the npm packages and the Playwright Chromium
binary (via a `postinstall` script), satisfying the "install anything missing"
requirement with one command.

## Technical Context

**Language/Version**: TypeScript (Node.js v24.18.0, already installed on this
machine — confirmed via `node --version`). This is the first non-Python component in
the repo; it lives in its own `smoke-tests/` directory with its own `package.json` so
it never touches the Python dependency chain (`requirements.txt` stays Node-free).

**Primary Dependencies**: `@cucumber/cucumber` (BDD test runner, explicitly
requested), `playwright` (browser automation, explicitly requested), `typescript` +
`ts-node` (so Cucumber can load `.ts` step definitions directly, no separate build
step), `@types/node`. All new — nothing Node-related exists in the repo yet.

**Storage**: N/A — the suite reads/asserts against the running app's UI; it doesn't
persist its own data (Cucumber's console/JSON output is ephemeral run output, not a
data store).

**Testing**: This feature *is* a testing tool. Its own correctness is validated by
running it against the real app and confirming pass/fail behavior is accurate in both
directions (SC-004: a deliberate regression must fail; a correct app must pass).

**Target Platform**: Local developer machine (Windows, per this environment),
Chromium (Playwright's default browser) driving `http://127.0.0.1:5051` — the app's
existing hardcoded dev-server address (`app.py`'s `app.run(host="127.0.0.1",
port=5051, ...)`).

**Project Type**: Test-automation tooling, additive to the existing web application —
not a new application surface itself.

**Performance Goals**: SC-002 — full suite run completes in under 3 minutes. The
main risk to this budget is the Home/Scanner page's primary action (a full crypto
scan can take minutes over many symbols); research.md addresses this by scoping that
scenario's check to "scan started" rather than "scan completed."

**Constraints**: Single browser (Chromium) — no cross-browser matrix. Assumes the app
is already running locally (the suite does not start/stop `python app.py`). No CI
wiring in this feature's scope (spec Assumptions).

**Scale/Scope**: 3 `.feature` files (Home/Scanner, Crypto Lookup, History), each with
one scenario covering main-text + primary-action, per FR-002/SC-003's "at least 3 of
5" floor. Small, deliberately minimal per the request ("only main functions and main
text").

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution's six principles were written for the app's own runtime
behavior (warnings, process visibility, data durability for end users). This feature
is dev/test tooling that *verifies* that behavior rather than implementing new
user-facing behavior, so most principles apply by analogy rather than directly:

| Principle | How this feature relates |
|---|---|
| I. Zero Loophole Execution | Directly applicable and encoded as FR-009: every check in the suite must explicitly pass or fail — no step is allowed to silently no-op or report a false pass when it couldn't actually verify something. |
| II. Mandatory Failure Warnings | Analogous, not literal (there's no end user here) — a failing scenario's Cucumber output *is* the "warning," and it is never suppressed or swallowed (default Cucumber behavior: a failed step fails the run with a visible message). |
| III. Process Visibility | Satisfied by Cucumber's default behavior: each scenario/step is printed to the console as it runs, so the person running the suite always knows what's happening. |
| IV. UI Text Integrity | Not directly applicable — this feature verifies existing UI, it doesn't render any. (It incidentally *could* catch some overlap/cutoff regressions by asserting on text visibility, but exhaustive UI-integrity testing is explicitly out of scope per the spec's Assumptions — that's the app's own concern, not this suite's.) |
| V. Live API Integrity | The suite exercises the real running app end-to-end with no mocking layer — when it checks the Crypto Lookup page, that's a real lookup hitting real Binance/Yahoo/CoinGecko calls through the actual app, never faked. This keeps the smoke suite consistent with the app's own "never fake live data" principle. |
| VI. Data Durability | Not applicable to this feature — the crypto lookup's persistence is already covered by this repo's existing `pytest` suite (`tests/test_storage_ticker_lookups.py`); duplicating that at the browser level would violate the spec's own "smoke-level only" scope. |

No violations requiring justification. Complexity Tracking is not needed.

**Post-Phase 1 re-check**: The table above already reflects the finished design
(research.md's tool-choice and scenario-scoping decisions, and contracts/'s explicit
selector/text dependencies). No new gate violations were introduced during Phase 1
design.

## Project Structure

### Documentation (this feature)

```text
specs/002-smoke-test-suite/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md          # Phase 1 output (/speckit-plan command)
├── contracts/               # Phase 1 output (/speckit-plan command) — ui-contract.md
└── tasks.md                  # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
smoke-tests/                       # NEW — self-contained Node/TS project
├── package.json                    # scripts: "test" (run cucumber), "postinstall"
│                                     #   (playwright install chromium)
├── tsconfig.json
├── cucumber.cjs                     # Cucumber config: feature/step paths,
│                                     #   ts-node/register, default World
├── features/
│   ├── home.feature                  # Home/Scanner: main heading + start-scan check
│   ├── crypto-lookup.feature          # Crypto Lookup: main heading + lookup check
│   └── history.feature                 # History: main heading + list-renders check
└── step-definitions/
    ├── world.ts                        # Custom World: holds Playwright page/browser,
    │                                     #   BASE_URL (default http://127.0.0.1:5051)
    ├── hooks.ts                         # Before/After: launch/close browser+page
    ├── common.steps.ts                   # Shared "page has heading X" step
    ├── home.steps.ts
    ├── crypto-lookup.steps.ts
    └── history.steps.ts
```

**Structure Decision**: A new top-level `smoke-tests/` directory, entirely separate
from the Python app's files — this is the only sensible option given the language
switch (Node/TypeScript vs. the app's Python). It has its own `package.json`, so
`npm install` here never touches `requirements.txt`/`pip`, and the Python app is
completely unaware this suite exists (the suite only talks to the app over HTTP, like
a browser would). None of the plan template's src/tests or backend/frontend options
apply directly since this isn't application source code — it's a separate,
self-contained tooling project living alongside the app it tests.

## Complexity Tracking

Not applicable — the Constitution Check above found no violations to justify.
