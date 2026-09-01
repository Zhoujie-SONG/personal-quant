from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.data.repositories.market_repository import ParquetMarketRepository
from etf_quant.domain.enums import AdjustType, CanonicalMarketSource, PITQueryMode
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.market_data import LongbridgeMarketDataProvider
from etf_quant.services.data_ingestion import MarketDataIngestionService


class DailyBarContext:
    def __init__(self, trade_date: date, closes: list[str]) -> None:
        self.trade_date = trade_date
        self.closes = closes
        self.history_calls = 0

    def trading_days(self, *_: object) -> SimpleNamespace:
        return SimpleNamespace(
            trading_days=[self.trade_date],
            half_trading_days=[],
        )

    def history_candlesticks_by_date(self, *_: object) -> list[SimpleNamespace]:
        close = self.closes[self.history_calls]
        self.history_calls += 1
        return [
            SimpleNamespace(
                open="4.000",
                high="4.020",
                low="3.990",
                close=close,
                volume=100,
                turnover="400",
                timestamp=datetime(
                    self.trade_date.year,
                    self.trade_date.month,
                    self.trade_date.day,
                    tzinfo=timezone.utc,
                ),
                trade_session="Normal",
            )
        ]


def build_stack(tmp_path, context: DailyBarContext):
    policy = DailyBarAvailabilityPolicy()
    cache = LongbridgeRawBarCache(tmp_path / "raw")
    provider = LongbridgeMarketDataProvider(
        LongbridgeClient(context, max_attempts=1),
        availability_policy=policy,
        raw_cache=cache,
        sdk_version="test",
    )
    repository = ParquetMarketRepository(tmp_path / "canonical")
    service = MarketDataIngestionService(provider, repository, policy)
    return cache, repository, service


def query(
    repository: ParquetMarketRepository,
    trade_date: date,
    as_of: datetime,
    mode: PITQueryMode,
):
    return repository.get_bars(
        "510300.SH",
        trade_date,
        trade_date,
        source=CanonicalMarketSource.LONGBRIDGE,
        as_of=as_of,
        mode=mode,
    )


def test_provisional_is_audited_but_only_finalized_bar_enters_canonical(
    tmp_path, monkeypatch
) -> None:
    trade_date = date(2024, 1, 4)
    context = DailyBarContext(trade_date, ["4.012", "4.008"])
    cache, repository, service = build_stack(tmp_path, context)
    clock = {"now": datetime(2024, 1, 4, 7, 3, tzinfo=timezone.utc)}
    monkeypatch.setattr(
        "etf_quant.providers.longbridge.market_data.utc_now",
        lambda: clock["now"],
    )

    assert service.ingest_daily_bars("510300.SH", trade_date, trade_date) == 0
    raw = cache.load("510300.SH", trade_date, trade_date, AdjustType.NONE)
    assert [item.close for item in raw] == ["4.012"]
    manifest_path = (
        tmp_path
        / "raw"
        / "longbridge"
        / "bars"
        / "510300.SH"
        / "none"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provisional_dates"] == [trade_date.isoformat()]
    assert manifest["finalized_dates"] == []
    assert query(repository, trade_date, clock["now"], PITQueryMode.ECONOMIC) == []

    clock["now"] = datetime(2024, 1, 4, 7, 16, tzinfo=timezone.utc)
    assert service.ingest_daily_bars("510300.SH", trade_date, trade_date) == 1
    raw = cache.load("510300.SH", trade_date, trade_date, AdjustType.NONE)
    assert [item.close for item in raw] == ["4.012", "4.008"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provisional_dates"] == []
    assert manifest["finalized_dates"] == [trade_date.isoformat()]

    economic = query(
        repository,
        trade_date,
        datetime(2024, 1, 4, 7, 15, 30, tzinfo=timezone.utc),
        PITQueryMode.ECONOMIC,
    )
    assert [item.close for item in economic] == [Decimal("4.008")]
    assert query(
        repository,
        trade_date,
        datetime(2024, 1, 4, 7, 15, 30, tzinfo=timezone.utc),
        PITQueryMode.SYSTEM_REPLAY,
    ) == []
    replay = query(repository, trade_date, clock["now"], PITQueryMode.SYSTEM_REPLAY)
    assert [item.close for item in replay] == [Decimal("4.008")]
    revisions = repository.get_bar_revisions(
        "510300.SH", trade_date, CanonicalMarketSource.LONGBRIDGE.value
    )
    assert [item.bar.close for item in revisions] == [Decimal("4.008")]


def test_old_historical_bar_is_immediately_finalized_and_ingested(
    tmp_path, monkeypatch
) -> None:
    trade_date = date(2019, 1, 2)
    context = DailyBarContext(trade_date, ["4.008"])
    cache, repository, service = build_stack(tmp_path, context)
    retrieved_at = datetime(2026, 1, 2, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "etf_quant.providers.longbridge.market_data.utc_now",
        lambda: retrieved_at,
    )

    assert service.ingest_daily_bars("510300.SH", trade_date, trade_date) == 1
    finalized = cache.load_finalized(
        "510300.SH",
        trade_date,
        trade_date,
        adjust_type=AdjustType.NONE,
        finalization_cutoffs={
            trade_date: datetime(2019, 1, 2, 7, 15, tzinfo=timezone.utc)
        },
    )
    assert [item.close for item in finalized] == ["4.008"]
    economic = query(
        repository,
        trade_date,
        datetime(2019, 1, 2, 7, 16, tzinfo=timezone.utc),
        PITQueryMode.ECONOMIC,
    )
    assert [item.close for item in economic] == [Decimal("4.008")]
