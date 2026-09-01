# Universe Diagnostic U1 — Logical Asset Effective Breadth Check

## Answer first

Nominal active risky assets: **15**  
Analyzed common-window assets: **12**  
Common-window effective breadth: **4.07**  
Effective ratio (analyzed N denominator): **33.9%**

Structural redundancy candidates:
- NASDAQ100 vs SP500
- HSTECH vs HK_BROAD

High-overlap but economically distinct (diagnostic only):
- CN_LARGE vs CN_SMALL
- CN_LARGE vs CN_DIVIDEND
- CN_LARGE vs CONSUMER
- CN_SMALL vs CN_GROWTH
- CN_SMALL vs HEALTHCARE
- CN_GROWTH vs HEALTHCARE

Short-history assets:
- None

Unresolved benchmark mappings:
- SEMI
- BOND_LONG
- BOND_MED
- CASH

**NO ASSET WAS AUTOMATICALLY REMOVED.**

## Scope and interpretation

This is a statistical redundancy diagnostic, not M2, a universe freeze, a vehicle-selection exercise, or a performance claim. It uses native index/spot levels only; no ETF prices, profitability metrics, forward-filled cross-market prices, artificial zero returns, or return-based asset selection are used. `N_eff` is descriptive and is not an optimal asset count.

All histories are `HISTORICAL_LATEST`: the provider snapshot retrieved now may contain current corrected history and does not prove historical publication vintages. Metadata: retrieval cutoff **2026-09-01**, data retrieved at **2026-09-01T08:23:45.123383+00:00**, source baseline Git commit **1363bba058dae3ae79af2d6412868a55cf549ee9**, benchmark mapping SHA-256 **6432ac54d0b0aae969cefe7844dfce81df9aa89938c60dfd3ecbc30449df448e**. The containing U1 artifact commit is reported at handoff because a Git object cannot self-reference its own final hash.

## 1. Benchmark mapping

- CN_LARGE: 000300.SH / longbridge / INDEX / RESOLVED
- CN_SMALL: 000852.SH / longbridge / INDEX / RESOLVED
- CN_GROWTH: 399006.SZ / longbridge / INDEX / RESOLVED
- CN_DIVIDEND: 000922.SH / longbridge / INDEX / RESOLVED
- SEMI: UNRESOLVED / none / INDEX / UNRESOLVED
- HEALTHCARE: 000991.SH / longbridge / INDEX / RESOLVED
- CONSUMER: 000932.SH / longbridge / INDEX / RESOLVED
- COAL: 399998.SZ / longbridge / INDEX / RESOLVED
- NASDAQ100: .NDX.US / longbridge / INDEX / RESOLVED
- SP500: .SPX.US / longbridge / INDEX / RESOLVED
- HSTECH: HSTECH.HK / longbridge / INDEX / RESOLVED
- HK_BROAD: HSI.HK / longbridge / INDEX / RESOLVED
- GOLD: Au99.99 / akshare / SPOT / RESOLVED
- BOND_LONG: UNRESOLVED / none / INDEX / UNRESOLVED
- BOND_MED: UNRESOLVED / none / INDEX / UNRESOLVED
- CASH: UNRESOLVED / none / CASH_PROXY / UNRESOLVED
- OIL: UNRESOLVED / none / INDEX / UNRESOLVED

The exact audited snapshot is in `benchmark_registry_snapshot.yaml`. Official mapping references:

- [Longbridge symbol and history documentation](https://open.longbridge.com/docs/quote/pull/history-candlestick)
- [CSI 300 methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300_Index_Methodology_cn.pdf)
- [CSI 1000 methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175402-000852_Index_Methodology_cn.pdf)
- [CSI Dividend methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000922_Index_Methodology_cn.pdf)
- [CSI industry methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000841_Index_Methodology_cn.pdf)
- [CSI All Share Health Care factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000991factsheet.pdf)
- [CSI Coal methodology](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175431-399998_Index_Methodology_cn.pdf)
- [SZSE ChiNext notice](https://www.szse.cn/disclosure/notice/general/t20100531_500454.html)
- [Nasdaq-100 overview](https://www.nasdaq.com/products/global-indexes/nasdaq-100)
- [S&P 500 official page](https://www.spglobal.com/spdji/en/indices/equity/sp-500/)
- [Hang Seng TECH factsheet](https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/factsheets/hsteche.pdf)
- [Shanghai Gold Exchange daily quotes](https://www.sge.com.cn/sjzx/mrhq)

## 2. Coverage and data quality

`coverage.csv` reports first/last valid date and observation count. Warnings are preserved rather than silently cleaned:

- CN_LARGE: 1 calendar gaps exceed 14 days

Unresolved assets remain part of the nominal candidate universe but cannot enter numeric matrices. CASH is excluded from EX_CASH because no real cash-return series is available; no zero-return proxy was manufactured. OIL remains inactive, `INDEX_ONLY / NON_EXECUTABLE`, and is excluded.

## 3. Common window

The common daily-return window is **2020-07-28 to 2026-08-31**, with **1392** date-level intersection observations across **12** analyzable EX_CASH assets. No asset was dropped merely to lengthen this window.

## 4. Pairwise maximum-history correlations

`pairwise_correlations.csv` contains daily primary and weekly robustness results. Each pair uses only its own shared valid dates and records start, end, and n. Redundancy bands use raw rho; negative correlation is never treated as redundancy through `abs(rho)`.

## 5. Rolling correlations

`rolling_pair_correlations.csv` provides 252- and 756-observation statistics for required focus pairs and GOLD-versus-risk-asset comparisons. Unresolved pairs are explicitly `UNAVAILABLE`; insufficient windows are `SKIPPED_SHORT_HISTORY`.

## 6. Clustering

Average linkage is computed from daily common-window correlation distance `sqrt(0.5 * (1-rho))`. Cluster order: **NASDAQ100, SP500, GOLD, CN_DIVIDEND, COAL, HSTECH, HK_BROAD, CONSUMER, HEALTHCARE, CN_SMALL, CN_LARGE, CN_GROWTH**. The exact merge rows are in `cluster_linkage.csv`; see `dendrogram.png` and `correlation_heatmap.png`.

## 7. Eigenvalue spectrum

The descending eigenvalues are in `eigenvalues.csv`. Largest eigenvalue: **5.220**; sum: **12.000** (equal to analyzed N within numeric precision).

## 8. Participation ratio

EX_CASH common-window `N_eff = N^2 / sum(lambda_i^2)` is **4.07** for analyzed N=12, ratio **33.9%**. The nominal active risky count remains 15; unresolved mappings explain the gap between nominal and analyzed N.

Rolling 756-observation effective breadth: **median=3.84, p10=3.66, p90=4.11, min=3.60, max=4.18, latest=3.95**.

## 9. Required focus pairs

- CN_LARGE vs CN_DIVIDEND: rho=0.778, n=2582, 2016-01-14 to 2026-09-01, band=HIGH
- CN_GROWTH vs SEMI: unavailable (unresolved or missing data)
- CN_DIVIDEND vs COAL: rho=0.740, n=2582, 2016-01-14 to 2026-09-01, band=MODERATE
- NASDAQ100 vs SP500: rho=0.932, n=4189, 2010-01-05 to 2026-08-31, band=VERY_HIGH
- HSTECH vs HK_BROAD: rho=0.911, n=1499, 2020-07-28 to 2026-09-01, band=VERY_HIGH
- BOND_LONG vs BOND_MED: unavailable (unresolved or missing data)

GOLD versus available risk assets:

- CN_LARGE vs GOLD: rho=0.088, n=2353
- CN_SMALL vs GOLD: rho=0.100, n=2353
- CN_GROWTH vs GOLD: rho=0.052, n=2353
- CN_DIVIDEND vs GOLD: rho=0.083, n=2352
- HEALTHCARE vs GOLD: rho=0.057, n=2353
- CONSUMER vs GOLD: rho=0.047, n=2353
- COAL vs GOLD: rho=0.053, n=2353
- NASDAQ100 vs GOLD: rho=0.003, n=2273
- SP500 vs GOLD: rho=0.014, n=2273
- HSTECH vs GOLD: rho=0.087, n=1434
- HK_BROAD vs GOLD: rho=0.081, n=2284

## 10. Unresolved benchmark/data issues

- SEMI
- BOND_LONG
- BOND_MED
- CASH

These are evidence gaps, not rejection decisions. SEMI was not replaced by an ETF or name-similar index. BOND_LONG and BOND_MED were not approximated with yield changes. CASH was not assigned zero returns.

## 11. Purely diagnostic conclusion

Nominal active risky assets: 15

Common-window effective breadth: 4.07

Effective ratio: 33.9% of analyzed N (12); nominal-universe coverage is separately reported.

Structural redundancy candidates:
- NASDAQ100 vs SP500
- HSTECH vs HK_BROAD

High-overlap but economically distinct:
- CN_LARGE vs CN_SMALL
- CN_LARGE vs CN_DIVIDEND
- CN_LARGE vs CONSUMER
- CN_SMALL vs CN_GROWTH
- CN_SMALL vs HEALTHCARE
- CN_GROWTH vs HEALTHCARE

Short-history assets:
- None

Unresolved benchmark mappings:
- SEMI
- BOND_LONG
- BOND_MED
- CASH

NO ASSET WAS AUTOMATICALLY REMOVED.
