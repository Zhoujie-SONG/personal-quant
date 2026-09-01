from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, TypeVar
from zoneinfo import ZoneInfo

from etf_quant.domain.enums import (
    AssetClass,
    DataAvailabilityClass,
    HistoricalDataSemantics,
    IndexHistoryStatus,
    MetadataFreshness,
    PITQueryMode,
    ResolvedFieldStatus,
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


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class FieldObservationSummary(Generic[T]):
    value: T
    source: str
    availability_class: DataAvailabilityClass
    effective_from: date | None
    effective_to: date | None
    available_time: datetime
    ingest_time: datetime
    snapshot_at: datetime | None
    provider_payload_hash: str
    freshness: MetadataFreshness

    def __post_init__(self) -> None:
        if not self.source or not self.provider_payload_hash:
            raise DataValidationError("candidate source and provider_payload_hash are required")
        _require_aware(self.available_time, "available_time")
        _require_aware(self.ingest_time, "ingest_time")
        _require_aware(self.snapshot_at, "snapshot_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            item.name: _json_value(getattr(self, item.name))
            for item in fields(self)
        }


@dataclass(frozen=True, slots=True)
class ResolvedField(Generic[T]):
    field_name: str
    value: T | None
    status: ResolvedFieldStatus
    source: str | None
    availability_class: DataAvailabilityClass | None
    effective_from: date | None
    effective_to: date | None
    available_time: datetime | None
    ingest_time: datetime | None
    snapshot_at: datetime | None
    provider_payload_hash: str | None
    freshness: MetadataFreshness | None
    resolution_reason: str
    candidate_observations: tuple[FieldObservationSummary[Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.field_name or not self.resolution_reason:
            raise DataValidationError("field_name and resolution_reason are required")
        if self.status is ResolvedFieldStatus.RESOLVED and self.value is None:
            raise DataValidationError("RESOLVED field requires a non-null value")
        if self.status in {ResolvedFieldStatus.UNKNOWN, ResolvedFieldStatus.CONFLICT} and self.value is not None:
            raise DataValidationError(f"{self.status.value} field cannot expose a selected value")
        for name in ("available_time", "ingest_time", "snapshot_at"):
            _require_aware(getattr(self, name), name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "value": _json_value(self.value),
            "status": self.status.value,
            "source": self.source,
            "availability_class": (
                self.availability_class.value if self.availability_class is not None else None
            ),
            "effective_from": _json_value(self.effective_from),
            "effective_to": _json_value(self.effective_to),
            "available_time": _json_value(self.available_time),
            "ingest_time": _json_value(self.ingest_time),
            "snapshot_at": _json_value(self.snapshot_at),
            "provider_payload_hash": self.provider_payload_hash,
            "freshness": self.freshness.value if self.freshness is not None else None,
            "resolution_reason": self.resolution_reason,
            "candidate_observations": [item.to_dict() for item in self.candidate_observations],
        }


@dataclass(frozen=True, slots=True)
class ResolvedETFMetadata:
    symbol: str
    as_of: datetime
    mode: PITQueryMode
    research_data_cutoff: datetime | None
    policy_id: str
    tracking_index: ResolvedField[str]
    list_date: ResolvedField[date]
    delist_date: ResolvedField[date]
    trading_cycle: ResolvedField[str]
    settlement_cycle: ResolvedField[str]
    price_limit_pct: ResolvedField[Decimal]
    asset_class: ResolvedField[AssetClass]
    market_timezone: ResolvedField[str]
    contract_liquidation_rule: ResolvedField[str]
    management_fee: ResolvedField[Decimal]
    fund_name: ResolvedField[str]
    fund_company: ResolvedField[str]
    fund_type: ResolvedField[str]
    nav: ResolvedField[Decimal]
    iopv: ResolvedField[Decimal]
    shares: ResolvedField[Decimal]
    aum: ResolvedField[Decimal]

    def __post_init__(self) -> None:
        if not self.symbol or not self.policy_id:
            raise DataValidationError("symbol and policy_id are required")
        _require_aware(self.as_of, "as_of")
        _require_aware(self.research_data_cutoff, "research_data_cutoff")

    def field(self, field_name: str) -> ResolvedField[Any]:
        value = getattr(self, field_name, None)
        if not isinstance(value, ResolvedField):
            raise KeyError(field_name)
        return value

    def to_dict(self) -> dict[str, Any]:
        metadata_fields = {
            item.name: getattr(self, item.name).to_dict()
            for item in fields(self)
            if isinstance(getattr(self, item.name), ResolvedField)
        }
        return {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "mode": self.mode.value,
            "research_data_cutoff": _json_value(self.research_data_cutoff),
            "policy_id": self.policy_id,
            "fields": metadata_fields,
        }


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"unsupported metadata serialization type: {type(value).__name__}")


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
