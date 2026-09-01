from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import yaml

from etf_quant.domain.enums import DataAvailabilityClass


@dataclass(frozen=True, slots=True)
class SourceCapability:
    provider: str
    dataset: str
    field: str
    availability_class: DataAvailabilityClass
    historical_coverage: str
    frequency: str
    timezone: str
    formal_backtest_allowed: bool
    notes: str

    def __post_init__(self) -> None:
        for name in ("provider", "dataset", "field", "historical_coverage", "frequency", "timezone"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        ZoneInfo(self.timezone)


@dataclass(frozen=True, slots=True)
class DataSourceRegistry:
    capabilities: tuple[SourceCapability, ...]
    etf_cemetery_completeness: str

    @classmethod
    def from_yaml(cls, path: Path) -> "DataSourceRegistry":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise ValueError("data source registry must be a mapping")
        rows = payload.get("capabilities", [])
        if not isinstance(rows, list):
            raise ValueError("capabilities must be a list")
        capabilities: list[SourceCapability] = []
        required = {
            "provider", "dataset", "field", "availability_class",
            "historical_coverage", "frequency", "timezone",
            "formal_backtest_allowed", "notes",
        }
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise ValueError(f"capabilities[{index}] must be a mapping")
            missing = required - set(row)
            if missing:
                raise ValueError(f"capabilities[{index}] missing {sorted(missing)}")
            capabilities.append(
                SourceCapability(
                    provider=str(row["provider"]),
                    dataset=str(row["dataset"]),
                    field=str(row["field"]),
                    availability_class=DataAvailabilityClass(str(row["availability_class"])),
                    historical_coverage=str(row["historical_coverage"]),
                    frequency=str(row["frequency"]),
                    timezone=str(row["timezone"]),
                    formal_backtest_allowed=bool(row["formal_backtest_allowed"]),
                    notes=str(row["notes"]),
                )
            )
        return cls(
            capabilities=tuple(capabilities),
            etf_cemetery_completeness=str(
                payload.get("etf_cemetery_completeness", "UNVERIFIED")
            ),
        )

    def find(self, provider: str, dataset: str, field: str) -> SourceCapability:
        matches = [
            item for item in self.capabilities
            if (item.provider, item.dataset, item.field) == (provider, dataset, field)
        ]
        if len(matches) != 1:
            raise KeyError(f"capability not uniquely registered: {provider}/{dataset}/{field}")
        return matches[0]
