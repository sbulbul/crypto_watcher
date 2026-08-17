<!--
Sync Impact Report
- Version change: (unratified template) → 1.0.0
- Rationale: Initial ratification. The constitution file existed only as an unfilled
  template ([PROJECT_NAME] Constitution with all placeholders empty); this is the
  first concrete adoption, not an amendment, so MAJOR version 1.0.0 is used.
- Modified principles: none (initial set, not renames)
- Added sections:
  - Core Principles: Zero Loophole Execution, Mandatory Failure Warnings,
    Process Visibility, UI Text Integrity, Live API Integrity, Data Durability
  - Reliability Standards
  - Development Workflow
  - Governance
- Removed sections: none
- Deferred / TODO placeholders: none — all template tokens replaced with concrete text.
- Templates requiring follow-up: none checked automatically by this command (out of
  scope per Scope Guard); dependent commands read this file at runtime.
-->

# Crypto Watcher Constitution

## Core Principles

### I. Zero Loophole Execution
Every function MUST handle every input and failure branch explicitly. No code path
may exit silently without either producing a defined result or raising/reporting an
error. Bare `except: pass` (or equivalent silent catch-and-ignore in any language),
ignored return/error codes, and untested conditional branches that fall through with
no defined outcome are all treated as bugs ("loopholes") and MUST be fixed before the
change is considered done — not routed around, suppressed, or deferred.

**Rationale**: The user requires that none of the app's functions have a gap where
behavior is undefined. Undetected loopholes are the primary way a scanner, scorer, or
trading function can act on bad silent state without anyone noticing.

### II. Mandatory Failure Warnings (NON-NEGOTIABLE)
Any error, exception, timeout, or unexpected condition anywhere in the app — API
fetch, scoring, signal generation, paper trading, storage — MUST surface a visible
warning to the user through the UI (banner, toast, alert panel, or equivalent).
Logging to a file or console alone does NOT satisfy this principle. Failures MUST
NOT be discoverable only by reading server logs or by noticing missing/stale data
after the fact.

**Rationale**: The user must always be warned when something goes wrong, in the
moment, without having to go looking for it.

### III. Process Visibility
Every user-invocable function or background job (scans, signal generation, paper
trades, market-flow refresh, data fetches) MUST report its lifecycle state to the
user: start, meaningful in-progress status for any non-trivial operation, and a
clear completion or failure state. The user MUST never be left unable to tell
whether an action is running, stuck, or finished.

**Rationale**: The user requires to always be notified of the process of any
function in the app, not just its final output.

### IV. UI Text Integrity
UI layouts MUST NOT allow text to overlap, clip, or be cut off at any supported
viewport or window size the app is used at. Elements displaying dynamic content
(prices, symbols, scores, alerts, warnings) MUST wrap, resize, or scroll to fit
their content. Any UI change MUST be visually verified — by running the app and
inspecting the rendered page, not by reading markup alone — before it is
considered done.

**Rationale**: The user explicitly requires no text overlap or cutoff anywhere
in the UI.

### V. Live API Integrity
All external data calls (yfinance, `requests`-based endpoints, and any future
integration) MUST hit real, live endpoints and MUST validate the response (status
code, expected shape/schema, non-empty payload) before the data is used or shown.
Placeholder data, mocked responses, or silently-substituted fallback data MUST
NEVER be presented to the user as if it were live data. If a live call fails,
Principle II (Mandatory Failure Warnings) governs the response — never a silent,
unlabeled fallback.

**Rationale**: The user requires that all API calls be legit and return properly;
faked or stale data masquerading as live data is treated as a defect.

### VI. Data Durability
Any data the user has generated or the app has captured — trades, scans, scores,
settings, history — MUST persist reliably in the storage layer / database and MUST
NOT be silently lost, overwritten, or dropped on crash, restart, or error. Writes
MUST be confirmed to have succeeded; a failed write MUST raise a Principle II
warning rather than proceeding as though it had succeeded.

**Rationale**: The user requires that their data always be there and never gone.

## Reliability Standards

Before any change touching an API call, storage/persistence, a background job, or
the UI is considered complete, it MUST be checked against all six Core Principles
above. Concretely:
- Any new or modified function is walked through its input space to confirm no
  branch exits without a defined result or a surfaced error (Principle I).
- Any new external call includes response validation and an explicit failure path
  that produces a user-visible warning (Principles II, V).
- Any operation that takes non-trivial time emits a start/progress/completion (or
  failure) signal the user can see (Principle III).
- Any UI change is exercised in the running app at the app's supported window
  sizes to confirm no overlapping or truncated text (Principle IV).
- Any write to `storage.py` / the database is confirmed to succeed, and failure is
  never allowed to pass silently (Principle VI).

## Development Workflow

This is a single-maintainer project; "review" means the author (or an assisting
agent) explicitly re-checks a change against the Reliability Standards above before
calling it done, rather than assuming a passing test run or a clean diff is
sufficient. Manual verification in the running app (not just static code reading)
is required for anything touching API calls, storage, or UI, per Principles II–V.

## Governance

This constitution supersedes ad hoc practice for this project. Any change to it
MUST update this file directly, include a Sync Impact Report as an HTML comment at
the top of the file, and bump the version per semantic versioning:
- MAJOR: a principle is removed or redefined in a backward-incompatible way.
- MINOR: a new principle or materially expanded section is added.
- PATCH: wording, clarification, or typo fixes with no semantic change.

Every change to the app MUST be checked against the six Core Principles before it
is considered complete — this replaces any informal "looks good" judgment. When a
principle is genuinely infeasible for a specific change, the exception and its
reasoning MUST be written down in the relevant task/PR description rather than
silently skipped, since silent skipping is itself the kind of loophole Principle I
forbids.

**Version**: 1.0.0 | **Ratified**: 2026-08-17 | **Last Amended**: 2026-08-17
