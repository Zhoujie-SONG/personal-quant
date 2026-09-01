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
- M1A.1 PIT queries filtered on both policy availability and actual observation time; M1A.2 supersedes this with two explicit modes.
- Preserved complete revision history through `get_bar_revisions` and added T1/T2 correction tests.
- Blocked forward-adjusted history from the formal PIT canonical ingestion path; formal baseline input is unadjusted only.
- Split raw cache requested coverage from calendar-verified dates; M1A.2 supersedes the verification state with provisional/finalized cutoff semantics.
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

## M1A.2 — PIT semantics finalization

Status: **COMPLETE (offline gate passed) / REAL API UNVERIFIED**

Completed:

- Split canonical reads into explicit `PITQueryMode.ECONOMIC` and `PITQueryMode.SYSTEM_REPLAY`; callers must also specify the canonical source.
- Defined formal market source as Longbridge and prevented implicit multi-source same-date results.
- Classified current Longbridge historical OHLCV as `HISTORICAL_LATEST`, distinct from a true historical provider vintage.
- Upgraded immutable canonical revision storage to schema v3 with policy-independent `value_hash`, separate `availability_policy_id`, and `historical_data_semantics`.
- Added explicit v1/v2-to-v3 migration tooling and fail-fast mixed-schema detection for both PIT and revision queries.
- Split raw daily-bar cache state into `provisional_dates` and `finalized_dates`; a current-day non-empty response cannot finalize before the configured safety cutoff.
- Added regression coverage for 2019 data ingested in 2026, source isolation, policy/value revision separation, mixed-schema migration, and pre/post-cutoff cache behavior.
- All offline tests pass; integration remains excluded by default.

## M1A.2a — Finalization promotion fix

Status: **COMPLETE (offline gate passed) / REAL API UNVERIFIED**

Completed:

- Added a finalized-only raw-cache read path for formal Longbridge daily-bar ingestion while retaining provisional observations for audit.
- Required each returned observation's own `retrieved_at` to meet the date cutoff; later date finalization cannot promote an earlier preliminary value.
- Preserved normal historical ingestion for bars retrieved after their original finalization cutoff.
- Added fail-fast protection when the same schema-v3 `observation_id` is presented with conflicting `historical_data_semantics`.
- Added full offline provider/cache → ingestion service → Parquet repository regression coverage, including Economic and System Replay queries.
- Reserved the M3 requirement to freeze `research_data_cutoff` and `dataset_snapshot_id` for every historical research run.

## M1B — AkShare supplemental provider and metadata PIT foundation

Status: **COMPLETE (offline gate passed; AkShare integration passed) / LONGBRIDGE TOKEN EXPIRED**

Completed:

- Added the four-way provider-neutral `DataAvailabilityClass` and machine-readable `configs/data_sources.yaml` registry.
- Added strict AkShare supplemental adapters for ETF spot/universe, SZSE scale snapshots, and unadjusted daily reconciliation bars; DataFrames never cross the adapter.
- Added immutable ETF and Index metadata observations with PIT-aware SQLite repositories and optional `research_data_cutoff`.
- Enforced no historical backfill for snapshot-only fields and added forward-collected PIT snapshot accumulation.
- Preserved delisted metadata observations while marking cemetery completeness `UNVERIFIED`.
- Added index `BACKFILLED`/`LIVE` classification and an empty provenance-required curated index registry.
- Added canonical trading-calendar observation storage with half-day/session preservation.
- Added idempotent `snapshot_etf_metadata.py` and tolerance-configured `reconcile_market_data.py` scripts.
- Added offline tests for availability classification, snapshot discipline, revision preservation, Economic/System Replay semantics, DataFrame/schema boundaries, index/calendar behavior, snapshot idempotency, and reconciliation tolerances.
- Real AkShare integration passed. Real Longbridge reconciliation remains blocked because all gate calls returned token-expired failures.

## Next milestone recommendation (paused)

M2 is explicitly paused after M1B. Vehicle Selector, final Logical Asset universe, strategy, backtest, Macro, LLM, GBDT, portfolio construction, optimization, broker integration, and live orders remain out of scope.
