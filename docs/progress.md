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

Unverified:

- Real A-share ETF/index permissions and response shapes for this account; credentials were not available during offline delivery.
- Realtime quote entitlement.

Technical debt intentionally deferred:

- AkShare supplemental ETF discovery/NAV/IOPV/shares/AUM.
- Complete ETF/index metadata histories, including delist and index launch/methodology vintages.
- Canonical repositories for instruments and trading calendars.
- Raw cache concurrency locking and corruption recovery.
- Exchange half-day session-close mapping (the A-share normal session is currently encoded as 09:30–15:00).

## Next milestone recommendation

Proceed to P0/P1B only after the capability probe is reviewed. Define and freeze the 15–30 Logical Asset universe, then add AkShare as a supplemental provider and implement PIT metadata/canonical repositories. Vehicle Selector and its historical-availability tests should follow before any strategy or backtest work. Macro, LLM, GBDT, optimization, and live orders remain out of scope.

