# M2B.0 Historical ETF Vehicle Candidate Evidence Pack

## Technical summary

M2B.0 records a **candidate evidence pack**, not an execution-vehicle registry.
It covers the 14 non-cash active Logical Assets in frozen Universe v1 and keeps
CASH as an explicit non-vehicle balance. The pack contains 17 evidence records:
14 `EXACT_TRACKING`, 2 `ECONOMIC_PROXY_CANDIDATE`, 1
`REJECTED_SEMANTIC_MISMATCH`, and 0 `UNRESOLVED`. Every candidate remains
`UNREVIEWED`; no vehicle is approved, selected, ranked, or frozen.

The global completeness assessment is `PARTIAL_CURATED`, with
`historical_cemetery_complete: false`. No delisted candidate was found in this
bounded pass, but the absence of an authoritative all-history ETF security master
means this is not evidence that no qualifying ETF was ever delisted.

## Scope and decision boundary

- Frozen Logical Asset Universe v1 is unchanged and hash-bound to this pack.
- HSTECH remains deferred; no candidate discovery was performed for it.
- OIL remains inactive, index-only, and non-executable; no equity proxy was added.
- CASH uses `CASH_BALANCE` with `vehicle_required: false`.
- Only exchange-traded funds are admitted. LOF and other vehicle types fail validation.
- Current AUM, trading volume, spread, liquidity, performance, ranking, and selector
  criteria are expressly excluded.
- Listing dates and Logical-Asset mapping-effective dates are separate fields.
  Their equality in a record means the reviewed evidence supports mapping from
  listing, not that the schema treats the concepts as equivalent.

## Coverage by Logical Asset

`GOOD` below means that this pack has at least one evidence-complete exact candidate
for the frozen benchmark (or an explicit non-vehicle CASH contract). It does not
mean approved, investable, liquid, historically exhaustive, or suitable for a
strategy.

| Logical Asset | Frozen research benchmark | Candidates | Exact | Proxy | Rejected | Earliest exact listing |
|---|---|---:|---:|---:|---:|---|
| CN_LARGE | 000300 / CSI 300 | 1 | 1 | 0 | 0 | 2012-05-28 |
| CN_SMALL | 000852 / CSI 1000 | 1 | 1 | 0 | 0 | 2016-11-04 |
| CN_GROWTH | 399006 / ChiNext | 1 | 1 | 0 | 0 | 2011-12-09 |
| CN_DIVIDEND | 000922 / CSI Dividend | 2 | 1 | 1 | 0 | 2019-12-20 |
| SEMI | H30184 | 1 | 1 | 0 | 0 | 2019-06-12 |
| HEALTHCARE | 000991 | 2 | 1 | 1 | 0 | 2015-01-08 |
| CONSUMER | 000932 | 1 | 1 | 0 | 0 | 2013-09-16 |
| COAL | 399998 | 1 | 1 | 0 | 0 | 2020-03-02 |
| SP500 | S&P 500 | 1 | 1 | 0 | 0 | 2014-01-15 |
| NASDAQ100 | Nasdaq-100 | 1 | 1 | 0 | 0 | 2013-05-15 |
| HK_BROAD | Hang Seng Index | 1 | 1 | 0 | 0 | 2012-10-22 |
| GOLD | Au99.99 economic gold exposure | 2 | 1 | 0 | 1 | 2013-07-29 |
| BOND_LONG | H11077 / 10Y government bond | 1 | 1 | 0 | 0 | 2017-08-24 |
| BOND_MED | H00140 / 5Y government bond | 1 | 1 | 0 | 0 | 2013-03-25 |
| CASH | CASH_BALANCE | 0 | 0 | 0 | 0 | — |

Machine-readable counts and dates are in [`coverage.csv`](coverage.csv).

## Candidate detail

Evidence completeness means official evidence covers vehicle identity, listing
period, and tracking-index identity. A complete row is still unapproved.

| Logical Asset | Symbol | Fund | Tracking index | Class | List date | Delist date | QDII | Evidence complete | Unresolved issue |
|---|---|---|---|---|---|---|---|---|---|
| CN_LARGE | 510300.SH | 华泰柏瑞沪深300ETF | 000300 | EXACT_TRACKING | 2012-05-28 | — | false | yes | Historical cemetery not exhaustive |
| CN_SMALL | 512100.SH | 南方中证1000ETF | 000852 | EXACT_TRACKING | 2016-11-04 | — | false | yes | Historical cemetery not exhaustive |
| CN_GROWTH | 159915.SZ | 易方达创业板ETF | 399006 | EXACT_TRACKING | 2011-12-09 | — | false | yes | Historical cemetery not exhaustive |
| CN_DIVIDEND | 515180.SH | 易方达中证红利ETF | 000922 | EXACT_TRACKING | 2019-12-20 | — | false | yes | Historical cemetery not exhaustive |
| CN_DIVIDEND | 510880.SH | 华泰柏瑞上证红利ETF | 000015 | ECONOMIC_PROXY_CANDIDATE | 2007-01-18 | — | false | yes | Different dividend index; manual semantic review required |
| SEMI | 512480.SH | 国联安中证全指半导体ETF | H30184 | EXACT_TRACKING | 2019-06-12 | — | false | yes | Historical cemetery not exhaustive |
| HEALTHCARE | 159938.SZ | 广发中证全指医药卫生ETF | 000991 | EXACT_TRACKING | 2015-01-08 | — | false | yes | Historical cemetery not exhaustive |
| HEALTHCARE | 512170.SH | 华宝中证医疗ETF | 399989 | ECONOMIC_PROXY_CANDIDATE | 2019-06-17 | — | false | yes | Narrower/different index; manual semantic review required |
| CONSUMER | 159928.SZ | 汇添富中证主要消费ETF | 000932 | EXACT_TRACKING | 2013-09-16 | — | false | yes | Historical cemetery not exhaustive |
| COAL | 515220.SH | 国泰中证煤炭ETF | 399998 | EXACT_TRACKING | 2020-03-02 | — | false | yes | Historical cemetery not exhaustive |
| SP500 | 513500.SH | 博时标普500ETF | SPX net total return | EXACT_TRACKING | 2014-01-15 | — | true | yes | Historical cemetery and historical QDII operating constraints not assessed |
| NASDAQ100 | 513100.SH | 国泰纳斯达克100ETF | NDX | EXACT_TRACKING | 2013-05-15 | — | true | yes | Historical cemetery and historical QDII operating constraints not assessed |
| HK_BROAD | 159920.SZ | 华夏恒生ETF | HSI | EXACT_TRACKING | 2012-10-22 | — | true | yes | Historical cemetery and historical QDII operating constraints not assessed |
| GOLD | 518880.SH | 华安黄金ETF | Au99.99 | EXACT_TRACKING | 2013-07-29 | — | false | yes | Historical cemetery not exhaustive |
| GOLD | 517520.SH | 永赢沪深港黄金产业股票ETF | 931238 | REJECTED_SEMANTIC_MISMATCH | 2023-11-01 | — | false | yes | Gold-industry equities are not spot-gold exposure |
| BOND_LONG | 511260.SH | 十年国债ETF | H11077 full-price | EXACT_TRACKING | 2017-08-24 | — | false | yes | Historical cemetery not exhaustive |
| BOND_MED | 511010.SH | 国债ETF | H00140 full-price | EXACT_TRACKING | 2013-03-25 | — | false | yes | Historical cemetery not exhaustive |

## Candidate-level evidence findings

### China broad/style and industry sleeves

- **510300.SH / CN_LARGE — EXACT_TRACKING.** SSE official fund material
  identifies the ETF, its 2012-05-28 listing, and CSI 300 tracking objective.
- **512100.SH / CN_SMALL — EXACT_TRACKING.** SSE official fund material
  identifies the ETF, its 2016-11-04 listing, and CSI 1000 tracking objective.
- **159915.SZ / CN_GROWTH — EXACT_TRACKING.** SZSE official listing and product
  references establish the vehicle, 2011-12-09 listing, and 399006 tracking.
- **515180.SH / CN_DIVIDEND — EXACT_TRACKING.** SSE fund material and CSI
  methodology support the 000922 mapping from the documented 2019-12-20 listing.
- **510880.SH / CN_DIVIDEND — ECONOMIC_PROXY_CANDIDATE.** The official tracking
  index is SSE Dividend 000015, not the frozen CSI Dividend 000922 benchmark.
- **512480.SH / SEMI — EXACT_TRACKING.** SSE fund material and the CSI H30184
  factsheet support the mapping from the 2019-06-12 listing.
- **159938.SZ / HEALTHCARE — EXACT_TRACKING.** Official manager and SZSE records
  support the 000991 mapping from the 2015-01-08 listing.
- **512170.SH / HEALTHCARE — ECONOMIC_PROXY_CANDIDATE.** It tracks CSI Medical
  399989 rather than frozen broad health-care benchmark 000991.
- **159928.SZ / CONSUMER — EXACT_TRACKING.** Official manager material supports
  the 000932 mapping from the 2013-09-16 listing.
- **515220.SH / COAL — EXACT_TRACKING.** SSE fund material and CSI methodology
  support the 399998 mapping from the 2020-03-02 listing.

### Cross-border equity sleeve

- **513500.SH / SP500 — EXACT_TRACKING.** Official SSE fund reporting identifies
  the 2014-01-15 listing and RMB-adjusted S&P 500 net-total-return benchmark.
- **513100.SH / NASDAQ100 — EXACT_TRACKING.** Official SSE fund material identifies
  the 2013-05-15 listing and Nasdaq-100 tracking objective.
- **159920.SZ / HK_BROAD — EXACT_TRACKING.** Official manager and SZSE product
  records identify the 2012-10-22 listing and Hang Seng Index mapping.

### Diversifiers

- **518880.SH / GOLD — EXACT_TRACKING.** SSE listing material and the Shanghai
  Gold Exchange ETF reference support Au99.99 spot-gold semantics.
- **517520.SH / GOLD — REJECTED_SEMANTIC_MISMATCH.** CSI methodology shows that
  931238 represents gold-industry equities. It cannot stand in for Au99.99 spot
  gold, irrespective of any empirical return relationship.
- **511260.SH / BOND_LONG — EXACT_TRACKING.** Official SSE and CSI evidence maps
  the ETF to H11077, a 10-year government-bond full-price index. No yield-change
  series is substituted.
- **511010.SH / BOND_MED — EXACT_TRACKING.** Official SSE and CSI evidence maps
  the ETF to H00140, a 5-year government-bond full-price index. No yield-change
  series is substituted.

## Evidence method

The live AkShare `fund_etf_spot_em` endpoint supplied a one-time current ETF
snapshot as a discovery seed. That snapshot has `CURRENT_SNAPSHOT` semantics and
was not used to infer historical existence, historical continuity, delisting, or
mapping periods. Each retained record instead carries its own retrieval timestamp,
claim, provenance URL, official flag, and evidence scope.

Primary evidence consists of official SSE/SZSE listings and fund disclosures,
official fund-manager documents where needed, and CSI/SGE index or product
references. Exact candidates require official coverage of vehicle identity,
listing period, and tracking index. The evidence pack is bound to source commit
`f866a80f1f3496d6c8ac8f1644abe052367a7194` and to the SHA-256 of frozen
`configs/universe_v1.yaml`.

## Validation and limitations

The offline validator fails fast on out-of-scope Logical Assets, CASH ETF records,
non-ETF vehicle types, silently approved proxies, incomplete exact mappings,
invalid listing or mapping dates, overlapping symbol periods, cemetery-completeness
claims, and selector/performance fields. Adjacent effective periods for a genuine
tracking-index change remain representable, and known delisted observations are
retained rather than overwritten or dropped.

Remaining evidence gaps are material:

1. Historical ETF cemetery completeness is unresolved.
2. Predecessor vehicles and terminated funds may be absent because the discovery
   seed is a current-survivor snapshot.
3. Historical tracking-index changes were not exhaustively reconstructed for every
   symbol; the schema supports them, but this pass found no verified change to add.
4. Listing and current product evidence do not establish tradability, subscription
   constraints, liquidity, or suitability at every historical date.
5. Human review is required before any candidate can enter a future historical
   vehicle registry. M2B.1, M2C, selection, and backtesting have not started.

## Freeze-gate result

`CANDIDATE_NOT_APPROVED`. The evidence pack is structurally valid and locally
complete for the documented exact/proxy/rejection claims, but globally
`PARTIAL_CURATED`. No candidate has been promoted into an execution mapping.

- `EXACT_TRACKING_CANDIDATES`: 14
- `PROXY_CANDIDATES`: 2
- `REJECTED_MISMATCHES`: 1
- `UNRESOLVED_CANDIDATES`: 0
