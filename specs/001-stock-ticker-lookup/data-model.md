# Data Model: Stock Ticker Lookup

## Entity: Ticker Lookup Result

Represents the outcome of one lookup, per the spec's Key Entities section. Held
in-memory for display, and persisted as one row per completed lookup (FR-013).

| Field | Type | Required | Notes |
|---|---|---|---|
| `ticker` | text | yes | Normalized to uppercase, trimmed of surrounding whitespace. Non-empty after trimming (FR-009 rejects empty submissions before this entity is created). |
| `price` | number | yes, on success | The retrieved price. Always > 0 when present; absent when the lookup produced a warning instead (FR-007/FR-008). |
| `price_type` | text enum: `live` \| `last_close` | yes, on success | Set per FR-011 — `last_close` whenever the price is not from the currently open trading session. |
| `recommendation` | text enum: `Buy` \| `Sell` \| `Hold` | yes, on success | Derived per `research.md`'s scoring decision. |
| `looked_up_at` | timestamp | yes | When the lookup was performed; used for both display and the persisted history's ordering. |
| `status` | text enum: `ok` \| `not_found` \| `unavailable` | yes | `ok` means `price`/`price_type`/`recommendation` are populated; `not_found`/`unavailable` mean they are absent and a warning message (FR-007/FR-008) is shown instead. |

**Validation rules**:
- `ticker` MUST be non-empty after trimming before a lookup is attempted (FR-009).
- `price`, when present, MUST be a positive number — a zero/negative/missing value is
  treated as `unavailable`, not a valid result (ties to Constitution Principle V:
  never present invalid data as if it were a real price).
- `recommendation`, when present, MUST be exactly one of `Buy`/`Sell`/`Hold` — no
  other label is valid output.

**Lifecycle**: A Ticker Lookup Result is created fresh on every submission (FR-010a
— a new submission always starts a new lookup, never mutates a prior one). On
`status = ok`, the result is persisted (FR-013); persistence is attempted regardless
of whether the page keeps a copy in memory, so a lookup that succeeds but fails to
save still triggers the FR-014 warning without discarding the on-screen result.

## Persisted form: `ticker_lookups` table

Follows the existing `storage.py` convention (`get_connection()` /
`CREATE TABLE IF NOT EXISTS` inside `init_db()`, alongside the current `scans` /
`scan_results` tables).

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
*completed* lookups. `looked_up_at` is stored the same way the existing tables store
timestamps (`started_at REAL`/`completed_at REAL` in `scans`) for consistency.

No dedicated history-browsing UI is in scope (per the spec's Assumptions section);
this table exists purely for durability and future reuse, so no update/delete
operations are needed — only insert (`save_ticker_lookup`) and a minimal read
(`list_ticker_lookups`) used for verification in `quickstart.md` and by tests.
