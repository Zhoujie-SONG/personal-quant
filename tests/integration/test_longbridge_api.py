from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.domain.enums import AdjustType, Market
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.market_data import LongbridgeMarketDataProvider

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def provider(tmp_path_factory: pytest.TempPathFactory) -> LongbridgeMarketDataProvider:
    required = ("LONGBRIDGE_APP_KEY", "LONGBRIDGE_APP_SECRET", "LONGBRIDGE_ACCESS_TOKEN")
    if not all(os.getenv(name) for name in required):
        pytest.skip("Longbridge credential environment variables are not set")
    return LongbridgeMarketDataProvider(
        LongbridgeClient.from_env(),
        availability_policy=DailyBarAvailabilityPolicy(),
        raw_cache=LongbridgeRawBarCache(tmp_path_factory.mktemp("longbridge-raw")),
    )


def test_real_longbridge_market_data_endpoints(provider: LongbridgeMarketDataProvider) -> None:
    end = date.today()
    start = end - timedelta(days=12)
    assert provider.get_static_info(["510300.SH"])
    assert provider.get_daily_bars("510300.SH", start, end, AdjustType.NONE)
    assert provider.get_daily_bars("000300.SH", start, end, AdjustType.NONE)
    assert provider.get_trading_days(Market.CN, start, end)
    assert provider.get_quote(["510300.SH"])
