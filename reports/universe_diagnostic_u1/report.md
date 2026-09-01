# Universe Diagnostic U1.1 — Effective Breadth Completion and Robustness

## Technical summary

All **15 active risky assets** now have verified economic benchmark histories and enter both EX_CASH matrices. Daily common-window effective breadth is **5.04** (33.6%); weekly robustness effective breadth is **4.83** (32.2%). Weekly is a fixed, pre-registered last-actual-observation-date intersection and is not a lag optimization.

Structural redundancy candidates:
- NASDAQ100 vs SP500
- HSTECH vs HK_BROAD

Economically distinct high-correlation pairs:
- CN_LARGE vs CN_SMALL
- CN_LARGE vs CN_DIVIDEND
- CN_LARGE vs CONSUMER
- CN_SMALL vs CN_GROWTH
- CN_SMALL vs SEMI
- CN_SMALL vs HEALTHCARE
- CN_GROWTH vs SEMI
- CN_GROWTH vs HEALTHCARE

Unresolved active benchmark mappings:
- CASH

**NO ASSET AUTOMATICALLY REMOVED.**

## All active risk assets are now measurable without ETF substitution

- CN_LARGE: 000300.SH / longbridge / INDEX / RESOLVED
- CN_SMALL: 000852.SH / longbridge / INDEX / RESOLVED
- CN_GROWTH: 399006.SZ / longbridge / INDEX / RESOLVED
- CN_DIVIDEND: 000922.SH / longbridge / INDEX / RESOLVED
- SEMI: H30184 / csindex / PRICE_INDEX / RESOLVED / primary=LONGBRIDGE_UNAVAILABLE
- HEALTHCARE: 000991.SH / longbridge / INDEX / RESOLVED
- CONSUMER: 000932.SH / longbridge / INDEX / RESOLVED
- COAL: 399998.SZ / longbridge / INDEX / RESOLVED
- NASDAQ100: .NDX.US / longbridge / INDEX / RESOLVED
- SP500: .SPX.US / longbridge / INDEX / RESOLVED
- HSTECH: HSTECH.HK / longbridge / INDEX / RESOLVED
- HK_BROAD: HSI.HK / longbridge / INDEX / RESOLVED
- GOLD: Au99.99 / akshare / SPOT / RESOLVED
- BOND_LONG: H11077 / csindex / FULL_PRICE_INDEX / RESOLVED / primary=LONGBRIDGE_UNAVAILABLE
- BOND_MED: H00140 / csindex / FULL_PRICE_INDEX / RESOLVED / primary=LONGBRIDGE_UNAVAILABLE
- CASH: UNRESOLVED / none / CASH_PROXY / UNRESOLVED
- OIL: UNRESOLVED / none / INDEX / UNRESOLVED

SEMI uses official **H30184** price-index history. BOND_LONG uses official **H11077 full-price** history; the clean-price derivative H01077 is explicitly forbidden. BOND_MED uses official **H00140 full-price** history. Longbridge static/history probes for each official code with both `.SH` and `.SZ` failed, so the registry preserves `LONGBRIDGE_UNAVAILABLE` while the supplemental source is the official CSI `index-perf` endpoint. No ETF or yield-change series is used.

Exact static/history attempts and supplemental exact-code checks are preserved in `benchmark_probe_results.json`.

Official references:

- [Longbridge symbol and history documentation](https://open.longbridge.com/docs/quote/pull/history-candlestick)
- [CSI 300 methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300_Index_Methodology_cn.pdf)
- [CSI 1000 methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175402-000852_Index_Methodology_cn.pdf)
- [CSI Dividend methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000922_Index_Methodology_cn.pdf)
- [CSI industry methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000841_Index_Methodology_cn.pdf)
- [CSI All Share Health Care factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000991factsheet.pdf)
- [CSI Coal methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175431-399998_Index_Methodology_cn.pdf)
- [CSI semiconductor factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30184factsheet.pdf)
- [SSE 10-year Treasury announcement](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20150911_3985075.shtml)
- [CSI 10-year Treasury factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H11077factsheet.pdf)
- [CSI 5-year Treasury factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H00140factsheet.pdf)
- [SZSE ChiNext notice](https://www.szse.cn/disclosure/notice/general/t20100531_500454.html)
- [Nasdaq-100 overview](https://www.nasdaq.com/products/global-indexes/nasdaq-100)
- [S&P 500 official page](https://www.spglobal.com/spdji/en/indices/equity/sp-500/)
- [Hang Seng TECH factsheet](https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/factsheets/hsteche.pdf)
- [Shanghai Gold Exchange daily quotes](https://www.sge.com.cn/sjzx/mrhq)

## Daily and weekly breadth tell the same diagnostic story at different close alignment

Daily common window: **2020-07-28 to 2026-08-31**, **1392** observations, N=15, N_eff=5.04, ratio=33.6%.

Weekly common window: **2020-08-07 to 2026-08-28**, **272** observations, N=15, N_eff=4.83, ratio=32.2%.

Daily is primary. Weekly is the cross-timezone robustness view. Each asset contributes its final real observation of the week; returns are intersected on those actual dates. No market price or return is forward-filled or set to zero, and no alternative lag was searched.

## Required pair evidence includes full-period and rolling correlations

- NASDAQ100 / SP500: daily=0.932; weekly=0.925; 252d median=0.939 [p10=0.882, p90=0.965]; 756d median=0.931 [p10=0.917, p90=0.953]
- HSTECH / HK_BROAD: daily=0.911; weekly=0.902; 252d median=0.940 [p10=0.888, p90=0.959]; 756d median=0.941 [p10=0.918, p90=0.950]
- CN_GROWTH / SEMI: daily=0.789; weekly=0.777; 252d median=0.785 [p10=0.645, p90=0.897]; 756d median=0.778 [p10=0.676, p90=0.879]
- BOND_LONG / BOND_MED: daily=0.737; weekly=0.882; 252d median=0.775 [p10=0.592, p90=0.914]; 756d median=0.730 [p10=0.682, p90=0.890]
- CN_DIVIDEND / COAL: daily=0.740; weekly=0.738; 252d median=0.747 [p10=0.580, p90=0.875]; 756d median=0.747 [p10=0.701, p90=0.789]

`pairwise_correlations.csv` contains maximum-history daily and weekly estimates. `rolling_pair_correlations.csv` contains the 252- and 756-observation distributions. Redundancy bands use raw rho, so negative correlation is not treated as duplication.

## Daily clustering and eigenvalue spectra preserve the full candidate set

Daily average-linkage clustering uses `sqrt(0.5 * (1-rho))`. Cluster order: **BOND_LONG, BOND_MED, NASDAQ100, SP500, GOLD, CN_DIVIDEND, COAL, HSTECH, HK_BROAD, SEMI, CN_SMALL, CN_LARGE, CN_GROWTH, HEALTHCARE, CONSUMER**. The daily and weekly eigenvalue spectra sum to **15.000** and **15.000**, respectively, matching their matrix dimension. See `correlation_heatmap.png`, `dendrogram.png`, `cluster_linkage.csv`, `eigenvalues.csv`, and `eigenvalues_weekly.csv`.

Rolling 756-observation daily effective breadth: **median=4.64, p10=4.45, p90=5.18, min=4.39, max=5.21, latest=4.74**.

## Scope, definitions, and data quality

This is a descriptive redundancy diagnostic, not M2, a universe freeze, a vehicle-selection exercise, or a performance claim. `N_eff = N^2 / sum(lambda_i^2)` is not an optimal asset count. CASH remains excluded from EX_CASH and no artificial zero-return proxy is created. OIL remains inactive, `INDEX_ONLY / NON_EXECUTABLE`, and outside both matrices.

All histories are unadjusted/native index or spot values with `HISTORICAL_LATEST` semantics. Retrieval cutoff: **2026-09-01**; latest retrieval: **2026-09-01T10:31:25.802048+00:00**; source baseline commit: **cf1c2b86b567e70d6f6cfcd91da32b0a01b074f9**; mapping SHA-256: **c08c8cb3669649984e07998c356da475f7dc8f4f68d40bd17fc00ee2647ed1ba**. The containing artifact commit is reported at handoff.

Data-quality checks preserve rather than silently clean exceptions:

- CN_LARGE: 1 calendar gaps exceed 14 days
- SEMI: 1 nonpositive raw level(s) set to missing for return calculation (2013-06-28); raw observations retained

Coverage and short-history status are in `coverage.csv`. Short-history assets:
- None

## Limitations and freeze-readiness boundary

The supplemental CSI histories are current official `HISTORICAL_LATEST` snapshots, not historical publication vintages. Daily cross-market correlations pair same calendar dates despite asynchronous closes; weekly results reduce that sensitivity but do not establish a causal or optimal universe. The benchmark registry remains candidate-only, and no Universe v1 is generated.

## Freeze gate

ANALYZED_ASSETS: CN_LARGE, CN_SMALL, CN_GROWTH, CN_DIVIDEND, SEMI, HEALTHCARE, CONSUMER, COAL, NASDAQ100, SP500, HSTECH, HK_BROAD, GOLD, BOND_LONG, BOND_MED

DAILY_N_EFF: 5.04

WEEKLY_N_EFF: 4.83

STRUCTURAL_REDUNDANCY_CANDIDATES: NASDAQ100 vs SP500, HSTECH vs HK_BROAD

ECONOMICALLY_DISTINCT_HIGH_CORRELATION: CN_LARGE vs CN_SMALL, CN_LARGE vs CN_DIVIDEND, CN_LARGE vs CONSUMER, CN_SMALL vs CN_GROWTH, CN_SMALL vs SEMI, CN_SMALL vs HEALTHCARE, CN_GROWTH vs SEMI, CN_GROWTH vs HEALTHCARE

UNRESOLVED_BENCHMARKS: CASH

NO ASSET AUTOMATICALLY REMOVED.
