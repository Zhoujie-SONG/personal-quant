from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from etf_quant.domain.enums import AdjustType
from etf_quant.providers.dto import RawMarketBar
from etf_quant.utils.time import shanghai_trade_date


class LongbridgeRawBarCache:
    """Filesystem raw cache with monthly record files and range coverage manifests."""

    schema_version = 1

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
    ) -> list[tuple[date, date]]:
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        manifest = self._read_manifest(symbol, adjust_type)
        covered: set[date] = set()
        for item in manifest.get("coverage", []):
            begin = date.fromisoformat(item["start_date"])
            end = date.fromisoformat(item["end_date"])
            cursor = max(begin, start_date)
            stop = min(end, end_date)
            while cursor <= stop:
                covered.add(cursor)
                cursor += timedelta(days=1)

        missing = [
            start_date + timedelta(days=offset)
            for offset in range((end_date - start_date).days + 1)
            if start_date + timedelta(days=offset) not in covered
        ]
        if not missing:
            return []
        ranges: list[tuple[date, date]] = []
        range_start = previous = missing[0]
        for current in missing[1:]:
            if current != previous + timedelta(days=1):
                ranges.append((range_start, previous))
                range_start = current
            previous = current
        ranges.append((range_start, previous))
        return ranges

    def save(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType,
        bars: list[RawMarketBar],
        *,
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
            by_identity = {
                (item["symbol"], item["provider_timestamp"]): item for item in existing
            }
            for bar in incoming:
                item = self._serialize_bar(bar)
                by_identity[(item["symbol"], item["provider_timestamp"])] = item
            records = sorted(by_identity.values(), key=lambda item: item["provider_timestamp"])
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
        coverage = list(manifest.get("coverage", []))
        coverage.append(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "retrieved_at": retrieved_at.isoformat(),
                "request_key": self.request_key(symbol, start_date, end_date, adjust_type),
            }
        )
        manifest["coverage"] = coverage
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
            cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
        return sorted(result, key=lambda item: item.provider_timestamp)

    def _directory(self, symbol: str, adjust_type: AdjustType) -> Path:
        safe_symbol = symbol.strip().upper().replace("/", "_").replace("\\", "_")
        return self.root / safe_symbol / adjust_type.value

    def _manifest_path(self, symbol: str, adjust_type: AdjustType) -> Path:
        return self._directory(symbol, adjust_type) / "manifest.json"

    def _read_manifest(self, symbol: str, adjust_type: AdjustType) -> dict[str, Any]:
        path = self._manifest_path(symbol, adjust_type)
        if not path.exists():
            return {"coverage": []}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != self.schema_version:
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
        return payload

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
