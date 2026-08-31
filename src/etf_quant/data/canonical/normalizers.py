from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from etf_quant.domain.enums import AssetClass, Exchange, InstrumentType, Market
from etf_quant.domain.models.instrument import Instrument
from etf_quant.domain.models.market_bar import MarketBar
from etf_quant.domain.models.trading_calendar import TradingCalendarEntry
from etf_quant.providers.dto import RawInstrument, RawMarketBar, RawTradingDay
from etf_quant.providers.longbridge.exceptions import LongbridgeDataError
from etf_quant.utils.time import shanghai_session_times, shanghai_trade_date


def _decimal(value: str, field_name: str) -> Decimal:
    if not value or not value.strip():
        raise LongbridgeDataError(
            f"missing {field_name}", operation="normalize_market_bar"
        )
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise LongbridgeDataError(
            f"invalid {field_name}", operation="normalize_market_bar"
        ) from exc
    if not result.is_finite():
        raise LongbridgeDataError(
            f"non-finite {field_name}", operation="normalize_market_bar"
        )
    return result


def normalize_market_bar(raw: RawMarketBar) -> MarketBar:
    trade_date = shanghai_trade_date(raw.provider_timestamp)
    _, close_time = shanghai_session_times(trade_date)
    return MarketBar(
        symbol=raw.symbol,
        trade_date=trade_date,
        open=_decimal(raw.open, "open"),
        high=_decimal(raw.high, "high"),
        low=_decimal(raw.low, "low"),
        close=_decimal(raw.close, "close"),
        volume=raw.volume,
        turnover=_decimal(raw.turnover, "turnover"),
        data_time=close_time,
        available_time=close_time,
        ingest_time=raw.retrieved_at,
        source=raw.provider,
    )


def normalize_instrument(raw: RawInstrument) -> Instrument:
    suffix = raw.symbol.rsplit(".", 1)[-1].upper()
    exchange = {
        "SH": Exchange.SHANGHAI,
        "SZ": Exchange.SHENZHEN,
    }.get(suffix, Exchange.UNKNOWN)
    name = raw.name_cn or raw.name_en or raw.symbol
    board = raw.board.lower()
    if raw.symbol.startswith(("15", "16", "50", "51", "52", "56", "58")):
        instrument_type = InstrumentType.ETF
    elif "index" in board:
        instrument_type = InstrumentType.INDEX
    else:
        instrument_type = InstrumentType.UNKNOWN
    list_date = _parse_optional_date(raw.listing_date)
    return Instrument(
        symbol=raw.symbol,
        exchange=exchange,
        name=name,
        instrument_type=instrument_type,
        asset_class=AssetClass.UNKNOWN,
        currency=raw.currency,
        list_date=list_date,
        delist_date=None,
        lot_size=raw.lot_size,
        market_timezone="Asia/Shanghai",
    )


def normalize_trading_day(raw: RawTradingDay) -> TradingCalendarEntry:
    open_time, close_time = shanghai_session_times(raw.trade_date)
    return TradingCalendarEntry(
        market=Market(raw.market),
        trade_date=raw.trade_date,
        is_open=True,
        session_open=open_time,
        session_close=close_time,
    )


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value[:10].replace("/", "-")
    if len(normalized) == 8 and "-" not in normalized:
        normalized = f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:]}"
    return date.fromisoformat(normalized)

