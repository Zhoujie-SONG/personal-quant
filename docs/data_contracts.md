# Data contracts — M0/M1A/M1A.1

## Canonical authority and dependency direction

Provider responses are observations, not the system source of truth. The only supported flow is:

```text
Provider -> Raw DTO -> Normalizer -> Canonical Model -> Repository
```

Future strategy and backtest modules may read only the canonical repository. They must not call Longbridge, AkShare, or read provider raw files directly.

Canonical/domain validation uses provider-neutral `DataNormalizationError` and `DataValidationError`. Code below the provider-neutral boundary (`data`, `domain`, `services`, repositories) must not import `etf_quant.providers.longbridge.*`; an AST-based unit test enforces this rule.

## Three timestamps and DailyBarAvailabilityPolicy

Every canonical `MarketBar` contains:

- `data_time`: the market event time represented by the record. For a normal A-share daily bar this is 15:00 Asia/Shanghai on `trade_date`.
- `available_time`: the earliest time allowed by the configured `DailyBarAvailabilityPolicy`.
- `ingest_time`: the actual time this system retrieved/observed this provider revision.

For daily bars:

```text
data_time      = session_close
available_time = session_close + configured EOD delay
ingest_time    = actual retrieval time
```

The default delay is 15 minutes and is read from `daily_bar_availability.eod_delay_minutes` in YAML. This is a conservative **system policy**, not a statement of exchange fact or a guarantee that every provider finalizes at that time. A policy change must be reviewed like any other PIT assumption.

Hard rule: **it is forbidden to generate a signal from T-day close and execute that signal at T-day close.** A signal using the completed T daily bar can trade no earlier than T+1, regardless of the configured intraday delay.

## Canonical MarketBar validation

Prices and turnover are `Decimal`; volume is an integer. All three timestamps are timezone-aware. OHLC must satisfy:

```text
low <= open <= high
low <= close <= high
```

Prices are positive; volume and turnover are non-negative. `source`, `symbol`, and `trade_date` are mandatory. Domain invariant failures raise `DataValidationError`; raw conversion failures raise `DataNormalizationError`.

## Immutable revision schema

Monthly Parquet partitions are revision logs. A later provider correction never overwrites or deletes an earlier observation.

Revision schema version 2 stores:

| Field | Meaning |
| --- | --- |
| `revision_schema_version` | Physical revision schema version (`2`) |
| `observation_id` | SHA-256 of symbol/date/source/ingest_time/payload_hash |
| `payload_hash` | SHA-256 of canonical OHLCV/value payload and availability timestamps |
| `symbol`, `trade_date`, `source` | Economic bar identity |
| `ingest_time` | `observed_at`: when this revision became known to this system |
| OHLCV, turnover | Values for this exact revision |
| `data_time`, `available_time` | Market and policy availability timestamps |

Exact duplicate observations are idempotent by `observation_id`. Different values or a different observation time remain separate and can be recovered with `get_bar_revisions`.

## PIT query semantics

For a requested `as_of`, a revision is eligible only when both conditions hold:

```text
available_time <= as_of
ingest_time    <= as_of
```

For each `(symbol, trade_date, source)`, the repository then selects the eligible row with the latest `ingest_time` (with `payload_hash` as a deterministic tie-breaker). Consequently, a query between an original observation T1 and a provider correction T2 returns T1; a query after T2 returns the correction.

## Adjustment discipline

`AdjustType.FORWARD` remains a provider capability, but the formal PIT canonical ingestion service rejects it. The formal PIT baseline accepts only `AdjustType.NONE`.

Until PIT corporate-action reconstruction exists, history forward-adjusted using today's adjustment knowledge must not be used as formal OOS/backtest input. It may only be handled outside the formal canonical path for capability checks or clearly labelled exploration.

## Raw cache completeness

Raw DTOs preserve provider strings for price/money fields and include retrieval time, provider, SDK version, and provider payload. Raw records retain distinct retrieval revisions rather than overwriting solely by market timestamp.

The coverage manifest separates:

- `requested_coverage`: ranges successfully requested, retained only for audit;
- `verified_dates`: expected trading dates for which a bar was actually returned.

Completeness is evaluated against trading-calendar dates. Weekend/holiday dates are not expected and require no bar. If an expected trading date is absent—including a current trading day whose finalized bar has not yet arrived—it remains missing and is requested again. A successful API response alone never proves a date range complete.

## Historical metadata discipline

A historical PIT fact that is unavailable must remain unknown. In particular, today's AUM, shares, NAV, IOPV, tracking index, list status, or other snapshot **must not be filled backward** into an earlier date.

Instrument metadata keeps nullable list/delist dates so later milestones can retain liquidated/delisted ETFs. Logical Asset to Execution Vehicle mapping is a separate PIT concern and is not implemented in M1A.1.

