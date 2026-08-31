from __future__ import annotations

from datetime import date
from typing import Protocol, Sequence, runtime_checkable

from etf_quant.domain.enums import AdjustType, Market
from etf_quant.providers.dto import RawInstrument, RawMarketBar, RawQuote, RawTradingDay


@runtime_checkable
class MarketDataProvider(Protocol):
    """Provider boundary. No vendor SDK type may cross this protocol."""

    @property
    def name(self) -> str: ...

    def get_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType = AdjustType.NONE,
    ) -> list[RawMarketBar]: ...

    def get_quote(self, symbols: Sequence[str]) -> list[RawQuote]: ...

    def get_static_info(self, symbols: Sequence[str]) -> list[RawInstrument]: ...

    def get_trading_days(
        self,
        market: Market,
        start_date: date,
        end_date: date,
    ) -> list[RawTradingDay]: ...

