from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from etf_quant.domain.enums import AssetClass, DataAvailabilityClass, PITQueryMode
from etf_quant.domain.exceptions import DataValidationError
from etf_quant.domain.models.metadata import ETFMetadataObservation, IndexMetadata


class MetadataRepository:
    """Immutable SQLite observation repository for ETF and index metadata."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "instrument_metadata.sqlite3"
        self._initialize()

    def append_etf_metadata(self, observations: Iterable[ETFMetadataObservation]) -> int:
        rows = list(observations)
        with self._connect() as connection:
            before = connection.total_changes
            for item in rows:
                payload = _etf_payload(item)
                observation_id = _stable_id(payload)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO etf_metadata_observations
                    (observation_id, symbol, source, availability_class,
                     effective_from, effective_to, available_time, ingest_time,
                     snapshot_at, provider_payload_hash, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        item.symbol,
                        item.source,
                        item.availability_class.value,
                        _optional_date(item.effective_from),
                        _optional_date(item.effective_to),
                        _datetime(item.available_time),
                        _datetime(item.ingest_time),
                        _optional_datetime(item.snapshot_at),
                        item.provider_payload_hash,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
            return connection.total_changes - before

    def get_metadata(
        self,
        symbol: str,
        *,
        as_of: datetime,
        mode: PITQueryMode,
        source: str | None = None,
        research_data_cutoff: datetime | None = None,
    ) -> ETFMetadataObservation | None:
        eligible = self.get_metadata_observations(
            symbol,
            as_of=as_of,
            mode=mode,
            source=source,
            research_data_cutoff=research_data_cutoff,
        )
        if not eligible:
            return None
        eligible_sources = {item.source for item in eligible}
        if source is None and len(eligible_sources) > 1:
            raise DataValidationError(
                "multiple eligible metadata sources require explicit resolution: "
                f"{sorted(eligible_sources)}"
            )
        return max(
            eligible,
            key=lambda item: (
                item.effective_from or date.min,
                item.snapshot_at or datetime.min.replace(tzinfo=timezone.utc),
                item.available_time,
                item.ingest_time,
                item.provider_payload_hash,
            ),
        )

    def get_metadata_observations(
        self,
        symbol: str,
        *,
        as_of: datetime,
        mode: PITQueryMode,
        research_data_cutoff: datetime | None = None,
        source: str | None = None,
    ) -> list[ETFMetadataObservation]:
        """Return every eligible immutable observation with provenance intact."""

        _validate_time(as_of, "as_of")
        if research_data_cutoff is not None:
            _validate_time(research_data_cutoff, "research_data_cutoff")
        query = "SELECT payload_json FROM etf_metadata_observations WHERE symbol = ?"
        parameters: list[object] = [symbol]
        if source is not None:
            query += " AND source = ?"
            parameters.append(source)
        with self._connect() as connection:
            candidates = [
                _etf_from_payload(json.loads(row[0]))
                for row in connection.execute(query, parameters).fetchall()
            ]
        eligible = [
            item for item in candidates
            if _metadata_eligible(item, as_of, mode, research_data_cutoff)
        ]
        return sorted(
            eligible,
            key=lambda item: (
                item.source,
                item.effective_from or date.min,
                item.snapshot_at or datetime.min.replace(tzinfo=timezone.utc),
                item.available_time,
                item.ingest_time,
                item.provider_payload_hash,
            ),
        )

    def get_etf_revisions(self, symbol: str) -> list[ETFMetadataObservation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM etf_metadata_observations "
                "WHERE symbol = ? ORDER BY ingest_time, observation_id",
                (symbol,),
            ).fetchall()
        return [_etf_from_payload(json.loads(row[0])) for row in rows]

    def append_index_metadata(self, observations: Iterable[IndexMetadata]) -> int:
        rows = list(observations)
        with self._connect() as connection:
            before = connection.total_changes
            for item in rows:
                payload = _index_payload(item)
                connection.execute(
                    "INSERT OR IGNORE INTO index_metadata_observations "
                    "(observation_id, index_code, source, available_time, ingest_time, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        _stable_id(payload), item.index_code, item.source,
                        _datetime(item.available_time), _datetime(item.ingest_time),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
            return connection.total_changes - before

    def get_index_metadata(
        self,
        index_code: str,
        *,
        as_of: datetime,
        mode: PITQueryMode,
        research_data_cutoff: datetime | None = None,
    ) -> IndexMetadata | None:
        _validate_time(as_of, "as_of")
        if research_data_cutoff is not None:
            _validate_time(research_data_cutoff, "research_data_cutoff")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM index_metadata_observations WHERE index_code = ?",
                (index_code,),
            ).fetchall()
        candidates = [_index_from_payload(json.loads(row[0])) for row in rows]
        eligible = [
            item for item in candidates
            if _index_eligible(item, as_of, mode, research_data_cutoff)
        ]
        return max(eligible, key=lambda item: (item.available_time, item.ingest_time)) if eligible else None

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS etf_metadata_observations (
                    observation_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    availability_class TEXT NOT NULL,
                    effective_from TEXT,
                    effective_to TEXT,
                    available_time TEXT NOT NULL,
                    ingest_time TEXT NOT NULL,
                    snapshot_at TEXT,
                    provider_payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_etf_metadata_symbol
                    ON etf_metadata_observations(symbol, source, available_time);
                CREATE TABLE IF NOT EXISTS index_metadata_observations (
                    observation_id TEXT PRIMARY KEY,
                    index_code TEXT NOT NULL,
                    source TEXT NOT NULL,
                    available_time TEXT NOT NULL,
                    ingest_time TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)


def _metadata_eligible(
    item: ETFMetadataObservation,
    as_of: datetime,
    mode: PITQueryMode,
    research_data_cutoff: datetime | None,
) -> bool:
    as_of_date = as_of.astimezone(ZoneInfo(item.market_timezone)).date()
    if item.effective_from and item.effective_from > as_of_date:
        return False
    if item.effective_to and item.effective_to < as_of_date:
        return False
    if item.available_time > as_of:
        return False
    if item.availability_class in {
        DataAvailabilityClass.SNAPSHOT_ONLY,
        DataAvailabilityClass.FORWARD_COLLECTED_PIT,
    } and (item.snapshot_at is None or item.snapshot_at > as_of):
        return False
    if mode is PITQueryMode.SYSTEM_REPLAY and item.ingest_time > as_of:
        return False
    if research_data_cutoff is not None and item.ingest_time > research_data_cutoff:
        return False
    return True


def _index_eligible(
    item: IndexMetadata,
    as_of: datetime,
    mode: PITQueryMode,
    research_data_cutoff: datetime | None,
) -> bool:
    as_of_date = as_of.date()
    if item.effective_from and item.effective_from > as_of_date:
        return False
    if item.effective_to and item.effective_to < as_of_date:
        return False
    if item.available_time > as_of:
        return False
    if item.availability_class in {
        DataAvailabilityClass.SNAPSHOT_ONLY,
        DataAvailabilityClass.FORWARD_COLLECTED_PIT,
    } and (item.snapshot_at is None or item.snapshot_at > as_of):
        return False
    if mode is PITQueryMode.SYSTEM_REPLAY and item.ingest_time > as_of:
        return False
    if research_data_cutoff is not None and item.ingest_time > research_data_cutoff:
        return False
    return True


def _etf_payload(item: ETFMetadataObservation) -> dict[str, object]:
    payload = asdict(item)
    payload["asset_class"] = item.asset_class.value
    payload["availability_class"] = item.availability_class.value
    for key in ("price_limit_pct", "management_fee", "nav", "iopv", "shares", "aum"):
        value = payload[key]
        payload[key] = str(value) if value is not None else None
    for key in ("list_date", "delist_date", "effective_from", "effective_to"):
        value = payload[key]
        payload[key] = value.isoformat() if value is not None else None
    for key in ("available_time", "ingest_time", "snapshot_at"):
        value = payload[key]
        payload[key] = _datetime(value) if value is not None else None  # type: ignore[arg-type]
    return payload


def _etf_from_payload(payload: dict[str, object]) -> ETFMetadataObservation:
    decimal_fields = ("price_limit_pct", "management_fee", "nav", "iopv", "shares", "aum")
    return ETFMetadataObservation(
        **{
            **payload,
            "asset_class": AssetClass(str(payload["asset_class"])),
            "availability_class": DataAvailabilityClass(str(payload["availability_class"])),
            **{key: Decimal(str(payload[key])) if payload[key] is not None else None for key in decimal_fields},
            **{key: date.fromisoformat(str(payload[key])) if payload[key] else None for key in ("list_date", "delist_date", "effective_from", "effective_to")},
            **{key: datetime.fromisoformat(str(payload[key])) if payload[key] else None for key in ("available_time", "ingest_time", "snapshot_at")},
        }
    )


def _index_payload(item: IndexMetadata) -> dict[str, object]:
    payload = asdict(item)
    payload["availability_class"] = item.availability_class.value
    for key in ("base_date", "launch_date", "effective_from", "effective_to"):
        value = payload[key]
        payload[key] = value.isoformat() if value else None
    for key in ("available_time", "ingest_time", "snapshot_at"):
        value = payload[key]
        payload[key] = _datetime(value) if value is not None else None  # type: ignore[arg-type]
    return payload


def _index_from_payload(payload: dict[str, object]) -> IndexMetadata:
    return IndexMetadata(
        **{
            **payload,
            "availability_class": DataAvailabilityClass(str(payload["availability_class"])),
            **{key: date.fromisoformat(str(payload[key])) if payload[key] else None for key in ("base_date", "launch_date", "effective_from", "effective_to")},
            **{
                key: datetime.fromisoformat(str(payload[key])) if payload[key] else None
                for key in ("available_time", "ingest_time", "snapshot_at")
            },
        }
    )


def _stable_id(payload: dict[str, object]) -> str:
    identity = dict(payload)
    identity.pop("ingest_time", None)
    identity.pop("available_time", None)
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _optional_datetime(value: datetime | None) -> str | None:
    return _datetime(value) if value is not None else None


def _optional_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _validate_time(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
