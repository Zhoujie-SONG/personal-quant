from __future__ import annotations

from datetime import date, timedelta

import pytest

from etf_quant.domain.enums import AdjustType
from etf_quant.providers.akshare.provider import AkShareSupplementalProvider

pytestmark = pytest.mark.integration


def test_real_akshare_m1b_endpoints() -> None:
    provider = AkShareSupplementalProvider()
    assert provider.get_etf_snapshots()
    assert provider.get_szse_scale_snapshots()
    end = date.today() - timedelta(days=1)
    assert provider.get_daily_bars(
        "510300.SH", end - timedelta(days=30), end, AdjustType.NONE
    )
