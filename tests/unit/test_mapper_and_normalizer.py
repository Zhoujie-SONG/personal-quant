from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from etf_quant.data.canonical.normalizers import normalize_market_bar
from etf_quant.domain.exceptions import DataNormalizationError
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.dto import RawMarketBar
from etf_quant.providers.longbridge.mapper import map_market_bar, to_longbridge_symbol


@pytest.mark.parametrize(
    ("input_symbol", "expected"),
    [("510300.sh", "510300.SH"), (" 159915.SZ ", "159915.SZ"), ("600519.SH", "600519.SH")],
)
def test_longbridge_symbol_mapping(input_symbol: str, expected: str) -> None:
    assert to_longbridge_symbol(input_symbol) == expected


@pytest.mark.parametrize("symbol", ["510300", "AAPL.US", "123.SH", "ABCDEF.SZ"])
def test_invalid_or_unsupported_symbol_is_rejected(symbol: str) -> None:
    with pytest.raises(ValueError):
        to_longbridge_symbol(symbol)


def test_sdk_bar_maps_to_raw_then_canonical_without_float() -> None:
    sdk_bar = SimpleNamespace(
        open="3.5001",
        high="3.6002",
        low="3.4003",
        close="3.5504",
        volume=123456,
        turnover="438320.1234",
        timestamp=datetime(2024, 1, 2, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        trade_session="Normal",
    )
    retrieved_at = datetime(2024, 1, 2, 8, 5, tzinfo=timezone.utc)
    raw = map_market_bar(
        sdk_bar,
        symbol="510300.SH",
        retrieved_at=retrieved_at,
        sdk_version="test",
    )
    policy = DailyBarAvailabilityPolicy(eod_delay=timedelta(minutes=15))
    bar = normalize_market_bar(raw, policy)
    assert str(bar.open) == "3.5001"
    assert str(bar.turnover) == "438320.1234"
    assert bar.data_time.hour == 15
    assert bar.available_time == bar.data_time + timedelta(minutes=15)
    assert bar.ingest_time == retrieved_at


@pytest.mark.parametrize(("field", "value"), [("open", ""), ("close", "NaN"), ("turnover", "bad")])
def test_missing_or_invalid_raw_data_is_rejected(field: str, value: str) -> None:
    raw_values = {
        "symbol": "510300.SH",
        "open": "3.5",
        "high": "3.6",
        "low": "3.4",
        "close": "3.55",
        "volume": 1,
        "turnover": "3.55",
        "provider_timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
        "retrieved_at": datetime(2024, 1, 2, 16, tzinfo=timezone.utc),
        "provider": "longbridge",
        "sdk_version": "test",
    }
    raw_values[field] = value
    with pytest.raises(DataNormalizationError):
        normalize_market_bar(
            RawMarketBar(**raw_values),  # type: ignore[arg-type]
            DailyBarAvailabilityPolicy(),
        )
