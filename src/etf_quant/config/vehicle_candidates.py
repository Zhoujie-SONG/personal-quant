from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml

from etf_quant.config.universe import FrozenUniverse
from etf_quant.domain.exceptions import DataValidationError


MAPPING_CLASSES = frozenset(
    {
        "EXACT_TRACKING",
        "ECONOMIC_PROXY_CANDIDATE",
        "REJECTED_SEMANTIC_MISMATCH",
        "UNRESOLVED",
    }
)
APPROVAL_STATUS = "UNREVIEWED"
REGISTRY_STATUS = "CANDIDATE_NOT_APPROVED"
COMPLETENESS_STATUS = "PARTIAL_CURATED"
EVIDENCE_SCOPES = frozenset(
    {
        "VEHICLE_IDENTITY",
        "LISTING_PERIOD",
        "TRACKING_INDEX",
        "SEMANTIC_MISMATCH",
        "CURRENT_EXISTENCE",
    }
)
DATA_SEMANTICS = frozenset(
    {
        "CURRENT_SURVIVOR_WITH_OFFICIAL_PRODUCT_HISTORY",
        "KNOWN_HISTORICAL_WITH_OFFICIAL_TERMINATION",
    }
)
_SYMBOL_RE = re.compile(r"^\d{6}\.(?:SH|SZ)$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_SELECTION_FIELDS = frozenset(
    {
        "aum",
        "current_aum",
        "adv",
        "current_adv",
        "average_daily_volume",
        "spread",
        "bid_ask_spread",
        "liquidity",
        "liquidity_score",
        "cagr",
        "sharpe",
        "calmar",
        "return_correlation",
        "tracking_error",
        "approval_criteria",
        "rank",
        "score",
    }
)


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    source_type: str
    source_url: str
    retrieved_at: datetime
    claim: str
    official: bool
    evidence_scopes: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, location: str) -> "CandidateEvidence":
        scopes = payload.get("evidence_scopes")
        if not isinstance(scopes, list) or not scopes:
            raise DataValidationError(f"{location}.evidence_scopes must be a non-empty list")
        evidence = cls(
            source_type=_required_str(payload, "source_type", location),
            source_url=_required_str(payload, "source_url", location),
            retrieved_at=_aware_datetime(payload.get("retrieved_at"), f"{location}.retrieved_at"),
            claim=_required_str(payload, "claim", location),
            official=_required_bool(payload, "official", location),
            evidence_scopes=tuple(str(scope) for scope in scopes),
        )
        evidence.validate(location=location)
        return evidence

    def validate(self, *, location: str) -> None:
        parsed = urlparse(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DataValidationError(f"{location}.source_url must be an HTTP(S) URL")
        unknown = set(self.evidence_scopes) - EVIDENCE_SCOPES
        if unknown:
            raise DataValidationError(f"{location} has unknown evidence scopes: {sorted(unknown)}")
        if len(set(self.evidence_scopes)) != len(self.evidence_scopes):
            raise DataValidationError(f"{location}.evidence_scopes must be unique")


@dataclass(frozen=True, slots=True)
class VehicleCandidate:
    logical_asset_id: str
    vehicle_symbol: str
    fund_name: str
    exchange: str
    vehicle_type: str
    tracking_index_code: str | None
    tracking_index_name: str | None
    mapping_class: str
    approval_status: str
    list_date: date | None
    delist_date: date | None
    mapping_effective_from: date
    mapping_effective_to: date | None
    cross_border: bool
    qdii: bool
    data_semantics: str
    evidence: tuple[CandidateEvidence, ...]
    notes: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, index: int) -> "VehicleCandidate":
        location = f"candidates[{index}]"
        forbidden = _find_forbidden_fields(payload)
        if forbidden:
            raise DataValidationError(
                f"{location} contains selector/performance fields forbidden in M2B.0: {sorted(forbidden)}"
            )
        evidence_payload = payload.get("evidence")
        if not isinstance(evidence_payload, list) or not evidence_payload:
            raise DataValidationError(f"{location}.evidence must be a non-empty list")
        candidate = cls(
            logical_asset_id=_required_str(payload, "logical_asset_id", location),
            vehicle_symbol=_required_str(payload, "vehicle_symbol", location),
            fund_name=_required_str(payload, "fund_name", location),
            exchange=_required_str(payload, "exchange", location),
            vehicle_type=_required_str(payload, "vehicle_type", location),
            tracking_index_code=_optional_str(payload.get("tracking_index_code")),
            tracking_index_name=_optional_str(payload.get("tracking_index_name")),
            mapping_class=_required_str(payload, "mapping_class", location),
            approval_status=_required_str(payload, "approval_status", location),
            list_date=_optional_date(payload.get("list_date"), f"{location}.list_date"),
            delist_date=_optional_date(payload.get("delist_date"), f"{location}.delist_date"),
            mapping_effective_from=_required_date(
                payload.get("mapping_effective_from"), f"{location}.mapping_effective_from"
            ),
            mapping_effective_to=_optional_date(
                payload.get("mapping_effective_to"), f"{location}.mapping_effective_to"
            ),
            cross_border=_required_bool(payload, "cross_border", location),
            qdii=_required_bool(payload, "qdii", location),
            data_semantics=_required_str(payload, "data_semantics", location),
            evidence=tuple(
                CandidateEvidence.from_mapping(item, location=f"{location}.evidence[{item_index}]")
                for item_index, item in enumerate(evidence_payload)
                if isinstance(item, Mapping)
            ),
            notes=_required_str(payload, "notes", location),
        )
        if len(candidate.evidence) != len(evidence_payload):
            raise DataValidationError(f"{location}.evidence items must be mappings")
        candidate.validate(location=location)
        return candidate

    @property
    def evidence_complete(self) -> bool:
        official_scopes = {
            scope
            for item in self.evidence
            if item.official
            for scope in item.evidence_scopes
        }
        return {"VEHICLE_IDENTITY", "LISTING_PERIOD", "TRACKING_INDEX"} <= official_scopes

    def validate(self, *, location: str) -> None:
        if not _SYMBOL_RE.fullmatch(self.vehicle_symbol):
            raise DataValidationError(f"{location}.vehicle_symbol must use canonical XXXXXX.SH/SZ")
        expected_exchange = "SSE" if self.vehicle_symbol.endswith(".SH") else "SZSE"
        if self.exchange != expected_exchange:
            raise DataValidationError(f"{location}.exchange does not match the symbol suffix")
        if self.vehicle_type != "ETF":
            raise DataValidationError("vehicle_type must be ETF under the M2B.0 ETF-only contract")
        if self.mapping_class not in MAPPING_CLASSES:
            raise DataValidationError(f"{location}.mapping_class is unsupported")
        if self.approval_status != APPROVAL_STATUS:
            raise DataValidationError("every M2B.0 candidate approval_status must be UNREVIEWED")
        if self.data_semantics not in DATA_SEMANTICS:
            raise DataValidationError(f"{location}.data_semantics is unsupported")
        if self.list_date is not None and self.delist_date is not None:
            if self.list_date > self.delist_date:
                raise DataValidationError("list_date cannot be after delist_date")
        if self.mapping_effective_to is not None:
            if self.mapping_effective_from >= self.mapping_effective_to:
                raise DataValidationError("mapping effective period must be non-empty and end-exclusive")
        if self.list_date is not None and self.mapping_effective_from < self.list_date:
            raise DataValidationError("mapping cannot become effective before vehicle listing")
        if self.delist_date is not None:
            if self.mapping_effective_from >= self.delist_date:
                raise DataValidationError("mapping cannot start on or after delist_date")
            if self.mapping_effective_to is None or self.mapping_effective_to > self.delist_date:
                raise DataValidationError("a delisted vehicle mapping must end no later than delist_date")
        if self.qdii and not self.cross_border:
            raise DataValidationError("QDII candidates must be marked cross_border")
        if self.delist_date is None and self.data_semantics != "CURRENT_SURVIVOR_WITH_OFFICIAL_PRODUCT_HISTORY":
            raise DataValidationError("current candidates must use current-survivor data semantics")
        if self.delist_date is not None and self.data_semantics != "KNOWN_HISTORICAL_WITH_OFFICIAL_TERMINATION":
            raise DataValidationError("delisted candidates require official-termination data semantics")
        if self.mapping_class == "EXACT_TRACKING":
            if self.tracking_index_code is None or self.tracking_index_name is None:
                raise DataValidationError("EXACT_TRACKING requires tracking index code and name")
            if not any(
                item.official and "TRACKING_INDEX" in item.evidence_scopes
                for item in self.evidence
            ):
                raise DataValidationError("EXACT_TRACKING requires official tracking-index evidence")
            if not self.evidence_complete:
                raise DataValidationError(
                    "EXACT_TRACKING requires official identity, listing-period, and tracking-index evidence"
                )
        if self.mapping_class == "REJECTED_SEMANTIC_MISMATCH" and not any(
            item.official and "SEMANTIC_MISMATCH" in item.evidence_scopes
            for item in self.evidence
        ):
            raise DataValidationError(
                "REJECTED_SEMANTIC_MISMATCH requires official semantic-mismatch evidence"
            )


@dataclass(frozen=True, slots=True)
class RegistryCompleteness:
    status: str
    historical_cemetery_complete: bool
    scope_note: str


@dataclass(frozen=True, slots=True)
class NonVehicleLogicalAsset:
    logical_asset_id: str
    execution_mode: str
    vehicle_required: bool
    notes: str


@dataclass(frozen=True, slots=True)
class HistoricalVehicleCandidateEvidencePack:
    schema_name: str
    schema_version: str
    registry_name: str
    status: str
    source_commit: str
    universe_name: str
    universe_file_sha256: str
    registry_completeness: RegistryCompleteness
    candidates: tuple[VehicleCandidate, ...]
    non_vehicle_logical_assets: tuple[NonVehicleLogicalAsset, ...]

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        *,
        universe_path: Path,
    ) -> "HistoricalVehicleCandidateEvidencePack":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise DataValidationError("candidate evidence pack must be a mapping")
        forbidden = _find_forbidden_fields(payload)
        if forbidden:
            raise DataValidationError(
                "candidate evidence pack contains selector/performance fields forbidden in M2B.0: "
                f"{sorted(forbidden)}"
            )
        universe = FrozenUniverse.from_yaml(universe_path)
        binding = _required_mapping(payload, "universe_binding")
        completeness_payload = _required_mapping(payload, "registry_completeness")
        candidate_payload = payload.get("candidates")
        if not isinstance(candidate_payload, list):
            raise DataValidationError("candidates must be a list")
        non_vehicle_payload = _required_mapping(payload, "non_vehicle_logical_assets")
        non_vehicle: list[NonVehicleLogicalAsset] = []
        for logical_asset_id, value in non_vehicle_payload.items():
            if not isinstance(value, Mapping):
                raise DataValidationError(f"non_vehicle_logical_assets.{logical_asset_id} must be a mapping")
            non_vehicle.append(
                NonVehicleLogicalAsset(
                    logical_asset_id=str(logical_asset_id),
                    execution_mode=_required_str(
                        value, "execution_mode", f"non_vehicle_logical_assets.{logical_asset_id}"
                    ),
                    vehicle_required=_required_bool(
                        value, "vehicle_required", f"non_vehicle_logical_assets.{logical_asset_id}"
                    ),
                    notes=_required_str(value, "notes", f"non_vehicle_logical_assets.{logical_asset_id}"),
                )
            )
        pack = cls(
            schema_name=_required_str(payload, "schema_name", "root"),
            schema_version=_required_str(payload, "schema_version", "root"),
            registry_name=_required_str(payload, "registry_name", "root"),
            status=_required_str(payload, "status", "root"),
            source_commit=_required_str(payload, "source_commit", "root"),
            universe_name=_required_str(binding, "universe_name", "universe_binding"),
            universe_file_sha256=_required_str(
                binding, "universe_file_sha256", "universe_binding"
            ),
            registry_completeness=RegistryCompleteness(
                status=_required_str(completeness_payload, "status", "registry_completeness"),
                historical_cemetery_complete=_required_bool(
                    completeness_payload,
                    "historical_cemetery_complete",
                    "registry_completeness",
                ),
                scope_note=_required_str(
                    completeness_payload, "scope_note", "registry_completeness"
                ),
            ),
            candidates=tuple(
                VehicleCandidate.from_mapping(item, index=index)
                for index, item in enumerate(candidate_payload)
                if isinstance(item, Mapping)
            ),
            non_vehicle_logical_assets=tuple(non_vehicle),
        )
        if len(pack.candidates) != len(candidate_payload):
            raise DataValidationError("candidate items must be mappings")
        pack.validate(universe=universe, universe_path=universe_path)
        return pack

    def validate(self, *, universe: FrozenUniverse, universe_path: Path) -> None:
        if self.schema_name != "historical_vehicle_candidate_evidence" or self.schema_version != "1.0":
            raise DataValidationError(
                "M2B.0 requires historical_vehicle_candidate_evidence schema version 1.0"
            )
        if self.status != REGISTRY_STATUS:
            raise DataValidationError("M2B.0 status must be CANDIDATE_NOT_APPROVED")
        if any(token in self.registry_name.upper() for token in {"FINAL", "FROZEN", "PRODUCTION"}):
            raise DataValidationError("candidate evidence pack cannot be named final/frozen/production")
        if not _COMMIT_RE.fullmatch(self.source_commit):
            raise DataValidationError("source_commit must be a full lowercase Git commit hash")
        if self.universe_name != universe.universe_name:
            raise DataValidationError("candidate pack is bound to the wrong frozen Universe")
        if not _SHA256_RE.fullmatch(self.universe_file_sha256):
            raise DataValidationError("universe_file_sha256 must be a lowercase SHA-256")
        actual_hash = hashlib.sha256(universe_path.read_bytes()).hexdigest()
        if self.universe_file_sha256 != actual_hash:
            raise DataValidationError("frozen Universe file hash differs from the candidate-pack binding")
        completeness = self.registry_completeness
        if completeness.status != COMPLETENESS_STATUS:
            raise DataValidationError("M2B.0 registry completeness must be PARTIAL_CURATED")
        if completeness.historical_cemetery_complete:
            raise DataValidationError("a current snapshot cannot imply historical cemetery completeness")

        active_ids = {asset.id for asset in universe.active_logical_assets}
        candidate_ids = {candidate.logical_asset_id for candidate in self.candidates}
        for candidate in self.candidates:
            if candidate.logical_asset_id in {"HSTECH", "OIL"}:
                raise DataValidationError(f"{candidate.logical_asset_id} vehicle discovery is forbidden")
            if candidate.logical_asset_id not in active_ids:
                raise DataValidationError(
                    f"candidate references non-ACTIVE Logical Asset {candidate.logical_asset_id}"
                )
            if candidate.logical_asset_id == "CASH":
                raise DataValidationError("CASH cannot carry an ETF candidate")
        expected_candidate_ids = active_ids - {"CASH"}
        if candidate_ids != expected_candidate_ids:
            missing = sorted(expected_candidate_ids - candidate_ids)
            extra = sorted(candidate_ids - expected_candidate_ids)
            raise DataValidationError(
                f"candidate coverage must match active non-CASH assets; missing={missing}, extra={extra}"
            )

        non_vehicle = {item.logical_asset_id: item for item in self.non_vehicle_logical_assets}
        if set(non_vehicle) != {"CASH"}:
            raise DataValidationError("non_vehicle_logical_assets must contain exactly CASH")
        cash = non_vehicle["CASH"]
        if cash.execution_mode != "CASH_BALANCE" or cash.vehicle_required:
            raise DataValidationError("CASH must use CASH_BALANCE with vehicle_required=false")
        self._validate_symbol_periods()

    def _validate_symbol_periods(self) -> None:
        by_symbol: dict[str, list[VehicleCandidate]] = {}
        for candidate in self.candidates:
            by_symbol.setdefault(candidate.vehicle_symbol, []).append(candidate)
        for symbol, rows in by_symbol.items():
            ordered = sorted(
                rows,
                key=lambda item: (
                    item.mapping_effective_from,
                    item.mapping_effective_to or date.max,
                    item.logical_asset_id,
                ),
            )
            for left, right in zip(ordered, ordered[1:]):
                if left.mapping_effective_to is None:
                    raise DataValidationError(
                        f"{symbol} has overlapping or duplicate effective mapping periods"
                    )
                if right.mapping_effective_from < left.mapping_effective_to:
                    raise DataValidationError(
                        f"{symbol} has overlapping or duplicate effective mapping periods"
                    )

    def coverage_rows(self) -> tuple[dict[str, str | int], ...]:
        rows: list[dict[str, str | int]] = []
        logical_asset_ids = sorted(
            {candidate.logical_asset_id for candidate in self.candidates} | {"CASH"}
        )
        for logical_asset_id in logical_asset_ids:
            items = [
                candidate
                for candidate in self.candidates
                if candidate.logical_asset_id == logical_asset_id
            ]
            exact = [item for item in items if item.mapping_class == "EXACT_TRACKING"]
            proxy = [
                item for item in items if item.mapping_class == "ECONOMIC_PROXY_CANDIDATE"
            ]
            unresolved = [item for item in items if item.mapping_class == "UNRESOLVED"]
            exact_dates = [item.list_date for item in exact if item.list_date is not None]
            if logical_asset_id == "CASH":
                coverage_status = "GOOD"
            elif exact and all(item.evidence_complete for item in exact):
                coverage_status = "GOOD"
            elif exact:
                coverage_status = "PARTIAL"
            elif proxy:
                coverage_status = "NO_EXACT_VEHICLE"
            else:
                coverage_status = "UNRESOLVED"
            rows.append(
                {
                    "logical_asset_id": logical_asset_id,
                    "exact_candidate_count": len(exact),
                    "proxy_candidate_count": len(proxy),
                    "unresolved_count": len(unresolved),
                    "earliest_exact_list_date": min(exact_dates).isoformat() if exact_dates else "",
                    "known_delisted_count": sum(item.delist_date is not None for item in items),
                    "evidence_complete_count": sum(item.evidence_complete for item in items),
                    "coverage_status": coverage_status,
                }
            )
        return tuple(rows)


def _find_forbidden_fields(payload: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_SELECTION_FIELDS:
                found.add(normalized)
            found.update(_find_forbidden_fields(value))
    elif isinstance(payload, list):
        for item in payload:
            found.update(_find_forbidden_fields(item))
    return found


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise DataValidationError(f"{key} must be a mapping")
    return value


def _required_str(payload: Mapping[str, Any], key: str, location: str) -> str:
    value = payload.get(key)
    if value is None or not str(value).strip():
        raise DataValidationError(f"{location}.{key} is required")
    return str(value).strip()


def _optional_str(value: object) -> str | None:
    return None if value in (None, "") else str(value).strip()


def _required_bool(payload: Mapping[str, Any], key: str, location: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise DataValidationError(f"{location}.{key} must be boolean")
    return value


def _required_date(value: object, location: str) -> date:
    result = _optional_date(value, location)
    if result is None:
        raise DataValidationError(f"{location} is required")
    return result


def _optional_date(value: object, location: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise DataValidationError(f"{location} must be an ISO calendar date") from exc


def _aware_datetime(value: object, location: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise DataValidationError(f"{location} must be an ISO datetime") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise DataValidationError(f"{location} must be timezone-aware")
    return result
