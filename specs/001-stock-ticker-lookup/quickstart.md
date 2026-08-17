# Quickstart: Validating Stock Ticker Lookup

Prerequisites: dependencies from `requirements.txt` installed; run from the repo
root (`crypto_watcher/`).

## 1. Start the app

```bash
python app.py
```

Open the app in a browser (the URL/port `app.py` prints on startup).

## 2. User Story 2 — reach the page from the main page

1. On the main page, confirm a clearly labeled button/link for the stock lookup
   feature is visible (FR-001).
2. Click it and confirm you land on the new ticker lookup page.

**Pass condition**: SC-001 — reaching a price + recommendation from the main page
takes 3 clicks or fewer (nav button → enter ticker → submit).

## 3. User Story 1 — happy path

1. On the lookup page, enter a known, actively traded ticker (e.g., `AAPL`) and
   submit.
2. Confirm a loading indicator appears immediately (FR-006), then is replaced by a
   price and a Buy/Sell/Hold recommendation (FR-003, FR-004).
3. Enter a second, different valid ticker and submit again without reloading the
   page; confirm the display updates in place (FR-010).
4. Submit the same ticker again immediately; confirm a fresh lookup runs and its
   result replaces what was shown (FR-010a — "always re-fetch" behavior).

**Pass condition**: SC-002 — result appears within ~5 seconds under normal network
conditions.

## 4. User Story 3 — failure warnings

1. Submit a ticker that does not exist (e.g., `ZZZZZZ`). Confirm a visible warning
   states the ticker was not found, and no price/recommendation is shown (FR-007).
2. Submit the lookup form with the ticker field empty. Confirm a message prompts you
   to enter a ticker, and no lookup is attempted (FR-009).
3. *(Optional, harder to trigger on demand)* Disconnect network access and submit a
   valid ticker; confirm a visible warning states the lookup failed, rather than a
   blank or frozen page (FR-008).

**Pass condition**: SC-003 — every failure case above produces a visible warning,
never a blank/broken page.

## 5. Data durability — lookup history persists

1. After completing at least one successful lookup (step 3), stop the app
   (`Ctrl+C`) and restart it (`python app.py`).
2. Inspect `data/crypto_watcher.db` (e.g., `sqlite3 data/crypto_watcher.db "select * from ticker_lookups order by id desc limit 5;"`)
   and confirm the lookup(s) from step 3 are present with `ticker`, `price`,
   `price_type`, `recommendation`, and `looked_up_at` populated (FR-013).

**Pass condition**: the row(s) survive the restart — nothing is lost (Constitution
Principle VI).

## 6. UI text integrity

1. Resize the browser window to a narrow width (e.g., ~360px, a typical phone
   width) and a wide desktop width.
2. At both sizes, submit a ticker and confirm the ticker, price, recommendation, and
   any warning text are fully visible — no overlapping or cut-off text (FR-012).
3. If possible, trigger the longest realistic warning message (e.g., the "not found"
   message) at the narrow width and confirm it still wraps cleanly.

**Pass condition**: SC-005 — no overlapping/cut-off text observed at any tested
width.

## 7. Consecutive lookups

1. From the lookup page, perform at least 10 consecutive lookups (mixing valid and
   invalid tickers) without reloading the page.

**Pass condition**: SC-004 — all 10 complete without needing a page reload.
