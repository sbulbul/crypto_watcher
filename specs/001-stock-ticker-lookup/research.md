# Research: Crypto Ticker Lookup

This supersedes the stock-ticker version of this research document. Most Technical
Context items are unchanged from that version (interaction pattern, testing
framework); what changed is everything downstream of the asset-class pivot —
recommendation methodology, price retrieval, and not-found/unavailable detection all
now map onto *real, already-existing* crypto functions instead of new stock-specific
code.

## Decision: Recommendation methodology for crypto tickers

**Decision**: Call `scanner.py`'s `score_from_history(coin, hist, market_flow)`
directly — the exact function the batch scanner already calls for every coin it
scans — for the single user-submitted ticker. `hist` comes from
`scanner.fetch_market_data([ticker])` (the same `yfinance` hourly-OHLCV bulk-download
helper the scanner uses, called with a one-item list) via `get_ticker_frame()`;
`market_flow` comes from `market_flow.fetch_market_flow(ticker, current_price)` (the
same Binance order-book/funding-rate/taker-buy-ratio fetch used elsewhere). The
function's return value already contains `quick_win_score`, `long_term_score`,
`signal`, and `long_term_signal` — the app's real dual-score output.

To reduce that dual-score output to the single Buy/Sell/Hold label FR-004 asks for,
reuse the exact candidate logic `scanner.py`'s `scan_market()` already uses to decide
what counts as a buy vs. sell setup (`config.py`'s `MIN_BUY_SCORE`/`MIN_SELL_SCORE`):

- `long_term_score >= MIN_SELL_SCORE` → **Sell**
- else if `quick_win_score >= MIN_BUY_SCORE` → **Buy**
- else → **Hold**

**Rationale**: FR-005 says the recommendation must use "the same evaluation criteria
the system already applies to coins elsewhere in the app." For crypto, unlike stocks,
this is achievable *literally* — `score_from_history()`/`calculate_score()` already
scores exactly this ticker type using exactly this data (Binance market-flow +
hourly OHLCV), because that is what the scanner has always done. This closes the gap
the stock version's research.md had to work around (crypto-only order-book/funding
data that stocks don't have) — the recommendation is no longer a parallel,
purpose-built scoring model; it *is* the app's model.

**Alternatives considered**:
- *Build a new, simplified crypto-specific score (as the stock version had to for
  equities)* — rejected: unnecessary now that the real scorer is directly usable,
  and would create two different scoring behaviors for the same coin depending on
  which page the user is on, which is exactly what FR-005 says not to do.
- *Call `calculate_score()` directly instead of via `score_from_history()`* —
  rejected: `score_from_history()` already contains the validated
  indicator-derivation logic (RSI, ATR, support/resistance, VWAP, volume averages)
  the scanner relies on; reimplementing that derivation for the lookup path would
  duplicate logic and risk it drifting out of sync with the scanner over time.

## Decision: Current price retrieval and "live" vs. "delayed" labeling

**Decision**: Call `storage.py`'s existing `fetch_latest_price(ticker)` directly —
the same multi-source fallback chain already used elsewhere in the app (Binance spot
ticker → Yahoo 1-minute history → Yahoo 1-hour `yf.download` fallback → CoinGecko
simple price). Label the result `"live"` when the Binance spot source answered
(`quote["source"] == "Binance spot"`), and `"delayed"` for any of the other three
fallback sources.

**Rationale**: `fetch_latest_price()` is already exactly "get the current price for a
crypto ticker, trying the fastest real source first" — no new price-fetch logic is
needed. Crypto markets trade continuously, so the stock version's "market
open/closed" framing for FR-011 doesn't apply; what *does* still matter is that a
user isn't shown a price from a slower, more-stale fallback source as if it were the
fastest real-time tick. Binance's spot ticker is the freshest of the four sources (a
live trade price), so "did it come from Binance" is a reasonable, already-observable
proxy for "live" vs. "delayed."

**Alternatives considered**: Treat all four sources as equally "live" (drop the
live/delayed distinction entirely) — rejected: FR-011 (updated for crypto) still
requires the distinction to be shown when the fastest source wasn't the one that
answered, and the underlying data-freshness gap between a live Binance tick and a
CoinGecko "simple price" snapshot is real enough to be worth surfacing.

## Decision: Distinguishing "ticker not found" from "data source unavailable"

**Decision**: A ticker is **not_found** (FR-007) when the whole pipeline runs
without an unexpected exception but produces no usable data — i.e.,
`fetch_latest_price()` returns `None` (every source either had no match or failed
its own internal check) and/or `fetch_market_data([ticker])`'s history is empty.
A ticker is **unavailable** (FR-008) when an exception propagates out of the lookup
orchestrator itself — e.g., an unexpected error inside `fetch_market_data()` (rather
than one of the individually-caught branches inside `fetch_latest_price()`), a
`market_flow.fetch_market_flow()` failure that raises instead of returning an error
dict, or any other unhandled error — treated as a safety-net catch-all distinct from
the normal "no data found for this symbol" path.

**Rationale**: `fetch_latest_price()` already swallows individual source failures
internally (each fallback is wrapped in its own `try/except: return None`), so by
design it cannot distinguish "invalid symbol" from "this one source is down" — but
because it tries four independent sources before giving up, a total `None` is a
reasonably strong signal that the symbol itself isn't recognized, not that
everything is simultaneously unreachable. This mirrors the same not-found vs.
unavailable split the stock version used, just re-grounded in real crypto data
sources instead of a single `yfinance` call. This directly serves Constitution
Principle I (no undefined branches): both failure shapes are explicitly produced,
not merged into one generic catch-all.

**Alternatives considered**: Report every failure as a single generic "lookup
failed" message — rejected for the same reason as in the stock version: less
actionable, and the spec's US3 acceptance scenarios describe the two cases with
different messages.

## Decision: Testing framework (unchanged)

**Decision**: Keep `pytest`, adopted during the stock version.

**Rationale**: Still the right tool for the same reason as before — deterministic,
network-free verification of the recommendation-mapping and not-found/unavailable
branches. Tests will mock at the `scanner`/`market_flow`/`storage` function
boundaries (`fetch_latest_price`, `fetch_market_data`, `fetch_market_flow`) instead
of mocking `yfinance.Ticker` directly, since those are now the actual seams the
lookup orchestrator calls through.

## Decision: Interaction pattern (unchanged)

**Decision**: Keep the client-side `fetch()`-on-submit pattern with an immediate
loading state and "always re-fetch, replace what's shown" behavior, validated during
the stock version's implementation.

**Rationale**: Nothing about the crypto pivot changes the shape of a single on-demand
lookup — it's still one short-lived server round trip per submission. No reason to
revisit a decision that already worked.
