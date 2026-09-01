from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, Callable
from urllib.parse import urlencode

import requests

from etf_quant.domain.enums import HistoricalDataSemantics
from etf_quant.providers.dto import RawBenchmarkLevel


class CSIResearchBenchmarkProvider:
    """Research-only adapter for the official CSI index-performance endpoint."""

    _URL = "https://www.csindex.com.cn/csindex-home/perf/index-perf"

    def __init__(self, *, transport: Callable[[str], dict[str, Any]] | None = None) -> None:
        self._transport = transport or self._get_json

    def get_daily_levels(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[RawBenchmarkLevel]:
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        query = urlencode(
            {
                "indexCode": symbol,
                "startDate": start_date.strftime("%Y%m%d"),
                "endDate": end_date.strftime("%Y%m%d"),
            }
        )
        payload = self._transport(f"{self._URL}?{query}")
        if payload.get("success") is not True or not isinstance(payload.get("data"), list):
            raise ValueError(f"CSI index-perf response failed for {symbol}")
        retrieved_at = datetime.now(UTC)
        observations: list[RawBenchmarkLevel] = []
        for row in payload["data"]:
            if not isinstance(row, dict):
                raise ValueError(f"CSI index-perf returned a non-object row for {symbol}")
            returned_code = str(row.get("indexCode", ""))
            if returned_code != symbol:
                raise ValueError(
                    f"CSI index-perf code mismatch: requested {symbol}, returned {returned_code}"
                )
            close = row.get("close")
            if close is None:
                continue
            observation_date = datetime.strptime(str(row["tradeDate"]), "%Y%m%d").date()
            observations.append(
                RawBenchmarkLevel(
                    symbol=symbol,
                    observation_date=observation_date,
                    level=str(close),
                    retrieved_at=retrieved_at,
                    provider="csindex",
                    sdk_version="official-index-perf-v1",
                    historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
                    provider_payload={
                        "index_code": returned_code,
                        "index_name_cn_all": str(row.get("indexNameCnAll", "")),
                        "index_name_en_all": str(row.get("indexNameEnAll", "")),
                        "trade_date": str(row["tradeDate"]),
                        "close": str(close),
                    },
                )
            )
        observations.sort(key=lambda item: item.observation_date)
        if not observations:
            raise ValueError(f"CSI index-perf returned no close observations for {symbol}")
        return observations

    @staticmethod
    def _get_json(url: str) -> dict[str, Any]:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return json.loads(response.text)
