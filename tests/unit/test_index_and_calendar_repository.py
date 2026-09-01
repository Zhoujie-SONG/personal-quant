from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from etf_quant.data.canonical.normalizers import normalize_trading_day
from etf_quant.data.repositories.calendar_repository import TradingCalendarRepository
from etf_quant.data.repositories.metadata_repository import MetadataRepository
from etf_quant.domain.enums import (
    DataAvailabilityClass,
    IndexHistoryStatus,
    Market,
    PITQueryMode,
)
from etf_quant.domain.models.metadata import IndexMetadata, TradingCalendarObservation
from etf_quant.domain.exceptions import DataNormalizationError
from etf_quant.providers.dto import RawTradingDay


def test_index_before_launch_is_backfilled_and_after_launch_is_live(tmp_path) -> None:
    item = IndexMetadata(
        index_code="FIXTURE.INDEX",
        base_date=None,
        launch_date=date(2020, 1, 2),
        methodology_version=None,
        is_total_return=None,
        source="curated-fixture",
        availability_class=DataAvailabilityClass.SNAPSHOT_ONLY,
        effective_from=date(2020, 1, 2),
        effective_to=None,
        available_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ingest_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        snapshot_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        source_note="unit-test fixture",
    )
    assert item.history_status(date(2019, 12, 31)) is IndexHistoryStatus.BACKFILLED
    assert item.history_status(date(2020, 1, 2)) is IndexHistoryStatus.LIVE
    repository = MetadataRepository(tmp_path)
    assert repository.append_index_metadata([item]) == 1
    assert repository.append_index_metadata([item]) == 0
    assert repository.get_index_metadata(
        item.index_code,
        as_of=datetime(2020, 1, 2, tzinfo=timezone.utc),
        mode=PITQueryMode.ECONOMIC,
    ) is None
    assert repository.get_index_metadata(
        item.index_code,
        as_of=datetime(2026, 1, 3, tzinfo=timezone.utc),
        mode=PITQueryMode.SYSTEM_REPLAY,
    ) == item


def test_trading_calendar_repository_preserves_half_day_and_pit_modes(tmp_path) -> None:
    repository = TradingCalendarRepository(tmp_path)
    item = TradingCalendarObservation(
        market="CN",
        trade_date=date(2019, 1, 2),
        is_open=True,
        session_open=datetime(2019, 1, 2, 1, 30, tzinfo=timezone.utc),
        session_close=datetime(2019, 1, 2, 4, 0, tzinfo=timezone.utc),
        is_half_day=True,
        available_time=datetime(2018, 12, 31, tzinfo=timezone.utc),
        ingest_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        source="longbridge",
    )
    assert repository.append_entries([item]) == 1
    economic = repository.get_calendar(
        Market.CN,
        item.trade_date,
        item.trade_date,
        as_of=datetime(2019, 1, 1, tzinfo=timezone.utc),
        mode=PITQueryMode.ECONOMIC,
    )
    assert len(economic) == 1
    assert economic[0].is_half_day is True
    assert economic[0].session_close.hour == 4
    assert repository.get_calendar(
        Market.CN,
        item.trade_date,
        item.trade_date,
        as_of=datetime(2019, 1, 1, tzinfo=timezone.utc),
        mode=PITQueryMode.SYSTEM_REPLAY,
    ) == []
    assert repository.get_calendar(
        Market.CN,
        item.trade_date,
        item.trade_date,
        as_of=datetime(2026, 1, 3, tzinfo=timezone.utc),
        mode=PITQueryMode.SYSTEM_REPLAY,
    ) == [item]


def test_unverified_half_day_does_not_assume_normal_session_close() -> None:
    with pytest.raises(DataNormalizationError, match="half-day session times are unverified"):
        normalize_trading_day(
            RawTradingDay(
                market="CN",
                trade_date=date(2026, 9, 1),
                is_half_day=True,
                retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                provider="longbridge",
                sdk_version="test",
            )
        )
