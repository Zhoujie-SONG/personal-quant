from __future__ import annotations

import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from etf_quant.domain.enums import AdjustType, HistoricalDataSemantics
from etf_quant.domain.exceptions import DataValidationError
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.dto import RawMarketBar
from etf_quant.services.data_ingestion import MarketDataIngestionService


class RecordingProvider:
    name = "test"

    def __init__(self) -> None:
        self.calls = 0

    def get_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType = AdjustType.NONE,
    ) -> list[RawMarketBar]:
        self.calls += 1
        return [
            RawMarketBar(
                symbol=symbol,
                open="3.95",
                high="4.10",
                low="3.90",
                close="4.00",
                volume=100,
                turnover="400",
                provider_timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
                retrieved_at=datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
                provider="test",
                sdk_version="test",
                historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
            )
        ]


class RecordingRepository:
    def __init__(self) -> None:
        self.bars: list[object] = []

    def append_bars(self, bars: object) -> int:
        self.bars = list(bars)  # type: ignore[arg-type]
        return len(self.bars)


def test_daily_bar_availability_policy_applies_configurable_delay() -> None:
    close = datetime(2024, 1, 2, 15, 0, tzinfo=timezone(timedelta(hours=8)))
    policy = DailyBarAvailabilityPolicy(eod_delay=timedelta(minutes=20))
    assert policy.available_at(close) == close + timedelta(minutes=20)
    assert policy.policy_id == "daily_bar_eod_v1_20m"


def test_formal_canonical_ingestion_rejects_forward_adjustment_before_provider_call() -> None:
    provider = RecordingProvider()
    repository = RecordingRepository()
    service = MarketDataIngestionService(
        provider,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        DailyBarAvailabilityPolicy(),
    )
    with pytest.raises(DataValidationError, match="unadjusted"):
        service.ingest_daily_bars(
            "510300.SH",
            date(2024, 1, 1),
            date(2024, 1, 3),
            adjust_type=AdjustType.FORWARD,
        )
    assert provider.calls == 0
    assert repository.bars == []


def test_formal_unadjusted_ingestion_uses_availability_policy() -> None:
    provider = RecordingProvider()
    repository = RecordingRepository()
    service = MarketDataIngestionService(
        provider,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        DailyBarAvailabilityPolicy(eod_delay=timedelta(minutes=15)),
    )
    assert service.ingest_daily_bars(
        "510300.SH", date(2024, 1, 1), date(2024, 1, 3)
    ) == 1
    bar = repository.bars[0]
    assert bar.available_time == bar.data_time + timedelta(minutes=15)  # type: ignore[attr-defined]


def test_lower_layers_do_not_import_longbridge_adapter() -> None:
    project_root = Path(__file__).parents[2]
    scoped_roots = [
        project_root / "src" / "etf_quant" / "data",
        project_root / "src" / "etf_quant" / "domain",
        project_root / "src" / "etf_quant" / "services",
    ]
    violations: list[str] = []
    for scoped_root in scoped_roots:
        for path in scoped_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                if any(
                    module.startswith("etf_quant.providers.longbridge")
                    for module in modules
                ):
                    violations.append(str(path.relative_to(project_root)))
    assert violations == []
