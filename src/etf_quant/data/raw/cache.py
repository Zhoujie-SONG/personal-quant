from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from etf_quant.domain.enums import AdjustType
from etf_quant.providers.dto import RawMarketBar
from etf_quant.utils.time import shanghai_trade_date


class LongbridgeRawBarCache:
    """Monthly raw cache with separate requested and calendar-verified coverage."""

    schema_version = 2

    def __init__(self, root: Path) -> None:
        self.root = root / "longbridge" / "bars"

    @staticmethod
    def request_key(
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType,
    ) -> str:
        payload = {
            "adjust_type": adjust_type.value,
            "end_date": end_date.isoformat(),
            "endpoint": "daily_bars",
            "provider": "longbridge",
            "start_date": start_date.isoformat(),
            "symbol": symbol.strip().upper(),
        }
        canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def missing_ranges(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType,
        *,
        expected_trading_dates: Collection[date],
    ) -> list[tuple[date, date]]:
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        expected = sorted(
            trade_date
            for trade_date in set(expected_trading_dates)
            if start_date <= trade_date <= end_date
        )
        if not expected:
            return []

        manifest = self._read_manifest(symbol, adjust_type)
        verified = {
            date.fromisoformat(value) for value in manifest.get("verified_dates", [])
        }
        verified.update(
            shanghai_trade_date(bar.provider_timestamp)
            for bar in self.load(symbol, start_date, end_date, adjust_type)
        )

        ranges: list[tuple[date, date]] = []
        active_start: date | None = None
        previous_missing: date | None = None
        for trade_date in expected:
            if trade_date not in verified:
                if active_start is None:
                    active_start = trade_date
                previous_missing = trade_date
            elif active_start is not None and previous_missing is not None:
                ranges.append((active_start, previous_missing))
                active_start = None
                previous_missing = None
        if active_start is not None and previous_missing is not None:
            ranges.append((active_start, previous_missing))
        return ranges

    def save(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType,
        bars: list[RawMarketBar],
        *,
        expected_trading_dates: Collection[date],
        retrieved_at: datetime,
        sdk_version: str,
    ) -> None:
        directory = self._directory(symbol, adjust_type)
        grouped: dict[tuple[int, int], list[RawMarketBar]] = {}
        for bar in bars:
            trade_date = shanghai_trade_date(bar.provider_timestamp)
            grouped.setdefault((trade_date.year, trade_date.month), []).append(bar)

        for (year, month), incoming in grouped.items():
            path = directory / f"year={year:04d}" / f"month={month:02d}.json"
            existing = self._read_records(path)
            by_identity = {self._record_identity(item): item for item in existing}
            for bar in incoming:
                item = self._serialize_bar(bar)
                by_identity[self._record_identity(item)] = item
            records = sorted(
                by_identity.values(),
                key=lambda item: (item["provider_timestamp"], item["retrieved_at"]),
            )
            self._atomic_write_json(
                path,
                {
                    "schema_version": self.schema_version,
                    "provider": "longbridge",
                    "sdk_version": sdk_version,
                    "records": records,
                },
            )

        manifest = self._read_manifest(symbol, adjust_type)
        manifest["schema_version"] = self.schema_version
        manifest["provider"] = "longbridge"
        manifest["symbol"] = symbol
        manifest["adjust_type"] = adjust_type.value
        manifest["sdk_version"] = sdk_version
        requested = list(manifest.get("requested_coverage", []))
        requested.append(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "retrieved_at": retrieved_at.isoformat(),
                "request_key": self.request_key(symbol, start_date, end_date, adjust_type),
            }
        )
        manifest["requested_coverage"] = requested

        expected = {
            trade_date
            for trade_date in expected_trading_dates
            if start_date <= trade_date <= end_date
        }
        returned = {shanghai_trade_date(bar.provider_timestamp) for bar in bars}
        verified = {
            date.fromisoformat(value) for value in manifest.get("verified_dates", [])
        }
        verified.update(expected & returned)
        manifest["verified_dates"] = [value.isoformat() for value in sorted(verified)]
        self._atomic_write_json(self._manifest_path(symbol, adjust_type), manifest)

    def load(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType,
    ) -> list[RawMarketBar]:
        directory = self._directory(symbol, adjust_type)
        result: list[RawMarketBar] = []
        cursor = date(start_date.year, start_date.month, 1)
        while cursor <= end_date:
            path = directory / f"year={cursor.year:04d}" / f"month={cursor.month:02d}.json"
            for item in self._read_records(path):
                bar = self._deserialize_bar(item)
                trade_date = shanghai_trade_date(bar.provider_timestamp)
                if start_date <= trade_date <= end_date:
                    result.append(bar)
            cursor = date(
                cursor.year + (cursor.month == 12),
                1 if cursor.month == 12 else cursor.month + 1,
                1,
            )
        return sorted(result, key=lambda item: (item.provider_timestamp, item.retrieved_at))

    def _directory(self, symbol: str, adjust_type: AdjustType) -> Path:
        safe_symbol = symbol.strip().upper().replace("/", "_").replace("\\", "_")
        return self.root / safe_symbol / adjust_type.value

    def _manifest_path(self, symbol: str, adjust_type: AdjustType) -> Path:
        return self._directory(symbol, adjust_type) / "manifest.json"

    def _read_manifest(self, symbol: str, adjust_type: AdjustType) -> dict[str, Any]:
        path = self._manifest_path(symbol, adjust_type)
        if not path.exists():
            return {"requested_coverage": [], "verified_dates": []}
        payload = json.loads(path.read_text(encoding="utf-8"))
        version = payload.get("schema_version")
        if version == 1:
            payload["requested_coverage"] = payload.pop("coverage", [])
            payload["verified_dates"] = []
            return payload
        if version != self.schema_version:
            raise ValueError(f"unsupported raw cache schema in {path}")
        return payload

    @staticmethod
    def _read_records(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("records", []))

    @staticmethod
    def _serialize_bar(bar: RawMarketBar) -> dict[str, Any]:
        payload = asdict(bar)
        payload["provider_timestamp"] = bar.provider_timestamp.isoformat()
        payload["retrieved_at"] = bar.retrieved_at.isoformat()
        payload["payload_hash"] = LongbridgeRawBarCache._payload_hash(payload)
        return payload

    @staticmethod
    def _record_identity(item: dict[str, Any]) -> tuple[str, str, str, str]:
        payload_hash = str(item.get("payload_hash") or LongbridgeRawBarCache._payload_hash(item))
        return (
            str(item["symbol"]),
            str(item["provider_timestamp"]),
            str(item["retrieved_at"]),
            payload_hash,
        )

    @staticmethod
    def _payload_hash(item: dict[str, Any]) -> str:
        value_fields = {
            key: item[key]
            for key in ("symbol", "open", "high", "low", "close", "volume", "turnover", "provider_timestamp")
            if key in item
        }
        canonical = json.dumps(value_fields, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _deserialize_bar(item: dict[str, Any]) -> RawMarketBar:
        return RawMarketBar(
            symbol=item["symbol"],
            open=item["open"],
            high=item["high"],
            low=item["low"],
            close=item["close"],
            volume=int(item["volume"]),
            turnover=item["turnover"],
            provider_timestamp=datetime.fromisoformat(item["provider_timestamp"]),
            retrieved_at=datetime.fromisoformat(item["retrieved_at"]),
            provider=item["provider"],
            sdk_version=item["sdk_version"],
            provider_payload=item.get("provider_payload", {}),
        )

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)
