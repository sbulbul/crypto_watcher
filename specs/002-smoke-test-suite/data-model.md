# Data Model: Smoke Test Suite

This feature has no persistent data entities — it's a test suite, not an
application. What follows are the structural "entities" of the suite itself, per the
spec's Key Entities section.

## Entity: Smoke Scenario

One Gherkin scenario, covering one main page/flow.

| Field | Type | Notes |
|---|---|---|
| Feature file | `.feature` | One per covered page (`home.feature`, `crypto-lookup.feature`, `history.feature`) |
| Scenario name | text | Plain-language description a non-technical reader can follow (SC-005) |
| Given | step | Navigates to the page under test |
| When | step | Performs the page's primary action (or, for History, simply observes the loaded list — see research.md) |
| Then | step(s) | Asserts main heading/text is correct (FR-003) and the resulting UI state after the action is as expected (FR-004) |

## Entity: World (Cucumber fixture)

Cucumber's "World" is the shared context object available to every step in a
scenario. This suite's custom World holds:

| Field | Type | Notes |
|---|---|---|
| `browser` | Playwright `Browser` | Launched once per scenario in a `Before` hook, closed in `After` (FR-008 — bounded lifecycle, never left hanging) |
| `page` | Playwright `Page` | The single tab each scenario drives |
| `baseUrl` | string | Defaults to `http://127.0.0.1:5051` (the app's hardcoded dev address); overridable via a `BASE_URL` environment variable so the suite isn't hardcoded to one port if the app is ever run elsewhere |

## Mapping: Scenario → App Route → Main Text → Primary Action

This is the closest thing this feature has to a schema — the concrete contract each
scenario depends on. Full detail lives in `contracts/ui-contract.md`; summarized
here for traceability:

| Scenario | Route | Main text asserted | Primary action asserted |
|---|---|---|---|
| Home/Scanner | `/` | `<h1>Crypto Hourly Watcher</h1>` | Click "Scan Crypto" → progress panel becomes visible |
| Crypto Lookup | `/crypto` | `<h1>Crypto Lookup</h1>` | Submit ticker "BTC" → a result or a warning becomes visible |
| History | `/history` | `<h1>Scan History</h1>` | The history list or the "No saved scans yet" empty state renders (one or the other, not neither) |
