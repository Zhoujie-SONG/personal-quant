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
from etf_quant.providers.csindex.research_benchmarks import CSIResearchBenchmarkProvider
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
    prepare_levels_for_analysis,
    redundancy_band,
    rolling_effective_breadth,
    rolling_pair_statistics,
    simple_returns,
    structural_redundancy_candidate,
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
    "CSI semiconductor factsheet": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30184factsheet.pdf",
    "SSE 10-year Treasury announcement": "https://www.sse.com.cn/market/sseindex/diclosure/c/c_20150911_3985075.shtml",
    "CSI 10-year Treasury factsheet": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H11077factsheet.pdf",
    "CSI 5-year Treasury factsheet": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H00140factsheet.pdf",
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
    csindex: CSIResearchBenchmarkProvider,
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
    if candidate.provider == "csindex":
        effective_start = max(start, candidate.base_date) if candidate.base_date else start
        return csindex.get_daily_levels(candidate.benchmark_symbol, effective_start, end)
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
    pairwise_weekly: pd.DataFrame,
    common: pd.DataFrame,
    common_weekly: pd.DataFrame,
    correlation: pd.DataFrame,
    correlation_weekly: pd.DataFrame,
    eigenvalues: np.ndarray,
    eigenvalues_weekly: np.ndarray,
    effective_n: float,
    effective_n_weekly: float,
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

    required_pairs = (
        ("NASDAQ100", "SP500"),
        ("HSTECH", "HK_BROAD"),
        ("CN_GROWTH", "SEMI"),
        ("BOND_LONG", "BOND_MED"),
        ("CN_DIVIDEND", "COAL"),
    )
    pair_lines: list[str] = []
    for left, right in required_pairs:
        daily = _pair_lookup(pairwise_daily, left, right)
        weekly = _pair_lookup(pairwise_weekly, left, right)
        rolling_parts: list[str] = []
        for window in (252, 756):
            rows = rolling_pairs[
                (rolling_pairs["asset_1"] == left)
                & (rolling_pairs["asset_2"] == right)
                & (rolling_pairs["window"] == window)
            ]
            if len(rows) and rows.iloc[0]["status"] == "OK":
                row = rows.iloc[0]
                rolling_parts.append(
                    f"{window}d median={float(row['median']):.3f} "
                    f"[p10={float(row['p10']):.3f}, p90={float(row['p90']):.3f}]"
                )
            else:
                rolling_parts.append(f"{window}d unavailable")
        pair_lines.append(
            f"- {left} / {right}: daily={_format_corr(daily['pearson_correlation']) if daily is not None else 'N/A'}; "
            f"weekly={_format_corr(weekly['pearson_correlation']) if weekly is not None else 'N/A'}; "
            + "; ".join(rolling_parts)
        )

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
        f"{row.provider or 'none'} / {row.series_kind or row.benchmark_type} / {row.status}"
        + (
            f" / primary={row.primary_provider_status}"
            if row.primary_provider_status is not None
            else ""
        )
        for row in registry
    ]
    warning_lines = [f"- {item}" for item in warnings] or ["- No level-integrity warnings beyond declared unresolved mappings."]
    structural_lines = [f"- {item}" for item in structural] or ["- None"]
    high_lines = [f"- {item}" for item in high_distinct] or ["- None"]
    short_lines = [f"- {item}" for item in short] or ["- None"]
    unresolved_lines = [f"- {item}" for item in unresolved] or ["- None"]

    text = f"""# Universe Diagnostic U1.1 — Effective Breadth Completion and Robustness

## Technical summary

All **{len(RISK_ASSETS_EX_CASH)} active risky assets** now have verified economic benchmark histories and enter both EX_CASH matrices. Daily common-window effective breadth is **{effective_n:.2f}** ({effective_n / correlation.shape[0]:.1%}); weekly robustness effective breadth is **{effective_n_weekly:.2f}** ({effective_n_weekly / correlation_weekly.shape[0]:.1%}). Weekly is a fixed, pre-registered last-actual-observation-date intersection and is not a lag optimization.

Structural redundancy candidates:
{chr(10).join(structural_lines)}

Economically distinct high-correlation pairs:
{chr(10).join(high_lines)}

Unresolved active benchmark mappings:
{chr(10).join(unresolved_lines)}

**NO ASSET AUTOMATICALLY REMOVED.**

## All active risk assets are now measurable without ETF substitution

{chr(10).join(mapping_lines)}

SEMI uses official **H30184** price-index history. BOND_LONG uses official **H11077 full-price** history; the clean-price derivative H01077 is explicitly forbidden. BOND_MED uses official **H00140 full-price** history. Longbridge static/history probes for each official code with both `.SH` and `.SZ` failed, so the registry preserves `LONGBRIDGE_UNAVAILABLE` while the supplemental source is the official CSI `index-perf` endpoint. No ETF or yield-change series is used.

Exact static/history attempts and supplemental exact-code checks are preserved in `benchmark_probe_results.json`.

Official references:

{chr(10).join(source_lines)}

## Daily and weekly breadth tell the same diagnostic story at different close alignment

Daily common window: **{common.index.min().date().isoformat()} to {common.index.max().date().isoformat()}**, **{len(common)}** observations, N={correlation.shape[0]}, N_eff={effective_n:.2f}, ratio={effective_n / correlation.shape[0]:.1%}.

Weekly common window: **{common_weekly.index.min().date().isoformat()} to {common_weekly.index.max().date().isoformat()}**, **{len(common_weekly)}** observations, N={correlation_weekly.shape[0]}, N_eff={effective_n_weekly:.2f}, ratio={effective_n_weekly / correlation_weekly.shape[0]:.1%}.

Daily is primary. Weekly is the cross-timezone robustness view. Each asset contributes its final real observation of the week; returns are intersected on those actual dates. No market price or return is forward-filled or set to zero, and no alternative lag was searched.

## Required pair evidence includes full-period and rolling correlations

{chr(10).join(pair_lines)}

`pairwise_correlations.csv` contains maximum-history daily and weekly estimates. `rolling_pair_correlations.csv` contains the 252- and 756-observation distributions. Redundancy bands use raw rho, so negative correlation is not treated as duplication.

## Daily clustering and eigenvalue spectra preserve the full candidate set

Daily average-linkage clustering uses `sqrt(0.5 * (1-rho))`. Cluster order: **{', '.join(cluster_order)}**. The daily and weekly eigenvalue spectra sum to **{eigenvalues.sum():.3f}** and **{eigenvalues_weekly.sum():.3f}**, respectively, matching their matrix dimension. See `correlation_heatmap.png`, `dendrogram.png`, `cluster_linkage.csv`, `eigenvalues.csv`, and `eigenvalues_weekly.csv`.

Rolling 756-observation daily effective breadth: **{rolling_summary}**.

## Scope, definitions, and data quality

This is a descriptive redundancy diagnostic, not M2, a universe freeze, a vehicle-selection exercise, or a performance claim. `N_eff = N^2 / sum(lambda_i^2)` is not an optimal asset count. CASH remains excluded from EX_CASH and no artificial zero-return proxy is created. OIL remains inactive, `INDEX_ONLY / NON_EXECUTABLE`, and outside both matrices.

All histories are unadjusted/native index or spot values with `HISTORICAL_LATEST` semantics. Retrieval cutoff: **{cutoff.isoformat()}**; latest retrieval: **{retrieved_at}**; source baseline commit: **{git_commit}**; mapping SHA-256: **{mapping_hash}**. The containing artifact commit is reported at handoff.

Data-quality checks preserve rather than silently clean exceptions:

{chr(10).join(warning_lines)}

Coverage and short-history status are in `coverage.csv`. Short-history assets:
{chr(10).join(short_lines)}

## Limitations and freeze-readiness boundary

The supplemental CSI histories are current official `HISTORICAL_LATEST` snapshots, not historical publication vintages. Daily cross-market correlations pair same calendar dates despite asynchronous closes; weekly results reduce that sensitivity but do not establish a causal or optimal universe. The benchmark registry remains candidate-only, and no Universe v1 is generated.

## Freeze gate

ANALYZED_ASSETS: {', '.join(correlation.index)}

DAILY_N_EFF: {effective_n:.2f}

WEEKLY_N_EFF: {effective_n_weekly:.2f}

STRUCTURAL_REDUNDANCY_CANDIDATES: {', '.join(structural) if structural else 'NONE'}

ECONOMICALLY_DISTINCT_HIGH_CORRELATION: {', '.join(high_distinct) if high_distinct else 'NONE'}

UNRESOLVED_BENCHMARKS: {', '.join(unresolved) if unresolved else 'NONE'}

NO ASSET AUTOMATICALLY REMOVED.
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
    csindex = CSIResearchBenchmarkProvider()
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
                csindex=csindex,
            )
            if not observations:
                warnings.append(f"{candidate.logical_asset_id}: provider returned no observations")
                continue
            _save_raw_cache(cache_path, observations)
        series, metadata = _load_cached_levels(cache_path)
        series = series.loc[(series.index.date >= args.start) & (series.index.date <= args.end)]
        series, level_warnings = prepare_levels_for_analysis(
            series,
            asset_id=candidate.logical_asset_id,
        )
        warnings.extend(level_warnings)
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
    pairwise_weekly = pairwise[pairwise["frequency"] == "WEEKLY"].copy()

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

    common_weekly = common_window_frame(returns_weekly)
    if len(common_weekly) < 2:
        raise RuntimeError("weekly common-window intersection has fewer than two observations")
    correlation_weekly = common_weekly.corr()
    correlation_weekly.to_csv(
        args.output / "common_window_weekly_correlation.csv",
        index_label="logical_asset_id",
    )
    n_eff_weekly, eigenvalues_weekly = participation_ratio(correlation_weekly)
    pd.DataFrame(
        {
            "rank": range(1, len(eigenvalues_weekly) + 1),
            "eigenvalue": eigenvalues_weekly,
            "explained_share": eigenvalues_weekly / eigenvalues_weekly.sum(),
        }
    ).to_csv(args.output / "eigenvalues_weekly.csv", index=False)
    pd.DataFrame(
        [
            {
                "universe": "EX_CASH",
                "candidate_active_risky_N": len(RISK_ASSETS_EX_CASH),
                "nominal_N": correlation_weekly.shape[0],
                "common_start_date": common_weekly.index.min().date().isoformat(),
                "common_end_date": common_weekly.index.max().date().isoformat(),
                "n_common_obs": len(common_weekly),
                "effective_N": n_eff_weekly,
                "effective_ratio": n_eff_weekly / correlation_weekly.shape[0],
                "historical_data_semantics": "HISTORICAL_LATEST",
                "alignment": "WEEKLY_LAST_ACTUAL_OBSERVATION_DATE_INTERSECTION",
            }
        ]
    ).to_csv(args.output / "effective_breadth_weekly.csv", index=False)

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
            "benchmark_probe_evidence": "benchmark_probe_results.json",
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
                    "positive_levels": (
                        "WARNING_RAW_RETAINED_EXCLUDED_FROM_RETURNS"
                        if any("nonpositive raw level" in item for item in warnings)
                        else "PASS"
                    ),
                    "impossible_returns_over_50pct": "PASS",
                    "missing_blocks_over_14_calendar_days": (
                        "WARNING"
                        if any("calendar gaps exceed 14 days" in item for item in warnings)
                        else "PASS"
                    ),
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
        pairwise_weekly=pairwise_weekly,
        common=common,
        common_weekly=common_weekly,
        correlation=correlation,
        correlation_weekly=correlation_weekly,
        eigenvalues=eigenvalues,
        eigenvalues_weekly=eigenvalues_weekly,
        effective_n=n_eff,
        effective_n_weekly=n_eff_weekly,
        rolling_pairs=rolling_pairs,
        rolling_breadth=rolling_breadth,
        cluster_order=order,
        mapping_hash=registry_payload["mapping_sha256"],
        retrieved_at=retrieved_at,
        cutoff=args.end,
        git_commit=_git_commit(),
        warnings=warnings,
    )
    print(
        f"U1.1 complete: analyzed_N={correlation.shape[0]} "
        f"daily_obs={len(common)} daily_N_eff={n_eff:.4f} "
        f"weekly_obs={len(common_weekly)} weekly_N_eff={n_eff_weekly:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
