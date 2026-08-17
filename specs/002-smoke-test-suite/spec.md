# Feature Specification: Smoke Test Suite

**Feature Branch**: `002-smoke-test-suite`

**Created**: 2026-08-17

**Status**: Draft

**Input**: User description: "I want to create a smoke test for the current app with Playwright, typescript. Cucumber and BDD. If there is any missing dependency or driver or anything then we should install it too. We will try to cover at least 50% of the app. I want to cover only main functions and main text in the app."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a smoke suite that verifies the app's main pages (Priority: P1)

As the maintainer, I run a single documented command and get back a pass/fail report
confirming that each of the app's main pages loads and shows its expected main
heading/text, so I can catch an obviously broken page (blank screen, wrong template,
crashed route) before I notice it by hand.

**Why this priority**: This is the whole point of a smoke test — a fast, low-effort
signal that the app is not obviously broken. Without it, nothing else in this feature
has value.

**Independent Test**: With the app running locally, run the suite's documented
command and confirm it reports pass for each covered page's main-text check.

**Acceptance Scenarios**:

1. **Given** the app is running locally, **When** the smoke suite runs, **Then** it
   opens each covered main page and confirms that page's primary heading/label text
   is present and correct.
2. **Given** a covered page's main heading text has been changed to something
   incorrect (a regression), **When** the smoke suite runs, **Then** the scenario for
   that page fails with a message identifying which page/text check failed.
3. **Given** the app is not running (nothing listening on its port), **When** the
   smoke suite runs, **Then** it fails clearly and quickly rather than hanging or
   timing out silently.

---

### User Story 2 - Smoke suite exercises each covered page's primary action (Priority: P2)

As the maintainer, for each main page the suite covers, it also performs that page's
single most important interactive action (e.g., submitting the crypto ticker lookup
form, starting a scan) and confirms a reasonable result appears, so the suite catches
broken *functionality*, not just broken *rendering*.

**Why this priority**: A page can render its heading correctly while its core action
is completely broken (e.g., a button that does nothing). This closes that gap, but
the suite is still useful for its primary purpose (US1) without it.

**Independent Test**: With the app running locally, run the suite and confirm that
each covered page's scenario includes at least one step that performs its primary
action and checks the outcome, not just an initial page-load check.

**Acceptance Scenarios**:

1. **Given** the crypto ticker lookup page is open, **When** the scenario submits a
   known valid ticker, **Then** it confirms a price and recommendation (or a clear
   warning) appears, matching the lookup feature's own behavior.
2. **Given** the scanner's main page is open, **When** the scenario starts a scan (or
   exercises whichever primary action that page offers), **Then** it confirms the
   expected resulting UI state appears.

---

### User Story 3 - Suite is runnable without manual environment troubleshooting (Priority: P3)

As a contributor (or the maintainer, on a machine that hasn't run this suite before),
I run the documented setup step(s) and everything the suite needs — Node.js
dependencies and the Playwright browser binary — gets installed automatically, so I
don't have to manually chase down missing packages or drivers before the suite will
run.

**Why this priority**: Improves the suite's usability and lowers the barrier to
running it, but the suite still delivers its core value (US1/US2) for the person who
already has the environment set up.

**Independent Test**: On a clone of the repo where the test-suite's dependencies have
never been installed, run only the documented setup command(s) and confirm the suite
can then run successfully with no additional manual steps.

**Acceptance Scenarios**:

1. **Given** a fresh checkout with no test-suite dependencies installed, **When** the
   documented setup command(s) are run, **Then** all required packages and the
   Playwright browser binary are installed without further manual intervention.
2. **Given** setup has already been run once, **When** it is run again, **Then** it
   completes quickly without reinstalling everything from scratch (no-op or fast
   check when nothing is missing).

### Edge Cases

- What happens when a covered page takes unusually long to load — does the suite
  wait a bounded amount of time and then fail clearly, rather than hanging
  indefinitely?
- What happens when the app is running but a covered page returns an error (e.g., a
  500) instead of its normal content?
- What happens when the primary action exercised in US2 legitimately produces a
  warning instead of a success result (e.g., looking up a ticker that happens to
  return "not found" at test time) — does the scenario still count that as a pass if
  a clear warning is shown, per the app's own constitution (a warning is correct
  behavior, not a bug)?
- What happens when Playwright's browser binary is already installed but out of
  date — does setup detect and update it, or only install when entirely missing?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST include an automated smoke-test suite built with
  Playwright (browser automation), TypeScript, and Cucumber (Gherkin-based BDD
  scenarios) — this is an explicit, non-negotiable choice of the requester, not left
  open for substitution.
- **FR-002**: The suite MUST cover at least 50% of the app's main navigable
  areas — interpreted as at least 3 of the app's 5 main pages/flows (Home/Scanner,
  History, Paper Trader, Scalper, Crypto Lookup; see Assumptions).
- **FR-003**: For each covered page, the suite MUST verify that page's main
  heading/label text is present and correct — not merely that the HTTP request
  succeeded.
- **FR-004**: For each covered page, the suite MUST also exercise that page's single
  primary interactive action and verify a reasonable resulting UI state appears
  (FR-per User Story 2) — page-load-only checks are not sufficient for a covered
  page.
- **FR-005**: Test scenarios MUST be written in Gherkin (Given/When/Then) so their
  intent is readable without reading the underlying TypeScript step-definition code.
- **FR-006**: Running the suite MUST be possible via a small, documented set of
  commands after cloning the repo and starting the app.
- **FR-007**: Setup MUST install any missing Node.js dependencies and the Playwright
  browser binary automatically as part of the documented setup command(s), rather
  than requiring the user to manually track down and install them.
- **FR-008**: If the app is not reachable when the suite runs, the suite MUST fail
  clearly and within a bounded time, rather than hanging indefinitely or reporting a
  false pass.
- **FR-009**: The suite MUST NOT silently skip or mark a check as passing when it
  could not actually verify the condition (e.g., an element that never appeared) —
  every check either explicitly passes or explicitly fails.

### Key Entities

- **Smoke Scenario**: One Gherkin scenario covering one main page/flow — a page-load
  + main-text check, plus (per US2) that page's primary action and its expected
  outcome. Written in a `.feature` file, implemented by TypeScript step definitions
  that drive Playwright.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the suite's documented setup command(s) on a machine that only
  has Node.js/npm already available results in every required package and the
  Playwright browser binary being installed with no manual steps beyond that command.
- **SC-002**: A full run of the suite completes in under 3 minutes against a locally
  running instance of the app.
- **SC-003**: At least 3 of the app's 5 main pages/flows (Home/Scanner, History,
  Paper Trader, Scalper, Crypto Lookup) each have at least one passing Gherkin
  scenario verifying both main text and a primary action.
- **SC-004**: Introducing a deliberate regression into a covered page's main heading
  text causes that page's scenario to fail, demonstrating the suite actually detects
  real breakage rather than always passing.
- **SC-005**: A person unfamiliar with the codebase can read any one `.feature` file
  and correctly describe, in plain language, what it verifies.

## Assumptions

- The specific tool stack (Playwright, TypeScript, Cucumber/BDD) was explicitly
  requested and is treated as fixed; specific package versions and exact wiring
  (e.g., how Cucumber invokes Playwright) are plan-level decisions.
- "The current app" refers to the Flask app as it exists now, including the crypto
  ticker lookup page — its 5 main navigable areas are: Home/Scanner (`/`), History
  (`/history`), Paper Trader (`/paper`), Scalper (`/scalper`), and Crypto Lookup
  (`/crypto`).
- "At least 50% of the app" is interpreted as functional/page coverage (at least
  half of the 5 main areas above get a scenario), not a source-code coverage
  percentage — a code-coverage metric doesn't map cleanly onto browser-driven BDD
  smoke scenarios, and the request's own phrasing ("main functions and main text")
  describes functional scope, not code lines.
- The suite assumes the app's local dev server is already running (e.g., via
  `python app.py`) before the suite is invoked; starting/stopping the Flask server is
  not part of the suite itself, consistent with how the existing `quickstart.md`
  validation guides already work in this repo.
- "Main text" means the primary heading/label a user would see confirming the right
  page loaded (e.g., an `<h1>`, a key button/nav label) — not exhaustive copy
  verification of every string on the page.
- Only the primary/happy path per covered page is exercised (smoke-level scope);
  edge cases, error states, and exhaustive input validation are out of scope here —
  those are already covered where they matter by this repo's existing `pytest` unit
  tests for the crypto lookup feature.
- The suite targets a single browser (Chromium, Playwright's default) — smoke tests
  don't need cross-browser coverage.
- Wiring this suite into a CI pipeline is out of scope for this feature; only the
  suite itself and its local run/setup instructions are in scope.
