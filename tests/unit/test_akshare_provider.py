from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from etf_quant.domain.enums import AdjustType, DataAvailabilityClass
from etf_quant.providers.akshare.exceptions import AkShareSchemaError
from etf_quant.providers.akshare.mapper import map_etf_spot_frame
from etf_quant.providers.akshare.provider import AkShareSupplementalProvider
from etf_quant.providers.dto import RawETFMetadataObservation, RawMarketBar


def spot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": "510300",
                "名称": "fixture ETF",
                "IOPV实时估值": "--",
                "最新份额": "1000000",
                "数据日期": date(2026, 9, 1),
                "更新时间": datetime(2026, 9, 1, 15, 1),
            }
        ]
    )


def history_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "日期": date(2026, 8, 31),
                "开盘": "4.00",
                "收盘": "4.01",
                "最高": "4.02",
                "最低": "3.99",
                "成交量": "123",
                "成交额": "49323",
            }
        ]
    )


class FakeAkShare:
    def fund_etf_spot_em(self) -> pd.DataFrame:
        return spot_frame()

    def fund_etf_scale_szse(self) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "基金代码", "基金简称", "基金类别", "上市日期",
                "基金份额", "基金管理人", "净值",
            ]
        )

    def fund_etf_hist_em(self, **_: object) -> pd.DataFrame:
        return history_frame()


def test_required_column_schema_break_fails_loudly() -> None:
    with pytest.raises(AkShareSchemaError, match="missing required columns"):
        map_etf_spot_frame(
            spot_frame().drop(columns=["代码"]),
            retrieved_at=datetime(2026, 9, 1, 8, tzinfo=timezone.utc),
        )


def test_optional_missing_value_stays_unknown_not_zero() -> None:
    result = map_etf_spot_frame(
        spot_frame(),
        retrieved_at=datetime(2026, 9, 1, 8, tzinfo=timezone.utc),
    )[0]
    assert result.iopv is None
    assert result.shares == "1000000"
    assert result.availability_class is DataAvailabilityClass.SNAPSHOT_ONLY


def test_provider_returns_project_dtos_and_never_dataframe() -> None:
    provider = AkShareSupplementalProvider(FakeAkShare(), sdk_version="test")
    snapshots = provider.discover_etfs()
    bars = provider.get_daily_bars(
        "510300.SH", date(2026, 8, 31), date(2026, 8, 31), AdjustType.NONE
    )
    assert all(isinstance(item, RawETFMetadataObservation) for item in snapshots)
    assert all(isinstance(item, RawMarketBar) for item in bars)
    assert bars[0].volume == 12300  # AkShare lots -> canonical shares
    assert not any(isinstance(item, pd.DataFrame) for item in [*snapshots, *bars])
