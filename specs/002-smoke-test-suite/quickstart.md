# Quickstart: Validating the Smoke Test Suite

Prerequisites: Node.js/npm installed (already present on this machine — `node
v24.18.0`, `npm 11.6.0`). Run from the repo root (`crypto_watcher/`).

## 1. Start the app (separate terminal)

```bash
python app.py
```

Leave this running — the suite assumes it's already up on `http://127.0.0.1:5051`
(FR-008: the suite must fail clearly if it isn't, not hang).

## 2. First-time setup — one command (US3, SC-001)

```bash
cd smoke-tests
npm install
```

`npm install`'s `postinstall` script installs the Playwright Chromium binary
automatically — no separate manual step. Confirm success by checking the command
exits 0 and `smoke-tests/node_modules/.bin/cucumber-js` (or equivalent) exists.

**Pass condition**: running this on a machine where `smoke-tests/node_modules` has
never existed installs everything needed, with no additional commands.

## 3. Run the suite (US1, US2)

```bash
npm test
```

**Pass condition**:
- All 3 scenarios (Home/Scanner, Crypto Lookup, History) report passed.
- The console output names each scenario and its steps as they run (Principle III —
  process visibility; SC-005 — a reader can tell what's being checked from the
  output alone).
- Total run time is under 3 minutes (SC-002).

## 4. Prove the suite actually detects breakage (SC-004)

1. Temporarily edit `templates/index.html`'s `<h1>Crypto Hourly Watcher</h1>` to
   something else (e.g., `<h1>Crypto Hourly Watcherz</h1>`).
2. Restart `python app.py` so the change takes effect.
3. Run `npm test` again from `smoke-tests/`.
4. Confirm the Home/Scanner scenario fails, with a message identifying the heading
   assertion that didn't match.
5. Revert the edit and restart the app.

**Pass condition**: the suite fails exactly the scenario tied to the broken page,
and passes the other two — proving it isn't a suite that always reports green.

## 5. Confirm bounded failure when the app isn't running (Edge Case)

1. Stop `python app.py`.
2. Run `npm test` from `smoke-tests/`.

**Pass condition**: the suite fails quickly (within its configured timeout, not
hanging indefinitely) with a clear connection-refused-style error, per FR-008.

## 6. Re-running setup is fast (US3, acceptance scenario 2)

```bash
npm install
```

Run a second time immediately after step 2.

**Pass condition**: completes quickly (npm's own up-to-date check short-circuits
reinstallation; Playwright's install step is similarly a no-op when the browser is
already present).
