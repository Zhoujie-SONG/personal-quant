# M2B.0.1 Vehicle Candidate Breadth and Targeted Cemetery Audit

## Decision summary

The candidate evidence pack now covers every obvious name or tracking-identity
match retained by the bounded 2026-09-04 current discovery snapshot. It contains
108 records: 107 current observations and one officially terminated historical
observation. All remain `UNREVIEWED`; the registry remains
`CANDIDATE_NOT_APPROVED / PARTIAL_CURATED`.

This milestone does not choose an ETF. It records semantic eligibility evidence
before any future PIT selector considers operational data. No AUM, turnover,
bid/ask cost, premium, performance, or ranking field was collected or used to
remove a candidate.

| Measure | Result |
|---|---:|
| Total candidates | 108 |
| Newly added versus M2B.0 | 91 |
| Current candidates | 107 |
| Exact frozen-benchmark candidates | 69 |
| Exact Logical Asset exposure candidates | 27 |
| Economic proxy candidates | 5 |
| Rejected semantic mismatches | 7 |
| Candidate-level unresolved records | 0 |
| Known historical / delisted candidates | 1 / 1 |
| Verified canonical identities / provider-code aliases | 15 / 20 |

## Semantic contract

`EXACT_BENCHMARK` requires both the canonical index identity and return/index
variant to match the frozen research benchmark. `EXACT_LOGICAL_EXPOSURE` preserves
the same core economic identity but records a material series distinction such as
price versus net-total-return, currency conversion, fair-value adjustment, or a
different official gold pricing contract. A provider/exchange code alias alone
does not make a proxy: for example, official evidence establishes that CSI 300
codes 000300 and 399300 are one canonical identity.

`ECONOMIC_PROXY_CANDIDATE` means the methodology itself differs. It is not an
approval. `REJECTED_SEMANTIC_MISMATCH` makes an obvious name-search false positive
explicit. `UNRESOLVED` remains available for a seed lacking reliable official
tracking evidence; none of the retained records in this pass remains at that
record-level state.

Every exact/logical record has official `VEHICLE_IDENTITY`, `LISTING_PERIOD`, and
`TRACKING_INDEX` evidence. Every code alias is separately backed by official
`INDEX_IDENTITY` evidence in `configs/index_identity_aliases_candidate.yaml`.

## Candidate breadth by Logical Asset

The symbol lists below are exhaustive for this bounded discovery snapshot and
scope. Dates in parentheses are listing dates. `C` means a current-survivor
observation; `H` means known historical with official termination. Evidence is
`complete` when the required official identity/listing/tracking scopes are present.

| Logical Asset | Tracking identity / variant | Semantic class | Symbols (listing date; state) | Evidence |
|---|---|---|---|---|
| CN_LARGE | CSI 300 / PRICE_INDEX | EXACT_BENCHMARK | 510300.SH (2012-05-28; C); 510310.SH (2013-03-25; C); 510320.SH (2025-04-25; C); 510330.SH (2013-01-16; C); 510350.SH (2019-08-16; C); 510360.SH (2015-09-09; C); 510370.SH (2020-10-27; C); 510380.SH (2018-02-07; C); 510390.SH (2018-01-26; C); 515130.SH (2020-05-11; C); 515310.SH (2019-12-25; C); 515330.SH (2019-12-26; C); 515350.SH (2020-02-07; C); 515360.SH (2019-11-01; C); 515380.SH (2020-03-23; C); 515390.SH (2020-01-10; C); 515660.SH (2019-12-24; C); 561930.SH (2024-09-20; C); 563520.SH (2024-11-18; C); 159300.SZ (2024-06-05; C); 159330.SZ (2024-08-19; C); 159393.SZ (2025-03-10; C); 159673.SZ (2023-07-17; C); 159919.SZ (2012-05-28; C); 159925.SZ (2013-04-11; C) | complete; 000300/399300 alias verified |
| CN_SMALL | CSI 1000 / PRICE_INDEX | EXACT_BENCHMARK | 512100.SH (2016-11-04; C); 516300.SH (2021-03-24; C); 560010.SH (2022-08-04; C); 560110.SH (2022-08-08; C); 159629.SZ (2022-08-03; C); 159633.SZ (2022-08-04; C); 159845.SZ (2021-03-31; C) | complete |
| CN_GROWTH | ChiNext 399006 / PRICE_INDEX | EXACT_BENCHMARK | 159205.SZ (2025-06-12; C); 159247.SZ (2026-02-02; C); 159810.SZ (2020-07-10; C); 159821.SZ (2020-10-29; C); 159908.SZ (2011-07-13; C); 159915.SZ (2011-12-09; C); 159948.SZ (2016-05-31; C); 159952.SZ (2017-05-19; C); 159956.SZ (2018-03-07; C); 159957.SZ (2018-01-04; C); 159958.SZ (2018-01-19; C); 159964.SZ (2019-04-19; C); 159971.SZ (2019-07-02; C); 159977.SZ (2019-09-27; C) | complete |
| CN_DIVIDEND | CSI Dividend 000922 / PRICE_INDEX | EXACT_BENCHMARK | 515080.SH (2019-12-27; C); 515180.SH (2019-12-20; C); 515890.SH (2020-04-20; C); 560020.SH (2023-10-16; C); 159581.SZ (2024-03-15; C); 159589.SZ (2024-03-26; C) | complete |
| CN_DIVIDEND | SSE Dividend 000015 / PRICE_INDEX | ECONOMIC_PROXY_CANDIDATE | 510880.SH (2007-01-18; C) | complete; not approved |
| CN_DIVIDEND | CSI Dividend Low Volatility H30269 / PRICE_INDEX | ECONOMIC_PROXY_CANDIDATE | 560890.SH (2024-09-20; H; delisted 2026-04-01) | complete including termination |
| SEMI | CSI All Share Semiconductor H30184 / PRICE_INDEX | EXACT_BENCHMARK | 512480.SH (2019-06-12; C) | complete |
| HEALTHCARE | CSI All Share Health Care 000991 / PRICE_INDEX | EXACT_BENCHMARK | 159938.SZ (2015-01-08; C) | complete |
| HEALTHCARE | CSI Medical 399989 / PRICE_INDEX | ECONOMIC_PROXY_CANDIDATE | 512170.SH (2019-06-17; C) | complete; not approved |
| CONSUMER | CSI Consumer Staples 000932 / PRICE_INDEX | EXACT_BENCHMARK | 512600.SH (2014-07-25; C); 560680.SH (2022-10-31; C); 159672.SZ (2023-04-03; C); 159689.SZ (2023-03-13; C); 159928.SZ (2013-09-16; C) | complete |
| COAL | CSI Coal 399998 / PRICE_INDEX | EXACT_BENCHMARK | 515220.SH (2020-03-02; C) | complete |
| SP500 | S&P 500 / currency-adjusted price or CNY NTR | EXACT_LOGICAL_EXPOSURE | 513500.SH (2014-01-15; C; NET_TOTAL_RETURN_CNY); 513650.SH (2023-04-04; C); 159612.SZ (2022-05-20; C); 159655.SZ (2022-10-25; C) | complete; differs from frozen PRICE_INDEX series |
| NASDAQ100 | Nasdaq-100 / currency or fair-value adjusted | EXACT_LOGICAL_EXPOSURE | 513100.SH (2013-05-15; C); 513110.SH (2023-03-20; C); 513300.SH (2020-11-05; C); 513390.SH (2023-05-08; C); 513870.SH (2023-11-02; C); 159501.SZ (2023-06-14; C); 159513.SZ (2023-07-28; C); 159659.SZ (2023-04-25; C); 159660.SZ (2023-04-17; C); 159696.SZ (2023-08-25; C); 159941.SZ (2015-07-13; C) | complete; differs from frozen PRICE_INDEX series |
| HK_BROAD | Hang Seng Index / currency or fair-value adjusted | EXACT_LOGICAL_EXPOSURE | 513210.SH (2024-04-22; C); 513600.SH (2015-01-26; C); 513660.SH (2015-01-26; C); 159271.SZ (2025-08-11; C); 159920.SZ (2012-10-22; C) | complete; differs from frozen HSI price series |
| HK_BROAD | Hang Seng HK Connect Index | ECONOMIC_PROXY_CANDIDATE | 520940.SH (2025-06-09; C) | complete; different access/constituent methodology |
| GOLD | SGE Au99.99/Au9999 / SPOT_PRICE | EXACT_BENCHMARK | 518880.SH (2013-07-29; C); 518800.SH (2013-07-29; C); 518850.SH (2020-06-05; C); 518660.SH (2020-05-29; C); 159812.SZ (2020-05-29; C); 159934.SZ (2013-12-16; C); 159937.SZ (2015-01-08; C) | complete; Au99.99/Au9999 alias verified |
| GOLD | SGE Shanghai Gold SHAU / BENCHMARK_PRICE | EXACT_LOGICAL_EXPOSURE | 518600.SH (2020-08-05; C); 518680.SH (2020-07-28; C); 518860.SH (2020-09-07; C); 518890.SH (2020-09-28; C); 159830.SZ (2021-07-19; C); 159831.SZ (2022-04-07; C); 159834.SZ (2022-03-16; C) | complete; official gold pricing contract differs from Au99.99 |
| GOLD | CSI SH-HK-SZ Gold Industry Equities 931238 | REJECTED_SEMANTIC_MISMATCH | 517400.SH (2024-05-08; C); 517520.SH (2023-11-01; C); 159315.SZ (2024-06-14; C); 159321.SZ (2024-05-27; C); 159322.SZ (2024-06-14; C); 159562.SZ (2024-01-22; C) | complete; equity exposure is not spot gold |
| GOLD | Money-market NAV | REJECTED_SEMANTIC_MISMATCH | 511670.SH (2017-08-28; C) | complete; name-search false positive |
| BOND_LONG | SSE 10Y Treasury H11077 / FULL_PRICE_INDEX | EXACT_BENCHMARK | 511260.SH (2017-08-24; C) | complete; no yield-series substitution |
| BOND_LONG | CSI 5–10Y Active Treasury 931018 | ECONOMIC_PROXY_CANDIDATE | 511020.SH (2019-02-22; C) | complete; different duration/methodology |
| BOND_MED | SSE 5Y Treasury H00140 / FULL_PRICE_INDEX | EXACT_BENCHMARK | 511010.SH (2013-03-25; C) | complete; no yield-series substitution |

CASH remains `CASH_BALANCE`; HSTECH remains deferred and OIL inactive. None has
an ETF record in this pack.

## High-breadth assets

CN_LARGE has 25 direct CSI 300 candidates, including six SZSE rows whose official
399300 quote-code alias resolves to the same CSI 300 identity as 000300. SP500 has
four and NASDAQ100 has eleven core-index candidates; all are deliberately
`EXACT_LOGICAL_EXPOSURE`, because their disclosed currency, fair-value, or
net-total-return treatment must not be represented as the frozen price-index
series. HK_BROAD has five core HSI candidates plus one separate HK-Connect proxy.
GOLD has fourteen valid spot-gold exposures split between exact Au99.99 and the
distinct Shanghai Gold benchmark, while all six gold-equity ETFs and one
money-market name false positive are explicitly rejected.

## Canonical identity audit

The candidate-only alias registry verifies 15 identities and 20 provider/code
representations. The material cross-code relationships are:

- CSI 300: CSINDEX/SSE `000300` and SZSE `399300`.
- S&P 500: frozen Longbridge `.SPX.US` and official-family `SPX`.
- Nasdaq-100: frozen Longbridge `.NDX.US` and official `NDX`.
- Hang Seng Index: frozen Longbridge `HSI.HK` and official `HSI`.
- SGE Au99.99: `Au99.99` and the provider-format label `Au9999`.

Shanghai Gold `SHAUCNY` is intentionally a separate canonical identity. Similar
names therefore cannot merge Au99.99 and SHAU series.

## Targeted historical cemetery audit

The audit searched official SSE/SZSE fund listings and historical statistics,
listing/termination notices, fund liquidation disclosures, manager product
documents, and index-provider records for the 14 active non-cash Logical Assets.
It found one additional terminated candidate:

- `560890.SH`, Xinhua CSI Dividend Low Volatility ETF, listed 2024-09-20 and
  terminated by SSE effective 2026-04-01. Its mapping period is
  `[2024-09-20, 2026-04-01)`. H30269 is a different dividend-low-volatility
  methodology, so the record is retained as an unreviewed economic proxy.

The status is `ADDITIONAL_TERMINATED_FOUND`, not `COMPLETE`. The search was
targeted, and no authoritative all-history ETF security master was established.

## Evidence and limitations

Stage one used the AkShare current ETF snapshot plus official exchange ETF tables
as a broad name/index seed. Stage two used official SSE/SZSE product/listing
records, official fund disclosures, and CSI/SGE/S&P/Nasdaq/Hang Seng identity
references. The current snapshot never establishes historical existence by
itself.

No candidate-level tracking evidence remains unresolved. Global research gaps do:
historical cemetery completeness, unobserved predecessor vehicles, exhaustive
tracking-index change histories, and historically versioned return/currency
benchmark wording. Those gaps prevent approval and remain future manual review
work. M2B.1, Vehicle Selector, strategy, backtest, portfolio, and execution have
not started.

## Freeze-gate result

`CANDIDATE_NOT_APPROVED / PARTIAL_CURATED`. The evidence set is broad enough to
avoid a one-representative-ETF bias, but it is not an approved Historical Vehicle
Registry and must not be consumed as production mappings.
