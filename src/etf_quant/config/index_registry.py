from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping

import yaml

from etf_quant.domain.enums import DataAvailabilityClass
from etf_quant.domain.models.metadata import IndexMetadata


def load_index_registry(path: Path) -> list[IndexMetadata]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping) or not isinstance(payload.get("indexes", []), list):
        raise ValueError("index registry must contain an indexes list")
    result: list[IndexMetadata] = []
    for index, row in enumerate(payload.get("indexes", [])):
        if not isinstance(row, Mapping):
            raise ValueError(f"indexes[{index}] must be a mapping")
        for required in ("index_code", "source", "source_note", "known_at"):
            if not row.get(required):
                raise ValueError(f"indexes[{index}].{required} is required")
        known_at = _datetime(row["known_at"])
        result.append(
            IndexMetadata(
                index_code=str(row["index_code"]),
                base_date=_date(row.get("base_date")),
                launch_date=_date(row.get("launch_date")),
                methodology_version=_optional_str(row.get("methodology_version")),
                is_total_return=row.get("is_total_return"),  # type: ignore[arg-type]
                source=str(row["source"]),
                availability_class=DataAvailabilityClass(
                    str(row.get("availability_class", "snapshot_only"))
                ),
                effective_from=_date(row.get("effective_from")),
                effective_to=_date(row.get("effective_to")),
                available_time=known_at,
                ingest_time=known_at.astimezone(timezone.utc),
                snapshot_at=known_at,
                source_note=str(row["source_note"]),
            )
        )
    return result


def _date(value: object) -> date | None:
    if value in (None, "", "UNKNOWN"):
        return None
    return date.fromisoformat(str(value))


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    return parsed


def _optional_str(value: object) -> str | None:
    return None if value in (None, "", "UNKNOWN") else str(value)
