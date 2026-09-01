from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

from etf_quant.data.repositories.metadata_repository import MetadataRepository
from etf_quant.domain.enums import AssetClass, DataAvailabilityClass, PITQueryMode
from etf_quant.domain.models.metadata import ETFMetadataObservation


def observation(
    *,
    snapshot_at: datetime | None,
    available_time: datetime,
    ingest_time: datetime,
    availability_class: DataAvailabilityClass,
    payload_hash: str,
    iopv: str | None = "4.00",
    effective_from: date | None = None,
    delist_date: date | None = None,
) -> ETFMetadataObservation:
    return ETFMetadataObservation(
        symbol="510300.SH",
        tracking_index=None,
        list_date=date(2012, 5, 28),
        delist_date=delist_date,
        trading_cycle=None,
        settlement_cycle=None,
        price_limit_pct=None,
        asset_class=AssetClass.UNKNOWN,
        market_timezone="Asia/Shanghai",
        contract_liquidation_rule=None,
        management_fee=None,
        fund_name="fixture ETF",
        fund_company=None,
        fund_type="ETF",
        nav=None,
        iopv=Decimal(iopv) if iopv is not None else None,
        shares=None,
        aum=None,
        effective_from=effective_from,
        effective_to=None,
        available_time=available_time,
        ingest_time=ingest_time,
        source="akshare",
        availability_class=availability_class,
        snapshot_at=snapshot_at,
        provider_payload_hash=payload_hash,
    )


def test_snapshot_only_cannot_backfill_historical_query(tmp_path) -> None:
    repository = MetadataRepository(tmp_path)
    snapshot_at = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    repository.append_etf_metadata(
        [
            observation(
                snapshot_at=snapshot_at,
                available_time=snapshot_at,
                ingest_time=snapshot_at,
                availability_class=DataAvailabilityClass.SNAPSHOT_ONLY,
                payload_hash="snapshot-20260901",
                effective_from=date(2012, 5, 28),
            )
        ]
    )
    assert repository.get_metadata(
        "510300.SH",
        as_of=datetime(2020, 1, 1, tzinfo=timezone.utc),
        mode=PITQueryMode.ECONOMIC,
    ) is None


def test_forward_collected_pit_selects_latest_snapshot_available_at_as_of(tmp_path) -> None:
    repository = MetadataRepository(tmp_path)
    first_time = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    second_time = datetime(2026, 9, 2, 8, tzinfo=timezone.utc)
    first = observation(
        snapshot_at=first_time,
        available_time=first_time,
        ingest_time=first_time,
        availability_class=DataAvailabilityClass.FORWARD_COLLECTED_PIT,
        payload_hash="day-1",
        iopv="4.00",
        effective_from=first_time.date(),
    )
    second = replace(
        first,
        snapshot_at=second_time,
        available_time=second_time,
        ingest_time=second_time,
        effective_from=second_time.date(),
        provider_payload_hash="day-2",
        iopv=Decimal("4.01"),
    )
    assert repository.append_etf_metadata([first, second]) == 2
    assert repository.get_metadata(
        first.symbol,
        as_of=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        mode=PITQueryMode.ECONOMIC,
    ).iopv == Decimal("4.00")
    assert repository.get_metadata(
        first.symbol,
        as_of=datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
        mode=PITQueryMode.ECONOMIC,
    ).iopv == Decimal("4.01")
    assert len(repository.get_etf_revisions(first.symbol)) == 2


def test_metadata_economic_vs_replay_and_research_cutoff(tmp_path) -> None:
    repository = MetadataRepository(tmp_path)
    item = observation(
        snapshot_at=None,
        available_time=datetime(2019, 1, 2, 8, tzinfo=timezone.utc),
        ingest_time=datetime(2026, 1, 2, 8, tzinfo=timezone.utc),
        availability_class=DataAvailabilityClass.HISTORICAL_LATEST,
        payload_hash="historical-latest",
        effective_from=date(2019, 1, 2),
    )
    repository.append_etf_metadata([item])
    historical_as_of = datetime(2019, 1, 2, 9, tzinfo=timezone.utc)
    assert repository.get_metadata(
        item.symbol, as_of=historical_as_of, mode=PITQueryMode.ECONOMIC
    ) == item
    assert repository.get_metadata(
        item.symbol, as_of=historical_as_of, mode=PITQueryMode.SYSTEM_REPLAY
    ) is None
    assert repository.get_metadata(
        item.symbol,
        as_of=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
        mode=PITQueryMode.SYSTEM_REPLAY,
    ) == item
    assert repository.get_metadata(
        item.symbol,
        as_of=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
        mode=PITQueryMode.ECONOMIC,
        research_data_cutoff=datetime(2025, 12, 31, tzinfo=timezone.utc),
    ) is None


def test_delisted_etf_and_unknown_fields_are_preserved(tmp_path) -> None:
    repository = MetadataRepository(tmp_path)
    item = observation(
        snapshot_at=None,
        available_time=datetime(2019, 1, 2, 8, tzinfo=timezone.utc),
        ingest_time=datetime(2026, 1, 2, 8, tzinfo=timezone.utc),
        availability_class=DataAvailabilityClass.HISTORICAL_LATEST,
        payload_hash="known-delisted",
        effective_from=date(2019, 1, 2),
        delist_date=date(2020, 6, 1),
        iopv=None,
    )
    repository.append_etf_metadata([item])
    stored = repository.get_etf_revisions(item.symbol)[0]
    assert stored.delist_date == date(2020, 6, 1)
    assert stored.iopv is None
    assert stored.tracking_index is None
    assert stored.asset_class is AssetClass.UNKNOWN
