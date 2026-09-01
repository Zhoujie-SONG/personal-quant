# Data source capabilities — M1B

Observed on 2026-09-01. The machine-readable authority is `configs/data_sources.yaml`; this document is its human-readable operational matrix.

## Real online capability gate

### Longbridge

The supplied credentials initialized, but the access token was expired (`401003`). No result is promoted to PASS.

| Capability | Result | Detail |
| --- | --- | --- |
| A-share ETF static | FAIL | token expired |
| A-share ETF unadjusted daily bars | FAIL | token expired |
| A-share index unadjusted daily bars | FAIL | token expired |
| CN trading calendar | FAIL | token expired |
| Realtime quote | FAIL | token expired |

This is neither `NO_CREDENTIAL` nor `NO_PERMISSION`. A refreshed token is required to re-run the matrix.

### AkShare

AkShare 1.18.60 was probed against real upstream sites and the M1B integration test passed.

| Endpoint | Result | Observed response | Role |
| --- | --- | --- | --- |
| `fund_etf_spot_em` | PASS | 1,595 rows; current ETF quote/IOPV/share columns | Supplemental snapshot/universe |
| `fund_etf_hist_em(adjust="")` | PASS | 21 rows for the August 2026 probe; named OHLCV/turnover columns | Reconciliation only |
| `fund_etf_scale_szse` | PASS | 1,038 rows; list/share/NAV/manager columns | Supplemental snapshot |

Official contract reference: [AKShare public-fund documentation](https://akshare.akfamily.xyz/data/fund/fund_public.html).

## Field availability matrix

| Source/dataset | Fields | Class | Available today | Available at historical T | Formal use |
| --- | --- | --- | --- | --- | --- |
| Longbridge historical daily bars | OHLCV, turnover | HISTORICAL_LATEST | Yes after token renewal | Economic history is available, but exact provider vintage at T is unproved | Primary unadjusted market baseline |
| AkShare ETF spot | name, IOPV, latest shares | SNAPSHOT_ONLY | Yes | No, unless actually collected at T | Discovery/current QA only |
| AkShare SZSE scale snapshot | list date, latest shares, NAV, manager | SNAPSHOT_ONLY | Yes | No historical backfill | Supplemental metadata only |
| AkShare unadjusted ETF history | OHLCV, turnover | HISTORICAL_LATEST | Yes | Values exist for old dates, but revision vintage at T is unproved | Reconciliation only |
| Internal daily metadata snapshots | whichever nullable fields were actually returned | FORWARD_COLLECTED_PIT | From first run onward | Yes only from actual collection start | Future PIT metadata research |
| True provider vintage archive | none currently proved | TRUE_HISTORICAL_VINTAGE | Not established | Not established | Not available |

Tracking index, management fee, trading/settlement rules, price limits, liquidation clauses, complete AUM history, complete delist cemetery, and historical IOPV/NAV revisions remain unresolved unless separately sourced and classified.

## Cemetery and calendar status

- `ETF_CEMETERY_COMPLETENESS = UNVERIFIED`.
- Known delisted ETFs and future delist observations can be retained, but survivorship bias is not claimed solved.
- Longbridge half-day capability is `UNVERIFIED` because the real calendar gate failed before a response was obtained.

## Reconciliation status

The reconciliation implementation and offline tolerance tests pass. The real Longbridge-vs-AkShare comparison is **BLOCKED / NOT RUN** because the Longbridge token expired and no cached primary bars exist. AkShare is not promoted to a formal market source as a result.
