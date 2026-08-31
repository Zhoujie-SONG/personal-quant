from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from etf_quant.data.repositories.market_repository import ParquetMarketRepository
from etf_quant.domain.models.market_bar import MarketBar


def canonical_bar() -> MarketBar:
    return MarketBar(
        symbol="510300.SH",
        trade_date=date(2024, 1, 2),
        open=Decimal("3.50000000"),
        high=Decimal("3.60000000"),
        low=Decimal("3.40000000"),
        close=Decimal("3.55000000"),
        volume=100,
        turnover=Decimal("355.0000"),
        data_time=datetime(2024, 1, 2, 7, 0, tzinfo=timezone.utc),
        available_time=datetime(2024, 1, 2, 7, 0, tzinfo=timezone.utc),
        ingest_time=datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc),
        source="longbridge",
    )


def test_repository_upserts_monthly_and_enforces_pit_as_of(tmp_path) -> None:
    repository = ParquetMarketRepository(tmp_path)
    assert repository.upsert_bars([canonical_bar()]) == 1
    assert repository.upsert_bars([canonical_bar()]) == 1
    partition_files = list(tmp_path.glob("market_bars/year=2024/month=01/*.parquet"))
    assert len(partition_files) == 1

    before_close = repository.get_bars(
        "510300.SH",
        date(2024, 1, 1),
        date(2024, 1, 31),
        as_of=datetime(2024, 1, 2, 6, 59, tzinfo=timezone.utc),
    )
    after_close = repository.get_bars(
        "510300.SH",
        date(2024, 1, 1),
        date(2024, 1, 31),
        as_of=datetime(2024, 1, 2, 7, 0, tzinfo=timezone.utc),
    )
    assert before_close == []
    assert len(after_close) == 1
    assert after_close[0].close == Decimal("3.55000000")

