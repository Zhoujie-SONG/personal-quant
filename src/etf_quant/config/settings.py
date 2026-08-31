from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import yaml


@dataclass(frozen=True, slots=True)
class LongbridgeSettings:
    max_attempts: int = 3
    retry_base_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_base_seconds < 0:
            raise ValueError("retry_base_seconds cannot be negative")


@dataclass(frozen=True, slots=True)
class Settings:
    timezone: str = "Asia/Shanghai"
    provider: str = "longbridge"
    raw_data_dir: Path = Path("data/raw")
    canonical_data_dir: Path = Path("data/canonical")
    longbridge: LongbridgeSettings = LongbridgeSettings()

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if self.provider != "longbridge":
            raise ValueError("M1A only supports the longbridge provider")

    @classmethod
    def from_yaml(cls, path: Path) -> "Settings":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise ValueError("settings YAML must contain a mapping")
        serialized_keys = {str(key).lower() for key in _walk_keys(payload)}
        credential_tokens = ("app_key", "app_secret", "access_token", "token", "secret")
        if any(token in key for key in serialized_keys for token in credential_tokens):
            raise ValueError("credentials are forbidden in YAML; use environment variables")
        longbridge_payload = payload.get("longbridge", {})
        if not isinstance(longbridge_payload, Mapping):
            raise ValueError("longbridge settings must be a mapping")
        return cls(
            timezone=str(payload.get("timezone", "Asia/Shanghai")),
            provider=str(payload.get("provider", "longbridge")),
            raw_data_dir=Path(str(payload.get("raw_data_dir", "data/raw"))),
            canonical_data_dir=Path(str(payload.get("canonical_data_dir", "data/canonical"))),
            longbridge=LongbridgeSettings(
                max_attempts=int(longbridge_payload.get("max_attempts", 3)),
                retry_base_seconds=float(longbridge_payload.get("retry_base_seconds", 0.5)),
            ),
        )


def _walk_keys(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        keys: list[str] = []
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(child))
        return keys
    if isinstance(value, list):
        keys = []
        for child in value:
            keys.extend(_walk_keys(child))
        return keys
    return []
