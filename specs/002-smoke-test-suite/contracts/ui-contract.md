# Contract: UI elements the suite depends on

This isn't an API contract (the app is server-rendered HTML, not a JSON API on the
page level) — it's the explicit list of DOM text/roles each scenario asserts
against. Anyone changing these in the app's templates should expect the
corresponding smoke scenario to fail, by design (that's the suite doing its job).
Per research.md's selector-strategy decision, everything here already exists in the
app's templates today — nothing was added for testability.

## Home / Scanner (`GET /`, `templates/index.html`)

| What | Locator strategy | Current value |
|---|---|---|
| Main heading | role `heading`, name | `Crypto Hourly Watcher` |
| Scan limit input | `getByLabel` | label text `Scan limit` |
| Primary action button | role `button`, name | `Scan Crypto` |
| "Scan started" signal | CSS `#progressPanel.active` | **Not** the panel's text — corrected below |

**Corrected during implementation**: the panel's `#progressText` content is
dynamic — client-side JS (`renderProgress()` in `templates/index.html`) rewrites it
through `"Preparing crypto universe"` and then `"Scanning N of M"` as polling
progresses, so it's never a fixed string and asserting on one is unreliable
(confirmed by direct Playwright inspection, which caught `"Preparing crypto
universe"` a full second after the click). The stable signal is `#progressPanel`
gaining the `active` class, which is true the moment a scan starts regardless of
which phase its status text is in.

A second, unrelated fragility was found and fixed at the same time: a **small**
scan limit (e.g. 25, left over from manual testing) can complete in just a few
seconds — short enough to race against Playwright's own browser-launch/navigation
overhead and finish (panel deactivates again) before the assertion ever observes
it. The scenario now explicitly sets the limit to `250` (the app's own default)
before clicking, so the scan reliably outlasts that overhead, and explicitly stops
the scan afterward so it doesn't keep running server-side after the scenario ends.

**Scenario shape**: navigate to `/` → assert main heading → set scan limit to `250`
→ click "Scan Crypto" → assert `#progressPanel` gains the `active` class (bounded
wait, 10s) — does **not** wait for the scan to complete (research.md) → stop the
scan (cleanup, not an assertion).

## Crypto Lookup (`GET /crypto`, `templates/crypto.html`)

| What | Locator strategy | Current value |
|---|---|---|
| Main heading | role `heading`, name | `Crypto Lookup` |
| Ticker input | `getByLabel` | label text `Ticker symbol` |
| Submit button | role `button`, name | `Look Up` |
| Result container | `#resultState` (id — no unique static text, content is dynamic) | becomes visible (not `hidden`) on a successful lookup |
| Warning container | `#warningState` (id — same reason) | becomes visible on a `not_found`/`unavailable` response |

**Scenario shape**: navigate to `/crypto` → assert main heading → fill ticker input
with `BTC` → click "Look Up" → assert that **either** `#resultState` **or**
`#warningState` becomes visible within a bounded wait (e.g. 10s) — either outcome is
a pass per the spec's edge-case allowance (a clear warning is correct app behavior,
not a test failure); only "neither appears" or "still loading after the timeout" is
a failure.

## History (`GET /history`, `templates/history.html`)

| What | Locator strategy | Current value |
|---|---|---|
| Main heading | role `heading`, name | `Scan History` |
| Populated list | `.history-table` (existing class) | present when scans exist |
| Empty state | role `heading`, name | `No saved scans yet` (present when no scans exist) |

**Scenario shape**: navigate to `/history` → assert main heading → assert that
**either** `.history-table` **or** the "No saved scans yet" heading is present
(exactly one of the two is expected; both absent is a failure).

## Stability note

None of the above depend on data seeded by a previous test run (History's
either/or check tolerates both a fresh and a populated database), so the suite is
safe to run repeatedly against the same local app instance without setup/teardown
of app-level state.
