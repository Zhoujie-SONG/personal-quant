# Data source capabilities — M1B

Observed and revalidated on 2026-09-01. The machine-readable authority is `configs/data_sources.yaml`; this document is its human-readable operational matrix.

## Real online capability gate

### Longbridge

The refreshed credentials initialized successfully. The account reported CN LV1 real-time quote entitlement, and all five read-only capability probes passed.

| Capability | Result | Detail |
| --- | --- | --- |
| A-share ETF static | PASS | Provider returned and adapter mapped ETF static information |
| A-share ETF unadjusted daily bars | PASS | Provider returned finalized unadjusted daily bars |
| A-share index unadjusted daily bars | PASS | Provider returned unadjusted index daily bars |
| CN trading calendar | PASS | Provider returned CN trading dates |
| Realtime quote | PASS | Account has CN LV1 and provider returned a quote |

The earlier expired-token result is superseded by this gate run. Credentials were supplied only through process environment variables and are not stored in repository files.

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
| Longbridge historical daily bars | OHLCV, turnover | HISTORICAL_LATEST | Yes | Economic history is available, but exact provider vintage at T is unproved | Primary unadjusted market baseline |
| AkShare ETF spot | name, IOPV, latest shares | SNAPSHOT_ONLY | Yes | No, unless actually collected at T | Discovery/current QA only |
| AkShare SZSE scale snapshot | list date, latest shares, NAV, manager | SNAPSHOT_ONLY | Yes | No historical backfill | Supplemental metadata only |
| AkShare unadjusted ETF history | OHLCV, turnover | HISTORICAL_LATEST | Yes | Values exist for old dates, but revision vintage at T is unproved | Reconciliation only |
| Internal daily metadata snapshots | whichever nullable fields were actually returned | FORWARD_COLLECTED_PIT | From first run onward | Yes only from actual collection start | Future PIT metadata research |
| True provider vintage archive | none currently proved | TRUE_HISTORICAL_VINTAGE | Not established | Not established | Not available |

Tracking index, management fee, trading/settlement rules, price limits, liquidation clauses, complete AUM history, complete delist cemetery, and historical IOPV/NAV revisions remain unresolved unless separately sourced and classified.

## Cemetery and calendar status

- `ETF_CEMETERY_COMPLETENESS = UNVERIFIED`.
- Known delisted ETFs and future delist observations can be retained, but survivorship bias is not claimed solved.
- Longbridge trading-calendar access is verified. Half-day completeness remains `UNVERIFIED` because the probe did not establish a representative half-day session response.

## Reconciliation status

The reconciliation implementation and offline tolerance tests pass. The refreshed Longbridge side completed, but the real Longbridge-vs-AkShare comparison is **BLOCKED / NO COMPARISON RESULT** because the AkShare upstream Eastmoney history endpoint twice closed the connection (once through the configured proxy and once by direct connection). This is an upstream connectivity state, not a tolerance/data comparison failure. AkShare is not promoted to a formal market source as a result.
