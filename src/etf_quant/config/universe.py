from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import yaml


FROZEN_V1_ACTIVE_IDS = frozenset(
    {
        "CN_LARGE",
        "CN_SMALL",
        "CN_GROWTH",
        "CN_DIVIDEND",
        "SEMI",
        "HEALTHCARE",
        "CONSUMER",
        "COAL",
        "SP500",
        "NASDAQ100",
        "HK_BROAD",
        "GOLD",
        "BOND_LONG",
        "BOND_MED",
        "CASH",
    }
)

FROZEN_V1_NAMES = {
    "CN_LARGE": "沪深300",
    "CN_SMALL": "中证1000",
    "CN_GROWTH": "创业板",
    "CN_DIVIDEND": "红利",
    "SEMI": "半导体",
    "HEALTHCARE": "医药医疗",
    "CONSUMER": "消费",
    "COAL": "煤炭",
    "SP500": "标普500",
    "NASDAQ100": "纳斯达克100",
    "HK_BROAD": "港股宽基",
    "GOLD": "黄金",
    "BOND_LONG": "长久期中国国债",
    "BOND_MED": "中久期中国国债",
    "CASH": "现金",
}

FROZEN_V1_SLEEVES = {
    "CHINA_BROAD_STYLE": frozenset({"CN_LARGE", "CN_SMALL", "CN_GROWTH", "CN_DIVIDEND"}),
    "CHINA_INDUSTRY": frozenset({"SEMI", "HEALTHCARE", "CONSUMER", "COAL"}),
    "OVERSEAS_EQUITY": frozenset({"SP500", "NASDAQ100", "HK_BROAD"}),
    "COMMODITY": frozenset({"GOLD"}),
    "DEFENSIVE": frozenset({"BOND_LONG", "BOND_MED", "CASH"}),
}

FROZEN_V1_CLUSTERS = {
    "CN_GROWTH_TECH": frozenset({"CN_GROWTH", "SEMI"}),
    "US_EQUITY": frozenset({"SP500", "NASDAQ100"}),
    "CN_RATES": frozenset({"BOND_LONG", "BOND_MED"}),
}

FROZEN_V1_BENCHMARKS: dict[str, tuple[str | None, str | None, str, str | None]] = {
    "CN_LARGE": ("000300.SH", "longbridge", "INDEX", None),
    "CN_SMALL": ("000852.SH", "longbridge", "INDEX", None),
    "CN_GROWTH": ("399006.SZ", "longbridge", "INDEX", None),
    "CN_DIVIDEND": ("000922.SH", "longbridge", "INDEX", None),
    "SEMI": ("H30184", "csindex", "INDEX", "PRICE_INDEX"),
    "HEALTHCARE": ("000991.SH", "longbridge", "INDEX", None),
    "CONSUMER": ("000932.SH", "longbridge", "INDEX", None),
    "COAL": ("399998.SZ", "longbridge", "INDEX", None),
    "SP500": (".SPX.US", "longbridge", "INDEX", None),
    "NASDAQ100": (".NDX.US", "longbridge", "INDEX", None),
    "HK_BROAD": ("HSI.HK", "longbridge", "INDEX", None),
    "GOLD": ("Au99.99", "akshare", "SPOT", None),
    "BOND_LONG": ("H11077", "csindex", "INDEX", "FULL_PRICE_INDEX"),
    "BOND_MED": ("H00140", "csindex", "INDEX", "FULL_PRICE_INDEX"),
    "CASH": (None, None, "CASH_PROXY", None),
}

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL_LIKE_ID_RE = re.compile(r"^\d{6}(?:\.(?:SH|SZ))?$")
_FORBIDDEN_VEHICLE_FIELDS = {"execution_symbol", "vehicle_symbol", "etf_symbol"}


@dataclass(frozen=True, slots=True)
class BenchmarkReference:
    symbol: str | None
    provider: str | None
    benchmark_type: str
    series_kind: str | None


@dataclass(frozen=True, slots=True)
class FrozenLogicalAsset:
    id: str
    name_cn: str
    status: str
    sleeve: str
    benchmark_reference: BenchmarkReference


@dataclass(frozen=True, slots=True)
class FrozenCandidate:
    id: str
    status: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FrozenUniverse:
    schema_name: str
    schema_version: str
    universe_name: str
    universe_status: str
    freeze_date: str
    freeze_source_commit: str
    u1_commit: str
    u1_1_commit: str
    benchmark_registry_path: str
    benchmark_registry_source_commit: str
    benchmark_mapping_hash: str
    active_logical_assets: tuple[FrozenLogicalAsset, ...]
    deferred_inactive_candidates: tuple[FrozenCandidate, ...]
    sleeves: Mapping[str, tuple[str, ...]]
    predeclared_risk_clusters: Mapping[str, tuple[str, ...]]
    execution_vehicle_registry: str | None
    vehicle_selector_status: str

    @classmethod
    def from_yaml(cls, path: Path) -> "FrozenUniverse":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise ValueError("universe config must be a mapping")
        freeze = _mapping(payload, "freeze_provenance")
        registry = _mapping(payload, "benchmark_registry")
        execution = _mapping(payload, "execution_vehicle_boundary")

        assets: list[FrozenLogicalAsset] = []
        for index, row_value in enumerate(_list(payload, "active_logical_assets")):
            if not isinstance(row_value, Mapping):
                raise ValueError(f"active_logical_assets[{index}] must be a mapping")
            forbidden = _FORBIDDEN_VEHICLE_FIELDS.intersection(row_value)
            if forbidden:
                raise ValueError(f"execution vehicle fields are forbidden: {sorted(forbidden)}")
            reference = _mapping(row_value, "benchmark_reference")
            assets.append(
                FrozenLogicalAsset(
                    id=_required_str(row_value, "id"),
                    name_cn=_required_str(row_value, "name_cn"),
                    status=_required_str(row_value, "status"),
                    sleeve=_required_str(row_value, "sleeve"),
                    benchmark_reference=BenchmarkReference(
                        symbol=_optional_str(reference.get("symbol")),
                        provider=_optional_str(reference.get("provider")),
                        benchmark_type=_required_str(reference, "benchmark_type"),
                        series_kind=_optional_str(reference.get("series_kind")),
                    ),
                )
            )

        candidates: list[FrozenCandidate] = []
        for index, row_value in enumerate(_list(payload, "deferred_inactive_candidates")):
            if not isinstance(row_value, Mapping):
                raise ValueError(f"deferred_inactive_candidates[{index}] must be a mapping")
            candidates.append(
                FrozenCandidate(
                    id=_required_str(row_value, "id"),
                    status=_required_str(row_value, "status"),
                    payload=dict(row_value),
                )
            )

        universe = cls(
            schema_name=_required_str(payload, "schema_name"),
            schema_version=_required_str(payload, "schema_version"),
            universe_name=_required_str(payload, "universe_name"),
            universe_status=_required_str(payload, "universe_status"),
            freeze_date=_required_str(freeze, "freeze_date"),
            freeze_source_commit=_required_str(freeze, "freeze_source_commit"),
            u1_commit=_required_str(freeze, "u1_commit"),
            u1_1_commit=_required_str(freeze, "u1_1_commit"),
            benchmark_registry_path=_required_str(registry, "path"),
            benchmark_registry_source_commit=_required_str(
                registry, "benchmark_registry_source_commit"
            ),
            benchmark_mapping_hash=_required_str(registry, "benchmark_mapping_hash"),
            active_logical_assets=tuple(assets),
            deferred_inactive_candidates=tuple(candidates),
            sleeves=_string_tuple_mapping(payload, "sleeves"),
            predeclared_risk_clusters=_string_tuple_mapping(
                payload, "predeclared_risk_clusters"
            ),
            execution_vehicle_registry=_optional_str(execution.get("execution_vehicle_registry")),
            vehicle_selector_status=_required_str(execution, "vehicle_selector_status"),
        )
        universe.validate()
        return universe

    def validate(self) -> None:
        if self.schema_name != "logical_asset_universe" or self.schema_version != "1.0":
            raise ValueError("Universe v1 requires logical_asset_universe schema version 1.0")
        if self.universe_status != "FROZEN_V1":
            raise ValueError("Universe v1 status must be FROZEN_V1")
        try:
            date.fromisoformat(self.freeze_date)
        except ValueError as exc:
            raise ValueError("freeze_date must be an ISO calendar date") from exc
        for name, value in {
            "freeze_source_commit": self.freeze_source_commit,
            "u1_commit": self.u1_commit,
            "u1_1_commit": self.u1_1_commit,
            "benchmark_registry_source_commit": self.benchmark_registry_source_commit,
        }.items():
            if not _COMMIT_RE.fullmatch(value):
                raise ValueError(f"{name} must be a full lowercase Git commit hash")
        if not _HASH_RE.fullmatch(self.benchmark_mapping_hash):
            raise ValueError("benchmark_mapping_hash must be a lowercase SHA-256")

        ids = [asset.id for asset in self.active_logical_assets]
        if len(ids) != 15 or len(set(ids)) != len(ids):
            raise ValueError("Universe v1 requires exactly 15 unique ACTIVE logical assets")
        if frozenset(ids) != FROZEN_V1_ACTIVE_IDS:
            raise ValueError("ACTIVE logical assets differ from the human-approved v1 freeze")
        for asset in self.active_logical_assets:
            if asset.status != "ACTIVE":
                raise ValueError(f"{asset.id} must have ACTIVE status")
            if asset.name_cn != FROZEN_V1_NAMES[asset.id]:
                raise ValueError(f"{asset.id} name differs from the human-approved v1 freeze")
            if _SYMBOL_LIKE_ID_RE.fullmatch(asset.id) or "." in asset.id:
                raise ValueError(f"{asset.id} looks like a market/execution symbol, not a Logical Asset ID")
            expected = FROZEN_V1_BENCHMARKS[asset.id]
            actual = (
                asset.benchmark_reference.symbol,
                asset.benchmark_reference.provider,
                asset.benchmark_reference.benchmark_type,
                asset.benchmark_reference.series_kind,
            )
            if actual != expected:
                raise ValueError(f"{asset.id} benchmark reference differs from the frozen mapping")

        actual_sleeves = {name: frozenset(members) for name, members in self.sleeves.items()}
        if actual_sleeves != FROZEN_V1_SLEEVES:
            raise ValueError("sleeve assignments differ from the human-approved v1 freeze")
        assignments = [member for members in self.sleeves.values() for member in members]
        if len(assignments) != len(ids) or set(assignments) != set(ids):
            raise ValueError("every ACTIVE logical asset must appear in exactly one sleeve")
        sleeve_by_asset = {member: sleeve for sleeve, members in self.sleeves.items() for member in members}
        if any(sleeve_by_asset[asset.id] != asset.sleeve for asset in self.active_logical_assets):
            raise ValueError("asset sleeve field does not match the declared sleeve membership")

        actual_clusters = {
            name: frozenset(members) for name, members in self.predeclared_risk_clusters.items()
        }
        if actual_clusters != FROZEN_V1_CLUSTERS:
            raise ValueError("risk clusters differ from the human-approved v1 freeze")
        if any(not members.issubset(FROZEN_V1_ACTIVE_IDS) for members in actual_clusters.values()):
            raise ValueError("all risk cluster members must be ACTIVE logical assets")
        if any({"CN_DIVIDEND", "COAL"}.issubset(members) for members in actual_clusters.values()):
            raise ValueError("CN_DIVIDEND and COAL must remain economically distinct")

        candidates = {item.id: item for item in self.deferred_inactive_candidates}
        if set(candidates) != {"HSTECH", "OIL"}:
            raise ValueError("deferred/inactive candidates must be exactly HSTECH and OIL")
        if candidates["HSTECH"].status != "DEFERRED_REDUNDANCY":
            raise ValueError("HSTECH must remain DEFERRED_REDUNDANCY")
        if candidates["OIL"].status != "INACTIVE_NO_VALID_ETF_VEHICLE":
            raise ValueError("OIL must remain INACTIVE_NO_VALID_ETF_VEHICLE")
        if self.execution_vehicle_registry is not None:
            raise ValueError("Universe v1 must not embed an execution vehicle registry")
        if self.vehicle_selector_status != "NOT_IMPLEMENTED":
            raise ValueError("Vehicle Selector must remain NOT_IMPLEMENTED in Universe v1")

    def validate_benchmark_registry(self, registry_path: Path) -> None:
        raw = registry_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.benchmark_mapping_hash:
            raise ValueError("benchmark registry content does not match the frozen mapping hash")
        payload = yaml.safe_load(raw) or {}
        if not isinstance(payload, Mapping) or not isinstance(payload.get("benchmarks"), list):
            raise ValueError("benchmark registry must contain a benchmarks list")
        rows = {
            str(row["logical_asset_id"]): row
            for row in payload["benchmarks"]
            if isinstance(row, Mapping) and row.get("logical_asset_id") is not None
        }
        for asset in self.active_logical_assets:
            if asset.id not in rows:
                raise ValueError(f"benchmark registry is missing {asset.id}")
            row = rows[asset.id]
            actual = (
                _optional_str(row.get("benchmark_symbol")),
                _optional_str(row.get("provider")),
                _required_str(row, "benchmark_type"),
                _optional_str(row.get("series_kind")),
            )
            expected = FROZEN_V1_BENCHMARKS[asset.id]
            if actual != expected:
                raise ValueError(f"candidate benchmark registry no longer matches {asset.id}")


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be a mapping")
    return value


def _list(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"{key} is required")
    return str(value)


def _optional_str(value: object) -> str | None:
    return None if value in (None, "") else str(value)


def _string_tuple_mapping(payload: Mapping[str, Any], key: str) -> dict[str, tuple[str, ...]]:
    value = _mapping(payload, key)
    result: dict[str, tuple[str, ...]] = {}
    for name, members in value.items():
        if not isinstance(members, list) or not members:
            raise ValueError(f"{key}.{name} must be a non-empty list")
        result[str(name)] = tuple(str(member) for member in members)
    return result
