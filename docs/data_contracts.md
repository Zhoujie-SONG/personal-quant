# Data contracts — M0/M1A/M1A.1/M1A.2

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

## Historical metadata discipline

A historical PIT fact that is unavailable remains unknown. Today's AUM, shares, NAV, IOPV, tracking index, list status, or other snapshot must not be filled backward. Logical Asset to Execution Vehicle mapping remains out of scope.
