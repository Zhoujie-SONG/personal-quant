from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

from etf_quant.config.metadata_resolution import (
    ETF_METADATA_FIELDS,
    FieldResolutionPolicy,
    MetadataConflictPolicy,
    MetadataResolutionPolicy,
)
from etf_quant.domain.enums import (
    AssetClass,
    MetadataFreshness,
    PITQueryMode,
    ResolvedFieldStatus,
)
from etf_quant.domain.exceptions import DataValidationError
from etf_quant.domain.models.metadata import (
    ETFMetadataObservation,
    FieldObservationSummary,
    ResolvedETFMetadata,
    ResolvedField,
)


class MetadataObservationRepository(Protocol):
    def get_metadata_observations(
        self,
        symbol: str,
        *,
        as_of: datetime,
        mode: PITQueryMode,
        research_data_cutoff: datetime | None = None,
        source: str | None = None,
    ) -> list[ETFMetadataObservation]: ...


@dataclass(frozen=True, slots=True)
class _FieldCandidate:
    observation: ETFMetadataObservation
    value: Any
    freshness: MetadataFreshness

    def summary(self) -> FieldObservationSummary[Any]:
        item = self.observation
        return FieldObservationSummary(
            value=self.value,
            source=item.source,
            availability_class=item.availability_class,
            effective_from=item.effective_from,
            effective_to=item.effective_to,
            available_time=item.available_time,
            ingest_time=item.ingest_time,
            snapshot_at=item.snapshot_at,
            provider_payload_hash=item.provider_payload_hash,
            freshness=self.freshness,
        )


class MetadataResolver:
    """Resolve eligible immutable ETF observations independently by field."""

    def __init__(
        self,
        repository: MetadataObservationRepository,
        policy: MetadataResolutionPolicy,
    ) -> None:
        self._repository = repository
        self._policy = policy

    def resolve(
        self,
        symbol: str,
        *,
        as_of: datetime,
        mode: PITQueryMode,
        research_data_cutoff: datetime | None = None,
    ) -> ResolvedETFMetadata:
        if not symbol:
            raise DataValidationError("symbol is required")
        _require_aware(as_of, "as_of")
        if research_data_cutoff is not None:
            _require_aware(research_data_cutoff, "research_data_cutoff")
        if not isinstance(mode, PITQueryMode):
            raise DataValidationError("mode must be an explicit PITQueryMode")

        observations = self._repository.get_metadata_observations(
            symbol,
            as_of=as_of,
            mode=mode,
            research_data_cutoff=research_data_cutoff,
        )
        unknown_sources = {item.source for item in observations} - set(self._policy.known_sources)
        if unknown_sources:
            raise DataValidationError(
                f"eligible metadata contains unconfigured sources: {sorted(unknown_sources)}"
            )
        resolved = {
            field_name: self._resolve_field(
                field_name,
                observations,
                as_of,
                self._policy.fields[field_name],
            )
            for field_name in ETF_METADATA_FIELDS
        }
        return ResolvedETFMetadata(
            symbol=symbol,
            as_of=as_of,
            mode=mode,
            research_data_cutoff=research_data_cutoff,
            policy_id=self._policy.policy_id,
            **resolved,
        )

    def _resolve_field(
        self,
        field_name: str,
        observations: list[ETFMetadataObservation],
        as_of: datetime,
        field_policy: FieldResolutionPolicy,
    ) -> ResolvedField[Any]:
        candidates: dict[str, _FieldCandidate] = {}
        for source in field_policy.source_precedence:
            source_values = [
                item
                for item in observations
                if item.source == source and not _is_unknown_value(field_name, getattr(item, field_name))
            ]
            if not source_values:
                continue
            selected = _latest_same_source(field_name, source_values)
            candidates[source] = _FieldCandidate(
                observation=selected,
                value=getattr(selected, field_name),
                freshness=_freshness(selected, as_of, field_policy.max_age_seconds),
            )

        ordered = [candidates[source] for source in field_policy.source_precedence if source in candidates]
        summaries = tuple(item.summary() for item in ordered)
        if not ordered:
            return _empty_field(
                field_name,
                ResolvedFieldStatus.UNKNOWN,
                "all eligible source observations are null or absent for this field",
                summaries,
            )

        fresh = [item for item in ordered if item.freshness is not MetadataFreshness.EXPIRED]
        if not fresh:
            distinct = {_comparable_value(item.value) for item in ordered}
            if (
                field_policy.conflict_policy is MetadataConflictPolicy.REQUIRE_AGREEMENT
                and len(distinct) > 1
            ):
                return _empty_field(
                    field_name,
                    ResolvedFieldStatus.STALE,
                    "all non-null candidates are stale and disagree; no stale winner selected",
                    summaries,
                    freshness=MetadataFreshness.EXPIRED,
                )
            selected = ordered[0]
            return _selected_field(
                field_name,
                selected,
                ResolvedFieldStatus.STALE,
                "all non-null candidates exceed the configured freshness limit; "
                "highest-precedence stale value retained for audit",
                summaries,
            )

        if field_policy.conflict_policy is MetadataConflictPolicy.REQUIRE_AGREEMENT:
            distinct = {_comparable_value(item.value) for item in fresh}
            if len(distinct) > 1:
                return _empty_field(
                    field_name,
                    ResolvedFieldStatus.CONFLICT,
                    "fresh require-agreement sources disagree; no winner selected",
                    summaries,
                )

        selected = fresh[0]
        selected_index = field_policy.source_precedence.index(selected.observation.source)
        if selected_index == 0:
            reason = f"selected highest-precedence fresh source {selected.observation.source}"
        else:
            skipped = ", ".join(field_policy.source_precedence[:selected_index])
            reason = (
                f"fallback to {selected.observation.source}; higher-precedence sources "
                f"({skipped}) had no fresh non-null value"
            )
        if len({_comparable_value(item.value) for item in ordered}) > 1:
            reason += "; competing source disagreement retained in candidate_observations"
        return _selected_field(
            field_name,
            selected,
            ResolvedFieldStatus.RESOLVED,
            reason,
            summaries,
        )


def _same_source_order(item: ETFMetadataObservation) -> tuple[date, datetime, datetime, datetime]:
    minimum = datetime.min.replace(tzinfo=UTC)
    return (
        item.effective_from or date.min,
        item.snapshot_at or minimum,
        item.available_time,
        item.ingest_time,
    )


def _latest_same_source(
    field_name: str,
    observations: list[ETFMetadataObservation],
) -> ETFMetadataObservation:
    latest_order = max(_same_source_order(item) for item in observations)
    latest = [item for item in observations if _same_source_order(item) == latest_order]
    values = {_comparable_value(getattr(item, field_name)) for item in latest}
    if len(values) > 1:
        raise DataValidationError(
            f"ambiguous same-source {field_name} revisions share the latest semantic "
            "temporal key but disagree in value"
        )
    return max(latest, key=lambda item: item.provider_payload_hash)


def _freshness(
    item: ETFMetadataObservation,
    as_of: datetime,
    max_age_seconds: int | None,
) -> MetadataFreshness:
    if max_age_seconds is None:
        return MetadataFreshness.NOT_APPLICABLE
    reference = item.snapshot_at or item.available_time
    age_seconds = (
        as_of.astimezone(UTC) - reference.astimezone(UTC)
    ).total_seconds()
    return (
        MetadataFreshness.FRESH
        if age_seconds <= max_age_seconds
        else MetadataFreshness.EXPIRED
    )


def _is_unknown_value(field_name: str, value: object) -> bool:
    if value is None:
        return True
    if field_name == "asset_class" and value is AssetClass.UNKNOWN:
        return True
    return isinstance(value, str) and not value.strip()


def _comparable_value(value: object) -> tuple[str, str]:
    if isinstance(value, AssetClass):
        return (type(value).__name__, value.value)
    return (type(value).__name__, str(value))


def _selected_field(
    field_name: str,
    selected: _FieldCandidate,
    status: ResolvedFieldStatus,
    reason: str,
    summaries: tuple[FieldObservationSummary[Any], ...],
) -> ResolvedField[Any]:
    item = selected.observation
    return ResolvedField(
        field_name=field_name,
        value=selected.value,
        status=status,
        source=item.source,
        availability_class=item.availability_class,
        effective_from=item.effective_from,
        effective_to=item.effective_to,
        available_time=item.available_time,
        ingest_time=item.ingest_time,
        snapshot_at=item.snapshot_at,
        provider_payload_hash=item.provider_payload_hash,
        freshness=selected.freshness,
        resolution_reason=reason,
        candidate_observations=summaries,
    )


def _empty_field(
    field_name: str,
    status: ResolvedFieldStatus,
    reason: str,
    summaries: tuple[FieldObservationSummary[Any], ...],
    *,
    freshness: MetadataFreshness | None = None,
) -> ResolvedField[Any]:
    return ResolvedField(
        field_name=field_name,
        value=None,
        status=status,
        source=None,
        availability_class=None,
        effective_from=None,
        effective_to=None,
        available_time=None,
        ingest_time=None,
        snapshot_at=None,
        provider_payload_hash=None,
        freshness=freshness,
        resolution_reason=reason,
        candidate_observations=summaries,
    )


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataValidationError(f"{name} must be timezone-aware")
