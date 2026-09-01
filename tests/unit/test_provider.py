from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.domain.enums import AdjustType, Market
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.market_data import LongbridgeMarketDataProvider


class FakeContext:
    def __init__(self) -> None:
        self.history_calls = 0

    def static_info(self, symbols: list[str]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                symbol=symbols[0], name_cn="300ETF", name_en="CSI 300 ETF",
                exchange="SSE", currency="CNY", lot_size=100,
                listing_date=date(2012, 5, 28), board="CNFund",
            )
        ]

    def history_candlesticks_by_date(self, *_: object) -> list[SimpleNamespace]:
        self.history_calls += 1
        return [
            SimpleNamespace(
                open="3.5", high="3.6", low="3.4", close="3.55", volume=100,
                turnover="355", timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
                trade_session="Normal",
            )
        ]

    def trading_days(self, *_: object) -> SimpleNamespace:
        return SimpleNamespace(trading_days=[date(2024, 1, 2)], half_trading_days=[])

    def quote(self, symbols: list[str]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                symbol=symbols[0], last_done="3.55", prev_close="3.50", open="3.5",
                high="3.6", low="3.4", volume=100, turnover="355",
                timestamp=datetime(2024, 1, 2, 7, tzinfo=timezone.utc), trade_status="Normal",
            )
        ]


def test_provider_maps_all_endpoints_and_reuses_history_cache(tmp_path) -> None:
    context = FakeContext()
    provider = LongbridgeMarketDataProvider(
        LongbridgeClient(context, max_attempts=1),
        availability_policy=DailyBarAvailabilityPolicy(),
        raw_cache=LongbridgeRawBarCache(tmp_path),
        sdk_version="test",
    )
    assert provider.get_static_info(["510300.SH"])[0].lot_size == 100
    first = provider.get_daily_bars(
        "510300.SH", date(2024, 1, 1), date(2024, 1, 3), AdjustType.NONE
    )
    second = provider.get_daily_bars(
        "510300.SH", date(2024, 1, 1), date(2024, 1, 3), AdjustType.NONE
    )
    assert len(first) == len(second) == 1
    assert context.history_calls == 1
    assert provider.get_trading_days(Market.CN, date(2024, 1, 1), date(2024, 1, 3))[0].trade_date == date(2024, 1, 2)
    assert provider.get_quote(["510300.SH"])[0].last_done == "3.55"
