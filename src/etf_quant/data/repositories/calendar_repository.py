from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from etf_quant.domain.enums import HistoricalDataSemantics, Market, PITQueryMode
from etf_quant.domain.models.metadata import TradingCalendarObservation


class TradingCalendarRepository:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "trading_calendar.sqlite3"
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS calendar_observations (
                    observation_id TEXT PRIMARY KEY,
                    market TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    available_time TEXT NOT NULL,
                    ingest_time TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def append_entries(self, observations: Iterable[TradingCalendarObservation]) -> int:
        with self._connect() as connection:
            before = connection.total_changes
            for item in observations:
                payload = _payload(item)
                encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                observation_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                connection.execute(
                    "INSERT OR IGNORE INTO calendar_observations "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        observation_id, item.market, item.trade_date.isoformat(),
                        _dt(item.available_time), _dt(item.ingest_time), encoded,
                    ),
                )
            return connection.total_changes - before

    def get_calendar(
        self,
        market: Market,
        start_date: date,
        end_date: date,
        *,
        as_of: datetime,
        mode: PITQueryMode,
        research_data_cutoff: datetime | None = None,
    ) -> list[TradingCalendarObservation]:
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM calendar_observations "
                "WHERE market = ? AND trade_date BETWEEN ? AND ?",
                (market.value, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        by_date: dict[date, TradingCalendarObservation] = {}
        for row in rows:
            item = _from_payload(json.loads(row[0]))
            if item.available_time > as_of:
                continue
            if mode is PITQueryMode.SYSTEM_REPLAY and item.ingest_time > as_of:
                continue
            if research_data_cutoff is not None and item.ingest_time > research_data_cutoff:
                continue
            prior = by_date.get(item.trade_date)
            if prior is None or (item.available_time, item.ingest_time) > (
                prior.available_time, prior.ingest_time
            ):
                by_date[item.trade_date] = item
        return [by_date[value] for value in sorted(by_date)]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)


def _payload(item: TradingCalendarObservation) -> dict[str, object]:
    return {
        "market": item.market,
        "trade_date": item.trade_date.isoformat(),
        "is_open": item.is_open,
        "session_open": _optional_dt(item.session_open),
        "session_close": _optional_dt(item.session_close),
        "is_half_day": item.is_half_day,
        "available_time": _dt(item.available_time),
        "ingest_time": _dt(item.ingest_time),
        "source": item.source,
        "historical_data_semantics": item.historical_data_semantics.value,
        "availability_policy_id": item.availability_policy_id,
    }


def _from_payload(payload: dict[str, object]) -> TradingCalendarObservation:
    return TradingCalendarObservation(
        market=str(payload["market"]),
        trade_date=date.fromisoformat(str(payload["trade_date"])),
        is_open=bool(payload["is_open"]),
        session_open=datetime.fromisoformat(str(payload["session_open"])) if payload["session_open"] else None,
        session_close=datetime.fromisoformat(str(payload["session_close"])) if payload["session_close"] else None,
        is_half_day=bool(payload["is_half_day"]),
        available_time=datetime.fromisoformat(str(payload["available_time"])),
        ingest_time=datetime.fromisoformat(str(payload["ingest_time"])),
        source=str(payload["source"]),
        historical_data_semantics=HistoricalDataSemantics(
            str(
                payload.get(
                    "historical_data_semantics",
                    HistoricalDataSemantics.HISTORICAL_LATEST.value,
                )
            )
        ),
        availability_policy_id=str(
            payload.get("availability_policy_id", "legacy_calendar_retrieval_time_v0")
        ),
    )


def _dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _optional_dt(value: datetime | None) -> str | None:
    return _dt(value) if value else None
