from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from etf_quant.providers.akshare.research_benchmarks import AkShareResearchBenchmarkProvider
from etf_quant.providers.dto import RawBenchmarkLevel
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.research_benchmarks import LongbridgeResearchBenchmarkProvider
from etf_quant.research.universe_diagnostic import (
    ACTIVE_LOGICAL_ASSETS,
    RISK_ASSETS_EX_CASH,
    average_linkage,
    common_window_frame,
    correlation_distance_matrix,
    ex_cash,
    history_flag,
    load_benchmark_registry,
    pairwise_correlation_rows,
    participation_ratio,
    redundancy_band,
    rolling_effective_breadth,
    rolling_pair_statistics,
    simple_returns,
    structural_redundancy_candidate,
    validate_levels,
    weekly_returns,
)


FOCUS_PAIRS = (
    ("CN_LARGE", "CN_DIVIDEND"),
    ("CN_GROWTH", "SEMI"),
    ("CN_DIVIDEND", "COAL"),
    ("NASDAQ100", "SP500"),
    ("HSTECH", "HK_BROAD"),
    ("BOND_LONG", "BOND_MED"),
)
OFFICIAL_SOURCES = {
    "Longbridge symbol and history documentation": "https://open.longbridge.com/docs/quote/pull/history-candlestick",
    "CSI 300 methodology": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300_Index_Methodology_cn.pdf",
    "CSI 1000 methodology": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175402-000852_Index_Methodology_cn.pdf",
    "CSI Dividend methodology": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000922_Index_Methodology_cn.pdf",
    "CSI industry methodology": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000841_Index_Methodology_cn.pdf",
    "CSI All Share Health Care factsheet": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000991factsheet.pdf",
    "CSI Coal methodology": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20231208175431-399998_Index_Methodology_cn.pdf",
    "SZSE ChiNext notice": "https://www.szse.cn/disclosure/notice/general/t20100531_500454.html",
    "Nasdaq-100 overview": "https://www.nasdaq.com/products/global-indexes/nasdaq-100",
    "S&P 500 official page": "https://www.spglobal.com/spdji/en/indices/equity/sp-500/",
    "Hang Seng TECH factsheet": "https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/factsheets/hsteche.pdf",
    "Shanghai Gold Exchange daily quotes": "https://www.sge.com.cn/sjzx/mrhq",
}


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _cache_path(root: Path, asset_id: str) -> Path:
    return root / f"{asset_id}.csv"


def _save_raw_cache(path: Path, observations: list[RawBenchmarkLevel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "observation_date": row.observation_date.isoformat(),
                "level": row.level,
                "symbol": row.symbol,
                "provider": row.provider,
                "retrieved_at": row.retrieved_at.isoformat(),
                "sdk_version": row.sdk_version,
                "historical_data_semantics": row.historical_data_semantics.value,
            }
            for row in observations
        ]
    ).to_csv(path, index=False)


def _load_cached_levels(path: Path) -> tuple[pd.Series, dict[str, str]]:
    frame = pd.read_csv(path)
    required = {
        "observation_date", "level", "provider", "retrieved_at",
        "historical_data_semantics", "symbol",
    }
    if not required.issubset(frame.columns):
        raise ValueError(f"cache {path} lacks columns: {required - set(frame.columns)}")
    if set(frame["historical_data_semantics"].dropna()) != {"historical_latest"}:
        raise ValueError(f"cache {path} is not HISTORICAL_LATEST")
    series = pd.Series(
        pd.to_numeric(frame["level"], errors="raise").to_numpy(),
        index=pd.to_datetime(frame["observation_date"], errors="raise"),
        name=path.stem,
    ).sort_index()
    metadata = {
        "provider": str(frame["provider"].iloc[-1]),
        "symbol": str(frame["symbol"].iloc[-1]),
        "retrieved_at": str(frame["retrieved_at"].max()),
        "historical_data_semantics": "HISTORICAL_LATEST",
    }
    return series, metadata


def _download(
    candidate: Any,
    *,
    start: date,
    end: date,
    longbridge: LongbridgeResearchBenchmarkProvider | None,
    akshare: AkShareResearchBenchmarkProvider,
) -> list[RawBenchmarkLevel]:
    if candidate.provider == "longbridge":
        if longbridge is None:
            raise RuntimeError("Longbridge credentials are required for uncached Longbridge benchmarks")
        return longbridge.get_daily_levels(
            candidate.benchmark_symbol,
            start,
            end,
            timezone=candidate.timezone,
        )
    if candidate.provider == "akshare":
        rows = akshare.get_sge_spot_levels(candidate.benchmark_symbol)
        return [row for row in rows if start <= row.observation_date <= end]
    raise ValueError(f"unsupported provider: {candidate.provider}")


def _plot_heatmap(correlation: pd.DataFrame, order: list[str], output: Path) -> None:
    matrix = correlation.loc[order, order]
    size = max(8.0, 0.65 * len(order))
    fig, ax = plt.subplots(figsize=(size, size - 0.8))
    image = ax.imshow(matrix, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(order)), order, rotation=55, ha="right", fontsize=8)
    ax.set_yticks(range(len(order)), order, fontsize=8)
    ax.set_title("U1 common-window daily return correlation (EX_CASH)")
    fig.colorbar(image, ax=ax, fraction=0.045, pad=0.04, label="Pearson correlation")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _plot_dendrogram(linkage: np.ndarray, labels: list[str], output: Path) -> None:
    n = len(labels)
    children = {n + i: (int(row[0]), int(row[1]), float(row[2])) for i, row in enumerate(linkage)}

    def leaves(node: int) -> list[int]:
        if node < n:
            return [node]
        left, right, _ = children[node]
        return leaves(left) + leaves(right)

    root = 2 * n - 2
    leaf_order = leaves(root)
    x_position = {leaf: pos for pos, leaf in enumerate(leaf_order)}
    node_x: dict[int, float] = dict(x_position)
    node_y: dict[int, float] = {leaf: 0.0 for leaf in leaf_order}
    fig, ax = plt.subplots(figsize=(max(10, 0.75 * n), 6))
    for node in range(n, 2 * n - 1):
        left, right, height = children[node]
        left_x, right_x = node_x[left], node_x[right]
        ax.plot([left_x, left_x], [node_y[left], height], color="#334155", linewidth=1.2)
        ax.plot([right_x, right_x], [node_y[right], height], color="#334155", linewidth=1.2)
        ax.plot([left_x, right_x], [height, height], color="#334155", linewidth=1.2)
        node_x[node] = (left_x + right_x) / 2
        node_y[node] = height
    ax.set_xticks(range(n), [labels[i] for i in leaf_order], rotation=50, ha="right")
    ax.set_ylabel("Correlation distance")
    ax.set_title("Average-linkage clustering of common-window daily returns")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _focus_pairs(available: Iterable[str]) -> list[tuple[str, str]]:
    available_set = set(available)
    pairs = list(FOCUS_PAIRS)
    if "GOLD" in available_set:
        pairs.extend(("GOLD", asset) for asset in available_set if asset not in {"GOLD", "CASH"})
    return pairs


def _pair_lookup(pairwise: pd.DataFrame, left: str, right: str) -> pd.Series | None:
    rows = pairwise[
        ((pairwise["asset_1"] == left) & (pairwise["asset_2"] == right))
        | ((pairwise["asset_1"] == right) & (pairwise["asset_2"] == left))
    ]
    return rows.iloc[0] if len(rows) else None


def _format_corr(value: Any) -> str:
    return "N/A" if pd.isna(value) else f"{float(value):.3f}"


def _build_report(
    *,
    output: Path,
    registry: list[Any],
    coverage: pd.DataFrame,
    pairwise_daily: pd.DataFrame,
    common: pd.DataFrame,
    correlation: pd.DataFrame,
    eigenvalues: np.ndarray,
    effective_n: float,
    rolling_pairs: pd.DataFrame,
    rolling_breadth: pd.Series,
    cluster_order: list[str],
    mapping_hash: str,
    retrieved_at: str,
    cutoff: date,
    git_commit: str,
    warnings: list[str],
) -> None:
    unresolved = [row.logical_asset_id for row in registry if row.active and row.status == "UNRESOLVED"]
    short = coverage.loc[
        coverage["history_flag"].isin({"SHORT_HISTORY", "VERY_SHORT_HISTORY"}),
        "logical_asset_id",
    ].tolist()
    rolling_3y = {
        tuple(sorted((str(row.asset_1), str(row.asset_2)))): float(row.median)
        for row in rolling_pairs.itertuples()
        if row.window == 756 and row.status == "OK"
    }
    structural: list[str] = []
    high_distinct: list[str] = []
    for row in pairwise_daily.itertuples():
        rho = float(row.pearson_correlation)
        key = tuple(sorted((row.asset_1, row.asset_2)))
        median = rolling_3y.get(key, float("nan"))
        label = f"{row.asset_1} vs {row.asset_2}"
        if structural_redundancy_candidate(rho, median):
            structural.append(label)
        elif rho >= 0.75:
            high_distinct.append(label)

    focus_lines = []
    for left, right in FOCUS_PAIRS:
        row = _pair_lookup(pairwise_daily, left, right)
        if row is None:
            focus_lines.append(f"- {left} vs {right}: unavailable (unresolved or missing data)")
        else:
            focus_lines.append(
                f"- {left} vs {right}: rho={_format_corr(row['pearson_correlation'])}, "
                f"n={int(row['n_obs'])}, {row['start_date']} to {row['end_date']}, "
                f"band={row['redundancy_band']}"
            )
    gold_rows = pairwise_daily[
        (pairwise_daily["asset_1"] == "GOLD") | (pairwise_daily["asset_2"] == "GOLD")
    ]
    gold_lines = [
        f"- {row.asset_1} vs {row.asset_2}: rho={row.pearson_correlation:.3f}, n={row.n_obs}"
        for row in gold_rows.itertuples()
    ] or ["- GOLD comparison unavailable"]

    rolling_status = "SKIPPED: fewer than 756 common-window observations"
    rolling_summary = rolling_status
    if not rolling_breadth.empty:
        rolling_summary = (
            f"median={rolling_breadth.median():.2f}, p10={rolling_breadth.quantile(.1):.2f}, "
            f"p90={rolling_breadth.quantile(.9):.2f}, min={rolling_breadth.min():.2f}, "
            f"max={rolling_breadth.max():.2f}, latest={rolling_breadth.iloc[-1]:.2f}"
        )
    source_lines = [f"- [{label}]({url})" for label, url in OFFICIAL_SOURCES.items()]
    mapping_lines = [
        f"- {row.logical_asset_id}: {row.benchmark_symbol or 'UNRESOLVED'} / "
        f"{row.provider or 'none'} / {row.benchmark_type} / {row.status}"
        for row in registry
    ]
    warning_lines = [f"- {item}" for item in warnings] or ["- No level-integrity warnings beyond declared unresolved mappings."]
    structural_lines = [f"- {item}" for item in structural] or ["- None"]
    high_lines = [f"- {item}" for item in high_distinct] or ["- None"]
    short_lines = [f"- {item}" for item in short] or ["- None"]
    unresolved_lines = [f"- {item}" for item in unresolved] or ["- None"]

    text = f"""# Universe Diagnostic U1 — Logical Asset Effective Breadth Check

## Answer first

Nominal active risky assets: **{len(RISK_ASSETS_EX_CASH)}**  
Analyzed common-window assets: **{correlation.shape[0]}**  
Common-window effective breadth: **{effective_n:.2f}**  
Effective ratio (analyzed N denominator): **{effective_n / correlation.shape[0]:.1%}**

Structural redundancy candidates:
{chr(10).join(structural_lines)}

High-overlap but economically distinct (diagnostic only):
{chr(10).join(high_lines)}

Short-history assets:
{chr(10).join(short_lines)}

Unresolved benchmark mappings:
{chr(10).join(unresolved_lines)}

**NO ASSET WAS AUTOMATICALLY REMOVED.**

## Scope and interpretation

This is a statistical redundancy diagnostic, not M2, a universe freeze, a vehicle-selection exercise, or a performance claim. It uses native index/spot levels only; no ETF prices, profitability metrics, forward-filled cross-market prices, artificial zero returns, or return-based asset selection are used. `N_eff` is descriptive and is not an optimal asset count.

All histories are `HISTORICAL_LATEST`: the provider snapshot retrieved now may contain current corrected history and does not prove historical publication vintages. Metadata: retrieval cutoff **{cutoff.isoformat()}**, data retrieved at **{retrieved_at}**, source baseline Git commit **{git_commit}**, benchmark mapping SHA-256 **{mapping_hash}**. The containing U1 artifact commit is reported at handoff because a Git object cannot self-reference its own final hash.

## 1. Benchmark mapping

{chr(10).join(mapping_lines)}

The exact audited snapshot is in `benchmark_registry_snapshot.yaml`. Official mapping references:

{chr(10).join(source_lines)}

## 2. Coverage and data quality

`coverage.csv` reports first/last valid date and observation count. Warnings are preserved rather than silently cleaned:

{chr(10).join(warning_lines)}

Unresolved assets remain part of the nominal candidate universe but cannot enter numeric matrices. CASH is excluded from EX_CASH because no real cash-return series is available; no zero-return proxy was manufactured. OIL remains inactive, `INDEX_ONLY / NON_EXECUTABLE`, and is excluded.

## 3. Common window

The common daily-return window is **{common.index.min().date().isoformat()} to {common.index.max().date().isoformat()}**, with **{len(common)}** date-level intersection observations across **{correlation.shape[0]}** analyzable EX_CASH assets. No asset was dropped merely to lengthen this window.

## 4. Pairwise maximum-history correlations

`pairwise_correlations.csv` contains daily primary and weekly robustness results. Each pair uses only its own shared valid dates and records start, end, and n. Redundancy bands use raw rho; negative correlation is never treated as redundancy through `abs(rho)`.

## 5. Rolling correlations

`rolling_pair_correlations.csv` provides 252- and 756-observation statistics for required focus pairs and GOLD-versus-risk-asset comparisons. Unresolved pairs are explicitly `UNAVAILABLE`; insufficient windows are `SKIPPED_SHORT_HISTORY`.

## 6. Clustering

Average linkage is computed from daily common-window correlation distance `sqrt(0.5 * (1-rho))`. Cluster order: **{', '.join(cluster_order)}**. The exact merge rows are in `cluster_linkage.csv`; see `dendrogram.png` and `correlation_heatmap.png`.

## 7. Eigenvalue spectrum

The descending eigenvalues are in `eigenvalues.csv`. Largest eigenvalue: **{eigenvalues[0]:.3f}**; sum: **{eigenvalues.sum():.3f}** (equal to analyzed N within numeric precision).

## 8. Participation ratio

EX_CASH common-window `N_eff = N^2 / sum(lambda_i^2)` is **{effective_n:.2f}** for analyzed N={correlation.shape[0]}, ratio **{effective_n / correlation.shape[0]:.1%}**. The nominal active risky count remains {len(RISK_ASSETS_EX_CASH)}; unresolved mappings explain the gap between nominal and analyzed N.

Rolling 756-observation effective breadth: **{rolling_summary}**.

## 9. Required focus pairs

{chr(10).join(focus_lines)}

GOLD versus available risk assets:

{chr(10).join(gold_lines)}

## 10. Unresolved benchmark/data issues

{chr(10).join(unresolved_lines)}

These are evidence gaps, not rejection decisions. SEMI was not replaced by an ETF or name-similar index. BOND_LONG and BOND_MED were not approximated with yield changes. CASH was not assigned zero returns.

## 11. Purely diagnostic conclusion

Nominal active risky assets: {len(RISK_ASSETS_EX_CASH)}

Common-window effective breadth: {effective_n:.2f}

Effective ratio: {effective_n / correlation.shape[0]:.1%} of analyzed N ({correlation.shape[0]}); nominal-universe coverage is separately reported.

Structural redundancy candidates:
{chr(10).join(structural_lines)}

High-overlap but economically distinct:
{chr(10).join(high_lines)}

Short-history assets:
{chr(10).join(short_lines)}

Unresolved benchmark mappings:
{chr(10).join(unresolved_lines)}

NO ASSET WAS AUTOMATICALLY REMOVED.
"""
    (output / "report.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run explicit real-data U1 universe diagnostic")
    parser.add_argument("--registry", type=Path, default=Path("configs/logical_asset_benchmarks_candidate.yaml"))
    parser.add_argument("--output", type=Path, default=Path("reports/universe_diagnostic_u1"))
    parser.add_argument("--cache", type=Path, default=Path("data/raw/research/universe_diagnostic_u1"))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2000, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--refresh", action="store_true", help="Ignore cached snapshots and call providers")
    args = parser.parse_args()

    registry_payload, registry = load_benchmark_registry(args.registry)
    args.output.mkdir(parents=True, exist_ok=True)
    longbridge: LongbridgeResearchBenchmarkProvider | None = None
    akshare = AkShareResearchBenchmarkProvider()
    levels: dict[str, pd.Series] = {}
    provenance: dict[str, dict[str, str]] = {}
    warnings: list[str] = []

    for candidate in registry:
        if not candidate.active or candidate.status != "RESOLVED" or candidate.logical_asset_id == "CASH":
            continue
        cache_path = _cache_path(args.cache, candidate.logical_asset_id)
        if args.refresh or not cache_path.exists():
            if candidate.provider == "longbridge" and longbridge is None:
                longbridge = LongbridgeResearchBenchmarkProvider(LongbridgeClient.from_env())
            observations = _download(
                candidate,
                start=args.start,
                end=args.end,
                longbridge=longbridge,
                akshare=akshare,
            )
            if not observations:
                warnings.append(f"{candidate.logical_asset_id}: provider returned no observations")
                continue
            _save_raw_cache(cache_path, observations)
        series, metadata = _load_cached_levels(cache_path)
        series = series.loc[(series.index.date >= args.start) & (series.index.date <= args.end)]
        warnings.extend(validate_levels(series, asset_id=candidate.logical_asset_id))
        levels[candidate.logical_asset_id] = series
        provenance[candidate.logical_asset_id] = metadata

    returns_daily = ex_cash({name: simple_returns(series) for name, series in levels.items()})
    returns_weekly = ex_cash({name: weekly_returns(series) for name, series in levels.items()})
    if len(returns_daily) < 2:
        raise RuntimeError("U1 requires at least two resolved risk-asset histories")

    coverage_rows: list[dict[str, Any]] = []
    for candidate in registry:
        if not candidate.active:
            continue
        series = levels.get(candidate.logical_asset_id)
        if series is None:
            coverage_rows.append(
                {
                    "logical_asset_id": candidate.logical_asset_id,
                    "status": candidate.status,
                    "benchmark_symbol": candidate.benchmark_symbol,
                    "provider": candidate.provider,
                    "currency": candidate.currency,
                    "timezone": candidate.timezone,
                    "benchmark_type": candidate.benchmark_type,
                    "first_valid_date": None,
                    "last_valid_date": None,
                    "n_daily_obs": 0,
                    "history_flag": "UNRESOLVED" if candidate.status == "UNRESOLVED" else "NO_DATA",
                }
            )
            continue
        coverage_rows.append(
            {
                "logical_asset_id": candidate.logical_asset_id,
                "status": "ANALYZED" if candidate.logical_asset_id != "CASH" else "EXCLUDED_EX_CASH",
                "benchmark_symbol": candidate.benchmark_symbol,
                "provider": candidate.provider,
                "currency": candidate.currency,
                "timezone": candidate.timezone,
                "benchmark_type": candidate.benchmark_type,
                "first_valid_date": series.index.min().date().isoformat(),
                "last_valid_date": series.index.max().date().isoformat(),
                "n_daily_obs": len(series),
                "history_flag": history_flag(series.index.min().date(), series.index.max().date()),
            }
        )
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(args.output / "coverage.csv", index=False)

    pairwise_daily = pairwise_correlation_rows(returns_daily, frequency="DAILY")
    pairwise_weekly = pairwise_correlation_rows(returns_weekly, frequency="WEEKLY")
    pairwise = pd.concat([pairwise_daily, pairwise_weekly], ignore_index=True)
    pairwise["redundancy_band"] = pairwise["pearson_correlation"].map(redundancy_band)
    pairwise.to_csv(args.output / "pairwise_correlations.csv", index=False)
    pairwise_daily = pairwise[pairwise["frequency"] == "DAILY"].copy()

    common = common_window_frame(returns_daily)
    if len(common) < 2:
        raise RuntimeError("common-window intersection has fewer than two observations")
    correlation = common.corr()
    correlation.to_csv(args.output / "common_window_correlation.csv", index_label="logical_asset_id")
    n_eff, eigenvalues = participation_ratio(correlation)
    pd.DataFrame(
        {"rank": range(1, len(eigenvalues) + 1), "eigenvalue": eigenvalues, "explained_share": eigenvalues / eigenvalues.sum()}
    ).to_csv(args.output / "eigenvalues.csv", index=False)
    pd.DataFrame(
        [
            {
                "universe": "EX_CASH",
                "candidate_active_risky_N": len(RISK_ASSETS_EX_CASH),
                "nominal_N": correlation.shape[0],
                "common_start_date": common.index.min().date().isoformat(),
                "common_end_date": common.index.max().date().isoformat(),
                "n_common_obs": len(common),
                "effective_N": n_eff,
                "effective_ratio": n_eff / correlation.shape[0],
                "historical_data_semantics": "HISTORICAL_LATEST",
            }
        ]
    ).to_csv(args.output / "effective_breadth.csv", index=False)

    focus = _focus_pairs(returns_daily)
    rolling_pairs = rolling_pair_statistics(returns_daily, focus)
    rolling_pairs.to_csv(args.output / "rolling_pair_correlations.csv", index=False)
    rolling_breadth = rolling_effective_breadth(common)
    if rolling_breadth.empty:
        pd.DataFrame(
            [{"status": "SKIPPED", "reason": "fewer than 756 common-window observations", "window": 756}]
        ).to_csv(args.output / "rolling_effective_breadth.csv", index=False)
    else:
        pd.DataFrame(
            {
                "window_end": rolling_breadth.index.date,
                "effective_N": rolling_breadth.values,
                "analyzed_N": correlation.shape[0],
                "effective_ratio": rolling_breadth.values / correlation.shape[0],
            }
        ).to_csv(args.output / "rolling_effective_breadth.csv", index=False)

    distance = correlation_distance_matrix(correlation)
    linkage, order = average_linkage(distance)
    linkage_frame = pd.DataFrame(linkage, columns=["cluster_1", "cluster_2", "distance", "member_count"])
    linkage_frame.insert(0, "step", range(1, len(linkage_frame) + 1))
    linkage_frame["new_cluster_id"] = range(len(correlation), 2 * len(correlation) - 1)
    cluster_members: dict[int, list[str]] = {i: [name] for i, name in enumerate(correlation.index)}
    left_members: list[str] = []
    right_members: list[str] = []
    new_members: list[str] = []
    for row in linkage_frame.itertuples():
        left_id, right_id, new_id = int(row.cluster_1), int(row.cluster_2), int(row.new_cluster_id)
        left_members.append("|".join(cluster_members[left_id]))
        right_members.append("|".join(cluster_members[right_id]))
        cluster_members[new_id] = cluster_members[left_id] + cluster_members[right_id]
        new_members.append("|".join(cluster_members[new_id]))
    linkage_frame["cluster_1_members"] = left_members
    linkage_frame["cluster_2_members"] = right_members
    linkage_frame["new_cluster_members"] = new_members
    linkage_frame.to_csv(args.output / "cluster_linkage.csv", index=False)
    _plot_heatmap(correlation, order, args.output / "correlation_heatmap.png")
    _plot_dendrogram(linkage, list(correlation.index), args.output / "dendrogram.png")

    retrieved_at = max((item["retrieved_at"] for item in provenance.values()), default=datetime.now(UTC).isoformat())
    snapshot = dict(registry_payload)
    snapshot.update(
        {
            "data_retrieved_at": retrieved_at,
            "dataset_cutoff": args.end.isoformat(),
            "source_baseline_git_commit": _git_commit(),
            "artifact_git_commit": "SEE_CONTAINING_COMMIT",
            "providers_used": sorted({item["provider"] for item in provenance.values()}),
            "historical_data_semantics": "HISTORICAL_LATEST",
            "source_provenance": provenance,
        }
    )
    (args.output / "benchmark_registry_snapshot.yaml").write_text(
        yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (args.output / "data_quality.json").write_text(
        json.dumps(
            {
                "status": "PASS_WITH_WARNINGS" if warnings else "PASS",
                "checks": {
                    "duplicate_dates": "PASS",
                    "monotonic_dates": "PASS",
                    "positive_levels": "PASS",
                    "impossible_returns_over_50pct": "PASS",
                    "missing_blocks_over_14_calendar_days": "WARNING" if warnings else "PASS",
                    "timezone_date_conversion": "PASS_EXPLICIT_REGISTRY_TIMEZONE",
                },
                "warnings": warnings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _build_report(
        output=args.output,
        registry=registry,
        coverage=coverage,
        pairwise_daily=pairwise_daily,
        common=common,
        correlation=correlation,
        eigenvalues=eigenvalues,
        effective_n=n_eff,
        rolling_pairs=rolling_pairs,
        rolling_breadth=rolling_breadth,
        cluster_order=order,
        mapping_hash=registry_payload["mapping_sha256"],
        retrieved_at=retrieved_at,
        cutoff=args.end,
        git_commit=_git_commit(),
        warnings=warnings,
    )
    print(f"U1 complete: analyzed_N={correlation.shape[0]} common_obs={len(common)} N_eff={n_eff:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
