from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping

from etf_quant.domain.enums import DataAvailabilityClass, HistoricalDataSemantics


@dataclass(frozen=True, slots=True)
class RawInstrument:
    symbol: str
    name_cn: str
    name_en: str
    exchange: str
    currency: str
    lot_size: int
    listing_date: str | None
    board: str
    retrieved_at: datetime
    provider: str
    sdk_version: str
    provider_payload: Mapping[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class RawMarketBar:
    symbol: str
    open: str
    high: str
    low: str
    close: str
    volume: int
    turnover: str
    provider_timestamp: datetime
    retrieved_at: datetime
    provider: str
    sdk_version: str
    historical_data_semantics: HistoricalDataSemantics
    provider_payload: Mapping[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class RawQuote:
    symbol: str
    last_done: str
    prev_close: str
    open: str
    high: str
    low: str
    volume: int
    turnover: str
    provider_timestamp: datetime
    trade_status: str
    retrieved_at: datetime
    provider: str
    sdk_version: str
    provider_payload: Mapping[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class RawTradingDay:
    market: str
    trade_date: date
    is_half_day: bool
    retrieved_at: datetime
    provider: str
    sdk_version: str
    provider_payload: Mapping[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class RawETFMetadataObservation:
    symbol: str
    fund_name: str | None
    tracking_index: str | None
    list_date: str | None
    delist_date: str | None
    fund_type: str | None
    fund_company: str | None
    nav: str | None
    iopv: str | None
    shares: str | None
    aum: str | None
    snapshot_at: datetime
    available_time: datetime
    retrieved_at: datetime
    provider: str
    availability_class: DataAvailabilityClass
    provider_payload_hash: str
    provider_payload: Mapping[str, Any] = field(default_factory=dict, repr=False)
