from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from etf_quant.domain.models.market_bar import MarketBar


def make_bar(**overrides: object) -> MarketBar:
    shanghai = ZoneInfo("Asia/Shanghai")
    values: dict[str, object] = {
        "symbol": "510300.SH",
        "trade_date": date(2024, 1, 2),
        "open": Decimal("3.50"),
        "high": Decimal("3.60"),
        "low": Decimal("3.40"),
        "close": Decimal("3.55"),
        "volume": 100,
        "turnover": Decimal("355.00"),
        "data_time": datetime(2024, 1, 2, 15, 0, tzinfo=shanghai),
        "available_time": datetime(2024, 1, 2, 15, 0, tzinfo=shanghai),
        "ingest_time": datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc),
        "source": "longbridge",
    }
    values.update(overrides)
    return MarketBar(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("low", Decimal("3.51")),
        ("high", Decimal("3.54")),
        ("volume", -1),
        ("turnover", Decimal("-0.01")),
    ],
)
def test_market_bar_rejects_inconsistent_ohlcv(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        make_bar(**{field: value})


def test_market_bar_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_bar(ingest_time=datetime(2024, 1, 2, 16, 0))


def test_available_time_cannot_precede_close_time() -> None:
    shanghai = ZoneInfo("Asia/Shanghai")
    with pytest.raises(ValueError, match="available_time"):
        make_bar(available_time=datetime(2024, 1, 2, 14, 59, tzinfo=shanghai))

