from __future__ import annotations

import importlib.metadata
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from etf_quant.domain.enums import HistoricalDataSemantics
from etf_quant.providers.dto import RawBenchmarkLevel
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.utils.time import provider_datetime, utc_now


class LongbridgeResearchBenchmarkProvider:
    """Explicit, quota-conscious index-history adapter for research diagnostics.

    It deliberately accepts provider-native global index symbols and does not
    participate in the formal A-share canonical market-bar ingestion path.
    """

    def __init__(self, client: LongbridgeClient, *, sdk_version: str | None = None) -> None:
        self._client = client
        self._sdk_version = sdk_version or importlib.metadata.version("longbridge")

    def get_daily_levels(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        timezone: str,
        chunk_days: int = 366,
    ) -> list[RawBenchmarkLevel]:
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        if chunk_days < 1:
            raise ValueError("chunk_days must be positive")
        zone = ZoneInfo(timezone)
        observations: dict[date, RawBenchmarkLevel] = {}
        chunk_start = start_date
        while chunk_start <= end_date:
            chunk_end = min(end_date, chunk_start + timedelta(days=chunk_days - 1))
            retrieved_at = utc_now()
            response = self._client.query(
                "research_history_candlesticks_by_date",
                lambda context, begin=chunk_start, end=chunk_end: context.history_candlesticks_by_date(
                    symbol,
                    self._period_day(),
                    self._no_adjust(),
                    begin,
                    end,
                ),
            )
            for item in response:
                timestamp = provider_datetime(getattr(item, "timestamp"))
                observation_date = timestamp.astimezone(zone).date()
                observations[observation_date] = RawBenchmarkLevel(
                    symbol=symbol,
                    observation_date=observation_date,
                    level=str(getattr(item, "close")),
                    retrieved_at=retrieved_at,
                    provider="longbridge",
                    sdk_version=self._sdk_version,
                    historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
                    provider_payload={
                        "timestamp": timestamp.isoformat(),
                        "close": str(getattr(item, "close")),
                    },
                )
            chunk_start = chunk_end + timedelta(days=1)
        return [observations[key] for key in sorted(observations)]

    @staticmethod
    def _period_day() -> object:
        from longbridge.openapi import Period

        return Period.Day

    @staticmethod
    def _no_adjust() -> object:
        from longbridge.openapi import AdjustType

        return AdjustType.NoAdjust
