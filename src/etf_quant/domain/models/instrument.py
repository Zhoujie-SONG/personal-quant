from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from etf_quant.domain.enums import AssetClass, Exchange, InstrumentType


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    exchange: Exchange
    name: str
    instrument_type: InstrumentType
    asset_class: AssetClass
    currency: str
    list_date: date | None
    delist_date: date | None
    lot_size: int
    market_timezone: str = "Asia/Shanghai"

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol is required")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.delist_date and self.list_date and self.delist_date < self.list_date:
            raise ValueError("delist_date cannot precede list_date")
        ZoneInfo(self.market_timezone)

