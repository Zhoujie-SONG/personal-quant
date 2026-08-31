from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from etf_quant.domain.enums import Sleeve


@dataclass(frozen=True, slots=True)
class LogicalAsset:
    id: str
    name: str
    sleeve: Sleeve
    cluster: str
    benchmark_index: str | None
    market_timezone: str = "Asia/Shanghai"

    def __post_init__(self) -> None:
        if not self.id or not self.cluster:
            raise ValueError("logical asset id and cluster are required")
        ZoneInfo(self.market_timezone)

