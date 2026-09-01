from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping

import yaml


@dataclass(frozen=True, slots=True)
class ReconciliationConfig:
    symbols: tuple[str, ...]
    price_abs_tolerance: Decimal
    volume_relative_tolerance: Decimal
    turnover_relative_tolerance: Decimal
    warning_multiplier: Decimal

    @classmethod
    def from_yaml(cls, path: Path) -> "ReconciliationConfig":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise ValueError("reconciliation config must be a mapping")
        return cls(
            symbols=tuple(str(value) for value in payload.get("symbols", [])),
            price_abs_tolerance=Decimal(str(payload["price_abs_tolerance"])),
            volume_relative_tolerance=Decimal(str(payload["volume_relative_tolerance"])),
            turnover_relative_tolerance=Decimal(str(payload["turnover_relative_tolerance"])),
            warning_multiplier=Decimal(str(payload.get("warning_multiplier", 2))),
        )

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("at least one reconciliation symbol is required")
        if min(
            self.price_abs_tolerance,
            self.volume_relative_tolerance,
            self.turnover_relative_tolerance,
        ) < 0:
            raise ValueError("reconciliation tolerances cannot be negative")
        if self.warning_multiplier < 1:
            raise ValueError("warning_multiplier must be at least 1")
