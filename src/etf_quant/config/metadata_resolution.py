from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping

import yaml


ETF_METADATA_FIELDS = (
    "tracking_index",
    "list_date",
    "delist_date",
    "trading_cycle",
    "settlement_cycle",
    "price_limit_pct",
    "asset_class",
    "market_timezone",
    "contract_liquidation_rule",
    "management_fee",
    "fund_name",
    "fund_company",
    "fund_type",
    "nav",
    "iopv",
    "shares",
    "aum",
)

SAME_SOURCE_TEMPORAL_ORDERING = (
    "effective_from",
    "snapshot_at",
    "available_time",
    "ingest_time",
    "provider_payload_hash",
)


class MetadataConflictPolicy(StrEnum):
    PRECEDENCE_WITH_AUDIT = "PRECEDENCE_WITH_AUDIT"
    REQUIRE_AGREEMENT = "REQUIRE_AGREEMENT"


@dataclass(frozen=True, slots=True)
class FieldResolutionPolicy:
    field_name: str
    source_precedence: tuple[str, ...]
    max_age_seconds: int | None
    conflict_policy: MetadataConflictPolicy


@dataclass(frozen=True, slots=True)
class MetadataResolutionPolicy:
    schema_version: int
    policy_id: str
    known_sources: tuple[str, ...]
    same_source_temporal_ordering: tuple[str, ...]
    freshness_clock: str
    fields: Mapping[str, FieldResolutionPolicy]

    @classmethod
    def from_yaml(cls, path: Path) -> "MetadataResolutionPolicy":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise ValueError("metadata resolution policy must be a mapping")
        raw_fields = payload.get("fields")
        if not isinstance(raw_fields, Mapping):
            raise ValueError("metadata resolution policy requires a fields mapping")
        known_sources = _string_tuple(payload.get("known_sources"), "known_sources")
        policies: dict[str, FieldResolutionPolicy] = {}
        for field_name, value in raw_fields.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"fields.{field_name} must be a mapping")
            precedence = _string_tuple(
                value.get("source_precedence"),
                f"fields.{field_name}.source_precedence",
            )
            if len(set(precedence)) != len(precedence):
                raise ValueError(f"fields.{field_name}.source_precedence contains duplicates")
            unknown_sources = set(precedence) - set(known_sources)
            if unknown_sources:
                raise ValueError(
                    f"fields.{field_name} references unknown sources {sorted(unknown_sources)}"
                )
            if set(precedence) != set(known_sources):
                raise ValueError(
                    f"fields.{field_name}.source_precedence must explicitly order every known source"
                )
            max_age_raw = value.get("max_age_seconds")
            max_age = None if max_age_raw is None else int(max_age_raw)
            if max_age is not None and max_age < 0:
                raise ValueError(f"fields.{field_name}.max_age_seconds cannot be negative")
            policies[str(field_name)] = FieldResolutionPolicy(
                field_name=str(field_name),
                source_precedence=precedence,
                max_age_seconds=max_age,
                conflict_policy=MetadataConflictPolicy(str(value.get("conflict_policy"))),
            )
        policy = cls(
            schema_version=int(payload.get("schema_version", 0)),
            policy_id=str(payload.get("policy_id", "")),
            known_sources=known_sources,
            same_source_temporal_ordering=_string_tuple(
                payload.get("same_source_temporal_ordering"),
                "same_source_temporal_ordering",
            ),
            freshness_clock=str(payload.get("freshness_clock", "")),
            fields=policies,
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.schema_version != 1 or not self.policy_id:
            raise ValueError("metadata resolution policy requires schema_version 1 and policy_id")
        if set(self.fields) != set(ETF_METADATA_FIELDS):
            missing = set(ETF_METADATA_FIELDS) - set(self.fields)
            extra = set(self.fields) - set(ETF_METADATA_FIELDS)
            raise ValueError(f"metadata field policy mismatch; missing={sorted(missing)} extra={sorted(extra)}")
        if self.same_source_temporal_ordering != SAME_SOURCE_TEMPORAL_ORDERING:
            raise ValueError("same-source temporal ordering must match the M2A deterministic contract")
        if self.freshness_clock != "SNAPSHOT_AT_OR_AVAILABLE_TIME":
            raise ValueError("unsupported freshness clock")
        if len(set(self.known_sources)) != len(self.known_sources):
            raise ValueError("known_sources contains duplicates")


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    result = tuple(str(item) for item in value)
    if any(not item for item in result):
        raise ValueError(f"{name} cannot contain empty values")
    return result
