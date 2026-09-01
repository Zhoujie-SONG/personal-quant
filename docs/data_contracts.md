# Data contracts — M0/M1A/M1A.1/M1A.2/M1A.2a/M1B/M1B.1

## Canonical authority and dependency direction

Provider responses are observations, not the system source of truth. The only supported flow is:

```text
Provider -> Raw DTO -> Normalizer -> Canonical Model -> Repository
```

Future strategy and backtest modules may read only the canonical repository. They must not call Longbridge, AkShare, or provider raw files directly. Canonical/domain validation uses provider-neutral `DataNormalizationError` and `DataValidationError`; lower layers must not import `etf_quant.providers.longbridge.*`.

## Four distinct PIT concepts

These terms are not interchangeable:

- **economic availability**: `available_time`, the earliest instant at which the configured research policy permits use of a value;
- **system observation**: `ingest_time`, when this system actually retrieved that exact provider revision;
- **provider historical latest** (`HISTORICAL_LATEST`): history fetched now, containing the provider's current best version of old bars without proof that old vintages are recoverable;
- **true historical vintage** (`TRUE_HISTORICAL_VINTAGE`): a value tied to and reproducible from the provider revision actually published at the historical observation time.

Economic PIT does not create provider vintage history. Longbridge historical OHLCV is explicitly classified as `HISTORICAL_LATEST` until historical revision-vintage support is proved. Results may therefore be economically aligned by bar availability while still containing later provider corrections.

## Timestamps and availability policy

Every canonical `MarketBar` stores:

```text
data_time      = session_close
available_time = session_close + configured EOD delay
ingest_time    = actual retrieval time
```

The default 15-minute delay comes from `daily_bar_availability.eod_delay_minutes` in YAML. This is a conservative system policy, not an exchange fact or provider finalization guarantee. `availability_policy_id` records the rule separately, for example `daily_bar_eod_v1_15m`.

Hard rule: a signal using T close may execute no earlier than T+1, irrespective of the delay.

## Immutable revision schema v3

Monthly Parquet partitions are append-preserving revision logs. Later corrections never overwrite earlier observations.

| Field | Meaning |
| --- | --- |
| `revision_schema_version` | Physical schema version (`3`) |
| `observation_id` | Identity over symbol/date/source/ingest/value hash/policy/availability |
| `value_hash` | SHA-256 of provider/canonical bar values and data identity only |
| `availability_policy_id` | Independently versioned research availability rule |
| `historical_data_semantics` | `historical_latest` or `true_historical_vintage` |
| `symbol`, `trade_date`, `source` | Economic bar identity and provenance |
| `ingest_time` | System observation time (`observed_at`) |
| OHLCV, turnover, `data_time` | Value for this exact revision |
| `available_time` | Availability produced by the named policy |

`value_hash` deliberately excludes `available_time` and `availability_policy_id`. A policy change creates a distinct observation/policy revision but not a false provider price revision.

`historical_data_semantics` also remains outside `value_hash` and `observation_id`: it describes provenance, not price value. Because of that deliberate identity rule, appending the same `observation_id` with a different historical-data semantic is an error. The repository raises `DataValidationError` instead of silently replacing the stored observation.

## Explicit PIT query modes and source

`MarketRepository.get_bars` has no hidden PIT default. Callers must provide both `source` and `mode`:

```python
get_bars(..., source=CanonicalMarketSource.LONGBRIDGE,
         as_of=as_of, mode=PITQueryMode.ECONOMIC)
```

- `ECONOMIC`: requires `available_time <= as_of`; intended for historical research, walk-forward, and OOS work. `ingest_time` is not filtered, so historical data downloaded later remains usable. With `HISTORICAL_LATEST`, the newest stored provider revision is selected and is not claimed to be a true historical vintage.
- `SYSTEM_REPLAY`: requires both `available_time <= as_of` and `ingest_time <= as_of`; intended for live replay, incident reconstruction, and provider revision audit.

For each explicitly requested `(symbol, trade_date, source)`, the latest eligible observation is selected. The formal canonical market source in M1A.2 is `longbridge`. A future reconciliation source cannot leak multiple same-date rows into formal queries because source is mandatory and the formal enum exposes only Longbridge.

## Safe schema migration

Queries and appends inspect every matching partition. Any v1/v2 or mixed v1/v2/v3 set raises `SchemaMigrationRequiredError`; the repository never silently unions uncertain schemas.

Run the explicit one-time migration before querying legacy runtime data:

```text
python scripts/migrate_market_bar_revisions.py --canonical-root data/canonical
```

The utility atomically rewrites each legacy partition to v3, recomputes `value_hash`, preserves observations, labels Longbridge history `HISTORICAL_LATEST`, and assigns an honest `legacy_inferred_daily_bar_<seconds>s` policy id derived from stored timestamps. Back up runtime data before operational migration.

## Adjustment discipline

`AdjustType.FORWARD` remains a provider capability, but formal canonical ingestion accepts only `AdjustType.NONE`. Until PIT corporate-action reconstruction exists, history forward-adjusted with today's knowledge is forbidden as formal OOS input.

## Raw cache completeness and finalization

The raw manifest distinguishes:

- `requested_coverage`: request audit history;
- `provisional_dates`: expected trading dates that returned a bar before the configured cutoff;
- `finalized_dates`: expected trading dates observed at or after `session_close + EOD delay`.

Only `finalized_dates` satisfy cache completeness. A non-empty current-day response before the cutoff remains provisional and is fetched again. Weekend/holiday dates are not expected. Missing expected trading dates remain retryable. Legacy v2 `verified_dates` are conservatively reclassified as provisional because their cutoff proof was not stored.

Raw `load()` retains both provisional and finalized observations for audit. The formal Longbridge daily-bar provider uses the finalized-only cache interface: an observation is returned to canonical ingestion only when that exact observation's `retrieved_at` is at or after its trading date's cutoff. The ingestion service also fails fast if any normalized daily bar has `ingest_time < available_time`. Promoting a date to finalized does not retroactively promote an earlier preliminary observation. Old historical bars fetched long after their original cutoff remain eligible and ingest normally.

## Future research snapshot contract

`PITQueryMode.ECONOMIC` answers the economic-time question, but it does not freeze which later-ingested provider revisions a research run used. Before the M3 Backtester is implemented, every historical research run must freeze and persist both:

- `research_data_cutoff`: the latest allowed canonical `ingest_time` for that run;
- `dataset_snapshot_id`: an immutable identifier for the exact canonical dataset/revision set.

`as_of` and `research_data_cutoff` are different axes: `as_of` is the economic decision time, while the dataset cutoff controls the ingestion/revision vintage available to the research run. M3 must enforce both and must not rely on a mutable latest dataset.

## Historical metadata discipline

A historical PIT fact that is unavailable remains unknown. Today's AUM, shares, NAV, IOPV, tracking index, list status, or other snapshot must not be filled backward. Logical Asset to Execution Vehicle mapping remains out of scope.

## Metadata availability classification

Metadata uses provider-neutral `DataAvailabilityClass`:

- `TRUE_HISTORICAL_VINTAGE`: evidence supports the exact version published at historical time T;
- `HISTORICAL_LATEST`: a historical series fetched now, without historical revision-vintage proof;
- `SNAPSHOT_ONLY`: a current observation that is unavailable before its actual `snapshot_at`;
- `FORWARD_COLLECTED_PIT`: immutable snapshots accumulated by this system from its collection start onward.

A date-looking field does not prove historical vintage. Unproved claims are conservatively downgraded. **AVAILABLE TODAY and AVAILABLE AT HISTORICAL TIME T are different questions.**

## ETF metadata observations

ETF metadata is separate from `Instrument`. An immutable observation supports nullable `tracking_index`, list/delist dates, trading/settlement cycles, price limit, asset class/timezone, liquidation rule, management fee, fund name/company/type, NAV, IOPV, shares, and AUM. Unknown values stay `None` or `UNKNOWN`; no mapper guesses them.

Every observation stores `effective_from`, `effective_to`, `available_time`, `ingest_time`, `source`, `availability_class`, optional `snapshot_at`, and `provider_payload_hash`. Metadata `source` is dataset-qualified where one provider exposes complementary endpoints (for example `akshare:fund_etf_spot_em` versus `akshare:fund_etf_scale_szse`), so provenance and explicit resolution remain possible. SQLite uses an immutable observation identity; no `symbol PRIMARY KEY + UPDATE` path exists. Known delisted ETFs remain queryable. Complete historical cemetery coverage is explicitly `UNVERIFIED`.

`MetadataRepository.get_metadata_observations(symbol, as_of, mode, research_data_cutoff=None, source=None)` returns every eligible immutable observation and preserves its source/provenance. `get_metadata` is a single-source convenience query: callers may name `source`; if they omit it and more than one eligible source exists, the repository fails fast instead of silently selecting an entire winning row. M1B.1 deliberately does not merge fields across sources.

Both queries require timezone-aware `as_of` and, when supplied, timezone-aware `research_data_cutoff`. Economic mode respects effective period, availability, and snapshot time but may use a later-ingested `HISTORICAL_LATEST` observation. System Replay also requires `ingest_time <= as_of`. A research cutoff filters ingestion revisions independently of economic time.

For `SNAPSHOT_ONLY` and `FORWARD_COLLECTED_PIT`, `snapshot_at <= as_of` is mandatory. A 2026 snapshot therefore cannot answer a 2020 query. The daily snapshot service relabels observations actually persisted over time as `FORWARD_COLLECTED_PIT`; rerunning the same provider snapshot is idempotent.

## Index and calendar observations

`IndexMetadata` stores nullable base/launch dates, methodology version and total-return flag plus source, availability classification, effective period, availability, ingestion, snapshot time, and source note. Snapshot-class index observations obey the same no-backfill rule. If launch date is known, dates before launch are `BACKFILLED`; dates on/after launch are `LIVE`. The curated index registry is empty until cited values with `source_note` and timezone-aware `known_at` are supplied.

The canonical trading-calendar repository preserves each observed session's open/close and half-day flag. Longbridge historical calendar observations are `HISTORICAL_LATEST`, not proven historical publication vintages. Under `historical_calendar_session_close_v1`, `available_time` is the observed trading date's timezone-aware `session_close`, while `ingest_time` remains the actual retrieval time. This conservative research policy makes a historical session fact economically usable only after that session closed; it is not a claim about the exchange's original publication time. Economic queries filter on policy availability, while System Replay additionally filters on ingestion. The repository does not infer that every session closes at 15:00.

## M2A field-level MetadataResolver contract

M2A implements `MetadataResolver` for one caller-supplied ETF symbol. It does not know or infer any Logical Asset membership and does not read the frozen Universe v1. Historical Vehicle Registry and Vehicle Selector remain **NOT IMPLEMENTED**.

The resolver delegates all PIT eligibility to `MetadataRepository.get_metadata_observations(...)`; that repository result is its only observation input. It does not duplicate or weaken effective-period, availability, snapshot, System Replay, or `research_data_cutoff` filtering. Resolution then follows this fixed pipeline independently for each metadata field:

1. eligible immutable observations from the repository;
2. non-null per-source field candidates;
3. deterministic same-source selection ordered by `effective_from`, `snapshot_at`, `available_time`, `ingest_time`, and `provider_payload_hash`;
4. field-specific freshness evaluation;
5. configured source precedence or require-agreement conflict handling;
6. one `ResolvedField` with field-level provenance and all competing candidate summaries.

Whole-row last-write-wins is impossible in this contract. A newer spot row with null `list_date` cannot erase a valid scale-source `list_date`; an IOPV and a list date may resolve from different observations. Null values are skipped before same-source revision selection. `AssetClass.UNKNOWN` and empty strings are unknown, not inferred defaults. If every eligible source is null or absent, status is `UNKNOWN` and value remains `None`.

`ResolvedFieldStatus` has four explicit values:

- `RESOLVED`: a current non-null value satisfied the field policy;
- `UNKNOWN`: no eligible non-null field observation exists;
- `STALE`: non-null observations exist but all exceed the configured freshness limit; the highest-precedence stale value may be retained with `EXPIRED` provenance for audit, but is not treated as resolved;
- `CONFLICT`: fresh require-agreement candidates disagree, so no winner or value is exposed.

For `PRECEDENCE_WITH_AUDIT`, the first fresh non-null configured source wins and any disagreement remains in `candidate_observations`. A lower source is used only when higher sources have no fresh non-null value, and `resolution_reason` records the fallback. For `REQUIRE_AGREEMENT`, disagreement produces `CONFLICT` without guessing a winner.

Every selected field preserves `source`, `availability_class`, effective period, `available_time`, `ingest_time`, `snapshot_at`, and `provider_payload_hash`. Fallbacks, stale results, and conflicts also preserve per-source candidate summaries. `ResolvedETFMetadata.to_dict()` provides JSON-safe serialization without discarding Decimal/date/enum values or provenance.

The machine-readable policy is versioned as `etf_metadata_field_resolution_v1` in `configs/metadata_resolution.yaml`. The freshness clock is `snapshot_at`, falling back to `available_time` only when no snapshot exists. Initial engineering limits are:

- IOPV: 3,600 seconds;
- NAV: 259,200 seconds (3 days);
- shares and AUM: 2,678,400 seconds (31 days);
- trading/settlement cycle, price limit, liquidation rule, management fee, fund name/company/type: 31,536,000 seconds (365 days);
- tracking/list/delist identity, asset class, and market timezone: non-expiring in policy v1.

These are versioned data-validity engineering policies, not alpha, ranking, or portfolio parameters. All resolver datetimes must be timezone-aware. Current-snapshot values still cannot answer an earlier `as_of` because repository eligibility is evaluated before resolution.
