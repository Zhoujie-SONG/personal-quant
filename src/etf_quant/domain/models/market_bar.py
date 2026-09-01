from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from etf_quant.domain.enums import HistoricalDataSemantics
from etf_quant.domain.exceptions import DataValidationError


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataValidationError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MarketBar:
    symbol: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    turnover: Decimal
    data_time: datetime
    available_time: datetime
    ingest_time: datetime
    source: str
    availability_policy_id: str
    historical_data_semantics: HistoricalDataSemantics

    def __post_init__(self) -> None:
        for field_name in ("data_time", "available_time", "ingest_time"):
            _require_aware(getattr(self, field_name), field_name)
        if not self.symbol or not self.source or not self.availability_policy_id:
            raise DataValidationError(
                "symbol, source, and availability_policy_id are required"
            )
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise DataValidationError("OHLC prices must be positive")
        if self.low > min(self.open, self.close):
            raise DataValidationError("low cannot exceed open or close")
        if self.high < max(self.open, self.close):
            raise DataValidationError("high cannot be below open or close")
        if self.high < self.low:
            raise DataValidationError("high cannot be below low")
        if self.volume < 0 or self.turnover < 0:
            raise DataValidationError("volume and turnover cannot be negative")
        if self.available_time < self.data_time:
            raise DataValidationError("available_time cannot precede market data_time")
