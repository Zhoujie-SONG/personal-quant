from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from etf_quant.config.metadata_resolution import (
    ETF_METADATA_FIELDS,
    MetadataConflictPolicy,
    MetadataResolutionPolicy,
)
from etf_quant.data.repositories.metadata_repository import MetadataRepository
from etf_quant.domain.enums import (
    AssetClass,
    DataAvailabilityClass,
    MetadataFreshness,
    PITQueryMode,
    ResolvedFieldStatus,
)
from etf_quant.domain.exceptions import DataValidationError
from etf_quant.domain.models.metadata import ETFMetadataObservation
from etf_quant.services.metadata_resolution import MetadataResolver


ROOT = Path(__file__).parents[2]
POLICY_PATH = ROOT / "configs" / "metadata_resolution.yaml"
UNIVERSE_PATH = ROOT / "configs" / "universe_v1.yaml"
SPOT = "akshare:fund_etf_spot_em"
SCALE = "akshare:fund_etf_scale_szse"
SYMBOL = "510300.SH"


def policy() -> MetadataResolutionPolicy:
    return MetadataResolutionPolicy.from_yaml(POLICY_PATH)


def resolver(tmp_path: Path, observations: list[ETFMetadataObservation]) -> MetadataResolver:
    repository = MetadataRepository(tmp_path)
    repository.append_etf_metadata(observations)
    return MetadataResolver(repository, policy())


def observation(
    *,
    source: str,
    observed_at: datetime,
    payload_hash: str,
    availability_class: DataAvailabilityClass = DataAvailabilityClass.SNAPSHOT_ONLY,
    available_time: datetime | None = None,
    ingest_time: datetime | None = None,
    snapshot_at: datetime | None | object = ...,  # Ellipsis means observed_at.
    effective_from: date | None | object = ...,
    **overrides: object,
) -> ETFMetadataObservation:
    values: dict[str, object] = {
        "symbol": SYMBOL,
        "tracking_index": None,
        "list_date": None,
        "delist_date": None,
        "trading_cycle": None,
        "settlement_cycle": None,
        "price_limit_pct": None,
        "asset_class": AssetClass.UNKNOWN,
        "market_timezone": "Asia/Shanghai",
        "contract_liquidation_rule": None,
        "management_fee": None,
        "fund_name": None,
        "fund_company": None,
        "fund_type": None,
        "nav": None,
        "iopv": None,
        "shares": None,
        "aum": None,
        "effective_from": observed_at.date() if effective_from is ... else effective_from,
        "effective_to": None,
        "available_time": available_time or observed_at,
        "ingest_time": ingest_time or observed_at,
        "source": source,
        "availability_class": availability_class,
        "snapshot_at": observed_at if snapshot_at is ... else snapshot_at,
        "provider_payload_hash": payload_hash,
    }
    values.update(overrides)
    return ETFMetadataObservation(**values)  # type: ignore[arg-type]


def test_policy_is_versioned_and_covers_every_metadata_field() -> None:
    loaded = policy()

    assert loaded.schema_version == 1
    assert loaded.policy_id == "etf_metadata_field_resolution_v1"
    assert set(loaded.fields) == set(ETF_METADATA_FIELDS)
    assert loaded.fields["tracking_index"].conflict_policy is MetadataConflictPolicy.REQUIRE_AGREEMENT
    assert loaded.fields["iopv"].max_age_seconds == 3600
    assert loaded.fields["nav"].max_age_seconds == 259200
    assert loaded.fields["shares"].max_age_seconds == 2678400
    assert loaded.fields["aum"].max_age_seconds == 2678400


def test_field_level_merge_preserves_spot_iopv_and_scale_list_date_provenance(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    scale = observation(
        source=SCALE,
        observed_at=timestamp,
        payload_hash="scale-list-date",
        list_date=date(2012, 5, 28),
    )
    spot = observation(
        source=SPOT,
        observed_at=timestamp + timedelta(minutes=1),
        payload_hash="spot-iopv",
        iopv=Decimal("4.012"),
    )

    result = resolver(tmp_path, [spot, scale]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(minutes=30),
        mode=PITQueryMode.ECONOMIC,
    )

    assert result.list_date.value == date(2012, 5, 28)
    assert result.list_date.source == SCALE
    assert result.list_date.provider_payload_hash == "scale-list-date"
    assert result.iopv.value == Decimal("4.012")
    assert result.iopv.source == SPOT
    assert result.iopv.provider_payload_hash == "spot-iopv"


def test_newer_whole_row_cannot_erase_complementary_older_source_field(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    scale = observation(
        source=SCALE,
        observed_at=timestamp,
        payload_hash="scale-company",
        fund_company="Example Fund Co",
    )
    newer_spot = observation(
        source=SPOT,
        observed_at=timestamp + timedelta(minutes=10),
        payload_hash="newer-spot",
        fund_company=None,
        iopv=Decimal("4.01"),
    )

    result = resolver(tmp_path, [newer_spot, scale]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(minutes=20),
        mode=PITQueryMode.ECONOMIC,
    )

    assert result.fund_company.value == "Example Fund Co"
    assert result.fund_company.source == SCALE
    assert result.iopv.source == SPOT


def test_snapshot_only_observation_cannot_answer_historical_as_of(tmp_path) -> None:
    observed_at = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    item = observation(
        source=SPOT,
        observed_at=observed_at,
        payload_hash="future-snapshot",
        iopv=Decimal("4.00"),
    )

    result = resolver(tmp_path, [item]).resolve(
        SYMBOL,
        as_of=datetime(2020, 1, 1, tzinfo=timezone.utc),
        mode=PITQueryMode.ECONOMIC,
    )

    assert result.iopv.status is ResolvedFieldStatus.UNKNOWN
    assert result.iopv.value is None
    assert result.iopv.candidate_observations == ()


def test_resolver_inherits_economic_vs_system_replay_from_repository(tmp_path) -> None:
    available = datetime(2019, 1, 2, 8, tzinfo=timezone.utc)
    ingested = datetime(2026, 1, 2, 8, tzinfo=timezone.utc)
    item = observation(
        source=SPOT,
        observed_at=available,
        payload_hash="historical-latest",
        availability_class=DataAvailabilityClass.HISTORICAL_LATEST,
        snapshot_at=None,
        effective_from=date(2019, 1, 2),
        available_time=available,
        ingest_time=ingested,
        tracking_index="000300.SH",
    )
    service = resolver(tmp_path, [item])
    as_of = datetime(2019, 1, 2, 9, tzinfo=timezone.utc)

    economic = service.resolve(SYMBOL, as_of=as_of, mode=PITQueryMode.ECONOMIC)
    replay = service.resolve(SYMBOL, as_of=as_of, mode=PITQueryMode.SYSTEM_REPLAY)

    assert economic.tracking_index.value == "000300.SH"
    assert replay.tracking_index.status is ResolvedFieldStatus.UNKNOWN


def test_research_data_cutoff_is_passed_to_repository_eligibility(tmp_path) -> None:
    available = datetime(2019, 1, 2, 8, tzinfo=timezone.utc)
    ingested = datetime(2026, 1, 2, 8, tzinfo=timezone.utc)
    item = observation(
        source=SPOT,
        observed_at=available,
        payload_hash="late-ingest",
        availability_class=DataAvailabilityClass.HISTORICAL_LATEST,
        snapshot_at=None,
        effective_from=date(2019, 1, 2),
        available_time=available,
        ingest_time=ingested,
        tracking_index="000300.SH",
    )
    service = resolver(tmp_path, [item])
    as_of = datetime(2026, 2, 1, tzinfo=timezone.utc)

    visible = service.resolve(SYMBOL, as_of=as_of, mode=PITQueryMode.ECONOMIC)
    cut_off = service.resolve(
        SYMBOL,
        as_of=as_of,
        mode=PITQueryMode.ECONOMIC,
        research_data_cutoff=datetime(2025, 12, 31, tzinfo=timezone.utc),
    )

    assert visible.tracking_index.status is ResolvedFieldStatus.RESOLVED
    assert cut_off.tracking_index.status is ResolvedFieldStatus.UNKNOWN


def test_source_precedence_selects_scale_shares_and_audits_disagreement(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    scale = observation(
        source=SCALE,
        observed_at=timestamp,
        payload_hash="scale-shares",
        shares=Decimal("100000000"),
    )
    spot = observation(
        source=SPOT,
        observed_at=timestamp,
        payload_hash="spot-shares",
        shares=Decimal("99000000"),
    )

    field = resolver(tmp_path, [spot, scale]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(hours=1),
        mode=PITQueryMode.ECONOMIC,
    ).shares

    assert field.status is ResolvedFieldStatus.RESOLVED
    assert field.value == Decimal("100000000")
    assert field.source == SCALE
    assert len(field.candidate_observations) == 2
    assert "disagreement retained" in field.resolution_reason


def test_higher_priority_null_falls_back_to_lower_priority_valid_source(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    scale = observation(
        source=SCALE,
        observed_at=timestamp,
        payload_hash="scale-null",
        shares=None,
    )
    spot = observation(
        source=SPOT,
        observed_at=timestamp,
        payload_hash="spot-valid",
        shares=Decimal("99000000"),
    )

    field = resolver(tmp_path, [scale, spot]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(hours=1),
        mode=PITQueryMode.ECONOMIC,
    ).shares

    assert field.value == Decimal("99000000")
    assert field.source == SPOT
    assert "fallback" in field.resolution_reason


def test_dynamic_field_freshness_distinguishes_resolved_from_stale(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    item = observation(
        source=SPOT,
        observed_at=timestamp,
        payload_hash="spot-iopv",
        iopv=Decimal("4.00"),
    )
    service = resolver(tmp_path, [item])

    fresh = service.resolve(
        SYMBOL,
        as_of=timestamp + timedelta(minutes=30),
        mode=PITQueryMode.ECONOMIC,
    ).iopv
    stale = service.resolve(
        SYMBOL,
        as_of=timestamp + timedelta(hours=2),
        mode=PITQueryMode.ECONOMIC,
    ).iopv

    assert fresh.status is ResolvedFieldStatus.RESOLVED
    assert fresh.freshness is MetadataFreshness.FRESH
    assert stale.status is ResolvedFieldStatus.STALE
    assert stale.freshness is MetadataFreshness.EXPIRED
    assert stale.value == Decimal("4.00")


def test_require_agreement_disagreement_is_conflict_without_winner(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    scale = observation(
        source=SCALE,
        observed_at=timestamp,
        payload_hash="scale-index",
        tracking_index="000300.SH",
    )
    spot = observation(
        source=SPOT,
        observed_at=timestamp,
        payload_hash="spot-index",
        tracking_index="000905.SH",
    )

    field = resolver(tmp_path, [spot, scale]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(minutes=1),
        mode=PITQueryMode.ECONOMIC,
    ).tracking_index

    assert field.status is ResolvedFieldStatus.CONFLICT
    assert field.value is None
    assert field.source is None
    assert {item.value for item in field.candidate_observations} == {"000300.SH", "000905.SH"}


def test_all_null_values_remain_unknown(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    scale = observation(source=SCALE, observed_at=timestamp, payload_hash="scale-null", iopv=None)
    spot = observation(source=SPOT, observed_at=timestamp, payload_hash="spot-null", iopv=None)

    field = resolver(tmp_path, [spot, scale]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(minutes=30),
        mode=PITQueryMode.ECONOMIC,
    ).iopv

    assert field.status is ResolvedFieldStatus.UNKNOWN
    assert field.value is None
    assert field.source is None


def test_same_source_revisions_use_deterministic_temporal_and_hash_order(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    earlier_hash = observation(
        source=SPOT,
        observed_at=timestamp,
        payload_hash="aaa",
        iopv=Decimal("4.00"),
    )
    later_hash = replace(earlier_hash, provider_payload_hash="zzz", iopv=Decimal("4.01"))

    field = resolver(tmp_path, [later_hash, earlier_hash]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(minutes=30),
        mode=PITQueryMode.ECONOMIC,
    ).iopv

    assert field.value == Decimal("4.01")
    assert field.provider_payload_hash == "zzz"
    assert len(field.candidate_observations) == 1


def test_same_source_exact_ordering_tie_with_different_values_fails_fast(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    first = observation(
        source=SPOT,
        observed_at=timestamp,
        payload_hash="same-provider-hash",
        iopv=Decimal("4.00"),
    )
    conflicting = replace(first, iopv=Decimal("4.01"))
    service = resolver(tmp_path, [first, conflicting])

    with pytest.raises(DataValidationError, match="share every configured ordering key"):
        service.resolve(
            SYMBOL,
            as_of=timestamp + timedelta(minutes=30),
            mode=PITQueryMode.ECONOMIC,
        )


def test_naive_as_of_and_cutoff_fail_fast(tmp_path) -> None:
    service = resolver(tmp_path, [])

    with pytest.raises(DataValidationError, match="as_of must be timezone-aware"):
        service.resolve(SYMBOL, as_of=datetime(2026, 9, 1), mode=PITQueryMode.ECONOMIC)
    with pytest.raises(DataValidationError, match="research_data_cutoff must be timezone-aware"):
        service.resolve(
            SYMBOL,
            as_of=datetime(2026, 9, 1, tzinfo=timezone.utc),
            mode=PITQueryMode.ECONOMIC,
            research_data_cutoff=datetime(2026, 9, 1),
        )


def test_field_level_provenance_survives_json_serialization_and_access(tmp_path) -> None:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    item = observation(
        source=SPOT,
        observed_at=timestamp,
        payload_hash="serializable-iopv",
        iopv=Decimal("4.012"),
    )
    result = resolver(tmp_path, [item]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(minutes=30),
        mode=PITQueryMode.ECONOMIC,
    )

    encoded = json.dumps(result.to_dict(), ensure_ascii=False)
    decoded = json.loads(encoded)

    assert result.field("iopv") is result.iopv
    assert decoded["fields"]["iopv"]["value"] == "4.012"
    assert decoded["fields"]["iopv"]["source"] == SPOT
    assert decoded["fields"]["iopv"]["provider_payload_hash"] == "serializable-iopv"
    assert decoded["fields"]["iopv"]["candidate_observations"][0]["availability_class"] == "snapshot_only"


def test_resolver_never_modifies_frozen_universe(tmp_path) -> None:
    before = UNIVERSE_PATH.read_bytes()
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    item = observation(
        source=SPOT,
        observed_at=timestamp,
        payload_hash="no-universe-side-effect",
        iopv=Decimal("4.00"),
    )

    resolver(tmp_path, [item]).resolve(
        SYMBOL,
        as_of=timestamp + timedelta(minutes=30),
        mode=PITQueryMode.ECONOMIC,
    )

    assert UNIVERSE_PATH.read_bytes() == before
