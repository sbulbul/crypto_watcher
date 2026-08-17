# Research: Smoke Test Suite

## Decision: Cucumber + Playwright wiring

**Decision**: Use the official `@cucumber/cucumber` package as the test runner,
with `playwright` (the core library, not `@playwright/test`) driving the browser
from inside Cucumber step definitions. TypeScript step definitions are loaded
directly via `ts-node`'s Cucumber integration (`requireModule: ['ts-node/register']`
in `cucumber.cjs`) — no separate compile step.

**Rationale**: The request explicitly named "Cucumber and BDD," which points at
Cucumber.js itself as the runner (Gherkin `.feature` files → step definitions),
not merely "write BDD-style tests." `playwright` (not `@playwright/test`) is the
right dependency here because `@playwright/test` bundles its *own* test runner,
which would compete with Cucumber for that role — we only want Playwright's browser
automation API, with Cucumber orchestrating scenarios.

**Alternatives considered**:
- *`playwright-bdd`* (generates Playwright Test spec files from `.feature` files,
  then runs via `npx playwright test`) — a popular modern approach that gets
  Playwright's own HTML reporter, tracing, and parallelism for free. Rejected here
  because it runs on `@playwright/test`'s runner under the hood, not Cucumber.js
  itself — a less literal match for "Cucumber" as explicitly requested. Worth
  reconsidering later if the suite grows and richer reporting/tracing becomes
  valuable.
- *Compiling TypeScript to JS before running Cucumber* — rejected in favor of
  `ts-node` for a simpler single-command developer loop (no build step to forget to
  run before testing).

## Decision: Which 3 pages to cover, and how

**Decision**: Cover Home/Scanner (`/`), Crypto Lookup (`/crypto`), and History
(`/history`) — 3 of the app's 5 main areas (60%, clearing the 50% floor). Paper
Trader and Scalper are left uncovered for this first pass.

**Rationale**: These three give the best spread for the least fragility:
- **Home/Scanner** is the app's primary/original feature and entry point.
- **Crypto Lookup** is the newest feature (the previous `specs/001-...` work) and
  has a simple, fast, deterministic primary action (submit a ticker, see a result).
- **History** exercises a third distinct rendering path (a populated-or-empty list)
  with no interactive action needed beyond loading it, keeping the third scenario
  cheap.

Paper Trader and Scalper both involve starting a longer-running background process
with more complex state (open positions, simulated fills over time) — harder to
smoke-test quickly and deterministically, and the spec only requires clearing 50%,
which three pages already do. Extending to these later is straightforward (same
patterns) if the maintainer wants more coverage.

**Alternatives considered**: Covering all 5 pages — rejected for now as more than
requested ("only main functions") and slower to build/run for marginal benefit over
the 50% floor; noted in quickstart.md as an easy future extension.

## Decision: Home/Scanner's primary-action check is bounded to "scan started," not "scan completed"

**Decision**: The Home/Scanner scenario clicks "Scan Crypto" and asserts the
progress panel becomes visible (i.e., a scan is running) — it does **not** wait for
the scan to finish.

**Rationale**: `scan_market()` can take minutes over the full symbol universe (it
makes many live external API calls) — waiting for full completion would blow
SC-002's 3-minute budget for the *entire suite*, not just this one scenario, and
would make the suite flaky against live market data availability. "The button
starts a real scan" is still a meaningful, real (non-mocked) functional check per
Constitution Principle V — it just doesn't wait for every downstream API call to
resolve.

**Alternatives considered**: Passing a very small `limit` (e.g., 25) and waiting for
completion — rejected: still a live multi-symbol scan of unpredictable duration
depending on network conditions, and still meaningfully slower than the other two
scenarios for comparatively little extra signal over "did the scan start."

## Decision: Selector strategy — no app source changes for testability

**Decision**: Assert using Playwright's user-facing locators (`getByRole('heading',
{ name: ... })`, `getByRole('button', { name: ... })`, `getByLabel(...)`,
`getByText(...)`) against the app's existing semantic HTML (`<h1>`, labelled
`<input>`s, button text) — no `data-testid` attributes or other test-only markup
are added to the app's templates.

**Rationale**: The app's templates already have real headings (`<h1>Crypto Hourly
Watcher</h1>`, `<h1>Crypto Lookup</h1>`, `<h1>Scan History</h1>`), a labelled ticker
input (`<label for="ticker">`), and semantically real buttons ("Scan Crypto", "Look
Up") — all directly and robustly targetable without touching application code. This
also means this feature ships with **zero changes to the app itself**, which keeps
its blast radius to a new, independent directory only, and sidesteps needing to
re-verify the constitution's UI principles against modified app markup.

**Alternatives considered**: Adding `data-testid` attributes throughout the
templates — rejected as unnecessary app-code churn given the existing markup is
already stable and semantic enough for reliable role/text-based locators.

## Decision: Automatic dependency/driver installation

**Decision**: `smoke-tests/package.json` declares a `postinstall` script that runs
`playwright install chromium`, so a single `npm install` installs both the npm
packages *and* the Playwright browser binary — satisfying "if there is any missing
dependency or driver... install it too" with one command (FR-007, SC-001).

**Rationale**: Playwright's browser binaries are not npm packages — they're
downloaded separately via its CLI — so without a `postinstall` hook, a user would
need to remember a second manual step (`npx playwright install`) after `npm
install`. Wiring it as `postinstall` makes the one-command setup exact and
mistake-proof. `npm install`'s own dependency resolution already handles "install
whatever npm packages are missing," so no additional logic is needed for that half.

**Confirmed during implementation** (closes the "outdated binary" Edge Case in
spec.md): this machine already had an unrelated Chromium build cached
(`chromium-1228`) before this suite's `npm install` ran. `postinstall`'s
`playwright install chromium` added the version this project's `playwright`
dependency actually needs (`chromium-1234`) alongside it, without being told to —
Playwright's CLI resolves against the installed `playwright` package version, not
against whatever happens to already be cached. No extra update-detection logic is
needed; a stale/mismatched binary is corrected automatically on every
`npm install`.

**Alternatives considered**: A separate `npm run setup` script requiring two
commands (`npm install && npm run setup`) — rejected as strictly worse UX than a
single command doing both automatically, with no offsetting benefit.

## Decision: No app server auto-start

**Decision** (carried over from spec.md's Assumptions, confirmed here): The suite
assumes `python app.py` is already running; it does not spawn/manage that process
itself.

**Rationale**: Managing a Python subprocess from a Node/TypeScript test suite (start,
wait for port readiness, guarantee teardown even on crash) is meaningfully more
complex than the smoke-test scope calls for, and this repo's own `quickstart.md`
guides already establish "start the app first" as the normal workflow — consistent
with existing conventions rather than inventing a new one.
