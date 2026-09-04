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

Status: **COMPLETE (offline gate, Longbridge integration, and provider capability gates passed) / REAL RECONCILIATION UPSTREAM-BLOCKED**

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
- Real AkShare integration passed in the original M1B run. With refreshed process-only credentials, the Longbridge integration test passed (`1 passed`) and the capability gate passed ETF static, ETF bars, index bars, CN trading calendar, and realtime quote.
- A subsequent end-to-end reconciliation attempt reached Longbridge successfully but produced no comparison result because the AkShare/Eastmoney historical endpoint closed both proxied and direct connections; this is recorded as upstream-blocked rather than a data mismatch.

## M1B.1 — Calendar PIT and metadata observation semantics fix

Status: **COMPLETE (offline gate passed)**

Completed:

- Separated historical calendar economic availability from system ingestion with the explicit `historical_calendar_session_close_v1` policy and `HISTORICAL_LATEST` provenance.
- Made later-downloaded calendar history visible to Economic PIT after the historical session close while preserving the ingestion gate for System Replay.
- Added `get_metadata_observations` to return all eligible ETF metadata observations with source provenance intact.
- Qualified AkShare metadata sources by endpoint so spot and SZSE scale observations remain distinguishable; market-bar reconciliation source semantics are unchanged.
- Removed implicit cross-source whole-row selection: `get_metadata` now requires explicit resolution whenever multiple eligible sources exist.
- Applied snapshot-time eligibility consistently to Index metadata and rejected naive `research_data_cutoff` values.
- Removed duplicated ETF snapshot eligibility logic and documented the future field-level `MetadataResolver` contract without implementing M2 resolution or selection.

## U1 — Logical Asset redundancy diagnostic

Status: **PASS**

Completed:

- Built the research-only candidate benchmark registry and real-data coverage/correlation/effective-breadth diagnostic.
- Preserved CASH as EX_CASH and OIL as inactive, non-executable informational exposure.
- Produced evidence for human review without automatically removing assets or defining Universe v1.

## U1.1 — Effective breadth completion and robustness

Status: **PASS**

Completed:

- Resolved SEMI to official H30184 price-index history and BOND_LONG/BOND_MED to official H11077/H00140 full-price histories after explicit Longbridge-unavailable probes.
- Added weekly common-window effective breadth as a fixed cross-timezone robustness diagnostic without forward fill, zero fill, or lag optimization.
- Recorded daily N_eff 5.04 and weekly N_eff 4.83, plus the required structural-pair evidence.

## U-FREEZE — Logical Asset Universe v1.0

Status: **FROZEN_V1**

Completed:

- Froze exactly 15 ACTIVE Logical Assets in `configs/universe_v1.yaml`, including CASH.
- Deferred HSTECH for human-approved structural redundancy and kept OIL inactive/non-executable.
- Froze five sleeve assignments and three semi-static prior risk clusters without implementing cluster caps or portfolio construction.
- Pinned the research benchmark provenance to the U1.1 baseline commit and candidate-registry SHA-256.
- Enforced machine-readable freeze invariants and the separation of Logical Assets, research benchmarks, and future execution vehicles.
- Recorded the full human decision and provenance in `docs/universe_v1_freeze.md`.

## M2A — Field-level ETF MetadataResolver

Status: **COMPLETE (offline gate passed)**

Completed:

- Added versioned, machine-readable per-field source precedence, freshness, and conflict policies in `configs/metadata_resolution.yaml`.
- Added `ResolvedField`/`ResolvedETFMetadata` domain contracts with `RESOLVED`, `UNKNOWN`, `STALE`, and `CONFLICT` states.
- Implemented deterministic non-null same-source revision selection without relying on SQLite row order.
- Implemented per-field cross-source precedence, explicit fallback reasons, require-agreement conflicts, and retained competing observation summaries.
- Preserved field-level source, availability, effective-period, snapshot, ingestion, and provider-payload provenance through JSON-safe serialization.
- Reused repository PIT eligibility as the only input gate, including Economic/System Replay, snapshot-time, and research-cutoff semantics.
- Added offline coverage for complementary field merges, no whole-row overwrite, PIT modes, cutoff, freshness, fallback, conflict, unknown, deterministic revisions, aware datetimes, serialization, and frozen-Universe immutability.

Scope boundary:

- Historical Vehicle Registry: **NOT IMPLEMENTED**
- Logical Asset to ETF mapping: **NOT IMPLEMENTED**
- Vehicle Selector and ETF ranking: **NOT IMPLEMENTED**
- Strategy, backtest, portfolio construction, optimization, and execution: **NOT IMPLEMENTED**

## M2A.1 — Same-source metadata revision tie semantics

Status: **COMPLETE (offline gate passed)**

Completed:

- Removed provider payload hash from semantic latest-revision chronology.
- Made equal-time, conflicting same-source field values fail fast while retaining
  hash only as a deterministic representative for already-equal values.
- Advanced metadata resolution policy semantics to
  `etf_metadata_field_resolution_v1_1` without changing freshness windows.

## M2B.0 — Historical ETF vehicle candidate discovery and evidence pack

Status: **COMPLETE / CANDIDATE_NOT_APPROVED / PARTIAL_CURATED**

Completed:

- Added `configs/historical_vehicle_candidates.yaml`, bound to frozen Universe v1
  and its file hash, with 17 evidence records across all 14 active non-cash
  Logical Assets.
- Classified 14 records as exact-tracking candidates, 2 as economic proxy
  candidates, and 1 as a rejected semantic mismatch; all remain `UNREVIEWED`.
- Kept CASH as `CASH_BALANCE` with no ETF, HSTECH deferred, and OIL inactive with
  no vehicle discovery or equity proxy.
- Separated listing dates from mapping-effective periods and retained a contract
  for adjacent historical tracking-index periods and delisted observations.
- Added official claim-level provenance plus current-snapshot semantics that cannot
  imply historical-universe or cemetery completeness.
- Added an offline fail-fast validator, regression tests, machine-readable coverage,
  and the technical evidence report under `reports/vehicle_candidate_m2b0/`.

Scope boundary:

- Approved Historical Vehicle Registry: **NOT IMPLEMENTED**
- Vehicle Selector, ranking, and liquidity screening: **NOT IMPLEMENTED**
- Strategy, backtest, portfolio, Macro, LLM, broker, and execution: **NOT IMPLEMENTED**

## M2B.0.1 — Vehicle candidate breadth and targeted cemetery audit

Status: **COMPLETE / CANDIDATE_NOT_APPROVED / PARTIAL_CURATED**

Completed:

- Expanded the candidate evidence pack from 17 representative records to 108
  evidence-bearing dispositions across all 14 active non-cash Logical Assets.
- Retained 107 current candidates without size, turnover, trading-cost, premium,
  performance, or ranking filters; all remain `UNREVIEWED`.
- Split semantic mapping into `EXACT_BENCHMARK` (69),
  `EXACT_LOGICAL_EXPOSURE` (27), economic proxy (5), rejected mismatch (7),
  and unresolved (0) states.
- Added the candidate-only canonical index identity registry with 15 identities
  and 20 officially evidenced provider/exchange code representations, including
  000300/399300 and Au99.99/Au9999.
- Distinguished price, full-price, net-total-return, currency/fair-value-adjusted,
  spot-price, and Shanghai-Gold benchmark variants without changing Universe v1.
- Preserved 510880 and 512170 as unapproved proxies and 517520 as a rejected
  spot-gold mismatch.
- Completed a targeted, non-exhaustive official cemetery audit and retained
  terminated 560890.SH with the end-exclusive 2024-09-20 to 2026-04-01 mapping.
- Added machine-readable breadth/termination coverage, expanded evidence report,
  and fail-fast offline tests for alias, variant, semantic-class, retention, and
  cemetery-completeness contracts.

Scope boundary:

- Approved Historical Vehicle Registry: **NOT IMPLEMENTED**
- Vehicle Selector, ranking, and operational screening: **NOT IMPLEMENTED**
- Strategy, backtest, portfolio, Macro, LLM, broker, and execution: **NOT IMPLEMENTED**

## Next milestone

M2B.1 remains gated and has not started. M2B.0/M2B.0.1 have not approved or
frozen a Historical Vehicle Registry. Vehicle Selector remains deferred to a
later gate. Strategy, backtest, Macro, LLM, GBDT, portfolio construction,
optimization, broker integration, and live orders remain out of scope.
