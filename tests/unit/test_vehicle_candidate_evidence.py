from __future__ import annotations

import csv
import hashlib
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from etf_quant.config.vehicle_candidates import HistoricalVehicleCandidateEvidencePack
from etf_quant.domain.exceptions import DataValidationError


ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "configs" / "historical_vehicle_candidates.yaml"
UNIVERSE_PATH = ROOT / "configs" / "universe_v1.yaml"
COVERAGE_PATH = ROOT / "reports" / "vehicle_candidate_m2b0" / "coverage.csv"
UNIVERSE_SHA256 = "7a72fcb6ae8ab60cc2cbf89bf6276251c626e94e8dcd1169f2b08e4564c9ca2e"


def _payload() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _load(path: Path = CONFIG_PATH) -> HistoricalVehicleCandidateEvidencePack:
    return HistoricalVehicleCandidateEvidencePack.from_yaml(path, universe_path=UNIVERSE_PATH)


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "candidates.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_evidence_pack_loads_as_unapproved_partial_curated_registry() -> None:
    pack = _load()
    counts = {
        mapping_class: sum(item.mapping_class == mapping_class for item in pack.candidates)
        for mapping_class in {
            "EXACT_TRACKING",
            "ECONOMIC_PROXY_CANDIDATE",
            "REJECTED_SEMANTIC_MISMATCH",
            "UNRESOLVED",
        }
    }

    assert pack.status == "CANDIDATE_NOT_APPROVED"
    assert pack.registry_completeness.status == "PARTIAL_CURATED"
    assert pack.registry_completeness.historical_cemetery_complete is False
    assert len(pack.candidates) == 17
    assert counts == {
        "EXACT_TRACKING": 14,
        "ECONOMIC_PROXY_CANDIDATE": 2,
        "REJECTED_SEMANTIC_MISMATCH": 1,
        "UNRESOLVED": 0,
    }
    assert all(item.approval_status == "UNREVIEWED" for item in pack.candidates)


@pytest.mark.parametrize("logical_asset_id", ["HSTECH", "OIL"])
def test_deferred_or_inactive_asset_vehicle_is_rejected(
    tmp_path: Path, logical_asset_id: str
) -> None:
    payload = _payload()
    payload["candidates"][0]["logical_asset_id"] = logical_asset_id

    with pytest.raises(DataValidationError, match="vehicle discovery is forbidden"):
        _load(_write(tmp_path, payload))


def test_cash_etf_candidate_is_rejected_and_cash_balance_is_explicit(tmp_path: Path) -> None:
    pack = _load()
    cash = pack.non_vehicle_logical_assets[0]
    assert (cash.logical_asset_id, cash.execution_mode, cash.vehicle_required) == (
        "CASH",
        "CASH_BALANCE",
        False,
    )

    payload = _payload()
    payload["candidates"][0]["logical_asset_id"] = "CASH"
    with pytest.raises(DataValidationError, match="CASH cannot carry an ETF"):
        _load(_write(tmp_path, payload))


def test_non_etf_vehicle_type_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    payload["candidates"][0]["vehicle_type"] = "LOF"

    with pytest.raises(DataValidationError, match="vehicle_type must be ETF"):
        _load(_write(tmp_path, payload))


def test_exact_mapping_requires_complete_official_tracking_evidence(tmp_path: Path) -> None:
    payload = _payload()
    payload["candidates"][0]["tracking_index_code"] = None

    with pytest.raises(DataValidationError, match="requires tracking index code and name"):
        _load(_write(tmp_path, payload))

    payload = _payload()
    payload["candidates"][0]["evidence"][0]["evidence_scopes"] = ["TRACKING_INDEX"]
    with pytest.raises(DataValidationError, match="official identity, listing-period"):
        _load(_write(tmp_path, payload))


def test_proxy_remains_unreviewed_and_cannot_be_silently_approved(tmp_path: Path) -> None:
    pack = _load()
    proxies = [
        item for item in pack.candidates if item.mapping_class == "ECONOMIC_PROXY_CANDIDATE"
    ]
    assert {item.vehicle_symbol for item in proxies} == {"510880.SH", "512170.SH"}
    assert all(item.approval_status == "UNREVIEWED" for item in proxies)

    payload = _payload()
    proxy = next(
        item for item in payload["candidates"] if item["mapping_class"] == "ECONOMIC_PROXY_CANDIDATE"
    )
    proxy["approval_status"] = "APPROVED"
    with pytest.raises(DataValidationError, match="must be UNREVIEWED"):
        _load(_write(tmp_path, payload))


def test_known_delisted_candidate_is_retained_with_termination_semantics(tmp_path: Path) -> None:
    payload = _payload()
    candidate = payload["candidates"][0]
    candidate["delist_date"] = "2020-01-02"
    candidate["mapping_effective_to"] = "2020-01-02"
    candidate["data_semantics"] = "KNOWN_HISTORICAL_WITH_OFFICIAL_TERMINATION"
    candidate["evidence"][0]["claim"] += " Synthetic test termination evidence."

    pack = _load(_write(tmp_path, payload))
    retained = next(item for item in pack.candidates if item.vehicle_symbol == "510300.SH")
    assert retained.delist_date.isoformat() == "2020-01-02"
    assert retained.data_semantics == "KNOWN_HISTORICAL_WITH_OFFICIAL_TERMINATION"


def test_mapping_and_listing_date_validity_fail_fast(tmp_path: Path) -> None:
    payload = _payload()
    payload["candidates"][0]["mapping_effective_from"] = "2012-05-27"
    with pytest.raises(DataValidationError, match="before vehicle listing"):
        _load(_write(tmp_path, payload))

    payload = _payload()
    candidate = payload["candidates"][0]
    candidate["list_date"] = "2020-01-03"
    candidate["delist_date"] = "2020-01-02"
    candidate["mapping_effective_to"] = "2020-01-02"
    candidate["data_semantics"] = "KNOWN_HISTORICAL_WITH_OFFICIAL_TERMINATION"
    with pytest.raises(DataValidationError, match="list_date cannot be after delist_date"):
        _load(_write(tmp_path, payload))


def test_tracking_index_change_uses_adjacent_effective_periods(tmp_path: Path) -> None:
    payload = _payload()
    first = payload["candidates"][0]
    first["mapping_effective_to"] = "2020-01-01"
    successor = deepcopy(first)
    successor["tracking_index_code"] = "SYNTHETIC_SUCCESSOR"
    successor["tracking_index_name"] = "Synthetic successor index"
    successor["mapping_effective_from"] = "2020-01-01"
    successor["mapping_effective_to"] = None
    payload["candidates"].append(successor)

    pack = _load(_write(tmp_path, payload))
    periods = [item for item in pack.candidates if item.vehicle_symbol == "510300.SH"]
    assert len(periods) == 2
    assert periods[0].mapping_effective_to == periods[1].mapping_effective_from
    assert periods[0].tracking_index_code != periods[1].tracking_index_code


def test_overlapping_mapping_periods_are_rejected(tmp_path: Path) -> None:
    payload = _payload()
    duplicate = deepcopy(payload["candidates"][0])
    duplicate["mapping_effective_from"] = "2019-01-01"
    payload["candidates"].append(duplicate)

    with pytest.raises(DataValidationError, match="overlapping or duplicate"):
        _load(_write(tmp_path, payload))


def test_current_snapshot_cannot_claim_historical_cemetery_completeness(tmp_path: Path) -> None:
    payload = _payload()
    payload["registry_completeness"]["historical_cemetery_complete"] = True

    with pytest.raises(DataValidationError, match="historical cemetery completeness"):
        _load(_write(tmp_path, payload))


@pytest.mark.parametrize("field", ["current_aum", "liquidity", "sharpe", "rank"])
def test_selection_and_performance_fields_are_out_of_scope(tmp_path: Path, field: str) -> None:
    payload = _payload()
    payload["candidates"][0][field] = 1

    with pytest.raises(DataValidationError, match="forbidden in M2B.0"):
        _load(_write(tmp_path, payload))


def test_frozen_universe_is_hash_bound_and_excludes_hstech_and_oil() -> None:
    pack = _load()
    candidate_ids = {item.logical_asset_id for item in pack.candidates}

    assert hashlib.sha256(UNIVERSE_PATH.read_bytes()).hexdigest() == UNIVERSE_SHA256
    assert pack.universe_file_sha256 == UNIVERSE_SHA256
    assert "HSTECH" not in candidate_ids
    assert "OIL" not in candidate_ids


def test_coverage_artifact_matches_validated_registry() -> None:
    expected = {
        str(row["logical_asset_id"]): {key: str(value) for key, value in row.items()}
        for row in _load().coverage_rows()
    }
    with COVERAGE_PATH.open(encoding="utf-8", newline="") as stream:
        actual = {row["logical_asset_id"]: row for row in csv.DictReader(stream)}

    assert actual == expected
