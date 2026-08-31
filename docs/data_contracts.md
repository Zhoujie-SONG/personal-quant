# Data contracts — M0/M1A

## Canonical authority

Provider responses are observations, not the system source of truth. The only supported flow is:

```text
Provider -> Raw DTO -> Normalizer -> Canonical Model -> Repository
```

Future strategy and backtest modules may read only the canonical repository. They must not call Longbridge, AkShare, or read provider raw files directly.

## Three timestamps and PIT

Every canonical `MarketBar` contains:

- `data_time`: the market event time represented by the record. For an A-share daily bar this is 15:00 Asia/Shanghai on `trade_date`.
- `available_time`: the earliest economically valid time at which the completed record could be used. It is not the download time.
- `ingest_time`: when this system retrieved the observation.

PIT queries require `available_time <= as_of`. `ingest_time` must never substitute for economic availability.

Hard rule: **it is forbidden to generate a signal from T-day close and execute that signal at T-day close.** A signal using the completed T daily bar can trade no earlier than T+1. The `MarketBar` constructor and unit tests enforce `available_time >= data_time` (the A-share close time).

## Canonical MarketBar

Prices and turnover are `Decimal`; volume is an integer. All three timestamps are timezone-aware. OHLC must satisfy:

```text
low <= open <= high
low <= close <= high
```

Prices are positive; volume and turnover are non-negative. `source`, `symbol`, and `trade_date` are mandatory.

Canonical Parquet files are partitioned by `year/month`, not by day. An upsert rewrites the one affected monthly part and de-duplicates on `(symbol, trade_date, source)`. DuckDB supplies the PIT query layer.

## Raw data

Raw DTOs preserve provider strings for price/money fields and include `retrieved_at`, provider, SDK version, and a provider payload. Longbridge historical bars are cached by symbol and adjustment mode with monthly record files plus a coverage manifest. A successfully queried range is marked covered even if it contains a weekend/holiday and returns no bars.

## Historical metadata discipline

A historical PIT fact that is unavailable must remain unknown. In particular, today's AUM, shares, NAV, IOPV, tracking index, list status, or other snapshot **must not be filled backward** into an earlier date.

Instrument metadata keeps nullable list/delist dates so later milestones can retain liquidated/delisted ETFs. Logical Asset to Execution Vehicle mapping is a separate PIT concern and is not implemented in M0/M1A.

