from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from etf_quant.config.reconciliation import ReconciliationConfig
from etf_quant.data.repositories.metadata_repository import MetadataRepository
from etf_quant.domain.enums import (
    DataAvailabilityClass,
    HistoricalDataSemantics,
    ReconciliationStatus,
)
from etf_quant.providers.dto import RawETFMetadataObservation, RawMarketBar
from etf_quant.services.metadata_snapshot import MetadataSnapshotService
from etf_quant.services.reconciliation import reconcile_bars


def raw_snapshot() -> RawETFMetadataObservation:
    timestamp = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    return RawETFMetadataObservation(
        symbol="510300.SH",
        fund_name="fixture ETF",
        tracking_index=None,
        list_date=None,
        delist_date=None,
        fund_type="ETF",
        fund_company=None,
        nav=None,
        iopv="4.00",
        shares="100",
        aum=None,
        snapshot_at=timestamp,
        available_time=timestamp,
        retrieved_at=timestamp,
        provider="akshare",
        availability_class=DataAvailabilityClass.SNAPSHOT_ONLY,
        provider_payload_hash="stable-provider-payload",
    )


class SnapshotProvider:
    def get_etf_snapshots(self) -> list[RawETFMetadataObservation]:
        return [raw_snapshot()]

    def get_szse_scale_snapshots(self) -> list[RawETFMetadataObservation]:
        return []


def test_snapshot_service_is_idempotent_and_promotes_to_forward_collected(tmp_path) -> None:
    repository = MetadataRepository(tmp_path)
    service = MetadataSnapshotService(SnapshotProvider(), repository)
    assert service.snapshot() == 1
    assert service.snapshot() == 0
    revisions = repository.get_etf_revisions("510300.SH")
    assert len(revisions) == 1
    assert revisions[0].availability_class is DataAvailabilityClass.FORWARD_COLLECTED_PIT


def raw_bar(*, close: str, volume: int, turnover: str, source: str) -> RawMarketBar:
    return RawMarketBar(
        symbol="510300.SH",
        open="4.00",
        high="4.02",
        low="3.99",
        close=close,
        volume=volume,
        turnover=turnover,
        provider_timestamp=datetime(2026, 8, 31, 7, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        provider=source,
        sdk_version="test",
        historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
    )


def test_reconciliation_tolerance_emits_pass_warning_and_fail() -> None:
    config = ReconciliationConfig(
        symbols=("510300.SH",),
        price_abs_tolerance=Decimal("0.005"),
        volume_relative_tolerance=Decimal("0.02"),
        turnover_relative_tolerance=Decimal("0.02"),
        warning_multiplier=Decimal("2"),
    )
    primary = [raw_bar(close="4.000", volume=10000, turnover="40000", source="longbridge")]
    passing = [raw_bar(close="4.004", volume=9900, turnover="39800", source="akshare")]
    warning = [raw_bar(close="4.008", volume=9700, turnover="39000", source="akshare")]
    failing = [raw_bar(close="4.020", volume=8000, turnover="30000", source="akshare")]
    assert reconcile_bars(primary, passing, config)[0].status is ReconciliationStatus.PASS
    assert reconcile_bars(primary, warning, config)[0].status is ReconciliationStatus.WARNING
    assert reconcile_bars(primary, failing, config)[0].status is ReconciliationStatus.FAIL
