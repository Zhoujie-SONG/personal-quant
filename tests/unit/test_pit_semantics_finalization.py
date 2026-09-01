from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from etf_quant.data.repositories.market_repository import (
    ParquetMarketRepository,
    market_bar_observation_id,
    market_bar_value_hash,
)
from etf_quant.domain.enums import (
    CanonicalMarketSource,
    HistoricalDataSemantics,
    PITQueryMode,
)
from etf_quant.domain.exceptions import DataValidationError, SchemaMigrationRequiredError
from etf_quant.domain.models.market_bar import MarketBar


def bar(
    *,
    trade_date: date = date(2019, 1, 2),
    ingest_time: datetime = datetime(2026, 1, 2, 8, tzinfo=timezone.utc),
    source: str = "longbridge",
) -> MarketBar:
    data_time = datetime(
        trade_date.year, trade_date.month, trade_date.day, 7, tzinfo=timezone.utc
    )
    return MarketBar(
        symbol="510300.SH",
        trade_date=trade_date,
        open=Decimal("3.95"),
        high=Decimal("4.10"),
        low=Decimal("3.90"),
        close=Decimal("4.00"),
        volume=100,
        turnover=Decimal("400"),
        data_time=data_time,
        available_time=data_time + timedelta(minutes=15),
        ingest_time=ingest_time,
        source=source,
        availability_policy_id="daily_bar_eod_v1_15m",
        historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
    )


def query(
    repository: ParquetMarketRepository,
    *,
    as_of: datetime,
    mode: PITQueryMode,
) -> list[MarketBar]:
    return repository.get_bars(
        "510300.SH",
        date(2019, 1, 2),
        date(2019, 1, 2),
        source=CanonicalMarketSource.LONGBRIDGE,
        as_of=as_of,
        mode=mode,
    )


def test_economic_and_system_replay_have_distinct_ingest_semantics(tmp_path) -> None:
    repository = ParquetMarketRepository(tmp_path)
    repository.append_bars([bar()])
    historical_as_of = datetime(2019, 1, 2, 8, tzinfo=timezone.utc)

    assert query(repository, as_of=historical_as_of, mode=PITQueryMode.ECONOMIC)
    assert query(repository, as_of=historical_as_of, mode=PITQueryMode.SYSTEM_REPLAY) == []
    assert query(
        repository,
        as_of=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
        mode=PITQueryMode.SYSTEM_REPLAY,
    )

    with pytest.raises(TypeError):
        repository.get_bars(
            "510300.SH",
            date(2019, 1, 2),
            date(2019, 1, 2),
            source=CanonicalMarketSource.LONGBRIDGE,
            as_of=historical_as_of,
        )


def test_value_hash_is_independent_of_availability_policy(tmp_path) -> None:
    repository = ParquetMarketRepository(tmp_path)
    original = bar()
    changed_policy = replace(
        original,
        available_time=original.data_time + timedelta(minutes=30),
        availability_policy_id="daily_bar_eod_v2_30m",
    )
    assert market_bar_value_hash(original) == market_bar_value_hash(changed_policy)
    assert market_bar_observation_id(original) != market_bar_observation_id(changed_policy)

    repository.append_bars([original, changed_policy])
    revisions = repository.get_bar_revisions(
        original.symbol, original.trade_date, original.source
    )
    assert len(revisions) == 2
    assert len({revision.value_hash for revision in revisions}) == 1
    assert len({revision.availability_policy_id for revision in revisions}) == 2


def test_historical_semantics_conflict_for_same_observation_fails_fast(tmp_path) -> None:
    repository = ParquetMarketRepository(tmp_path)
    original = bar()
    conflicting = replace(
        original,
        historical_data_semantics=HistoricalDataSemantics.TRUE_HISTORICAL_VINTAGE,
    )
    assert market_bar_observation_id(original) == market_bar_observation_id(conflicting)

    repository.append_bars([original])
    with pytest.raises(DataValidationError, match="historical_data_semantics conflict"):
        repository.append_bars([conflicting])

    revisions = repository.get_bar_revisions(
        original.symbol, original.trade_date, original.source
    )
    assert len(revisions) == 1
    assert revisions[0].bar.historical_data_semantics is (
        HistoricalDataSemantics.HISTORICAL_LATEST
    )


def test_formal_query_is_explicitly_limited_to_longbridge_source(tmp_path) -> None:
    repository = ParquetMarketRepository(tmp_path)
    repository.append_bars([bar(), bar(source="reconciliation")])
    result = query(
        repository,
        as_of=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
        mode=PITQueryMode.ECONOMIC,
    )
    assert len(result) == 1
    assert result[0].source == CanonicalMarketSource.LONGBRIDGE.value


def test_mixed_legacy_schema_requires_explicit_migration(tmp_path) -> None:
    repository = ParquetMarketRepository(tmp_path)
    current = bar(trade_date=date(2019, 2, 1))
    repository.append_bars([current])

    legacy = bar()
    legacy_path = (
        tmp_path / "market_bars" / "year=2019" / "month=01" / "part-00000.parquet"
    )
    legacy_path.parent.mkdir(parents=True)
    legacy_row = {
        "revision_schema_version": 2,
        "observation_id": "legacy-observation",
        "payload_hash": "legacy-payload",
        "symbol": legacy.symbol,
        "trade_date": legacy.trade_date,
        "open": legacy.open,
        "high": legacy.high,
        "low": legacy.low,
        "close": legacy.close,
        "volume": legacy.volume,
        "turnover": legacy.turnover,
        "data_time": legacy.data_time,
        "available_time": legacy.available_time,
        "ingest_time": legacy.ingest_time,
        "source": legacy.source,
    }
    pq.write_table(pa.Table.from_pylist([legacy_row]), legacy_path)

    with pytest.raises(SchemaMigrationRequiredError, match="explicit v3 migration"):
        repository.get_bar_revisions(legacy.symbol, legacy.trade_date, legacy.source)

    assert repository.migrate_to_latest_schema() == 1
    assert set(repository.schema_versions().values()) == {3}
    revisions = repository.get_bar_revisions(
        legacy.symbol, legacy.trade_date, legacy.source
    )
    assert len(revisions) == 1
    assert revisions[0].availability_policy_id == "legacy_inferred_daily_bar_900s"
    assert revisions[0].bar.historical_data_semantics is (
        HistoricalDataSemantics.HISTORICAL_LATEST
    )
