from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pyarrow.parquet as pq

from etf_quant.data.repositories.market_repository import (
    REVISION_SCHEMA_VERSION,
    ParquetMarketRepository,
)
from etf_quant.domain.enums import (
    CanonicalMarketSource,
    HistoricalDataSemantics,
    PITQueryMode,
)
from etf_quant.domain.models.market_bar import MarketBar


def canonical_bar(*, close: str, ingest_hour: int) -> MarketBar:
    return MarketBar(
        symbol="510300.SH",
        trade_date=date(2024, 1, 2),
        open=Decimal("3.95000000"),
        high=Decimal("4.10000000"),
        low=Decimal("3.90000000"),
        close=Decimal(close),
        volume=100,
        turnover=Decimal("400.0000"),
        data_time=datetime(2024, 1, 2, 7, 0, tzinfo=timezone.utc),
        available_time=datetime(2024, 1, 2, 7, 15, tzinfo=timezone.utc),
        ingest_time=datetime(2024, 1, 2, ingest_hour, 0, tzinfo=timezone.utc),
        source="longbridge",
        availability_policy_id="daily_bar_eod_v1_15m",
        historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
    )


def query(repository: ParquetMarketRepository, as_of_hour: int) -> list[MarketBar]:
    return repository.get_bars(
        "510300.SH",
        date(2024, 1, 1),
        date(2024, 1, 31),
        source=CanonicalMarketSource.LONGBRIDGE,
        as_of=datetime(2024, 1, 2, as_of_hour, 0, tzinfo=timezone.utc),
        mode=PITQueryMode.SYSTEM_REPLAY,
    )


def test_revision_log_preserves_old_observation_and_pit_selects_latest_known(tmp_path) -> None:
    repository = ParquetMarketRepository(tmp_path)
    first = canonical_bar(close="4.00000000", ingest_hour=8)
    correction = canonical_bar(close="4.01000000", ingest_hour=12)

    assert repository.append_bars([first]) == 1
    assert repository.append_bars([correction]) == 1
    assert repository.append_bars([correction]) == 1  # exact observation is idempotent

    assert query(repository, 7) == []
    assert query(repository, 10)[0].close == Decimal("4.00000000")
    assert query(repository, 13)[0].close == Decimal("4.01000000")

    revisions = repository.get_bar_revisions(
        "510300.SH", date(2024, 1, 2), "longbridge"
    )
    assert [item.bar.close for item in revisions] == [
        Decimal("4.00000000"),
        Decimal("4.01000000"),
    ]
    assert len({item.observation_id for item in revisions}) == 2
    assert len({item.value_hash for item in revisions}) == 2


def test_revision_parquet_schema_contains_identity_fields(tmp_path) -> None:
    repository = ParquetMarketRepository(tmp_path)
    repository.append_bars([canonical_bar(close="4.00000000", ingest_hour=8)])
    path = next(tmp_path.glob("market_bars/year=2024/month=01/*.parquet"))
    table = pq.read_table(path)
    assert {
        "revision_schema_version",
        "observation_id",
        "value_hash",
        "availability_policy_id",
        "historical_data_semantics",
        "ingest_time",
    }.issubset(table.column_names)
    assert table.column("revision_schema_version").to_pylist() == [REVISION_SCHEMA_VERSION]
