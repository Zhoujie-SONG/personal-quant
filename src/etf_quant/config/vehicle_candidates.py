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
        "EXACT_BENCHMARK",
        "EXACT_LOGICAL_EXPOSURE",
        "ECONOMIC_PROXY_CANDIDATE",
        "REJECTED_SEMANTIC_MISMATCH",
        "UNRESOLVED",
    }
)
APPROVAL_STATUS = "UNREVIEWED"
REGISTRY_STATUS = "CANDIDATE_NOT_APPROVED"
COMPLETENESS_STATUS = "PARTIAL_CURATED"
IDENTITY_STATUS = "CANDIDATE_VERIFIED_IDENTITY"
EVIDENCE_SCOPES = frozenset(
    {
        "VEHICLE_IDENTITY",
        "LISTING_PERIOD",
        "TRACKING_INDEX",
        "INDEX_IDENTITY",
        "SEMANTIC_MISMATCH",
        "CURRENT_EXISTENCE",
        "TERMINATION",
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
        "premium",
        "premium_discount",
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
class IndexAlias:
    provider: str
    code: str
    alias_kind: str
    evidence: tuple[CandidateEvidence, ...]

    @property
    def evidence_complete(self) -> bool:
        return any(
            item.official and "INDEX_IDENTITY" in item.evidence_scopes for item in self.evidence
        )


@dataclass(frozen=True, slots=True)
class CanonicalIndexIdentity:
    canonical_index_id: str
    canonical_name: str
    logical_asset_id: str
    frozen_benchmark: bool
    frozen_return_variant: str | None
    aliases: tuple[IndexAlias, ...]


@dataclass(frozen=True, slots=True)
class CandidateIndexIdentityRegistry:
    schema_version: str
    status: str
    identities: tuple[CanonicalIndexIdentity, ...]

    @classmethod
    def from_yaml(cls, path: Path) -> "CandidateIndexIdentityRegistry":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise DataValidationError("candidate index identity registry must be a mapping")
        rows = payload.get("identities")
        if not isinstance(rows, list) or not rows:
            raise DataValidationError("index identity registry identities must be a non-empty list")
        identities: list[CanonicalIndexIdentity] = []
        for index, row in enumerate(rows):
            location = f"identities[{index}]"
            if not isinstance(row, Mapping):
                raise DataValidationError(f"{location} must be a mapping")
            aliases_payload = row.get("aliases")
            if not isinstance(aliases_payload, list) or not aliases_payload:
                raise DataValidationError(f"{location}.aliases must be a non-empty list")
            aliases: list[IndexAlias] = []
            for alias_index, alias_payload in enumerate(aliases_payload):
                alias_location = f"{location}.aliases[{alias_index}]"
                if not isinstance(alias_payload, Mapping):
                    raise DataValidationError(f"{alias_location} must be a mapping")
                evidence_payload = alias_payload.get("evidence")
                if not isinstance(evidence_payload, list) or not evidence_payload:
                    raise DataValidationError(f"{alias_location}.evidence must be a non-empty list")
                evidence = tuple(
                    CandidateEvidence.from_mapping(item, location=f"{alias_location}.evidence[{i}]")
                    for i, item in enumerate(evidence_payload)
                    if isinstance(item, Mapping)
                )
                if len(evidence) != len(evidence_payload):
                    raise DataValidationError(f"{alias_location}.evidence items must be mappings")
                alias = IndexAlias(
                    provider=_required_str(alias_payload, "provider", alias_location),
                    code=_required_str(alias_payload, "code", alias_location),
                    alias_kind=_required_str(alias_payload, "alias_kind", alias_location),
                    evidence=evidence,
                )
                if not alias.evidence_complete:
                    raise DataValidationError(
                        f"{alias_location} requires official INDEX_IDENTITY evidence"
                    )
                aliases.append(alias)
            identities.append(
                CanonicalIndexIdentity(
                    canonical_index_id=_required_str(row, "canonical_index_id", location),
                    canonical_name=_required_str(row, "canonical_name", location),
                    logical_asset_id=_required_str(row, "logical_asset_id", location),
                    frozen_benchmark=_required_bool(row, "frozen_benchmark", location),
                    frozen_return_variant=_optional_str(row.get("frozen_return_variant")),
                    aliases=tuple(aliases),
                )
            )
        registry = cls(
            schema_version=_required_str(payload, "schema_version", "root"),
            status=_required_str(payload, "status", "root"),
            identities=tuple(identities),
        )
        registry.validate()
        return registry

    def validate(self) -> None:
        if self.schema_version != "1.0":
            raise DataValidationError("candidate index identity schema_version must be 1.0")
        if self.status != IDENTITY_STATUS:
            raise DataValidationError(
                "candidate index identity status must be CANDIDATE_VERIFIED_IDENTITY"
            )
        ids = [item.canonical_index_id for item in self.identities]
        if len(ids) != len(set(ids)):
            raise DataValidationError("canonical_index_id values must be unique")
        alias_keys: list[tuple[str, str]] = []
        for item in self.identities:
            alias_keys.extend((alias.provider, alias.code) for alias in item.aliases)
        if len(alias_keys) != len(set(alias_keys)):
            raise DataValidationError("provider/code aliases must resolve to exactly one identity")

    def identity(self, canonical_index_id: str) -> CanonicalIndexIdentity:
        matches = [item for item in self.identities if item.canonical_index_id == canonical_index_id]
        if len(matches) != 1:
            raise DataValidationError(
                f"canonical index identity {canonical_index_id!r} is not verified"
            )
        return matches[0]

    def alias(self, *, canonical_index_id: str, provider: str, code: str) -> IndexAlias:
        identity = self.identity(canonical_index_id)
        matches = [
            item for item in identity.aliases if item.provider == provider and item.code == code
        ]
        if len(matches) != 1:
            raise DataValidationError(f"unverified alias {provider}:{code} for {canonical_index_id}")
        return matches[0]

    def frozen_identity(self, logical_asset_id: str) -> CanonicalIndexIdentity:
        matches = [
            item
            for item in self.identities
            if item.logical_asset_id == logical_asset_id and item.frozen_benchmark
        ]
        if len(matches) != 1:
            raise DataValidationError(
                f"{logical_asset_id} must have exactly one frozen candidate index identity"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class VehicleCandidate:
    logical_asset_id: str
    vehicle_symbol: str
    fund_name: str
    exchange: str
    vehicle_type: str
    tracking_index_provider: str | None
    tracking_index_code: str | None
    tracking_index_name: str | None
    canonical_index_id: str | None
    tracking_return_variant: str | None
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

    @property
    def is_current(self) -> bool:
        return self.data_semantics == "CURRENT_SURVIVOR_WITH_OFFICIAL_PRODUCT_HISTORY"

    @property
    def evidence_complete(self) -> bool:
        official_scopes = {
            scope for item in self.evidence if item.official for scope in item.evidence_scopes
        }
        return {"VEHICLE_IDENTITY", "LISTING_PERIOD", "TRACKING_INDEX"} <= official_scopes

    def validate(
        self,
        *,
        location: str,
        identities: CandidateIndexIdentityRegistry,
    ) -> None:
        if not _SYMBOL_RE.fullmatch(self.vehicle_symbol):
            raise DataValidationError(f"{location}.vehicle_symbol must use canonical XXXXXX.SH/SZ")
        expected_exchange = "SSE" if self.vehicle_symbol.endswith(".SH") else "SZSE"
        if self.exchange != expected_exchange:
            raise DataValidationError(f"{location}.exchange does not match the symbol suffix")
        if self.vehicle_type != "ETF":
            raise DataValidationError("vehicle_type must be ETF under the M2B.0.1 ETF-only contract")
        if self.mapping_class not in MAPPING_CLASSES:
            raise DataValidationError(f"{location}.mapping_class is unsupported")
        if self.approval_status != APPROVAL_STATUS:
            raise DataValidationError("every M2B.0.1 candidate approval_status must be UNREVIEWED")
        if self.data_semantics not in DATA_SEMANTICS:
            raise DataValidationError(f"{location}.data_semantics is unsupported")
        if self.list_date is not None and self.delist_date is not None and self.list_date > self.delist_date:
            raise DataValidationError("list_date cannot be after delist_date")
        if self.mapping_effective_to is not None and self.mapping_effective_from >= self.mapping_effective_to:
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
        if self.delist_date is None and not self.is_current:
            raise DataValidationError("current candidates must use current-survivor data semantics")
        if self.delist_date is not None:
            if self.data_semantics != "KNOWN_HISTORICAL_WITH_OFFICIAL_TERMINATION":
                raise DataValidationError("delisted candidates require official-termination data semantics")
            if not any(
                item.official and "TERMINATION" in item.evidence_scopes for item in self.evidence
            ):
                raise DataValidationError("delisted candidates require official termination evidence")

        if self.mapping_class in {"EXACT_BENCHMARK", "EXACT_LOGICAL_EXPOSURE"}:
            required = (
                self.tracking_index_provider,
                self.tracking_index_code,
                self.tracking_index_name,
                self.canonical_index_id,
                self.tracking_return_variant,
            )
            if any(value is None for value in required):
                raise DataValidationError(
                    f"{self.mapping_class} requires provider, code, name, canonical identity, and return variant"
                )
            if not self.evidence_complete:
                raise DataValidationError(
                    f"{self.mapping_class} requires official identity, listing-period, and tracking-index evidence"
                )
            identity = identities.identity(self.canonical_index_id or "")
            if identity.logical_asset_id != self.logical_asset_id:
                raise DataValidationError("canonical index identity belongs to another Logical Asset")
            identities.alias(
                canonical_index_id=self.canonical_index_id or "",
                provider=self.tracking_index_provider or "",
                code=self.tracking_index_code or "",
            )
            frozen = identities.frozen_identity(self.logical_asset_id)
            benchmark_equal = (
                identity.canonical_index_id == frozen.canonical_index_id
                and self.tracking_return_variant == frozen.frozen_return_variant
            )
            if self.mapping_class == "EXACT_BENCHMARK" and not benchmark_equal:
                raise DataValidationError(
                    "EXACT_BENCHMARK requires canonical identity and return variant to match the frozen benchmark"
                )
            if self.mapping_class == "EXACT_LOGICAL_EXPOSURE" and benchmark_equal:
                raise DataValidationError(
                    "EXACT_LOGICAL_EXPOSURE must preserve a disclosed identity or return-variant difference"
                )
        if self.mapping_class == "REJECTED_SEMANTIC_MISMATCH" and not any(
            item.official and "SEMANTIC_MISMATCH" in item.evidence_scopes for item in self.evidence
        ):
            raise DataValidationError(
                "REJECTED_SEMANTIC_MISMATCH requires official semantic-mismatch evidence"
            )


@dataclass(frozen=True, slots=True)
class RegistryCompleteness:
    status: str
    historical_cemetery_complete: bool
    targeted_cemetery_search: str
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
    index_identities: CandidateIndexIdentityRegistry

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        *,
        universe_path: Path,
        index_identity_path: Path,
    ) -> "HistoricalVehicleCandidateEvidencePack":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise DataValidationError("candidate evidence pack must be a mapping")
        forbidden = _find_forbidden_fields(payload)
        if forbidden:
            raise DataValidationError(
                "candidate evidence pack contains selector/performance fields forbidden in M2B.0.1: "
                f"{sorted(forbidden)}"
            )
        universe = FrozenUniverse.from_yaml(universe_path)
        identities = CandidateIndexIdentityRegistry.from_yaml(index_identity_path)
        binding = _required_mapping(payload, "universe_binding")
        completeness_payload = _required_mapping(payload, "registry_completeness")
        evidence_catalog = _parse_evidence_catalog(payload)
        candidates = _parse_candidate_groups(payload, evidence_catalog=evidence_catalog)
        non_vehicle = _parse_non_vehicle(payload)
        pack = cls(
            schema_name=_required_str(payload, "schema_name", "root"),
            schema_version=_required_str(payload, "schema_version", "root"),
            registry_name=_required_str(payload, "registry_name", "root"),
            status=_required_str(payload, "status", "root"),
            source_commit=_required_str(payload, "source_commit", "root"),
            universe_name=_required_str(binding, "universe_name", "universe_binding"),
            universe_file_sha256=_required_str(binding, "universe_file_sha256", "universe_binding"),
            registry_completeness=RegistryCompleteness(
                status=_required_str(completeness_payload, "status", "registry_completeness"),
                historical_cemetery_complete=_required_bool(
                    completeness_payload, "historical_cemetery_complete", "registry_completeness"
                ),
                targeted_cemetery_search=_required_str(
                    completeness_payload, "targeted_cemetery_search", "registry_completeness"
                ),
                scope_note=_required_str(completeness_payload, "scope_note", "registry_completeness"),
            ),
            candidates=tuple(candidates),
            non_vehicle_logical_assets=tuple(non_vehicle),
            index_identities=identities,
        )
        pack.validate(universe=universe, universe_path=universe_path)
        return pack

    def validate(self, *, universe: FrozenUniverse, universe_path: Path) -> None:
        if self.schema_name != "historical_vehicle_candidate_evidence" or self.schema_version != "1.1":
            raise DataValidationError(
                "M2B.0.1 requires historical_vehicle_candidate_evidence schema version 1.1"
            )
        if self.status != REGISTRY_STATUS:
            raise DataValidationError("M2B.0.1 status must be CANDIDATE_NOT_APPROVED")
        if any(token in self.registry_name.upper() for token in {"FINAL", "FROZEN", "PRODUCTION"}):
            raise DataValidationError("candidate evidence pack cannot be named final/frozen/production")
        if not _COMMIT_RE.fullmatch(self.source_commit):
            raise DataValidationError("source_commit must be a full lowercase Git commit hash")
        if self.universe_name != universe.universe_name:
            raise DataValidationError("candidate pack is bound to the wrong frozen Universe")
        if not _SHA256_RE.fullmatch(self.universe_file_sha256):
            raise DataValidationError("universe_file_sha256 must be a lowercase SHA-256")
        if self.universe_file_sha256 != hashlib.sha256(universe_path.read_bytes()).hexdigest():
            raise DataValidationError("frozen Universe file hash differs from the candidate-pack binding")
        completeness = self.registry_completeness
        if completeness.status != COMPLETENESS_STATUS:
            raise DataValidationError("M2B.0.1 registry completeness must be PARTIAL_CURATED")
        if completeness.historical_cemetery_complete:
            raise DataValidationError("targeted search cannot claim historical cemetery completeness")
        if completeness.targeted_cemetery_search in {"COMPLETE", "CEMETERY_COMPLETE"}:
            raise DataValidationError("targeted_cemetery_search must not claim COMPLETE")

        active_ids = {asset.id for asset in universe.active_logical_assets}
        candidate_ids = {candidate.logical_asset_id for candidate in self.candidates}
        for index, candidate in enumerate(self.candidates):
            if candidate.logical_asset_id in {"HSTECH", "OIL"}:
                raise DataValidationError(f"{candidate.logical_asset_id} vehicle discovery is forbidden")
            if candidate.logical_asset_id not in active_ids:
                raise DataValidationError(
                    f"candidate references non-ACTIVE Logical Asset {candidate.logical_asset_id}"
                )
            if candidate.logical_asset_id == "CASH":
                raise DataValidationError("CASH cannot carry an ETF candidate")
            candidate.validate(location=f"candidates[{index}]", identities=self.index_identities)
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
                if left.mapping_effective_to is None or right.mapping_effective_from < left.mapping_effective_to:
                    raise DataValidationError(
                        f"{symbol} has overlapping or duplicate effective mapping periods"
                    )

    def coverage_rows(self) -> tuple[dict[str, str | int], ...]:
        rows: list[dict[str, str | int]] = []
        logical_asset_ids = sorted(
            {candidate.logical_asset_id for candidate in self.candidates} | {"CASH"}
        )
        for logical_asset_id in logical_asset_ids:
            items = [item for item in self.candidates if item.logical_asset_id == logical_asset_id]
            current_exact = [
                item
                for item in items
                if item.is_current
                and item.mapping_class in {"EXACT_BENCHMARK", "EXACT_LOGICAL_EXPOSURE"}
            ]
            historical = [item for item in items if not item.is_current]
            unresolved = [item for item in items if item.mapping_class == "UNRESOLVED"]
            if logical_asset_id == "CASH":
                coverage_status = "NOT_APPLICABLE_CASH_BALANCE"
            elif unresolved:
                coverage_status = "PARTIAL_UNRESOLVED"
            elif current_exact:
                coverage_status = "CURRENT_BREADTH_EVIDENCED"
            else:
                coverage_status = "NO_EXACT_OR_LOGICAL_CURRENT_VEHICLE"
            rows.append(
                {
                    "logical_asset_id": logical_asset_id,
                    "current_exact_or_logical_candidate_count": len(current_exact),
                    "known_historical_candidate_count": len(historical),
                    "known_delisted_count": sum(item.delist_date is not None for item in items),
                    "exact_benchmark_count": sum(item.mapping_class == "EXACT_BENCHMARK" for item in items),
                    "exact_logical_exposure_count": sum(
                        item.mapping_class == "EXACT_LOGICAL_EXPOSURE" for item in items
                    ),
                    "proxy_candidate_count": sum(
                        item.mapping_class == "ECONOMIC_PROXY_CANDIDATE" for item in items
                    ),
                    "rejected_count": sum(
                        item.mapping_class == "REJECTED_SEMANTIC_MISMATCH" for item in items
                    ),
                    "unresolved_count": len(unresolved),
                    "all_discovered_symbols": ";".join(sorted(item.vehicle_symbol for item in items)),
                    "evidence_complete_count": sum(item.evidence_complete for item in items),
                    "coverage_status": coverage_status,
                }
            )
        return tuple(rows)


def _parse_evidence_catalog(payload: Mapping[str, Any]) -> dict[str, CandidateEvidence]:
    catalog = _required_mapping(payload, "evidence_catalog")
    result: dict[str, CandidateEvidence] = {}
    for key, value in catalog.items():
        if not isinstance(value, Mapping):
            raise DataValidationError(f"evidence_catalog.{key} must be a mapping")
        result[str(key)] = CandidateEvidence.from_mapping(
            value, location=f"evidence_catalog.{key}"
        )
    return result


def _parse_candidate_groups(
    payload: Mapping[str, Any], *, evidence_catalog: Mapping[str, CandidateEvidence]
) -> list[VehicleCandidate]:
    groups = _required_mapping(payload, "candidate_groups")
    root_defaults = _required_mapping(payload, "candidate_defaults")
    candidates: list[VehicleCandidate] = []
    for logical_asset_id, group_payload in groups.items():
        location = f"candidate_groups.{logical_asset_id}"
        if not isinstance(group_payload, Mapping):
            raise DataValidationError(f"{location} must be a mapping")
        rows = group_payload.get("vehicles")
        if not isinstance(rows, list) or not rows:
            raise DataValidationError(f"{location}.vehicles must be a non-empty list")
        defaults = {
            **root_defaults,
            **{key: value for key, value in group_payload.items() if key != "vehicles"},
        }
        for row_index, row in enumerate(rows):
            row_location = f"{location}.vehicles[{row_index}]"
            if not isinstance(row, Mapping):
                raise DataValidationError(f"{row_location} must be a mapping")
            merged = {**defaults, **row}
            forbidden = _find_forbidden_fields(merged)
            if forbidden:
                raise DataValidationError(
                    f"{row_location} contains selector/performance fields forbidden in M2B.0.1: "
                    f"{sorted(forbidden)}"
                )
            symbol = _required_str(merged, "vehicle_symbol", row_location)
            list_date = _optional_date(merged.get("list_date"), f"{row_location}.list_date")
            mapping_from = _optional_date(
                merged.get("mapping_effective_from"), f"{row_location}.mapping_effective_from"
            ) or list_date
            if mapping_from is None:
                raise DataValidationError(f"{row_location} requires mapping_effective_from or list_date")
            refs = merged.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                raise DataValidationError(f"{row_location}.evidence_refs must be a non-empty list")
            try:
                evidence = tuple(evidence_catalog[str(ref)] for ref in refs)
            except KeyError as exc:
                raise DataValidationError(f"{row_location} references unknown evidence {exc.args[0]}") from exc
            candidates.append(
                VehicleCandidate(
                    logical_asset_id=str(logical_asset_id),
                    vehicle_symbol=symbol,
                    fund_name=_required_str(merged, "fund_name", row_location),
                    exchange="SSE" if symbol.endswith(".SH") else "SZSE",
                    vehicle_type=_optional_str(merged.get("vehicle_type")) or "ETF",
                    tracking_index_provider=_optional_str(merged.get("tracking_index_provider")),
                    tracking_index_code=_optional_str(merged.get("tracking_index_code")),
                    tracking_index_name=_optional_str(merged.get("tracking_index_name")),
                    canonical_index_id=_optional_str(merged.get("canonical_index_id")),
                    tracking_return_variant=_optional_str(merged.get("tracking_return_variant")),
                    mapping_class=_required_str(merged, "mapping_class", row_location),
                    approval_status=_optional_str(merged.get("approval_status")) or APPROVAL_STATUS,
                    list_date=list_date,
                    delist_date=_optional_date(merged.get("delist_date"), f"{row_location}.delist_date"),
                    mapping_effective_from=mapping_from,
                    mapping_effective_to=_optional_date(
                        merged.get("mapping_effective_to"), f"{row_location}.mapping_effective_to"
                    ),
                    cross_border=_bool_with_default(merged.get("cross_border"), False, row_location),
                    qdii=_bool_with_default(merged.get("qdii"), False, row_location),
                    data_semantics=_optional_str(merged.get("data_semantics"))
                    or "CURRENT_SURVIVOR_WITH_OFFICIAL_PRODUCT_HISTORY",
                    evidence=evidence,
                    notes=_required_str(merged, "notes", row_location),
                )
            )
    return candidates


def _parse_non_vehicle(payload: Mapping[str, Any]) -> list[NonVehicleLogicalAsset]:
    result: list[NonVehicleLogicalAsset] = []
    for logical_asset_id, value in _required_mapping(payload, "non_vehicle_logical_assets").items():
        location = f"non_vehicle_logical_assets.{logical_asset_id}"
        if not isinstance(value, Mapping):
            raise DataValidationError(f"{location} must be a mapping")
        result.append(
            NonVehicleLogicalAsset(
                logical_asset_id=str(logical_asset_id),
                execution_mode=_required_str(value, "execution_mode", location),
                vehicle_required=_required_bool(value, "vehicle_required", location),
                notes=_required_str(value, "notes", location),
            )
        )
    return result


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


def _bool_with_default(value: object, default: bool, location: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise DataValidationError(f"{location} boolean field must be boolean")
    return value


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
