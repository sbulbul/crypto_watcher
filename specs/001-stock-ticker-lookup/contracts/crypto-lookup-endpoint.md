# Contract: Ticker Lookup Endpoint

This app is server-rendered (Flask + Jinja2); its only "external interface" for this
feature is the JSON endpoint the crypto lookup page's client-side `fetch()` call uses
to run a lookup without a full page reload (FR-006, FR-010a). This mirrors the
existing `/scan_status`-style JSON endpoints already in `app.py`, and replaces the
stock version's `/stock_lookup` contract.

## `GET /crypto_lookup`

**Query parameters**:
| Name | Required | Notes |
|---|---|---|
| `ticker` | yes | Raw user input; the endpoint normalizes (trim + uppercase + `-USD` suffix if missing — see data-model.md) before use. |

**Behavior**: Performs one on-demand lookup (FR-003, FR-004) — no queuing, no
caching. Each request is independent; submitting the same ticker twice performs the
lookup twice (per the "always re-fetch" clarification).

### Response: success

```json
{
  "status": "ok",
  "ticker": "BTC-USD",
  "price": 63877.21,
  "price_type": "live",
  "recommendation": "Hold",
  "looked_up_at": "2026-08-17T14:32:05Z"
}
```

- `price_type` is `"live"` (Binance spot source answered) or `"delayed"` (a fallback
  source answered instead) — FR-011.
- `recommendation` is one of `"Buy"` / `"Sell"` / `"Hold"`, derived from
  `score_from_history()`'s real `quick_win_score`/`long_term_score` output per
  research.md.
- A successful response means the result was also handed to persistence (FR-013); if
  persistence itself failed, `warning` (below) is still included alongside the
  `"ok"` status so the user sees the price/recommendation *and* the FR-014
  save-failure warning rather than losing the result.

### Response: ticker not found

```json
{
  "status": "not_found",
  "ticker": "ZZZZZZ-USD",
  "warning": "We couldn't find a ticker called \"ZZZZZZ-USD\". Check the symbol and try again."
}
```

Maps to FR-007 / spec acceptance scenario US3.1 — every price/history source
returned no usable data for the symbol (research.md's not-found decision).

### Response: data source unavailable

```json
{
  "status": "unavailable",
  "ticker": "BTC-USD",
  "warning": "We couldn't reach the market data source. Please try again in a moment."
}
```

Maps to FR-008 / spec acceptance scenario US3.2 — an unexpected error propagated out
of the lookup pipeline itself (research.md's not-found vs. unavailable decision).

### Response: missing ticker (empty submission)

Handled client-side per FR-009 — the page prompts the user before making a request
at all when the input is empty, so this endpoint is never called with a blank
`ticker`. If it somehow is (e.g., a malformed request), it responds the same way as
"not found" rather than a generic server error, since no branch may be left
undefined (Constitution Principle I).

### Response: history save failed (on an otherwise successful lookup)

```json
{
  "status": "ok",
  "ticker": "BTC-USD",
  "price": 63877.21,
  "price_type": "live",
  "recommendation": "Hold",
  "looked_up_at": "2026-08-17T14:32:05Z",
  "warning": "This result may not have been saved to your lookup history."
}
```

Maps to FR-014. The price/recommendation are still shown — a save failure must not
discard a result the user already has (Constitution Principle VI), it must only be
visibly flagged.

## Client-rendered states (page-side contract)

The crypto lookup page's JS must render exactly one of these states at a time, per
FR-006/FR-010a — unchanged from the stock version:
1. **Idle** — before any submission.
2. **Loading** — immediately on submit, replacing whatever was previously shown.
3. **Result** — `status: "ok"` response (plus an inline warning banner if `warning`
   is also present).
4. **Warning-only** — `status: "not_found"` or `"unavailable"` response; no
   price/recommendation is rendered (per US3 acceptance scenarios).
