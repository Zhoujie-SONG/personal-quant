from __future__ import annotations

import importlib.metadata
from datetime import date, datetime
from typing import Any

from etf_quant.domain.enums import AdjustType
from etf_quant.providers.akshare.exceptions import AkShareProviderError
from etf_quant.providers.akshare.mapper import (
    map_etf_history_frame,
    map_etf_spot_frame,
    map_szse_scale_frame,
)
from etf_quant.providers.dto import RawETFMetadataObservation, RawMarketBar
from etf_quant.utils.time import utc_now


class AkShareSupplementalProvider:
    """Small supplemental adapter; it is never a formal canonical market source."""

    def __init__(self, api: Any | None = None, *, sdk_version: str | None = None) -> None:
        if api is None:
            import akshare as api_module

            api = api_module
        self._api = api
        self._sdk_version = sdk_version or importlib.metadata.version("akshare")

    @property
    def name(self) -> str:
        return "akshare"

    def discover_etfs(self) -> list[RawETFMetadataObservation]:
        return self.get_etf_snapshots()

    def get_etf_snapshots(self) -> list[RawETFMetadataObservation]:
        retrieved_at = utc_now()
        frame = self._call("fund_etf_spot_em", self._api.fund_etf_spot_em)
        return map_etf_spot_frame(frame, retrieved_at=retrieved_at)

    def get_szse_scale_snapshots(self) -> list[RawETFMetadataObservation]:
        retrieved_at = utc_now()
        frame = self._call("fund_etf_scale_szse", self._api.fund_etf_scale_szse)
        return map_szse_scale_frame(frame, retrieved_at=retrieved_at)

    def get_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType = AdjustType.NONE,
    ) -> list[RawMarketBar]:
        if adjust_type is not AdjustType.NONE:
            raise AkShareProviderError("AkShare reconciliation requires unadjusted bars")
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        code = symbol.split(".", 1)[0]
        retrieved_at = utc_now()
        frame = self._call(
            "fund_etf_hist_em",
            lambda: self._api.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust="",
            ),
        )
        return map_etf_history_frame(
            frame,
            symbol=symbol,
            retrieved_at=retrieved_at,
            sdk_version=self._sdk_version,
        )

    @staticmethod
    def _call(endpoint: str, operation: Any) -> Any:
        try:
            return operation()
        except AkShareProviderError:
            raise
        except Exception as exc:
            raise AkShareProviderError(f"{endpoint} failed: {type(exc).__name__}: {exc}") from exc
