from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from etf_quant.domain.enums import (
    AssetClass,
    DataAvailabilityClass,
    HistoricalDataSemantics,
    IndexHistoryStatus,
)
from etf_quant.domain.exceptions import DataValidationError


def _require_aware(value: datetime | None, field_name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise DataValidationError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ETFMetadataObservation:
    symbol: str
    tracking_index: str | None
    list_date: date | None
    delist_date: date | None
    trading_cycle: str | None
    settlement_cycle: str | None
    price_limit_pct: Decimal | None
    asset_class: AssetClass
    market_timezone: str
    contract_liquidation_rule: str | None
    management_fee: Decimal | None
    fund_name: str | None
    fund_company: str | None
    fund_type: str | None
    nav: Decimal | None
    iopv: Decimal | None
    shares: Decimal | None
    aum: Decimal | None
    effective_from: date | None
    effective_to: date | None
    available_time: datetime
    ingest_time: datetime
    source: str
    availability_class: DataAvailabilityClass
    snapshot_at: datetime | None
    provider_payload_hash: str

    def __post_init__(self) -> None:
        if not self.symbol or not self.source or not self.provider_payload_hash:
            raise DataValidationError("symbol, source, and provider_payload_hash are required")
        _require_aware(self.available_time, "available_time")
        _require_aware(self.ingest_time, "ingest_time")
        _require_aware(self.snapshot_at, "snapshot_at")
        ZoneInfo(self.market_timezone)
        if self.delist_date and self.list_date and self.delist_date < self.list_date:
            raise DataValidationError("delist_date cannot precede list_date")
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            raise DataValidationError("effective_to cannot precede effective_from")
        if self.availability_class in {
            DataAvailabilityClass.SNAPSHOT_ONLY,
            DataAvailabilityClass.FORWARD_COLLECTED_PIT,
        } and self.snapshot_at is None:
            raise DataValidationError("snapshot availability classes require snapshot_at")
        for field_name in ("price_limit_pct", "management_fee", "nav", "iopv", "shares", "aum"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise DataValidationError(f"{field_name} cannot be negative")


@dataclass(frozen=True, slots=True)
class IndexMetadata:
    index_code: str
    base_date: date | None
    launch_date: date | None
    methodology_version: str | None
    is_total_return: bool | None
    source: str
    availability_class: DataAvailabilityClass
    effective_from: date | None
    effective_to: date | None
    available_time: datetime
    ingest_time: datetime
    snapshot_at: datetime | None
    source_note: str | None = None

    def __post_init__(self) -> None:
        if not self.index_code or not self.source:
            raise DataValidationError("index_code and source are required")
        _require_aware(self.available_time, "available_time")
        _require_aware(self.ingest_time, "ingest_time")
        _require_aware(self.snapshot_at, "snapshot_at")
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            raise DataValidationError("effective_to cannot precede effective_from")
        if self.availability_class in {
            DataAvailabilityClass.SNAPSHOT_ONLY,
            DataAvailabilityClass.FORWARD_COLLECTED_PIT,
        } and self.snapshot_at is None:
            raise DataValidationError("snapshot availability classes require snapshot_at")

    def history_status(self, data_date: date) -> IndexHistoryStatus | None:
        if self.launch_date is None:
            return None
        if data_date < self.launch_date:
            return IndexHistoryStatus.BACKFILLED
        return IndexHistoryStatus.LIVE


@dataclass(frozen=True, slots=True)
class TradingCalendarObservation:
    market: str
    trade_date: date
    is_open: bool
    session_open: datetime | None
    session_close: datetime | None
    is_half_day: bool
    available_time: datetime
    ingest_time: datetime
    source: str
    historical_data_semantics: HistoricalDataSemantics
    availability_policy_id: str

    def __post_init__(self) -> None:
        if not self.market or not self.source or not self.availability_policy_id:
            raise DataValidationError(
                "market, source, and availability_policy_id are required"
            )
        _require_aware(self.session_open, "session_open")
        _require_aware(self.session_close, "session_close")
        _require_aware(self.available_time, "available_time")
        _require_aware(self.ingest_time, "ingest_time")
        if self.is_open and (self.session_open is None or self.session_close is None):
            raise DataValidationError("open days require session times")
