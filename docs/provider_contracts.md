# Provider contracts — M0/M1A/M1A.1

## Boundary

`MarketDataProvider` is the only upstream market-data boundary. It returns project-owned Raw DTOs for:

- daily bars;
- quotes;
- security static information;
- trading days.

No Longbridge SDK class may escape the Longbridge adapter. Callers depend on the protocol, so a future provider can be added without changing ingestion or repositories.

The M1A.1 hardening does not change the `MarketDataProvider` protocol. Longbridge-specific exceptions remain inside `providers/longbridge/`; canonical normalization raises provider-neutral domain exceptions. An automated dependency-boundary test prevents lower layers from importing the Longbridge adapter.

## Provider roles

Longbridge is the **primary market-data provider** for ETF/index OHLCV, quote, static security information, and trading calendar.

AkShare is intentionally deferred to the next milestone. It will be a **supplemental ETF provider** for universe discovery and fund-specific observations such as IOPV, NAV, shares, and AUM. Tushare is not used.

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

Before treating cached daily bars as complete, the adapter obtains the expected CN trading dates through the existing trading-calendar endpoint. `requested_coverage` is audit history only; a date enters `verified_dates` only when it is an expected trading date and the historical-bar response actually contains that date. Missing expected dates remain retryable on the next call.

`AdjustType.FORWARD` remains available at the provider boundary. The formal canonical ingestion service accepts only `AdjustType.NONE`; provider capability must not be confused with formal PIT eligibility.

## Credentials and logging

The only accepted credential inputs are:

- `LONGBRIDGE_APP_KEY`
- `LONGBRIDGE_APP_SECRET`
- `LONGBRIDGE_ACCESS_TOKEN`

They are read from the environment by the SDK. YAML credentials are rejected. Client representations omit SDK config/context, and logging redacts any environment credential value.

## Capability probe

`scripts/check_longbridge_capabilities.py` checks ETF static info, ETF daily bars, index daily bars, CN trading days, and realtime quote. It does not write canonical storage. Successful historical calls are still raw-cached because the quota discipline applies to every historical fetch.

The matrix uses `PASS`, `FAIL`, and `NO_PERMISSION`; provider errors are printed as concise explanations without a traceback.
