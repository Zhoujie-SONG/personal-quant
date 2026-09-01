from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import yaml


ACTIVE_LOGICAL_ASSETS = (
    "CN_LARGE", "CN_SMALL", "CN_GROWTH", "CN_DIVIDEND", "SEMI",
    "HEALTHCARE", "CONSUMER", "COAL", "NASDAQ100", "SP500", "HSTECH",
    "HK_BROAD", "GOLD", "BOND_LONG", "BOND_MED", "CASH",
)
RISK_ASSETS_EX_CASH = tuple(x for x in ACTIVE_LOGICAL_ASSETS if x != "CASH")
ALLOWED_BENCHMARK_TYPES = {"INDEX", "SPOT", "CASH_PROXY"}


@dataclass(frozen=True, slots=True)
class BenchmarkCandidate:
    logical_asset_id: str
    benchmark_name: str
    benchmark_symbol: str | None
    provider: str | None
    currency: str | None
    timezone: str | None
    benchmark_type: str
    index_launch_date: date | None
    base_date: date | None
    known_backfilled_history: bool | None
    series_kind: str | None
    status: str
    notes: str
    primary_provider_status: str | None = None
    active: bool = True
    executable: bool = True


@dataclass(frozen=True, slots=True)
class OfficialSymbolProbeAttempt:
    symbol: str
    static_verified: bool
    history_verified: bool
    returned_official_code: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialSymbolProbeDecision:
    status: str
    resolved_symbol: str | None


def evaluate_official_symbol_probe(
    official_code: str,
    attempts: Sequence[OfficialSymbolProbeAttempt],
) -> OfficialSymbolProbeDecision:
    """Resolve only an exact official-code match with both probe gates passed."""
    verified = [
        attempt
        for attempt in attempts
        if attempt.static_verified
        and attempt.history_verified
        and attempt.returned_official_code == official_code
    ]
    if len(verified) == 1:
        return OfficialSymbolProbeDecision("RESOLVED", verified[0].symbol)
    return OfficialSymbolProbeDecision("LONGBRIDGE_UNAVAILABLE", None)


def load_benchmark_registry(path: Path) -> tuple[dict[str, Any], list[BenchmarkCandidate]]:
    raw = path.read_bytes()
    payload = yaml.safe_load(raw) or {}
    rows = payload.get("benchmarks")
    if not isinstance(rows, list):
        raise ValueError("benchmark registry must contain a benchmarks list")
    candidates: list[BenchmarkCandidate] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("every benchmark entry must be a mapping")
        asset_id = str(row["logical_asset_id"])
        if asset_id in seen:
            raise ValueError(f"duplicate logical_asset_id: {asset_id}")
        seen.add(asset_id)
        benchmark_type = str(row["benchmark_type"])
        if benchmark_type not in ALLOWED_BENCHMARK_TYPES:
            raise ValueError(f"forbidden benchmark_type {benchmark_type!r} for {asset_id}")
        status = str(row.get("status", "UNRESOLVED"))
        symbol = row.get("benchmark_symbol")
        provider = row.get("provider")
        if status == "UNRESOLVED" and (symbol is not None or provider is not None):
            raise ValueError(f"UNRESOLVED benchmark {asset_id} cannot carry a provider symbol")
        if status == "RESOLVED" and (not symbol or not provider):
            raise ValueError(f"RESOLVED benchmark {asset_id} requires symbol and provider")
        launch = row.get("index_launch_date")
        base_date = row.get("base_date")
        series_kind = str(row["series_kind"]) if row.get("series_kind") is not None else None
        if asset_id in {"BOND_LONG", "BOND_MED"} and status == "RESOLVED":
            if benchmark_type != "INDEX":
                raise ValueError(f"{asset_id} must use an index benchmark")
            if series_kind not in {"FULL_PRICE_INDEX", "TOTAL_RETURN_INDEX"}:
                raise ValueError(
                    f"{asset_id} requires FULL_PRICE_INDEX or TOTAL_RETURN_INDEX; "
                    "yield series and clean-price substitutions are forbidden"
                )
            if str(symbol).upper() == "H01077":
                raise ValueError("H01077 is the clean-price index and is forbidden for BOND_LONG")
        candidates.append(
            BenchmarkCandidate(
                logical_asset_id=asset_id,
                benchmark_name=str(row["benchmark_name"]),
                benchmark_symbol=str(symbol) if symbol is not None else None,
                provider=str(provider) if provider is not None else None,
                currency=str(row["currency"]) if row.get("currency") is not None else None,
                timezone=str(row["timezone"]) if row.get("timezone") is not None else None,
                benchmark_type=benchmark_type,
                index_launch_date=date.fromisoformat(str(launch)) if launch else None,
                base_date=date.fromisoformat(str(base_date)) if base_date else None,
                known_backfilled_history=row.get("known_backfilled_history"),
                series_kind=series_kind,
                status=status,
                notes=str(row.get("notes", "")),
                primary_provider_status=(
                    str(row["primary_provider_status"])
                    if row.get("primary_provider_status") is not None
                    else None
                ),
                active=bool(row.get("active", True)),
                executable=bool(row.get("executable", True)),
            )
        )
    payload["mapping_sha256"] = hashlib.sha256(raw).hexdigest()
    return payload, candidates


def validate_levels(levels: pd.Series, *, asset_id: str) -> list[str]:
    warnings: list[str] = []
    if not isinstance(levels.index, pd.DatetimeIndex):
        raise ValueError(f"{asset_id}: levels require a DatetimeIndex")
    if levels.index.has_duplicates:
        raise ValueError(f"{asset_id}: duplicate dates")
    if not levels.index.is_monotonic_increasing:
        raise ValueError(f"{asset_id}: non-monotonic dates")
    numeric = pd.to_numeric(levels, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{asset_id}: non-numeric or missing index levels")
    if (numeric <= 0).any():
        raise ValueError(f"{asset_id}: zero/negative index levels")
    returns = simple_returns(numeric)
    extreme = returns[returns.abs() > 0.50]
    if not extreme.empty:
        warnings.append(f"{asset_id}: {len(extreme)} daily returns exceed 50% absolute")
    gaps = levels.index.to_series().diff().dt.days.dropna()
    if (gaps > 14).any():
        warnings.append(f"{asset_id}: {int((gaps > 14).sum())} calendar gaps exceed 14 days")
    return warnings


def prepare_levels_for_analysis(
    levels: pd.Series,
    *,
    asset_id: str,
) -> tuple[pd.Series, list[str]]:
    """Preserve raw anomalies as explicit missing values with audit warnings."""
    if not isinstance(levels.index, pd.DatetimeIndex):
        raise ValueError(f"{asset_id}: levels require a DatetimeIndex")
    if levels.index.has_duplicates:
        raise ValueError(f"{asset_id}: duplicate dates")
    if not levels.index.is_monotonic_increasing:
        raise ValueError(f"{asset_id}: non-monotonic dates")
    numeric = pd.to_numeric(levels, errors="coerce")
    if numeric.isna().any():
        raise ValueError(f"{asset_id}: non-numeric or missing raw index levels")
    warnings: list[str] = []
    invalid = numeric <= 0
    if invalid.any():
        dates = ", ".join(numeric.index[invalid].strftime("%Y-%m-%d"))
        warnings.append(
            f"{asset_id}: {int(invalid.sum())} nonpositive raw level(s) set to missing "
            f"for return calculation ({dates}); raw observations retained"
        )
        numeric = numeric.mask(invalid)
    returns = simple_returns(numeric)
    extreme = returns[returns.abs() > 0.50]
    if not extreme.empty:
        warnings.append(f"{asset_id}: {len(extreme)} daily returns exceed 50% absolute")
    gaps = numeric.index.to_series().diff().dt.days.dropna()
    if (gaps > 14).any():
        warnings.append(f"{asset_id}: {int((gaps > 14).sum())} calendar gaps exceed 14 days")
    numeric.name = levels.name
    return numeric, warnings


def simple_returns(levels: pd.Series) -> pd.Series:
    """Calculate simple returns without filling missing prices or returns."""
    numeric = pd.to_numeric(levels, errors="coerce")
    return numeric.pct_change(fill_method=None).dropna()


def weekly_returns(levels: pd.Series) -> pd.Series:
    """Use each asset's last valid observation per Friday-ended week."""
    frame = levels.rename("level").to_frame()
    weekly = frame.resample("W-FRI").agg(
        level=("level", "last"),
        observation_date=("level", lambda values: values.last_valid_index()),
    )
    returns = weekly["level"].pct_change(fill_method=None)
    valid = returns.notna() & weekly["observation_date"].notna()
    return pd.Series(
        returns.loc[valid].to_numpy(),
        index=pd.DatetimeIndex(weekly.loc[valid, "observation_date"]),
        name=levels.name,
    )


def pairwise_overlap(left: pd.Series, right: pd.Series) -> pd.DataFrame:
    return pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()


def pairwise_correlation_rows(
    returns: Mapping[str, pd.Series],
    *,
    frequency: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    names = list(returns)
    for i, left_name in enumerate(names):
        for right_name in names[i + 1:]:
            overlap = pairwise_overlap(returns[left_name], returns[right_name])
            rows.append(
                {
                    "asset_1": left_name,
                    "asset_2": right_name,
                    "frequency": frequency,
                    "start_date": overlap.index.min().date().isoformat() if len(overlap) else None,
                    "end_date": overlap.index.max().date().isoformat() if len(overlap) else None,
                    "n_obs": len(overlap),
                    "pearson_correlation": overlap.iloc[:, 0].corr(overlap.iloc[:, 1]) if len(overlap) >= 2 else np.nan,
                }
            )
    return pd.DataFrame(rows)


def common_window_frame(returns: Mapping[str, pd.Series]) -> pd.DataFrame:
    if not returns:
        return pd.DataFrame()
    return pd.concat(returns, axis=1).dropna(how="any")


def participation_ratio(correlation: pd.DataFrame | np.ndarray) -> tuple[float, np.ndarray]:
    matrix = np.asarray(correlation, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
        raise ValueError("correlation matrix must be non-empty and square")
    if not np.allclose(matrix, matrix.T, atol=1e-10, equal_nan=False):
        raise ValueError("correlation matrix must be symmetric")
    eigenvalues = np.linalg.eigvalsh(matrix)
    eigenvalues[np.abs(eigenvalues) < 1e-12] = 0.0
    n_eff = float(eigenvalues.sum() ** 2 / np.square(eigenvalues).sum())
    return n_eff, eigenvalues[::-1]


def correlation_distance(rho: float) -> float:
    if not -1.0 <= rho <= 1.0:
        raise ValueError("correlation must be in [-1, 1]")
    return math.sqrt(0.5 * (1.0 - rho))


def correlation_distance_matrix(correlation: pd.DataFrame) -> pd.DataFrame:
    clipped = correlation.clip(-1.0, 1.0)
    values = np.sqrt(0.5 * (1.0 - clipped.to_numpy(dtype=float)))
    np.fill_diagonal(values, 0.0)
    return pd.DataFrame(values, index=correlation.index, columns=correlation.columns)


def average_linkage(distance: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Deterministic UPGMA over a precomputed correlation-distance matrix."""
    labels = list(distance.index)
    if labels != list(distance.columns):
        raise ValueError("distance matrix index and columns must match")
    n = len(labels)
    if n < 2:
        return np.empty((0, 4), dtype=float), labels
    base = distance.to_numpy(dtype=float)
    clusters: dict[int, tuple[int, ...]] = {i: (i,) for i in range(n)}
    children: dict[int, tuple[int, int]] = {}
    linkage: list[list[float]] = []
    for step in range(n - 1):
        active = sorted(clusters)
        best: tuple[float, int, int] | None = None
        for pos, left in enumerate(active):
            for right in active[pos + 1:]:
                values = [base[i, j] for i in clusters[left] for j in clusters[right]]
                candidate = (float(np.mean(values)), left, right)
                if best is None or candidate < best:
                    best = candidate
        assert best is not None
        dist, left, right = best
        new_id = n + step
        members = clusters.pop(left) + clusters.pop(right)
        clusters[new_id] = members
        children[new_id] = (left, right)
        linkage.append([float(left), float(right), dist, float(len(members))])

    def leaves(node: int) -> list[int]:
        if node < n:
            return [node]
        left, right = children[node]
        return leaves(left) + leaves(right)

    order = [labels[i] for i in leaves(2 * n - 2)]
    return np.asarray(linkage), order


def redundancy_band(rho: float) -> str:
    if pd.isna(rho):
        return "INSUFFICIENT_DATA"
    if rho < 0.60:
        return "LOW_MODERATE"
    if rho < 0.75:
        return "MODERATE"
    if rho < 0.90:
        return "HIGH"
    return "VERY_HIGH"


def structural_redundancy_candidate(full_rho: float, rolling_3y_median: float) -> bool:
    return bool(full_rho >= 0.90 and rolling_3y_median >= 0.85)


def history_flag(first_date: date, last_date: date) -> str:
    years = (last_date - first_date).days / 365.25
    if years < 3:
        return "VERY_SHORT_HISTORY"
    if years < 5:
        return "SHORT_HISTORY"
    return "OK"


def ex_cash(returns: Mapping[str, pd.Series]) -> dict[str, pd.Series]:
    return {name: series for name, series in returns.items() if name != "CASH"}


def rolling_pair_statistics(
    returns: Mapping[str, pd.Series],
    pairs: Iterable[tuple[str, str]],
    windows: Sequence[int] = (252, 756),
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for left, right in pairs:
        if left not in returns or right not in returns:
            for window in windows:
                rows.append({"asset_1": left, "asset_2": right, "window": window, "status": "UNAVAILABLE"})
            continue
        overlap = pairwise_overlap(returns[left], returns[right])
        for window in windows:
            rolling = overlap["left"].rolling(window).corr(overlap["right"]).dropna()
            if rolling.empty:
                rows.append({"asset_1": left, "asset_2": right, "window": window, "status": "SKIPPED_SHORT_HISTORY"})
                continue
            rows.append(
                {
                    "asset_1": left,
                    "asset_2": right,
                    "window": window,
                    "status": "OK",
                    "n_windows": len(rolling),
                    "first_window_end": rolling.index.min().date().isoformat(),
                    "last_window_end": rolling.index.max().date().isoformat(),
                    "median": rolling.median(),
                    "p10": rolling.quantile(0.10),
                    "p90": rolling.quantile(0.90),
                    "min": rolling.min(),
                    "max": rolling.max(),
                    "latest": rolling.iloc[-1],
                }
            )
    return pd.DataFrame(rows)


def rolling_effective_breadth(common_returns: pd.DataFrame, window: int = 756) -> pd.Series:
    if len(common_returns) < window:
        return pd.Series(dtype=float, name="effective_N")
    values: list[float] = []
    index: list[pd.Timestamp] = []
    for end in range(window, len(common_returns) + 1):
        sample = common_returns.iloc[end - window:end]
        n_eff, _ = participation_ratio(sample.corr())
        values.append(n_eff)
        index.append(sample.index[-1])
    return pd.Series(values, index=pd.DatetimeIndex(index), name="effective_N")
