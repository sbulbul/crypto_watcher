# Feature Specification: Crypto Ticker Lookup

**Feature Branch**: `001-stock-ticker-lookup`
<!-- Directory/branch slug intentionally unchanged from its original "stock" name after
     the 2026-08-17 pivot below — Spec Kit feature slugs are stable identifiers, not
     living documentation. The content throughout this spec describes crypto only. -->

**Created**: 2026-08-17

**Status**: Draft

**Input**: User description: "Build a page where users enter a crypto ticker and see its current price and a buy/sell recommendation. I should navigate to this page with a button on main page." (Pivoted from an original "stock ticker" input — see Clarifications.)

## Clarifications

### Session 2026-08-17

- Q: Should a ticker lookup result (ticker, price, recommendation, timestamp) be saved anywhere, or is it purely shown on screen and discarded when the user leaves or looks up another ticker? → A: Save a lookup history — each completed lookup is persisted so it survives across sessions.
- Q: If the user submits the same ticker again while a previous lookup for it is still loading (or right after it just finished), what should happen? → A: Always re-fetch — every submission triggers a fresh lookup, replacing whatever is currently shown or loading.

### Session 2026-08-17 (pivot)

- Decision: This feature was re-scoped from stock (equity) tickers to cryptocurrency
  tickers, at the user's explicit request, replacing the equity version rather than
  adding a second feature. Reason: this app (`crypto_watcher`) already has full crypto
  evaluation infrastructure (Binance order-book/funding data, the existing buy/sell
  scorer) that stocks could never actually use — see `research.md` for what this
  unlocks. All user stories, functional requirements, and success criteria below are
  unchanged in structure from the original stock version; only the asset class and the
  two crypto-specific adjustments called out in FR-005 and FR-011 changed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Look up a ticker's price and recommendation (Priority: P1)

A user enters a cryptocurrency ticker symbol and sees that coin's current price along
with a Buy/Sell/Hold recommendation, so they can quickly decide what to do with it.

**Why this priority**: This is the entire value of the feature — without it there is
nothing to navigate to. It must work standalone before anything else matters.

**Independent Test**: Can be fully tested by opening the lookup page directly, entering
a known valid ticker (e.g., "BTC"), and confirming a current price and a Buy/Sell/Hold
recommendation are both displayed.

**Acceptance Scenarios**:

1. **Given** the ticker lookup page is open, **When** the user enters a valid ticker
   symbol and submits it, **Then** the page displays that ticker's current price and a
   Buy/Sell/Hold recommendation.
2. **Given** a price and recommendation are already shown for one ticker, **When** the
   user enters a different valid ticker and submits it, **Then** the page updates to
   show the new ticker's price and recommendation without requiring a full page reload.
3. **Given** the lookup is fetching data, **When** the user is waiting for results,
   **Then** the page shows a clear in-progress indicator until the price and
   recommendation appear (or a warning is shown, per User Story 3).

---

### User Story 2 - Reach the lookup page from the main page (Priority: P2)

A user on the app's main page clicks a button that takes them to the ticker lookup page.

**Why this priority**: The lookup page is only useful if users can find it. This is a
small, independently shippable addition once User Story 1 exists.

**Independent Test**: Can be fully tested by loading the main page, locating the new
button, clicking it, and confirming the user lands on the ticker lookup page.

**Acceptance Scenarios**:

1. **Given** the user is on the main page, **When** they look at the page, **Then** a
   clearly labeled button for the ticker lookup feature is visible.
2. **Given** the user is on the main page, **When** they click that button, **Then**
   they are taken to the ticker lookup page.

---

### User Story 3 - Get a clear warning when a lookup fails (Priority: P3)

A user enters a ticker that doesn't exist, or the price/recommendation data can't be
retrieved, and the page tells them clearly what went wrong instead of showing a blank
or broken result.

**Why this priority**: Builds on User Stories 1 and 2 by making the feature trustworthy
under failure conditions. Not required for the happy-path demo, but required before the
feature is considered reliable.

**Independent Test**: Can be fully tested by submitting a ticker symbol that does not
exist and confirming a visible, understandable warning appears in place of a price and
recommendation.

**Acceptance Scenarios**:

1. **Given** the ticker lookup page is open, **When** the user submits a ticker symbol
   that does not exist, **Then** the page shows a clear warning that the ticker was not
   found, and no price or recommendation is displayed.
2. **Given** the ticker lookup page is open, **When** the user submits a valid ticker
   but the underlying price/recommendation data cannot be retrieved (e.g., the data
   source is unreachable), **Then** the page shows a clear warning that the lookup
   failed, rather than a blank, frozen, or broken display.
3. **Given** the user submits the lookup form without entering a ticker, **When** they
   submit, **Then** the page shows a clear message asking them to enter a ticker,
   without attempting a lookup.

### Edge Cases

- What happens when the user enters a ticker symbol that doesn't exist or is misspelled?
- What happens when the fastest (real-time) price source is unavailable and the system
  has to fall back to a source with more lag — is that distinction shown to the user
  rather than presented as an equally live price? (Crypto markets trade continuously,
  so there is no "market closed" case the way there would be for stocks — see FR-011.)
- What happens when the price/recommendation data source is slow, unreachable, or
  returns an error?
- When the user submits the same ticker again while a previous lookup is still in
  progress, or right after one finishes, the system starts a new lookup and its
  result replaces whatever was previously shown or loading (see FR-010a).
- What happens when the user types extra whitespace, lowercase letters, or special
  characters into the ticker field?
- What happens when a ticker symbol or recommendation text is unusually long — does the
  layout still display it fully, without overlapping or cutting off other page content?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The main page MUST display a clearly labeled button that navigates the
  user to the ticker lookup page.
- **FR-002**: The ticker lookup page MUST provide a way for the user to enter a
  cryptocurrency ticker symbol and submit it.
- **FR-003**: Upon submitting a valid ticker, the system MUST retrieve and display that
  ticker's current price.
- **FR-004**: Upon submitting a valid ticker, the system MUST display a Buy, Sell, or
  Hold recommendation alongside the price.
- **FR-005**: The recommendation MUST be produced using the same evaluation criteria the
  system already applies to coins elsewhere in the app (the same buy/sell scoring the
  scanner uses), so recommendations are consistent regardless of where in the app a
  user sees them.
- **FR-006**: While a lookup is in progress, the system MUST show the user a clear
  indication that the lookup is running, until it completes or fails.
- **FR-007**: If the submitted ticker does not exist or is not recognized, the system
  MUST show a visible warning stating the ticker was not found, instead of showing a
  blank, zero, or broken price/recommendation.
- **FR-008**: If price or recommendation data cannot be retrieved for any other reason
  (e.g., the data source is unreachable or returns an error), the system MUST show a
  visible warning describing that the lookup failed, instead of failing silently.
- **FR-009**: If the user submits the lookup without entering a ticker, the system MUST
  prompt them to enter one instead of performing a lookup.
- **FR-010**: The system MUST let the user look up another ticker after a lookup
  completes (successfully or not) without leaving the page.
- **FR-010a**: If the user submits a new lookup while a previous one is still in
  progress, the system MUST start the new lookup immediately and its result (or
  warning) MUST replace whatever was previously shown or loading, rather than
  queuing or blocking the new submission.
- **FR-011**: If the displayed price did not come from the fastest real-time source
  (for example, because the primary live price source was unavailable and the system
  fell back to a source with more lag), the system MUST clearly label it as such (e.g.,
  as a "delayed" price) rather than presenting it as equally live. Crypto markets trade
  continuously, so this reflects data-source freshness rather than a market being open
  or closed.
- **FR-012**: The ticker lookup page MUST display the ticker, price, recommendation, and
  any warning message fully, without any text overlapping or being cut off, regardless
  of the length of the values shown.
- **FR-013**: The system MUST persist every completed lookup (ticker, price, whether
  that price was live or delayed, recommendation, and timestamp) to a lookup
  history that survives across app restarts and sessions.
- **FR-014**: If saving a completed lookup to history fails, the system MUST show a
  visible warning that the result may not be saved, rather than silently discarding it
  (consistent with the app's constitution requirement that no data be silently lost).

### Key Entities

- **Ticker Lookup Result**: Represents the outcome of one lookup — the ticker symbol
  the user entered, the current price returned, whether that price is live or delayed,
  the Buy/Sell/Hold recommendation, and the time the lookup was performed. Each result
  is persisted as an entry in the user's lookup history.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from the main page to seeing a price and recommendation for
  a valid ticker in 3 clicks or fewer (navigate to the page, enter ticker, submit).
- **SC-002**: For a valid, actively traded ticker, the price and recommendation appear
  within 5 seconds of submission in at least 95% of lookups.
- **SC-003**: 100% of lookups for a non-existent or unreachable ticker result in a
  visible warning message, with none resulting in a blank or broken page.
- **SC-004**: Users can perform at least 10 consecutive ticker lookups on the same page
  visit without needing to reload the page.
- **SC-005**: In usability review across the range of supported ticker symbol lengths
  and recommendation text, no instance of overlapping or cut-off text is observed.

## Assumptions

- "Ticker" refers to cryptocurrency ticker symbols only (matching the rest of this
  app); other asset types (e.g., stocks) are out of scope for this feature.
- The recommendation is a simple three-way label (Buy / Sell / Hold) rather than a
  numeric score, matching how the app communicates decisions elsewhere.
- The recommendation is generated using the same buy/sell scoring the app already runs
  for other coins it scans; this feature only needs to run that same scoring for a
  single, user-specified ticker on demand.
- A lookup is a single on-demand fetch triggered by the user submitting a ticker; the
  price and recommendation do not automatically refresh in the background while the
  page is open.
- Only one ticker is looked up at a time; comparing multiple tickers side by side is out
  of scope for this feature.
- All users of the app see the same lookup experience; no per-user permissions or
  account-specific behavior apply to this feature.
- The main page already exists and can be modified to add a new navigation button.
- Persisted lookup history is written for durability and future reuse, but a
  dedicated screen for browsing/searching past history is out of scope for this
  feature; only the current lookup's result must be shown on the page itself.
