# Research: Stock Ticker Lookup

All Technical Context items were resolvable from the existing repository; no items
required external research beyond reading the current codebase. This document
records the decisions and — most importantly — the one non-obvious tradeoff
(recommendation methodology) that the spec's FR-005 assumption couldn't fully
resolve on its own.

## Decision: Recommendation methodology for stock tickers

**Decision**: Compute the Buy/Sell/Hold recommendation from real, `yfinance`-sourced
technical signals for the ticker (recent price change %, short-vs-longer
moving-average trend, and volume trend), combined into a single 0–100 score and
mapped to a signal using the same threshold philosophy already codified in
`config.py` (`MIN_BUY_SCORE = 25`, `MIN_SELL_SCORE = 55`): score at or below the buy
threshold → Buy, score at or above the sell threshold → Sell, otherwise → Hold.

**Rationale**: The feature spec (FR-005) says the recommendation must use "the same
evaluation criteria the system already applies to stocks elsewhere in the app." In
practice, the app's only existing scoring logic (`scorer.py`'s
`score_market_flow()`) scores *crypto* market-microstructure signals — order-book
bid/ask imbalance, taker-buy ratio, and futures funding rate — all sourced from
Binance's crypto exchange APIs (`market_flow.py`). None of those inputs exist for an
equity ticker; Yahoo Finance (via `yfinance`, the only equity-capable dependency the
app has) does not expose an order book or a funding rate for stocks. Literally
calling the existing scorer is therefore not possible without fabricating inputs,
which would violate the constitution's Live API Integrity principle (no data
presented as live that isn't real). The closest honest interpretation of FR-005 is
to reuse the app's *scoring architecture* — a numeric score compared against
`config.py`'s existing buy/sell thresholds, producing the same three-way signal
vocabulary used elsewhere — computed from signals that are actually available and
real for equities.

**Alternatives considered**:
- *Feed default/placeholder values into `score_market_flow()`* — rejected: would
  silently present fabricated crypto-microstructure data as if it were a real signal
  for a stock, violating Constitution Principle V (Live API Integrity) and Principle
  I (no undefined/faked branches).
- *Call an external stock-analyst-rating or recommendation API* — rejected: adds a
  new third-party dependency (and likely an API key requirement) beyond what the
  user asked for, when the app already has a capable, dependency-free data source
  (`yfinance`) for the raw inputs needed to score momentum/trend.
- *New lightweight technical-indicator score computed only from real `yfinance`
  data, using the app's existing score→threshold→signal pattern* — **selected**:
  no new dependencies, uses only real fetched data, and stays as consistent with the
  rest of the app's decision-making style as is technically possible.

## Decision: Current price retrieval

**Decision**: Fetch the ticker's most recent price via `yfinance` (the same library
`scanner.py` already uses for market data), reading the latest available close from
its returned history/quote data. If the most recent price is not from the currently
open trading session (e.g., the market is closed), label it as a last-close price
per FR-011 rather than presenting it as live.

**Rationale**: `yfinance` is already a project dependency and already proven to work
against this exact kind of ticker data in `scanner.py`; introducing a second stock
data source (e.g., a paid quote API) is unnecessary and out of scope.

**Alternatives considered**: The `requests`-based Binance/CoinGecko helpers in
`storage.py` (`fetch_binance_price`, `fetch_coingecko_price`) were considered for
consistency, but both are crypto-exchange-specific endpoints and cannot resolve an
equity ticker like "AAPL" — rejected as inapplicable to this feature's domain.

## Decision: Distinguishing "ticker not found" from "data source unavailable"

**Decision**: Treat a `yfinance` response with no usable price/history data for the
submitted symbol as "not found" (FR-007); treat a network error, timeout, or
unexpected/malformed response as "unavailable" (FR-008). These map to two distinct
warning messages so the user knows whether the ticker itself was the problem or the
lookup failed for an unrelated reason.

**Rationale**: `yfinance` generally does not raise a distinct exception for an
unknown ticker — it typically returns an empty result — so the "not found" case must
be detected by validating the response shape/emptiness rather than by catching a
specific error type. This directly serves Constitution Principle I (no undefined
branches): both failure shapes must be explicitly checked for, not merged into one
generic catch-all.

**Alternatives considered**: A single generic "lookup failed" message for both cases
— rejected because it's less actionable for the user and the spec's two acceptance
scenarios (US3, scenarios 1 and 2) explicitly describe them as different messages.

## Decision: Testing framework

**Decision**: Adopt `pytest`.

**Rationale**: No test framework exists in the repo today. `pytest` is the de facto
standard for Python projects and is needed to exercise this feature's required
failure branches (not-found ticker, unavailable data source, failed history write)
deterministically and without depending on live network calls in every test run —
directly supporting the constitution's Zero Loophole Execution principle by making
every branch verifiable.

**Alternatives considered**: `unittest` (Python stdlib, avoids adding a dependency)
— rejected in favor of `pytest`'s simpler assertion/fixture syntax, which keeps the
first test suite in this repo approachable for a single maintainer.

## Decision: Interaction pattern (loading / re-fetch behavior)

**Decision**: A client-side `fetch()` call triggered on form submit, showing a
loading indicator immediately and replacing it with the result or a warning when the
response arrives — no background polling/threading like the multi-symbol scan uses.

**Rationale**: A single-ticker lookup is one short-lived external call, unlike the
multi-symbol `scan_market()` flow (which runs in a background thread and is polled
via `/scan_status` because it can take much longer over many symbols). Matching that
heavier pattern here would add complexity the spec's scope (SC-002: 5 seconds, one
ticker at a time) doesn't require. Re-submitting while a lookup is in flight simply
issues a new `fetch()` and renders whichever response is the latest one requested,
satisfying the "always re-fetch, replace what's shown" clarification.

**Alternatives considered**: Reusing the existing background-thread + polling
pattern (`/start_scan` + `/scan_status`) — rejected as unnecessary complexity for a
single, fast, on-demand request.
