from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from etf_quant.domain.enums import HistoricalDataSemantics
from etf_quant.providers.dto import RawBenchmarkLevel
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.exceptions import LongbridgeProviderError
from etf_quant.utils.time import provider_datetime, utc_now


@dataclass(frozen=True, slots=True)
class LongbridgeBenchmarkProbe:
    attempted_symbol: str
    static_returned: bool
    static_symbol: str | None
    static_name: str | None
    history_count: int
    history_error: str | None


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

    def probe_symbol(
        self,
        symbol: str,
        *,
        history_start: date,
        history_end: date,
    ) -> LongbridgeBenchmarkProbe:
        """Run independent static and unadjusted-history gates for one symbol."""
        static_rows = self._client.query(
            "research_static_probe",
            lambda context: context.static_info([symbol]),
        )
        static_match = next(
            (item for item in static_rows if str(getattr(item, "symbol", "")) == symbol),
            None,
        )
        history_count = 0
        history_error: str | None = None
        try:
            history_rows = self._client.query(
                "research_history_probe",
                lambda context: context.history_candlesticks_by_date(
                    symbol,
                    self._period_day(),
                    self._no_adjust(),
                    history_start,
                    history_end,
                ),
            )
            history_count = len(history_rows)
        except LongbridgeProviderError as exc:
            history_error = str(exc)
        return LongbridgeBenchmarkProbe(
            attempted_symbol=symbol,
            static_returned=static_match is not None,
            static_symbol=str(getattr(static_match, "symbol", "")) if static_match else None,
            static_name=(
                str(getattr(static_match, "name_en", "") or getattr(static_match, "name_cn", ""))
                if static_match
                else None
            ),
            history_count=history_count,
            history_error=history_error,
        )

    @staticmethod
    def _period_day() -> object:
        from longbridge.openapi import Period

        return Period.Day

    @staticmethod
    def _no_adjust() -> object:
        from longbridge.openapi import AdjustType

        return AdjustType.NoAdjust
