from __future__ import annotations

from pathlib import Path

from etf_quant.config.data_sources import DataSourceRegistry
from etf_quant.domain.enums import DataAvailabilityClass


def test_data_availability_class_has_conservative_four_way_classification() -> None:
    assert {item.value for item in DataAvailabilityClass} == {
        "true_historical_vintage",
        "historical_latest",
        "snapshot_only",
        "forward_collected_pit",
    }


def test_machine_readable_source_registry_defines_formal_and_supplemental_roles() -> None:
    root = Path(__file__).parents[2]
    registry = DataSourceRegistry.from_yaml(root / "configs" / "data_sources.yaml")
    longbridge = registry.find("longbridge", "historical_daily_ohlcv", "OHLCV_turnover")
    akshare = registry.find(
        "akshare", "fund_etf_hist_em", "OHLCV_turnover"
    )
    spot = registry.find(
        "akshare", "fund_etf_spot_em", "symbol_fund_name_iopv_latest_shares"
    )
    assert longbridge.formal_backtest_allowed is True
    assert longbridge.availability_class is DataAvailabilityClass.HISTORICAL_LATEST
    assert akshare.formal_backtest_allowed is False
    assert spot.availability_class is DataAvailabilityClass.SNAPSHOT_ONLY
    assert registry.etf_cemetery_completeness == "UNVERIFIED"
