from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from etf_quant.research.universe_diagnostic import (
    OfficialSymbolProbeAttempt,
    common_window_frame,
    correlation_distance,
    evaluate_official_symbol_probe,
    ex_cash,
    history_flag,
    load_benchmark_registry,
    pairwise_correlation_rows,
    pairwise_overlap,
    participation_ratio,
    prepare_levels_for_analysis,
    redundancy_band,
    simple_returns,
    structural_redundancy_candidate,
    weekly_returns,
)


def test_return_alignment_excludes_missing_dates() -> None:
    left = pd.Series([0.1, 0.2, 0.3], index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]))
    right = pd.Series([0.4, 0.5], index=pd.to_datetime(["2020-01-02", "2020-01-06"]))

    overlap = pairwise_overlap(left, right)

    assert list(overlap.index.strftime("%Y-%m-%d")) == ["2020-01-02", "2020-01-06"]


def test_simple_returns_does_not_zero_fill_missing_prices() -> None:
    levels = pd.Series(
        [100.0, np.nan, 110.0, 121.0],
        index=pd.date_range("2020-01-01", periods=4),
    )

    returns = simple_returns(levels)

    assert list(returns.index) == [pd.Timestamp("2020-01-04")]
    assert returns.iloc[0] == pytest.approx(0.1)
    assert not (returns == 0).any()


def test_nonpositive_official_level_is_explicitly_missing_not_bridged() -> None:
    levels = pd.Series(
        [100.0, 0.0, 110.0, 121.0],
        index=pd.date_range("2020-01-01", periods=4),
    )

    prepared, warnings = prepare_levels_for_analysis(levels, asset_id="SEMI")
    returns = simple_returns(prepared)

    assert pd.isna(prepared.iloc[1])
    assert list(returns.index) == [pd.Timestamp("2020-01-04")]
    assert "2020-01-02" in warnings[0]


def test_weekly_returns_use_last_actual_observation_date_and_preserve_missing_week() -> None:
    levels = pd.Series(
        [100.0, 105.0, 110.0, 121.0],
        index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-09", "2020-01-24"]),
    )

    returns = weekly_returns(levels)

    assert list(returns.index) == [pd.Timestamp("2020-01-09")]
    assert returns.iloc[0] == pytest.approx(110.0 / 105.0 - 1.0)


def test_weekly_common_window_aligns_only_last_actual_observation_dates() -> None:
    left_levels = pd.Series(
        [100.0, 110.0, 121.0],
        index=pd.to_datetime(["2020-01-03", "2020-01-09", "2020-01-17"]),
    )
    right_levels = pd.Series(
        [200.0, 220.0, 242.0],
        index=pd.to_datetime(["2020-01-03", "2020-01-10", "2020-01-17"]),
    )

    common = common_window_frame(
        {"LEFT": weekly_returns(left_levels), "RIGHT": weekly_returns(right_levels)}
    )

    assert list(common.index) == [pd.Timestamp("2020-01-17")]
    assert pd.Timestamp("2020-01-10") not in common.index


def test_pairwise_max_history_uses_only_pair_overlap_dates() -> None:
    left = pd.Series([0.1, 0.2, 0.4], index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]))
    right = pd.Series([0.3, 0.6, 0.8], index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-04"]))

    row = pairwise_correlation_rows({"A": left, "B": right}, frequency="DAILY").iloc[0]

    assert row["start_date"] == "2020-01-02"
    assert row["end_date"] == "2020-01-03"
    assert row["n_obs"] == 2
    assert row["pearson_correlation"] == pytest.approx(1.0)


def test_participation_ratio_known_synthetic_matrix() -> None:
    correlation = np.array([[1.0, 0.5], [0.5, 1.0]])

    effective_n, eigenvalues = participation_ratio(correlation)

    assert eigenvalues == pytest.approx([1.5, 0.5])
    assert effective_n == pytest.approx(1.6)


def test_identity_correlation_gives_nominal_effective_breadth() -> None:
    effective_n, _ = participation_ratio(np.eye(5))
    assert effective_n == pytest.approx(5.0)


def test_perfect_positive_correlation_gives_one_effective_asset() -> None:
    effective_n, _ = participation_ratio(np.ones((4, 4)))
    assert effective_n == pytest.approx(1.0)


def test_weekly_participation_ratio_uses_weekly_common_matrix() -> None:
    index = pd.to_datetime(["2020-01-03", "2020-01-10", "2020-01-17", "2020-01-24"])
    weekly = pd.DataFrame(
        {"A": [0.01, -0.02, 0.03, -0.01], "B": [-0.01, -0.02, -0.03, -0.01]},
        index=index,
    )

    effective_n, eigenvalues = participation_ratio(weekly.corr())

    assert eigenvalues.sum() == pytest.approx(2.0)
    assert 1.0 <= effective_n <= 2.0


def test_negative_correlation_is_not_flagged_as_redundancy() -> None:
    assert redundancy_band(-0.95) == "LOW_MODERATE"
    assert structural_redundancy_candidate(-0.95, -0.90) is False


def test_cash_is_excluded_from_ex_cash_without_manufacturing_returns() -> None:
    values = pd.Series([0.1])
    result = ex_cash({"CN_LARGE": values, "CASH": pd.Series([0.0])})
    assert set(result) == {"CN_LARGE"}


@pytest.mark.parametrize(
    ("rho", "expected"),
    [(1.0, 0.0), (0.0, np.sqrt(0.5)), (-1.0, 1.0)],
)
def test_clustering_distance_formula(rho: float, expected: float) -> None:
    assert correlation_distance(rho) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("first_date", "last_date", "expected"),
    [
        (date(2024, 1, 1), date(2026, 1, 1), "VERY_SHORT_HISTORY"),
        (date(2022, 1, 1), date(2026, 1, 1), "SHORT_HISTORY"),
        (date(2019, 1, 1), date(2026, 1, 1), "OK"),
    ],
)
def test_short_history_flag(first_date: date, last_date: date, expected: str) -> None:
    assert history_flag(first_date, last_date) == expected


def test_unresolved_registry_does_not_silently_substitute_etf() -> None:
    path = Path("configs/logical_asset_benchmarks_candidate.yaml")
    _, candidates = load_benchmark_registry(path)
    cash = next(item for item in candidates if item.logical_asset_id == "CASH")

    assert cash.status == "UNRESOLVED"
    assert cash.benchmark_symbol is None
    assert cash.provider is None
    assert all(item.benchmark_type != "ETF" for item in candidates)


def test_unavailable_official_symbol_probe_cannot_silently_resolve() -> None:
    decision = evaluate_official_symbol_probe(
        "H30184",
        [
            OfficialSymbolProbeAttempt("H30184.SH", False, False),
            OfficialSymbolProbeAttempt("H30184.SZ", False, False),
        ],
    )

    assert decision.status == "LONGBRIDGE_UNAVAILABLE"
    assert decision.resolved_symbol is None


@pytest.mark.parametrize(
    ("symbol", "series_kind", "message"),
    [
        ("H11077", "YIELD_SERIES", "requires FULL_PRICE_INDEX"),
        ("H01077", "FULL_PRICE_INDEX", "clean-price index"),
    ],
)
def test_bond_benchmark_rejects_yield_and_clean_price_substitutions(
    tmp_path: Path,
    symbol: str,
    series_kind: str,
    message: str,
) -> None:
    registry = tmp_path / "bond_registry.yaml"
    registry.write_text(
        f"""benchmarks:
  - logical_asset_id: BOND_LONG
    benchmark_name: invalid bond proxy
    benchmark_symbol: {symbol}
    provider: csindex
    currency: CNY
    timezone: Asia/Shanghai
    benchmark_type: INDEX
    series_kind: {series_kind}
    index_launch_date: 2013-03-07
    base_date: 2008-12-31
    known_backfilled_history: true
    status: RESOLVED
    notes: must fail
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_benchmark_registry(registry)


def test_registry_rejects_etf_benchmark_type(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """benchmarks:
  - logical_asset_id: SEMI
    benchmark_name: forbidden vehicle
    benchmark_symbol: 512480.SH
    provider: longbridge
    currency: CNY
    timezone: Asia/Shanghai
    benchmark_type: ETF
    index_launch_date: null
    known_backfilled_history: false
    status: RESOLVED
    notes: must fail
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="forbidden benchmark_type"):
        load_benchmark_registry(registry)
