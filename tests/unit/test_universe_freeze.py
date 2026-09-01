from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from etf_quant.config.universe import (
    FROZEN_V1_ACTIVE_IDS,
    FROZEN_V1_BENCHMARKS,
    FROZEN_V1_CLUSTERS,
    FROZEN_V1_NAMES,
    FROZEN_V1_SLEEVES,
    FrozenUniverse,
)


ROOT = Path(__file__).parents[2]
UNIVERSE_PATH = ROOT / "configs" / "universe_v1.yaml"
BENCHMARK_REGISTRY_PATH = ROOT / "configs" / "logical_asset_benchmarks_candidate.yaml"


def load_universe() -> FrozenUniverse:
    return FrozenUniverse.from_yaml(UNIVERSE_PATH)


def test_frozen_universe_has_exact_human_approved_active_assets() -> None:
    universe = load_universe()
    ids = [asset.id for asset in universe.active_logical_assets]

    assert universe.schema_version == "1.0"
    assert universe.universe_status == "FROZEN_V1"
    assert len(ids) == 15
    assert len(ids) == len(set(ids))
    assert set(ids) == FROZEN_V1_ACTIVE_IDS
    assert "CASH" in ids
    assert "HSTECH" not in ids
    assert "OIL" not in ids
    assert all(asset.status == "ACTIVE" for asset in universe.active_logical_assets)
    assert {asset.id: asset.name_cn for asset in universe.active_logical_assets} == FROZEN_V1_NAMES


def test_every_active_asset_has_exactly_one_frozen_sleeve() -> None:
    universe = load_universe()
    assignments = [member for members in universe.sleeves.values() for member in members]

    assert {name: frozenset(members) for name, members in universe.sleeves.items()} == FROZEN_V1_SLEEVES
    assert len(assignments) == 15
    assert len(assignments) == len(set(assignments))
    assert set(assignments) == FROZEN_V1_ACTIVE_IDS


def test_predeclared_clusters_reference_only_active_assets_and_keep_roles_distinct() -> None:
    universe = load_universe()
    clusters = {
        name: frozenset(members) for name, members in universe.predeclared_risk_clusters.items()
    }

    assert clusters == FROZEN_V1_CLUSTERS
    assert all(members <= FROZEN_V1_ACTIVE_IDS for members in clusters.values())
    assert {"SP500", "NASDAQ100"} <= FROZEN_V1_ACTIVE_IDS
    assert {"CN_GROWTH", "SEMI"} <= FROZEN_V1_ACTIVE_IDS
    assert {"BOND_LONG", "BOND_MED"} <= FROZEN_V1_ACTIVE_IDS
    assert not any({"CN_DIVIDEND", "COAL"} <= members for members in clusters.values())


def test_deferred_and_inactive_decisions_are_not_active() -> None:
    universe = load_universe()
    candidates = {candidate.id: candidate for candidate in universe.deferred_inactive_candidates}

    assert candidates["HSTECH"].status == "DEFERRED_REDUNDANCY"
    assert candidates["HSTECH"].payload["evidence"] == {
        "daily_correlation": 0.911,
        "weekly_correlation": 0.902,
        "rolling_756_day_median": 0.941,
    }
    assert candidates["OIL"].status == "INACTIVE_NO_VALID_ETF_VEHICLE"
    assert candidates["OIL"].payload["roles"] == ["INDEX_ONLY", "NON_EXECUTABLE"]


def test_benchmark_provenance_is_frozen_and_separate_from_execution_vehicles() -> None:
    universe = load_universe()
    references = {
        asset.id: (
            asset.benchmark_reference.symbol,
            asset.benchmark_reference.provider,
            asset.benchmark_reference.benchmark_type,
            asset.benchmark_reference.series_kind,
        )
        for asset in universe.active_logical_assets
    }

    assert references == FROZEN_V1_BENCHMARKS
    assert universe.benchmark_registry_path == "configs/logical_asset_benchmarks_candidate.yaml"
    assert universe.benchmark_registry_source_commit == "cafbea27dbfd8d72e85fc2ac3ef1bf2f34a7e7c1"
    assert universe.freeze_source_commit == "cafbea27dbfd8d72e85fc2ac3ef1bf2f34a7e7c1"
    assert universe.execution_vehicle_registry is None
    assert universe.vehicle_selector_status == "NOT_IMPLEMENTED"
    assert all(not re.fullmatch(r"\d{6}(?:\.(?:SH|SZ))?", asset.id) for asset in universe.active_logical_assets)
    universe.validate_benchmark_registry(BENCHMARK_REGISTRY_PATH)


def test_execution_vehicle_symbol_field_is_rejected(tmp_path: Path) -> None:
    payload = yaml.safe_load(UNIVERSE_PATH.read_text(encoding="utf-8"))
    payload["active_logical_assets"][0]["etf_symbol"] = "510300.SH"
    invalid = tmp_path / "invalid_universe.yaml"
    invalid.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="execution vehicle fields are forbidden"):
        FrozenUniverse.from_yaml(invalid)


def test_benchmark_registry_hash_drift_fails_fast(tmp_path: Path) -> None:
    universe = load_universe()
    drifted = tmp_path / "drifted_registry.yaml"
    drifted.write_bytes(BENCHMARK_REGISTRY_PATH.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="frozen mapping hash"):
        universe.validate_benchmark_registry(drifted)
