from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from etf_quant.domain.enums import (
    AssetClass,
    DataAvailabilityClass,
    Exchange,
    InstrumentType,
    Market,
)
from etf_quant.domain.exceptions import DataNormalizationError
from etf_quant.domain.models.instrument import Instrument
from etf_quant.domain.models.market_bar import MarketBar
from etf_quant.domain.models.metadata import (
    ETFMetadataObservation,
    TradingCalendarObservation,
)
from etf_quant.domain.models.trading_calendar import TradingCalendarEntry
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.dto import (
    RawETFMetadataObservation,
    RawInstrument,
    RawMarketBar,
    RawTradingDay,
)
from etf_quant.utils.time import shanghai_session_times, shanghai_trade_date


def _decimal(value: str, field_name: str) -> Decimal:
    if not value or not value.strip():
        raise DataNormalizationError(f"missing {field_name}")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise DataNormalizationError(f"invalid {field_name}") from exc
    if not result.is_finite():
        raise DataNormalizationError(f"non-finite {field_name}")
    return result


def normalize_market_bar(
    raw: RawMarketBar,
    availability_policy: DailyBarAvailabilityPolicy,
) -> MarketBar:
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
        available_time=availability_policy.available_at(close_time),
        ingest_time=raw.retrieved_at,
        source=raw.provider,
        availability_policy_id=availability_policy.policy_id,
        historical_data_semantics=raw.historical_data_semantics,
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
    if raw.is_half_day:
        raise DataNormalizationError(
            "half-day session times are unverified; refusing to assume a 15:00 close"
        )
    open_time, close_time = shanghai_session_times(raw.trade_date)
    return TradingCalendarEntry(
        market=Market(raw.market),
        trade_date=raw.trade_date,
        is_open=True,
        session_open=open_time,
        session_close=close_time,
        is_half_day=raw.is_half_day,
    )


def normalize_trading_calendar_observation(
    raw: RawTradingDay,
) -> TradingCalendarObservation:
    entry = normalize_trading_day(raw)
    return TradingCalendarObservation(
        market=entry.market.value,
        trade_date=entry.trade_date,
        is_open=entry.is_open,
        session_open=entry.session_open,
        session_close=entry.session_close,
        is_half_day=entry.is_half_day,
        available_time=raw.retrieved_at,
        ingest_time=raw.retrieved_at,
        source=raw.provider,
    )


def normalize_etf_metadata(
    raw: RawETFMetadataObservation,
    *,
    availability_class: DataAvailabilityClass | None = None,
) -> ETFMetadataObservation:
    return ETFMetadataObservation(
        symbol=raw.symbol,
        tracking_index=raw.tracking_index,
        list_date=_parse_optional_date(raw.list_date),
        delist_date=_parse_optional_date(raw.delist_date),
        trading_cycle=None,
        settlement_cycle=None,
        price_limit_pct=None,
        asset_class=AssetClass.UNKNOWN,
        market_timezone="Asia/Shanghai",
        contract_liquidation_rule=None,
        management_fee=None,
        fund_name=raw.fund_name,
        fund_company=raw.fund_company,
        fund_type=raw.fund_type,
        nav=_optional_decimal(raw.nav, "nav"),
        iopv=_optional_decimal(raw.iopv, "iopv"),
        shares=_optional_decimal(raw.shares, "shares"),
        aum=_optional_decimal(raw.aum, "aum"),
        effective_from=raw.snapshot_at.date(),
        effective_to=None,
        available_time=raw.available_time,
        ingest_time=raw.retrieved_at,
        source=raw.provider,
        availability_class=availability_class or raw.availability_class,
        snapshot_at=raw.snapshot_at,
        provider_payload_hash=raw.provider_payload_hash,
    )


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value[:10].replace("/", "-")
    if len(normalized) == 8 and "-" not in normalized:
        normalized = f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:]}"
    return date.fromisoformat(normalized)


def _optional_decimal(value: str | None, field_name: str) -> Decimal | None:
    return None if value is None else _decimal(value, field_name)
