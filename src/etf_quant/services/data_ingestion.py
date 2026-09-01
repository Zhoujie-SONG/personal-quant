from __future__ import annotations

from datetime import date

from etf_quant.data.canonical.normalizers import normalize_market_bar
from etf_quant.data.repositories.market_repository import MarketRepository
from etf_quant.domain.enums import AdjustType
from etf_quant.domain.exceptions import DataValidationError
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.base import MarketDataProvider


class MarketDataIngestionService:
    def __init__(
        self,
        provider: MarketDataProvider,
        repository: MarketRepository,
        availability_policy: DailyBarAvailabilityPolicy,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._availability_policy = availability_policy

    def ingest_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        adjust_type: AdjustType = AdjustType.NONE,
    ) -> int:
        if adjust_type is not AdjustType.NONE:
            raise DataValidationError(
                "formal PIT canonical ingestion requires unadjusted daily bars; "
                "forward-adjusted history is provider capability only"
            )
        raw_bars = self._provider.get_daily_bars(symbol, start_date, end_date, adjust_type)
        canonical_bars = [
            normalize_market_bar(item, self._availability_policy) for item in raw_bars
        ]
        return self._repository.append_bars(canonical_bars)
