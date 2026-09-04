from __future__ import annotations

import csv
import hashlib
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from etf_quant.config.vehicle_candidates import HistoricalVehicleCandidateEvidencePack
from etf_quant.domain.exceptions import DataValidationError


ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "configs" / "historical_vehicle_candidates.yaml"
IDENTITY_PATH = ROOT / "configs" / "index_identity_aliases_candidate.yaml"
UNIVERSE_PATH = ROOT / "configs" / "universe_v1.yaml"
COVERAGE_PATH = ROOT / "reports" / "vehicle_candidate_m2b0" / "coverage.csv"
UNIVERSE_SHA256 = "7a72fcb6ae8ab60cc2cbf89bf6276251c626e94e8dcd1169f2b08e4564c9ca2e"


def _payload() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _identity_payload() -> dict:
    return yaml.safe_load(IDENTITY_PATH.read_text(encoding="utf-8"))


def _load(
    path: Path = CONFIG_PATH,
    *,
    identity_path: Path = IDENTITY_PATH,
) -> HistoricalVehicleCandidateEvidencePack:
    return HistoricalVehicleCandidateEvidencePack.from_yaml(
        path,
        universe_path=UNIVERSE_PATH,
        index_identity_path=identity_path,
    )


def _write(tmp_path: Path, payload: dict, name: str = "candidates.yaml") -> Path:
    path = tmp_path / name
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def _vehicle(payload: dict, logical_asset_id: str, symbol: str) -> dict:
    return next(
        item
        for item in payload["candidate_groups"][logical_asset_id]["vehicles"]
        if item["vehicle_symbol"] == symbol
    )


def test_evidence_pack_loads_as_unapproved_partial_curated_registry() -> None:
    pack = _load()

    assert pack.status == "CANDIDATE_NOT_APPROVED"
    assert pack.registry_completeness.status == "PARTIAL_CURATED"
    assert pack.registry_completeness.historical_cemetery_complete is False
    assert pack.registry_completeness.targeted_cemetery_search == "ADDITIONAL_TERMINATED_FOUND"
    assert len(pack.candidates) == 108
    assert Counter(item.mapping_class for item in pack.candidates) == {
        "EXACT_BENCHMARK": 69,
        "EXACT_LOGICAL_EXPOSURE": 27,
        "ECONOMIC_PROXY_CANDIDATE": 5,
        "REJECTED_SEMANTIC_MISMATCH": 7,
    }
    assert all(item.approval_status == "UNREVIEWED" for item in pack.candidates)


def test_multiple_vehicles_may_map_to_one_logical_asset() -> None:
    pack = _load()
    counts = Counter(item.logical_asset_id for item in pack.candidates)

    assert counts["CN_LARGE"] == 25
    assert counts["NASDAQ100"] == 11
    assert counts["GOLD"] == 21
    assert len({item.vehicle_symbol for item in pack.candidates}) == len(pack.candidates)


def test_canonical_alias_requires_official_identity_evidence(tmp_path: Path) -> None:
    payload = _identity_payload()
    csi_300 = next(
        item for item in payload["identities"] if item["canonical_index_id"] == "CSI_300"
    )
    shenzhen_alias = next(
        item for item in csi_300["aliases"] if item["code"] == "399300"
    )
    shenzhen_alias["evidence"][0]["official"] = False

    with pytest.raises(DataValidationError, match="official INDEX_IDENTITY evidence"):
        _load(identity_path=_write(tmp_path, payload, "identities.yaml"))


def test_unverified_alias_fails_fast(tmp_path: Path) -> None:
    payload = _payload()
    _vehicle(payload, "CN_LARGE", "159919.SZ")["tracking_index_code"] = "399301"

    with pytest.raises(DataValidationError, match="unverified alias"):
        _load(_write(tmp_path, payload))


def test_provider_code_alias_does_not_imply_proxy() -> None:
    pack = _load()
    shenzhen_csi_300 = next(
        item for item in pack.candidates if item.vehicle_symbol == "159919.SZ"
    )

    assert shenzhen_csi_300.tracking_index_code == "399300"
    assert shenzhen_csi_300.canonical_index_id == "CSI_300"
    assert shenzhen_csi_300.mapping_class == "EXACT_BENCHMARK"


def test_price_and_total_return_variants_are_distinguishable() -> None:
    pack = _load()
    sp500 = next(item for item in pack.candidates if item.vehicle_symbol == "513500.SH")
    frozen = pack.index_identities.frozen_identity("SP500")

    assert frozen.frozen_return_variant == "PRICE_INDEX"
    assert sp500.tracking_return_variant == "NET_TOTAL_RETURN_CNY"
    assert sp500.mapping_class == "EXACT_LOGICAL_EXPOSURE"


def test_exact_benchmark_contract_rejects_variant_difference(tmp_path: Path) -> None:
    payload = _payload()
    _vehicle(payload, "CN_LARGE", "510300.SH")["tracking_return_variant"] = (
        "NET_TOTAL_RETURN_INDEX"
    )

    with pytest.raises(DataValidationError, match="EXACT_BENCHMARK requires canonical identity"):
        _load(_write(tmp_path, payload))


def test_exact_logical_exposure_contract_requires_disclosed_difference(tmp_path: Path) -> None:
    payload = _payload()
    sp500 = _vehicle(payload, "SP500", "513500.SH")
    sp500["tracking_return_variant"] = "PRICE_INDEX"

    with pytest.raises(DataValidationError, match="must preserve a disclosed"):
        _load(_write(tmp_path, payload))


def test_exact_or_logical_mapping_requires_complete_official_evidence(tmp_path: Path) -> None:
    payload = _payload()
    payload["evidence_catalog"]["SSE_CURRENT_ETF_TABLE"]["evidence_scopes"] = [
        "TRACKING_INDEX"
    ]

    with pytest.raises(DataValidationError, match="official identity, listing-period"):
        _load(_write(tmp_path, payload))


def test_historical_terminated_etf_is_retained_with_official_termination() -> None:
    pack = _load()
    terminated = next(item for item in pack.candidates if item.vehicle_symbol == "560890.SH")

    assert terminated.logical_asset_id == "CN_DIVIDEND"
    assert terminated.list_date.isoformat() == "2024-09-20"
    assert terminated.delist_date.isoformat() == "2026-04-01"
    assert terminated.mapping_effective_to == terminated.delist_date
    assert terminated.data_semantics == "KNOWN_HISTORICAL_WITH_OFFICIAL_TERMINATION"


def test_delisted_candidate_requires_official_termination_evidence(tmp_path: Path) -> None:
    payload = _payload()
    terminated = _vehicle(payload, "CN_DIVIDEND", "560890.SH")
    terminated["evidence_refs"] = ["SSE_560890_LISTING_TRACKING", "CSINDEX_560890_PROXY"]

    with pytest.raises(DataValidationError, match="official termination evidence"):
        _load(_write(tmp_path, payload))


def test_no_cemetery_completeness_claim_is_allowed(tmp_path: Path) -> None:
    payload = _payload()
    payload["registry_completeness"]["historical_cemetery_complete"] = True

    with pytest.raises(DataValidationError, match="cemetery completeness"):
        _load(_write(tmp_path, payload))

    payload = _payload()
    payload["registry_completeness"]["targeted_cemetery_search"] = "COMPLETE"
    with pytest.raises(DataValidationError, match="must not claim COMPLETE"):
        _load(_write(tmp_path, payload))


def test_current_size_or_trading_activity_cannot_remove_candidates(tmp_path: Path) -> None:
    pack = _load()
    assert sum(item.is_current for item in pack.candidates) == 107

    payload = _payload()
    _vehicle(payload, "CN_LARGE", "510300.SH")["current_aum"] = 1
    with pytest.raises(DataValidationError, match="forbidden in M2B.0.1"):
        _load(_write(tmp_path, payload))


@pytest.mark.parametrize("field", ["liquidity", "spread", "premium", "sharpe", "rank"])
def test_selection_and_performance_fields_are_out_of_scope(tmp_path: Path, field: str) -> None:
    payload = _payload()
    _vehicle(payload, "CN_LARGE", "510300.SH")[field] = 1

    with pytest.raises(DataValidationError, match="forbidden in M2B.0.1"):
        _load(_write(tmp_path, payload))


def test_required_proxy_and_rejection_dispositions_are_preserved() -> None:
    pack = _load()
    by_symbol = {item.vehicle_symbol: item for item in pack.candidates}

    assert by_symbol["510880.SH"].mapping_class == "ECONOMIC_PROXY_CANDIDATE"
    assert by_symbol["512170.SH"].mapping_class == "ECONOMIC_PROXY_CANDIDATE"
    assert by_symbol["517520.SH"].mapping_class == "REJECTED_SEMANTIC_MISMATCH"
    assert all(by_symbol[symbol].approval_status == "UNREVIEWED" for symbol in by_symbol)


def test_mapping_and_listing_date_validity_fail_fast(tmp_path: Path) -> None:
    payload = _payload()
    row = _vehicle(payload, "CN_LARGE", "510300.SH")
    row["mapping_effective_from"] = "2012-05-27"

    with pytest.raises(DataValidationError, match="before vehicle listing"):
        _load(_write(tmp_path, payload))


def test_adjacent_mapping_periods_are_valid_and_overlap_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    first = _vehicle(payload, "CN_LARGE", "510300.SH")
    first["mapping_effective_to"] = "2020-01-01"
    successor = deepcopy(first)
    successor["mapping_effective_from"] = "2020-01-01"
    successor["mapping_effective_to"] = None
    payload["candidate_groups"]["CN_LARGE"]["vehicles"].append(successor)
    pack = _load(_write(tmp_path, payload))
    assert len([item for item in pack.candidates if item.vehicle_symbol == "510300.SH"]) == 2

    successor["mapping_effective_from"] = "2019-12-31"
    with pytest.raises(DataValidationError, match="overlapping or duplicate"):
        _load(_write(tmp_path, payload))


@pytest.mark.parametrize("logical_asset_id", ["HSTECH", "OIL"])
def test_deferred_or_inactive_asset_vehicle_is_rejected(
    tmp_path: Path, logical_asset_id: str
) -> None:
    payload = _payload()
    payload["candidate_groups"][logical_asset_id] = payload["candidate_groups"].pop("CN_LARGE")

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
    payload["candidate_groups"]["CASH"] = payload["candidate_groups"].pop("CN_LARGE")
    with pytest.raises(DataValidationError, match="CASH cannot carry an ETF"):
        _load(_write(tmp_path, payload))


def test_non_etf_vehicle_type_is_rejected(tmp_path: Path) -> None:
    payload = _payload()
    _vehicle(payload, "CN_LARGE", "510300.SH")["vehicle_type"] = "LOF"

    with pytest.raises(DataValidationError, match="vehicle_type must be ETF"):
        _load(_write(tmp_path, payload))


def test_proxy_remains_unreviewed_and_cannot_be_silently_approved(tmp_path: Path) -> None:
    payload = _payload()
    _vehicle(payload, "CN_DIVIDEND", "510880.SH")["approval_status"] = "APPROVED"

    with pytest.raises(DataValidationError, match="must be UNREVIEWED"):
        _load(_write(tmp_path, payload))


def test_frozen_universe_v1_is_unchanged() -> None:
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
