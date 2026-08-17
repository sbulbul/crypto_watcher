# Data Model: Crypto Ticker Lookup

## Entity: Ticker Lookup Result

Represents the outcome of one lookup, per the spec's Key Entities section. Held
in-memory for display, and persisted as one row per completed lookup (FR-013).

| Field | Type | Required | Notes |
|---|---|---|---|
| `ticker` | text | yes | Normalized to uppercase, trimmed of surrounding whitespace, and given the app's canonical crypto suffix if missing (see Validation rules) — e.g. user input `"btc"` becomes `"BTC-USD"`, matching the format `universe.py`/`scanner.py` already use everywhere else in the app. |
| `price` | number | yes, on success | The retrieved price. Always > 0 when present; absent when the lookup produced a warning instead (FR-007/FR-008). |
| `price_type` | text enum: `live` \| `delayed` | yes, on success | `live` when `fetch_latest_price()`'s Binance spot source answered; `delayed` when a fallback source (Yahoo/CoinGecko) answered instead (FR-011 — redefined for crypto's 24/7 market; see research.md). |
| `recommendation` | text enum: `Buy` \| `Sell` \| `Hold` | yes, on success | Derived from `score_from_history()`'s real `quick_win_score`/`long_term_score` output per research.md's "Recommendation methodology" decision. |
| `looked_up_at` | timestamp | yes | When the lookup was performed; used for both display and the persisted history's ordering. |
| `status` | text enum: `ok` \| `not_found` \| `unavailable` | yes | `ok` means `price`/`price_type`/`recommendation` are populated; `not_found`/`unavailable` mean they are absent and a warning message (FR-007/FR-008) is shown instead. |

**Validation rules**:
- `ticker` MUST be non-empty after trimming before a lookup is attempted (FR-009).
- `ticker` normalization: uppercase, trim whitespace, and if the result doesn't
  already end in `-USD` (or another already-qualified pair the app recognizes),
  append `-USD` — the yfinance-based functions this feature calls
  (`fetch_market_data`, `get_ticker_frame`) expect that suffixed form, matching how
  every other ticker in this app is represented (`universe.py` builds tickers as
  `f"{symbol}-USD"`). The Binance-facing helpers (`to_usdt_symbol`,
  `fetch_binance_price`) already strip this suffix internally, so normalizing to the
  suffixed form is safe for every downstream call.
- `price`, when present, MUST be a positive number — a zero/negative/missing value is
  treated as `not_found`, not a valid result (ties to Constitution Principle V: never
  present invalid data as if it were a real price).
- `recommendation`, when present, MUST be exactly one of `Buy`/`Sell`/`Hold` — no
  other label is valid output.

**Lifecycle**: A Ticker Lookup Result is created fresh on every submission (FR-010a
— a new submission always starts a new lookup, never mutates a prior one). On
`status = ok`, the result is persisted (FR-013); persistence is attempted regardless
of whether the page keeps a copy in memory, so a lookup that succeeds but fails to
save still triggers the FR-014 warning without discarding the on-screen result.

## Persisted form: `ticker_lookups` table

Unchanged from the stock version — this table already existed in `storage.py`'s
`init_db()` and is fully reused as-is; only the *values* written to `price_type` are
now `"live"`/`"delayed"` instead of `"live"`/`"last_close"`, which requires no schema
change since the column is a plain `TEXT`.

```sql
CREATE TABLE IF NOT EXISTS ticker_lookups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    price REAL NOT NULL,
    price_type TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    looked_up_at REAL NOT NULL
)
```

Only lookups with `status = ok` are ever written — there is nothing meaningful to
persist for a `not_found`/`unavailable` outcome, and FR-013 only requires persisting
*completed* lookups. No dedicated history-browsing UI is in scope (per the spec's
Assumptions section); this table exists purely for durability and future reuse, so
only `save_ticker_lookup()` (insert) and `list_ticker_lookups()` (minimal read, used
for verification in `quickstart.md` and by tests) are needed — both already exist
and require no changes for this pivot.
