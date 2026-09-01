from __future__ import annotations

import importlib.metadata
from datetime import UTC, datetime

import pandas as pd

from etf_quant.domain.enums import HistoricalDataSemantics
from etf_quant.providers.dto import RawBenchmarkLevel


class AkShareResearchBenchmarkProvider:
    """Explicit research-only adapter for Shanghai Gold Exchange spot history."""

    def get_sge_spot_levels(self, symbol: str) -> list[RawBenchmarkLevel]:
        import akshare as ak

        retrieved_at = datetime.now(UTC)
        frame = ak.spot_hist_sge(symbol=symbol)
        required = {"date", "close"}
        if not required.issubset(frame.columns):
            raise ValueError(f"AkShare SGE response lacks columns: {required - set(frame.columns)}")
        observations: list[RawBenchmarkLevel] = []
        for row in frame.loc[:, ["date", "close"]].itertuples(index=False):
            if pd.isna(row.date) or pd.isna(row.close):
                continue
            observation_date = pd.Timestamp(row.date).date()
            observations.append(
                RawBenchmarkLevel(
                    symbol=symbol,
                    observation_date=observation_date,
                    level=str(row.close),
                    retrieved_at=retrieved_at,
                    provider="akshare",
                    sdk_version=importlib.metadata.version("akshare"),
                    historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
                    provider_payload={"date": observation_date.isoformat(), "close": str(row.close)},
                )
            )
        return sorted(observations, key=lambda item: item.observation_date)
