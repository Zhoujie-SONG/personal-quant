from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

from etf_quant.domain.models.market_bar import MarketBar

REVISION_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class MarketBarObservation:
    observation_id: str
    payload_hash: str
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
        as_of: datetime,
    ) -> list[MarketBar]:
        """Return the latest observation actually known at as_of for each bar."""

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
                for existing in pq.read_table(path).to_pylist():
                    row = self._upgrade_row(existing)
                    by_observation_id[str(row["observation_id"])] = row
            for bar in incoming:
                row = self._to_row(bar)
                by_observation_id[str(row["observation_id"])] = row
            rows = sorted(
                by_observation_id.values(),
                key=lambda row: (
                    row["trade_date"],
                    row["symbol"],
                    row["source"],
                    row["ingest_time"],
                    row["payload_hash"],
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
        as_of: datetime,
    ) -> list[MarketBar]:
        self._validate_query(start_date, end_date, as_of)
        if not self._has_files():
            return []
        sql = f"""
            WITH eligible AS (
                SELECT *,
                       row_number() OVER (
                           PARTITION BY symbol, trade_date, source
                           ORDER BY ingest_time DESC, payload_hash DESC
                       ) AS revision_rank
                FROM read_parquet('{self._parquet_glob()}', hive_partitioning = false)
                WHERE symbol = ?
                  AND trade_date BETWEEN ? AND ?
                  AND available_time <= ?
                  AND ingest_time <= ?
            )
            SELECT symbol, trade_date, open, high, low, close, volume, turnover,
                   data_time, available_time, ingest_time, source
            FROM eligible
            WHERE revision_rank = 1
            ORDER BY trade_date, source
        """
        rows = self._fetchall(sql, [symbol, start_date, end_date, as_of, as_of])
        return [self._bar_from_tuple(row) for row in rows]

    def get_bar_revisions(
        self,
        symbol: str,
        trade_date: date,
        source: str,
    ) -> list[MarketBarObservation]:
        if not self._has_files():
            return []
        sql = f"""
            SELECT observation_id, payload_hash,
                   symbol, trade_date, open, high, low, close, volume, turnover,
                   data_time, available_time, ingest_time, source
            FROM read_parquet('{self._parquet_glob()}', hive_partitioning = false)
            WHERE symbol = ? AND trade_date = ? AND source = ?
            ORDER BY ingest_time, payload_hash
        """
        rows = self._fetchall(sql, [symbol, trade_date, source])
        return [
            MarketBarObservation(
                observation_id=str(row[0]),
                payload_hash=str(row[1]),
                observed_at=_aware_utc(row[12]),
                bar=self._bar_from_tuple(row[2:]),
            )
            for row in rows
        ]

    def _has_files(self) -> bool:
        return any(self.root.glob("year=*/month=*/part-*.parquet"))

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

    @staticmethod
    def _schema(pa: object) -> object:
        return pa.schema(
            [
                pa.field("revision_schema_version", pa.int16(), nullable=False),
                pa.field("observation_id", pa.string(), nullable=False),
                pa.field("payload_hash", pa.string(), nullable=False),
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
        payload_hash = market_bar_payload_hash(bar)
        observation_id = market_bar_observation_id(bar, payload_hash)
        return {
            "revision_schema_version": REVISION_SCHEMA_VERSION,
            "observation_id": observation_id,
            "payload_hash": payload_hash,
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
    def _upgrade_row(cls, row: Mapping[str, object]) -> dict[str, object]:
        if "observation_id" in row and "payload_hash" in row:
            return dict(row)
        return cls._to_row(cls._bar_from_mapping(row))

    @staticmethod
    def _bar_from_mapping(row: Mapping[str, object]) -> MarketBar:
        return MarketBar(
            symbol=str(row["symbol"]),
            trade_date=row["trade_date"],  # type: ignore[arg-type]
            open=Decimal(row["open"]),  # type: ignore[arg-type]
            high=Decimal(row["high"]),  # type: ignore[arg-type]
            low=Decimal(row["low"]),  # type: ignore[arg-type]
            close=Decimal(row["close"]),  # type: ignore[arg-type]
            volume=int(row["volume"]),  # type: ignore[arg-type]
            turnover=Decimal(row["turnover"]),  # type: ignore[arg-type]
            data_time=_aware_utc(row["data_time"]),
            available_time=_aware_utc(row["available_time"]),
            ingest_time=_aware_utc(row["ingest_time"]),
            source=str(row["source"]),
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
        )


def market_bar_payload_hash(bar: MarketBar) -> str:
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
        "available_time": _canonical_datetime(bar.available_time),
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def market_bar_observation_id(bar: MarketBar, payload_hash: str | None = None) -> str:
    value_hash = payload_hash or market_bar_payload_hash(bar)
    identity = "|".join(
        (
            bar.symbol,
            bar.trade_date.isoformat(),
            bar.source,
            _canonical_datetime(bar.ingest_time),
            value_hash,
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
