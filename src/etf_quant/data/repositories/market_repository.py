from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from etf_quant.domain.models.market_bar import MarketBar


class MarketRepository(ABC):
    @abstractmethod
    def upsert_bars(self, bars: Iterable[MarketBar]) -> int:
        """Persist canonical bars and return the number of input rows."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        as_of: datetime,
    ) -> list[MarketBar]:
        """Return only records whose available_time is not after as_of."""


class ParquetMarketRepository(MarketRepository):
    """Monthly-partitioned Parquet store queried through DuckDB."""

    def __init__(self, root: Path) -> None:
        self.root = root / "market_bars"

    def upsert_bars(self, bars: Iterable[MarketBar]) -> int:
        import pyarrow as pa
        import pyarrow.parquet as pq

        input_bars = list(bars)
        grouped: dict[tuple[int, int], list[MarketBar]] = {}
        for bar in input_bars:
            grouped.setdefault((bar.trade_date.year, bar.trade_date.month), []).append(bar)

        for (year, month), incoming in grouped.items():
            path = self.root / f"year={year:04d}" / f"month={month:02d}" / "part-00000.parquet"
            by_key: dict[tuple[str, date, str], dict[str, object]] = {}
            if path.exists():
                for row in pq.read_table(path).to_pylist():
                    by_key[(row["symbol"], row["trade_date"], row["source"])] = row
            for bar in incoming:
                row = self._to_row(bar)
                by_key[(bar.symbol, bar.trade_date, bar.source)] = row
            rows = sorted(by_key.values(), key=lambda row: (row["trade_date"], row["symbol"], row["source"]))
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
        import duckdb

        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        files = list(self.root.glob("year=*/month=*/part-*.parquet"))
        if not files:
            return []
        parquet_glob = (self.root / "year=*" / "month=*" / "part-*.parquet").as_posix()
        sql = f"""
            SELECT symbol, trade_date, open, high, low, close, volume, turnover,
                   data_time, available_time, ingest_time, source
            FROM read_parquet('{parquet_glob.replace("'", "''")}', hive_partitioning = false)
            WHERE symbol = ?
              AND trade_date BETWEEN ? AND ?
              AND available_time <= ?
            ORDER BY trade_date, source
        """
        connection = duckdb.connect(database=":memory:")
        try:
            rows = connection.execute(sql, [symbol, start_date, end_date, as_of]).fetchall()
        finally:
            connection.close()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _schema(pa: object) -> object:
        return pa.schema(
            [
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

    @staticmethod
    def _to_row(bar: MarketBar) -> dict[str, object]:
        return {
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

    @staticmethod
    def _from_row(row: tuple[object, ...]) -> MarketBar:
        return MarketBar(
            symbol=str(row[0]),
            trade_date=row[1],
            open=Decimal(row[2]),
            high=Decimal(row[3]),
            low=Decimal(row[4]),
            close=Decimal(row[5]),
            volume=int(row[6]),
            turnover=Decimal(row[7]),
            data_time=_aware_utc(row[8]),
            available_time=_aware_utc(row[9]),
            ingest_time=_aware_utc(row[10]),
            source=str(row[11]),
        )


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("repository timestamp is not a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

