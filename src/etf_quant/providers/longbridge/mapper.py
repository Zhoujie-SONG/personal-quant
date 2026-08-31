from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from etf_quant.domain.enums import Exchange
from etf_quant.providers.dto import RawInstrument, RawMarketBar, RawQuote, RawTradingDay
from etf_quant.utils.time import provider_datetime


def to_longbridge_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    parts = normalized.split(".")
    if len(parts) != 2 or len(parts[0]) != 6 or not parts[0].isdigit():
        raise ValueError(f"invalid A-share symbol: {symbol!r}")
    if parts[1] not in {Exchange.SHANGHAI.value, Exchange.SHENZHEN.value}:
        raise ValueError(f"unsupported A-share exchange suffix: {parts[1]!r}")
    return normalized


def _value(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _payload(obj: Any, fields: Iterable[str]) -> dict[str, Any]:
    return {name: _json_value(_value(obj, name)) for name in fields}


def map_static_info(
    obj: Any,
    *,
    retrieved_at: datetime,
    sdk_version: str,
) -> RawInstrument:
    fields = (
        "symbol", "name_cn", "name_en", "name_hk", "listing_date", "exchange",
        "currency", "lot_size", "total_shares", "circulating_shares", "hk_shares",
        "eps", "eps_ttm", "bps", "dividend_yield", "stock_derivatives", "board",
    )
    listing_date = _value(obj, "listing_date")
    return RawInstrument(
        symbol=str(_value(obj, "symbol")),
        name_cn=str(_value(obj, "name_cn", "") or ""),
        name_en=str(_value(obj, "name_en", "") or ""),
        exchange=str(_value(obj, "exchange", "") or ""),
        currency=str(_value(obj, "currency", "") or ""),
        lot_size=int(_value(obj, "lot_size", 0)),
        listing_date=_json_value(listing_date) if listing_date else None,
        board=str(_value(obj, "board", "") or ""),
        retrieved_at=retrieved_at,
        provider="longbridge",
        sdk_version=sdk_version,
        provider_payload=_payload(obj, fields),
    )


def map_market_bar(
    obj: Any,
    *,
    symbol: str,
    retrieved_at: datetime,
    sdk_version: str,
) -> RawMarketBar:
    fields = ("open", "high", "low", "close", "volume", "turnover", "timestamp", "trade_session")
    return RawMarketBar(
        symbol=symbol,
        open=str(_value(obj, "open", "")),
        high=str(_value(obj, "high", "")),
        low=str(_value(obj, "low", "")),
        close=str(_value(obj, "close", "")),
        volume=int(_value(obj, "volume", 0)),
        turnover=str(_value(obj, "turnover", "0")),
        provider_timestamp=provider_datetime(_value(obj, "timestamp")),
        retrieved_at=retrieved_at,
        provider="longbridge",
        sdk_version=sdk_version,
        provider_payload=_payload(obj, fields),
    )


def map_quote(
    obj: Any,
    *,
    retrieved_at: datetime,
    sdk_version: str,
) -> RawQuote:
    fields = (
        "symbol", "last_done", "prev_close", "open", "high", "low", "timestamp",
        "volume", "turnover", "trade_status",
    )
    return RawQuote(
        symbol=str(_value(obj, "symbol")),
        last_done=str(_value(obj, "last_done", "")),
        prev_close=str(_value(obj, "prev_close", "")),
        open=str(_value(obj, "open", "")),
        high=str(_value(obj, "high", "")),
        low=str(_value(obj, "low", "")),
        volume=int(_value(obj, "volume", 0)),
        turnover=str(_value(obj, "turnover", "0")),
        provider_timestamp=provider_datetime(_value(obj, "timestamp")),
        trade_status=str(_value(obj, "trade_status", "")),
        retrieved_at=retrieved_at,
        provider="longbridge",
        sdk_version=sdk_version,
        provider_payload=_payload(obj, fields),
    )


def map_trading_days(
    response: Any,
    *,
    market: str,
    retrieved_at: datetime,
    sdk_version: str,
) -> list[RawTradingDay]:
    half_days = set(_value(response, "half_trading_days", []) or [])
    return [
        RawTradingDay(
            market=market,
            trade_date=trade_day,
            is_half_day=trade_day in half_days,
            retrieved_at=retrieved_at,
            provider="longbridge",
            sdk_version=sdk_version,
            provider_payload={"trade_date": trade_day.isoformat(), "is_half_day": trade_day in half_days},
        )
        for trade_day in (_value(response, "trading_days", []) or [])
    ]
