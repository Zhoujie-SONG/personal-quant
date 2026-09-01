from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from etf_quant.domain.enums import Market


@dataclass(frozen=True, slots=True)
class TradingCalendarEntry:
    market: Market
    trade_date: date
    is_open: bool
    session_open: datetime | None
    session_close: datetime | None
    is_half_day: bool = False

    def __post_init__(self) -> None:
        if self.is_open and (self.session_open is None or self.session_close is None):
            raise ValueError("open days require session_open and session_close")
        for field_name in ("session_open", "session_close"):
            value = getattr(self, field_name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.session_open and self.session_close and self.session_close <= self.session_open:
            raise ValueError("session_close must be after session_open")
