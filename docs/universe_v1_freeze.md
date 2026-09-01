# Logical Asset Universe v1.0 Freeze

## Freeze record

- Freeze date: **2026-09-01**
- Universe status: **FROZEN_V1**
- Freeze baseline commit: `cafbea27dbfd8d72e85fc2ac3ef1bf2f34a7e7c1`
- U1 commit: `cf1c2b86b567e70d6f6cfcd91da32b0a01b074f9`
- U1.1 commit: `cafbea27dbfd8d72e85fc2ac3ef1bf2f34a7e7c1`
- Frozen config: `configs/universe_v1.yaml`
- Benchmark registry source: `configs/logical_asset_benchmarks_candidate.yaml`
- Benchmark registry SHA-256: `c08c8cb3669649984e07998c356da475f7dc8f4f68d40bd17fc00ee2647ed1ba`

This is a human-approved policy freeze. It does not rerun U1/U1.1, select assets from historical performance, choose ETF vehicles, or implement M2.

## Human-approved ACTIVE Logical Assets

The frozen universe contains exactly 15 ACTIVE Logical Assets:

| Logical Asset ID | Chinese name | Sleeve | Research benchmark |
|---|---|---|---|
| CN_LARGE | 沪深300 | CHINA_BROAD_STYLE | 000300.SH |
| CN_SMALL | 中证1000 | CHINA_BROAD_STYLE | 000852.SH |
| CN_GROWTH | 创业板 | CHINA_BROAD_STYLE | 399006.SZ |
| CN_DIVIDEND | 红利 | CHINA_BROAD_STYLE | 000922.SH |
| SEMI | 半导体 | CHINA_INDUSTRY | H30184 / CSI official / PRICE_INDEX |
| HEALTHCARE | 医药医疗 | CHINA_INDUSTRY | 000991.SH |
| CONSUMER | 消费 | CHINA_INDUSTRY | 000932.SH |
| COAL | 煤炭 | CHINA_INDUSTRY | 399998.SZ |
| SP500 | 标普500 | OVERSEAS_EQUITY | .SPX.US |
| NASDAQ100 | 纳斯达克100 | OVERSEAS_EQUITY | .NDX.US |
| HK_BROAD | 港股宽基 | OVERSEAS_EQUITY | HSI.HK |
| GOLD | 黄金 | COMMODITY | Au99.99 |
| BOND_LONG | 长久期中国国债 | DEFENSIVE | H11077 / FULL_PRICE_INDEX |
| BOND_MED | 中久期中国国债 | DEFENSIVE | H00140 / FULL_PRICE_INDEX |
| CASH | 现金 | DEFENSIVE | No market benchmark yet |

Research benchmark mapping and execution vehicle mapping are separate concepts. Universe v1 stores benchmark references only. It contains no ETF execution symbol, Historical Vehicle Registry, or Vehicle Selector output.

## Deferred and inactive candidates

### HSTECH — DEFERRED_REDUNDANCY

U1/U1.1 identified structural redundancy with HK_BROAD:

- Daily correlation: approximately 0.911
- Weekly correlation: approximately 0.902
- 756-day rolling median: approximately 0.941

Human freeze decision: **KEEP HK_BROAD; DEFER HSTECH**. HSTECH is not ACTIVE. Its additional overlap with China growth/technology exposure supports deferral but does not redefine the retained assets.

### OIL — INACTIVE_NO_VALID_ETF_VEHICLE

OIL remains `INDEX_ONLY / NON_EXECUTABLE`. Current ETF-only candidates do not provide verified execution exposure with matching crude-oil economic semantics. Oil & gas equity ETFs are not substitutes. OIL is not ACTIVE.

## Frozen sleeves

- CHINA_BROAD_STYLE: CN_LARGE, CN_SMALL, CN_GROWTH, CN_DIVIDEND
- CHINA_INDUSTRY: SEMI, HEALTHCARE, CONSUMER, COAL
- OVERSEAS_EQUITY: SP500, NASDAQ100, HK_BROAD
- COMMODITY: GOLD
- DEFENSIVE: BOND_LONG, BOND_MED, CASH

Each ACTIVE Logical Asset belongs to exactly one sleeve.

## Predeclared semi-static risk clusters

- CN_GROWTH_TECH: CN_GROWTH, SEMI
- US_EQUITY: SP500, NASDAQ100
- CN_RATES: BOND_LONG, BOND_MED

These are prior groupings for future risk control and portfolio construction. No cluster cap, optimization, or portfolio rule is implemented by this freeze. CN_DIVIDEND and COAL remain economically distinct and are not forced into a shared cluster.

## Diagnostic record and human decisions

U1.1 measured 15 active risky assets before the final freeze:

- DAILY_N_EFF: **5.04**
- WEEKLY_N_EFF: **4.83**
- Structural redundancy candidates: NASDAQ100 / SP500; HSTECH / HK_BROAD

The diagnostics informed, but did not automate, the following human decisions:

- SP500 and NASDAQ100 are both retained because they represent US broad core and US growth/technology tilt, respectively.
- HK_BROAD is retained; HSTECH is deferred for structural redundancy and overlap with China growth/technology exposure.
- CN_GROWTH and SEMI are retained as economically distinct.
- CN_DIVIDEND and COAL are retained as economically distinct.
- BOND_LONG and BOND_MED are retained because their duration roles differ.
- GOLD is retained for its distinct diversification role.
- OIL remains inactive because the execution semantics do not match available ETF-only vehicles.

No asset was automatically removed. Universe membership changes after this record require an explicit new version and human approval.
