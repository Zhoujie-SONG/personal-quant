# Progress

## M0 — engineering foundation

Status: **COMPLETE (offline gate passed)**

Completed:

- Python 3.11+ source-layout package and bounded dependencies.
- Immutable typed domain contracts for Instrument, MarketBar, TradingCalendarEntry, and LogicalAsset.
- YAML settings separated from code; YAML credentials rejected; `.env` ignored.
- Provider protocol, Raw DTO boundary, timezone/Decimal rules, and credential-safe logging.
- Unit-test and integration-test separation.

## M1A — Longbridge data foundation

Status: **COMPLETE / REAL API UNVERIFIED**

Completed:

- Longbridge static info, historical daily bars, CN trading days, and quote adapters.
- SDK response mapping, provider exception translation, and transient-only retry.
- Incremental monthly raw cache with coverage manifest, request key, retrieval timestamp, provider, and SDK version.
- MarketBar normalizer and monthly Parquet canonical repository queried through DuckDB with PIT filtering.
- Capability probe and sample ingestion script.
- Provider/data contract documentation and offline tests.

## M1A.1 — PIT hardening

Status: **COMPLETE (offline gate passed) / REAL API UNVERIFIED**

Completed:

- Replaced canonical use of Longbridge-specific errors with provider-neutral `DataNormalizationError` and `DataValidationError`.
- Added an automated lower-layer dependency boundary test; the provider protocol is unchanged.
- Added YAML-configured `DailyBarAvailabilityPolicy` with a conservative default 15-minute EOD delay.
- Changed canonical MarketBar storage to immutable revision schema v2 with `observation_id`, `payload_hash`, and `ingest_time`/observed-at identity.
- PIT queries now filter on both policy availability and actual observation time, then select the latest eligible revision per symbol/date/source.
- Preserved complete revision history through `get_bar_revisions` and added T1/T2 correction tests.
- Blocked forward-adjusted history from the formal PIT canonical ingestion path; formal baseline input is unadjusted only.
- Split raw cache requested coverage from calendar-verified dates; weekends, missing trading days, and unfinalized current-day retry behavior are tested.
- All offline tests pass; integration remains excluded by default.

Unverified:

- Real A-share ETF/index permissions and response shapes for this account; credentials were not available during offline delivery.
- Realtime quote entitlement.

Technical debt intentionally deferred:

- AkShare supplemental ETF discovery/NAV/IOPV/shares/AUM.
- Complete ETF/index metadata histories, including delist and index launch/methodology vintages.
- Canonical repositories for instruments and trading calendars.
- Raw cache concurrency locking and corruption recovery.
- Exchange half-day session-close mapping (the A-share normal session is currently encoded as 09:30–15:00).
- Historical correction refresh scheduling: canonical/raw storage can retain revisions, but verified old dates are not proactively re-polled.

## Next milestone recommendation (paused)

M1B is explicitly paused after M1A.1. When authorized later, proceed only after the capability probe and hardening review. AkShare, Vehicle Selector, strategy, backtest, Macro, LLM, GBDT, optimization, and live orders remain out of scope for this milestone.
