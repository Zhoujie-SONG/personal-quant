from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from etf_quant.research.universe_diagnostic import (
    correlation_distance,
    ex_cash,
    history_flag,
    load_benchmark_registry,
    pairwise_correlation_rows,
    pairwise_overlap,
    participation_ratio,
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


def test_weekly_returns_use_last_actual_observation_date_and_preserve_missing_week() -> None:
    levels = pd.Series(
        [100.0, 105.0, 110.0, 121.0],
        index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-09", "2020-01-24"]),
    )

    returns = weekly_returns(levels)

    assert list(returns.index) == [pd.Timestamp("2020-01-09")]
    assert returns.iloc[0] == pytest.approx(110.0 / 105.0 - 1.0)


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
    semi = next(item for item in candidates if item.logical_asset_id == "SEMI")

    assert semi.status == "UNRESOLVED"
    assert semi.benchmark_symbol is None
    assert semi.provider is None
    assert all(item.benchmark_type != "ETF" for item in candidates)


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
