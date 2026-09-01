from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

from etf_quant.domain.enums import (
    CanonicalMarketSource,
    HistoricalDataSemantics,
    PITQueryMode,
)
from etf_quant.domain.exceptions import DataValidationError, SchemaMigrationRequiredError
from etf_quant.domain.models.market_bar import MarketBar

REVISION_SCHEMA_VERSION = 3
LEGACY_POLICY_PREFIX = "legacy_inferred_daily_bar"


@dataclass(frozen=True, slots=True)
class MarketBarObservation:
    observation_id: str
    value_hash: str
    availability_policy_id: str
    observed_at: datetime
    bar: MarketBar


class MarketRepository(ABC):
    @abstractmethod
    def append_bars(self, bars: Iterable[MarketBar]) -> int:
        """Append immutable observations, idempotent by observation identity."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        source: CanonicalMarketSource,
        as_of: datetime,
        mode: PITQueryMode,
    ) -> list[MarketBar]:
        """Return one explicitly sourced observation under the requested PIT mode."""

    @abstractmethod
    def get_bar_revisions(
        self,
        symbol: str,
        trade_date: date,
        source: str,
    ) -> list[MarketBarObservation]:
        """Return every retained observation in observed-at order."""


class ParquetMarketRepository(MarketRepository):
    """Monthly Parquet revision log queried through DuckDB."""

    def __init__(self, root: Path) -> None:
        self.root = root / "market_bars"

    def append_bars(self, bars: Iterable[MarketBar]) -> int:
        import pyarrow as pa
        import pyarrow.parquet as pq

        input_bars = list(bars)
        grouped: dict[tuple[int, int], list[MarketBar]] = {}
        for bar in input_bars:
            grouped.setdefault((bar.trade_date.year, bar.trade_date.month), []).append(bar)

        for (year, month), incoming in grouped.items():
            path = self.root / f"year={year:04d}" / f"month={month:02d}" / "part-00000.parquet"
            by_observation_id: dict[str, dict[str, object]] = {}
            if path.exists():
                self._require_current_schema([path])
                for existing in pq.read_table(path).to_pylist():
                    observation_id = str(existing["observation_id"])
                    prior = by_observation_id.get(observation_id)
                    if (
                        prior is not None
                        and prior["historical_data_semantics"]
                        != existing["historical_data_semantics"]
                    ):
                        raise DataValidationError(
                            "historical_data_semantics conflict for observation_id "
                            f"{observation_id}"
                        )
                    by_observation_id[observation_id] = existing
            for bar in incoming:
                row = self._to_row(bar)
                observation_id = str(row["observation_id"])
                existing = by_observation_id.get(observation_id)
                if (
                    existing is not None
                    and existing["historical_data_semantics"]
                    != row["historical_data_semantics"]
                ):
                    raise DataValidationError(
                        "historical_data_semantics conflict for observation_id "
                        f"{observation_id}"
                    )
                by_observation_id[observation_id] = row
            rows = sorted(
                by_observation_id.values(),
                key=lambda row: (
                    row["trade_date"], row["symbol"], row["source"],
                    row["ingest_time"], row["availability_policy_id"], row["value_hash"],
                ),
            )
            table = pa.Table.from_pylist(rows, schema=self._schema(pa))
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp.parquet")
            pq.write_table(table, temporary, compression="zstd")
            temporary.replace(path)
        return len(input_bars)

    def get_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        source: CanonicalMarketSource,
        as_of: datetime,
        mode: PITQueryMode,
    ) -> list[MarketBar]:
        self._validate_query(start_date, end_date, as_of)
        if not isinstance(source, CanonicalMarketSource):
            raise DataValidationError("source must be an explicit CanonicalMarketSource")
        if not isinstance(mode, PITQueryMode):
            raise DataValidationError("mode must be an explicit PITQueryMode")
        files = self._files()
        if not files:
            return []
        self._require_current_schema(files)
        replay_clause = "AND ingest_time <= ?" if mode is PITQueryMode.SYSTEM_REPLAY else ""
        parameters: list[object] = [symbol, source.value, start_date, end_date, as_of]
        if mode is PITQueryMode.SYSTEM_REPLAY:
            parameters.append(as_of)
        sql = f"""
            WITH eligible AS (
                SELECT *,
                       row_number() OVER (
                           PARTITION BY symbol, trade_date, source
                           ORDER BY ingest_time DESC, availability_policy_id DESC,
                                    value_hash DESC
                       ) AS revision_rank
                FROM read_parquet('{self._parquet_glob()}', hive_partitioning = false)
                WHERE symbol = ? AND source = ?
                  AND trade_date BETWEEN ? AND ?
                  AND available_time <= ?
                  {replay_clause}
            )
            SELECT symbol, trade_date, open, high, low, close, volume, turnover,
                   data_time, available_time, ingest_time, source,
                   availability_policy_id, historical_data_semantics
            FROM eligible
            WHERE revision_rank = 1
            ORDER BY trade_date
        """
        return [self._bar_from_tuple(row) for row in self._fetchall(sql, parameters)]

    def get_bar_revisions(
        self,
        symbol: str,
        trade_date: date,
        source: str,
    ) -> list[MarketBarObservation]:
        files = self._files()
        if not files:
            return []
        self._require_current_schema(files)
        sql = f"""
            SELECT observation_id, value_hash, availability_policy_id,
                   symbol, trade_date, open, high, low, close, volume, turnover,
                   data_time, available_time, ingest_time, source,
                   availability_policy_id, historical_data_semantics
            FROM read_parquet('{self._parquet_glob()}', hive_partitioning = false)
            WHERE symbol = ? AND trade_date = ? AND source = ?
            ORDER BY ingest_time, availability_policy_id, value_hash
        """
        rows = self._fetchall(sql, [symbol, trade_date, source])
        return [
            MarketBarObservation(
                observation_id=str(row[0]),
                value_hash=str(row[1]),
                availability_policy_id=str(row[2]),
                observed_at=_aware_utc(row[13]),
                bar=self._bar_from_tuple(row[3:]),
            )
            for row in rows
        ]

    def schema_versions(self) -> dict[Path, int]:
        return {path: self._schema_version(path) for path in self._files()}

    def migrate_to_latest_schema(self) -> int:
        """Explicit one-time migration for legacy v1/v2 partitions."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        migrated = 0
        for path, version in self.schema_versions().items():
            if version == REVISION_SCHEMA_VERSION:
                continue
            if version not in {1, 2}:
                raise SchemaMigrationRequiredError(
                    f"unsupported market revision schema v{version} in {path}"
                )
            rows = [self._migrate_legacy_row(row) for row in pq.read_table(path).to_pylist()]
            deduplicated = {str(row["observation_id"]): row for row in rows}
            table = pa.Table.from_pylist(
                sorted(
                    deduplicated.values(),
                    key=lambda row: (
                        row["trade_date"], row["symbol"], row["source"],
                        row["ingest_time"], row["observation_id"],
                    ),
                ),
                schema=self._schema(pa),
            )
            temporary = path.with_suffix(".migrating.parquet")
            pq.write_table(table, temporary, compression="zstd")
            temporary.replace(path)
            migrated += 1
        return migrated

    def _files(self) -> list[Path]:
        return sorted(self.root.glob("year=*/month=*/part-*.parquet"))

    def _parquet_glob(self) -> str:
        value = (self.root / "year=*" / "month=*" / "part-*.parquet").as_posix()
        return value.replace("'", "''")

    @staticmethod
    def _fetchall(sql: str, parameters: list[object]) -> list[tuple[object, ...]]:
        import duckdb

        connection = duckdb.connect(database=":memory:")
        try:
            return connection.execute(sql, parameters).fetchall()
        finally:
            connection.close()

    @staticmethod
    def _validate_query(start_date: date, end_date: date, as_of: datetime) -> None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")

    @classmethod
    def _require_current_schema(cls, files: list[Path]) -> None:
        versions = {path: cls._schema_version(path) for path in files}
        stale = {path: version for path, version in versions.items() if version != REVISION_SCHEMA_VERSION}
        if stale:
            detail = ", ".join(f"{path}:v{version}" for path, version in stale.items())
            raise SchemaMigrationRequiredError(
                "market revision partitions require explicit v3 migration: " + detail
            )

    @staticmethod
    def _schema_version(path: Path) -> int:
        import pyarrow.parquet as pq

        names = set(pq.read_schema(path).names)
        if {"value_hash", "availability_policy_id", "historical_data_semantics"} <= names:
            return 3
        if {"observation_id", "payload_hash"} <= names:
            return 2
        return 1

    @staticmethod
    def _schema(pa: object) -> object:
        return pa.schema(
            [
                pa.field("revision_schema_version", pa.int16(), nullable=False),
                pa.field("observation_id", pa.string(), nullable=False),
                pa.field("value_hash", pa.string(), nullable=False),
                pa.field("availability_policy_id", pa.string(), nullable=False),
                pa.field("historical_data_semantics", pa.string(), nullable=False),
                pa.field("symbol", pa.string(), nullable=False),
                pa.field("trade_date", pa.date32(), nullable=False),
                pa.field("open", pa.decimal128(28, 8), nullable=False),
                pa.field("high", pa.decimal128(28, 8), nullable=False),
                pa.field("low", pa.decimal128(28, 8), nullable=False),
                pa.field("close", pa.decimal128(28, 8), nullable=False),
                pa.field("volume", pa.int64(), nullable=False),
                pa.field("turnover", pa.decimal128(38, 4), nullable=False),
                pa.field("data_time", pa.timestamp("us", tz="UTC"), nullable=False),
                pa.field("available_time", pa.timestamp("us", tz="UTC"), nullable=False),
                pa.field("ingest_time", pa.timestamp("us", tz="UTC"), nullable=False),
                pa.field("source", pa.string(), nullable=False),
            ]
        )

    @classmethod
    def _to_row(cls, bar: MarketBar) -> dict[str, object]:
        value_hash = market_bar_value_hash(bar)
        return {
            "revision_schema_version": REVISION_SCHEMA_VERSION,
            "observation_id": market_bar_observation_id(bar, value_hash),
            "value_hash": value_hash,
            "availability_policy_id": bar.availability_policy_id,
            "historical_data_semantics": bar.historical_data_semantics.value,
            "symbol": bar.symbol,
            "trade_date": bar.trade_date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "turnover": bar.turnover,
            "data_time": bar.data_time.astimezone(timezone.utc),
            "available_time": bar.available_time.astimezone(timezone.utc),
            "ingest_time": bar.ingest_time.astimezone(timezone.utc),
            "source": bar.source,
        }

    @classmethod
    def _migrate_legacy_row(cls, row: Mapping[str, object]) -> dict[str, object]:
        return cls._to_row(cls._legacy_bar_from_mapping(row))

    @staticmethod
    def _legacy_bar_from_mapping(row: Mapping[str, object]) -> MarketBar:
        data_time = _aware_utc(row["data_time"])
        available_time = _aware_utc(row["available_time"])
        delay_seconds = max(0, int((available_time - data_time).total_seconds()))
        return MarketBar(
            symbol=str(row["symbol"]),
            trade_date=row["trade_date"],  # type: ignore[arg-type]
            open=Decimal(row["open"]),  # type: ignore[arg-type]
            high=Decimal(row["high"]),  # type: ignore[arg-type]
            low=Decimal(row["low"]),  # type: ignore[arg-type]
            close=Decimal(row["close"]),  # type: ignore[arg-type]
            volume=int(row["volume"]),  # type: ignore[arg-type]
            turnover=Decimal(row["turnover"]),  # type: ignore[arg-type]
            data_time=data_time,
            available_time=available_time,
            ingest_time=_aware_utc(row["ingest_time"]),
            source=str(row["source"]),
            availability_policy_id=f"{LEGACY_POLICY_PREFIX}_{delay_seconds}s",
            historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
        )

    @staticmethod
    def _bar_from_tuple(row: tuple[object, ...]) -> MarketBar:
        return MarketBar(
            symbol=str(row[0]),
            trade_date=row[1],  # type: ignore[arg-type]
            open=Decimal(row[2]),  # type: ignore[arg-type]
            high=Decimal(row[3]),  # type: ignore[arg-type]
            low=Decimal(row[4]),  # type: ignore[arg-type]
            close=Decimal(row[5]),  # type: ignore[arg-type]
            volume=int(row[6]),
            turnover=Decimal(row[7]),  # type: ignore[arg-type]
            data_time=_aware_utc(row[8]),
            available_time=_aware_utc(row[9]),
            ingest_time=_aware_utc(row[10]),
            source=str(row[11]),
            availability_policy_id=str(row[12]),
            historical_data_semantics=HistoricalDataSemantics(str(row[13])),
        )


def market_bar_value_hash(bar: MarketBar) -> str:
    payload = {
        "symbol": bar.symbol,
        "trade_date": bar.trade_date.isoformat(),
        "source": bar.source,
        "open": _canonical_decimal(bar.open),
        "high": _canonical_decimal(bar.high),
        "low": _canonical_decimal(bar.low),
        "close": _canonical_decimal(bar.close),
        "volume": bar.volume,
        "turnover": _canonical_decimal(bar.turnover),
        "data_time": _canonical_datetime(bar.data_time),
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def market_bar_observation_id(bar: MarketBar, value_hash: str | None = None) -> str:
    identity = "|".join(
        (
            bar.symbol, bar.trade_date.isoformat(), bar.source,
            _canonical_datetime(bar.ingest_time),
            value_hash or market_bar_value_hash(bar),
            bar.availability_policy_id,
            _canonical_datetime(bar.available_time),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _canonical_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("repository timestamp is not a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
