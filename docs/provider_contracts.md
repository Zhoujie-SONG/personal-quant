# Provider contracts — M0/M1A/M1A.1/M1A.2/M1B

## Boundary

`MarketDataProvider` is the formal primary market-data boundary. It returns project-owned Raw DTOs for:

- daily bars;
- quotes;
- security static information;
- trading days.

No Longbridge SDK class may escape the Longbridge adapter. Callers depend on the protocol, so a future provider can be added without changing ingestion or repositories.

M1A.1/M1A.2 do not change the `MarketDataProvider` protocol. Longbridge-specific exceptions and SDK types remain inside `providers/longbridge/`; canonical normalization raises provider-neutral domain exceptions. An automated dependency-boundary test prevents lower layers from importing the Longbridge adapter.

## Provider roles

Longbridge is the **primary market-data provider** for ETF/index OHLCV, quote, static security information, and trading calendar.

M1B authorizes AkShare only as a supplemental adapter. Its market bars are reconciliation input and cannot become an implicit second formal market source. The formal canonical market source remains explicitly `longbridge`. Tushare is not used.

A provider is not the source of truth. The canonical store is the unified system interface. Future strategies may only read the canonical repository.

## Longbridge adapter

Supported M1A operations:

| Project method | Longbridge SDK call |
| --- | --- |
| `get_static_info` | `QuoteContext.static_info` |
| `get_daily_bars` | `QuoteContext.history_candlesticks_by_date` |
| `get_trading_days` | `QuoteContext.trading_days` |
| `get_quote` | `QuoteContext.quote` |

A-share symbols use `ticker.SH` or `ticker.SZ`, for example `510300.SH` and `159915.SZ`. The adapter validates and normalizes symbols before an SDK call.

All four calls are read-only and may be retried only for transient server, rate-limit, timeout, or connection errors. Invalid requests, permission failures, authentication failures, and invalid data are not retried. Provider exceptions are translated and never swallowed.

The SDK documents a sub-month trading-day query limit; the adapter chunks longer date intervals. Historical bar requests always consult/write the raw cache to conserve Longbridge's monthly unique-symbol quota.

Before treating cached daily bars as complete, the adapter obtains expected CN trading dates through the trading-calendar endpoint and computes the configured finalization cutoff for each date. `requested_coverage` is audit history only. A returned date before `session_close + EOD delay` is `provisional`; only a response retrieved at or after the cutoff enters `finalized_dates`. Missing and provisional expected dates remain retryable on the next call. The adapter and canonical normalizer receive the same explicit `DailyBarAvailabilityPolicy` instance.

Longbridge historical OHLCV is labelled `HISTORICAL_LATEST`: it is the provider's latest history as retrieved, not evidence of the exact revision visible at the historical date. `TRUE_HISTORICAL_VINTAGE` may be used only if a provider contract can reproduce timestamped historical revisions. Economic availability, system observation, provider historical latest, and true historical vintage are four separate concepts.

`AdjustType.FORWARD` remains available at the provider boundary. The formal canonical ingestion service accepts only `AdjustType.NONE`; provider capability must not be confused with formal PIT eligibility.

## Credentials and logging

The only accepted credential inputs are:

- `LONGBRIDGE_APP_KEY`
- `LONGBRIDGE_APP_SECRET`
- `LONGBRIDGE_ACCESS_TOKEN`

They are read from the environment by the SDK. YAML credentials are rejected. Client representations omit SDK config/context, and logging redacts any environment credential value.

## Capability probe

`scripts/check_longbridge_capabilities.py` checks ETF static info, ETF daily bars, index daily bars, CN trading days, and realtime quote. It does not write canonical storage. Successful historical calls are still raw-cached because the quota discipline applies to every historical fetch.

The matrix uses `PASS`, `FAIL`, `NO_PERMISSION`, and `NO_CREDENTIAL`; provider errors are printed as concise explanations without a traceback.

## M1B AkShare supplemental adapter

Longbridge remains the only formal `CanonicalMarketSource`. AkShare is supplemental and its market bars are reconciliation-only. The adapter exposes project DTOs; pandas DataFrames remain inside `providers/akshare/`.

Only three live-verified endpoints are connected:

| AkShare endpoint | M1B use | Availability |
| --- | --- | --- |
| `fund_etf_spot_em` | ETF discovery plus current name, IOPV and latest shares | `SNAPSHOT_ONLY` |
| `fund_etf_scale_szse` | Current SZSE list date, shares, NAV and manager snapshot | `SNAPSHOT_ONLY` |
| `fund_etf_hist_em(adjust="")` | Unadjusted OHLCV/turnover reconciliation | `HISTORICAL_LATEST`, never formal market input |

The mapper checks named required columns, tolerates only declared optional columns, and raises `AkShareSchemaError` on schema break. It never reads columns by position. Empty, `--`, `---`, `None`, NaN and NaT are missing—not zero. Required invalid numerics raise `AkShareDataError`. AkShare daily volume is explicitly converted from lots to shares (`×100`); turnover remains provider-reported yuan.

Live validation on 2026-09-01 used AkShare 1.18.60 and passed all three adapter endpoints. Network tests carry the `integration` marker and default pytest remains offline.

## M1B Longbridge gate status

The 2026-09-01 real gate had credentials but the access token was expired (`401003`). ETF static, ETF bars, index bars, trading calendar, and realtime quote all recorded `FAIL`. This is an authentication state, not a provider implementation bug or `NO_PERMISSION`. The probe now reports `NO_CREDENTIAL` explicitly when environment variables are absent.
