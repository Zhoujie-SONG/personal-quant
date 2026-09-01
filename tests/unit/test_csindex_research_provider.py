from __future__ import annotations

from datetime import date

import pytest

from etf_quant.providers.csindex.research_benchmarks import CSIResearchBenchmarkProvider


def test_csindex_provider_maps_exact_official_code_without_network() -> None:
    provider = CSIResearchBenchmarkProvider(
        transport=lambda _: {
            "success": True,
            "data": [
                {
                    "tradeDate": "20250102",
                    "indexCode": "H30184",
                    "indexNameCnAll": "中证全指半导体产品与设备指数",
                    "indexNameEnAll": "CSI All Share Semiconductors & Semiconductor Equipment Index",
                    "close": 4321.5,
                }
            ],
        }
    )

    rows = provider.get_daily_levels("H30184", date(2025, 1, 1), date(2025, 1, 3))

    assert len(rows) == 1
    assert rows[0].symbol == "H30184"
    assert rows[0].observation_date == date(2025, 1, 2)
    assert rows[0].level == "4321.5"
    assert rows[0].provider == "csindex"


def test_csindex_provider_fails_on_official_code_mismatch() -> None:
    provider = CSIResearchBenchmarkProvider(
        transport=lambda _: {
            "success": True,
            "data": [{"tradeDate": "20250102", "indexCode": "H01077", "close": 100.0}],
        }
    )

    with pytest.raises(ValueError, match="code mismatch"):
        provider.get_daily_levels("H11077", date(2025, 1, 1), date(2025, 1, 3))
