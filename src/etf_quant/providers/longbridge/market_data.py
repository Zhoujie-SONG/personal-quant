from __future__ import annotations

import importlib.metadata
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.domain.enums import AdjustType, Market
from etf_quant.providers.dto import RawInstrument, RawMarketBar, RawQuote, RawTradingDay
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.mapper import (
    map_market_bar,
    map_quote,
    map_static_info,
    map_trading_days,
    to_longbridge_symbol,
)
from etf_quant.utils.time import utc_now


class LongbridgeMarketDataProvider:
    def __init__(
        self,
        client: LongbridgeClient,
        *,
        raw_cache: LongbridgeRawBarCache | None = None,
        sdk_version: str | None = None,
    ) -> None:
        self._client = client
        self._cache = raw_cache or LongbridgeRawBarCache(Path("data/raw"))
        self._sdk_version = sdk_version or importlib.metadata.version("longbridge")

    @property
    def name(self) -> str:
        return "longbridge"

    def get_static_info(self, symbols: Sequence[str]) -> list[RawInstrument]:
        normalized = [to_longbridge_symbol(symbol) for symbol in symbols]
        retrieved_at = utc_now()
        response = self._client.query("static_info", lambda context: context.static_info(normalized))
        return [
            map_static_info(item, retrieved_at=retrieved_at, sdk_version=self._sdk_version)
            for item in response
        ]

    def get_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: AdjustType = AdjustType.NONE,
    ) -> list[RawMarketBar]:
        normalized = to_longbridge_symbol(symbol)
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        expected_trading_dates = {
            item.trade_date
            for item in self.get_trading_days(Market.CN, start_date, end_date)
        }
        for missing_start, missing_end in self._cache.missing_ranges(
            normalized,
            start_date,
            end_date,
            adjust_type,
            expected_trading_dates=expected_trading_dates,
        ):
            retrieved_at = utc_now()
            response = self._client.query(
                "history_candlesticks_by_date",
                lambda context, begin=missing_start, end=missing_end: context.history_candlesticks_by_date(
                    normalized,
                    self._period_day(),
                    self._adjust_type(adjust_type),
                    begin,
                    end,
                ),
            )
            bars = [
                map_market_bar(
                    item,
                    symbol=normalized,
                    retrieved_at=retrieved_at,
                    sdk_version=self._sdk_version,
                )
                for item in response
            ]
            self._cache.save(
                normalized,
                missing_start,
                missing_end,
                adjust_type,
                bars,
                expected_trading_dates={
                    trade_date
                    for trade_date in expected_trading_dates
                    if missing_start <= trade_date <= missing_end
                },
                retrieved_at=retrieved_at,
                sdk_version=self._sdk_version,
            )
        return self._cache.load(normalized, start_date, end_date, adjust_type)

    def get_trading_days(
        self,
        market: Market,
        start_date: date,
        end_date: date,
    ) -> list[RawTradingDay]:
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        result: list[RawTradingDay] = []
        chunk_start = start_date
        while chunk_start <= end_date:
            chunk_end = min(end_date, chunk_start + timedelta(days=27))
            retrieved_at = utc_now()
            response = self._client.query(
                "trading_days",
                lambda context, begin=chunk_start, end=chunk_end: context.trading_days(
                    self._market(market), begin, end
                ),
            )
            result.extend(
                map_trading_days(
                    response,
                    market=market.value,
                    retrieved_at=retrieved_at,
                    sdk_version=self._sdk_version,
                )
            )
            chunk_start = chunk_end + timedelta(days=1)
        return result

    def get_quote(self, symbols: Sequence[str]) -> list[RawQuote]:
        normalized = [to_longbridge_symbol(symbol) for symbol in symbols]
        retrieved_at = utc_now()
        response = self._client.query("quote", lambda context: context.quote(normalized))
        return [
            map_quote(item, retrieved_at=retrieved_at, sdk_version=self._sdk_version)
            for item in response
        ]

    @staticmethod
    def _period_day() -> object:
        from longbridge.openapi import Period

        return Period.Day

    @staticmethod
    def _adjust_type(adjust_type: AdjustType) -> object:
        from longbridge.openapi import AdjustType as LongbridgeAdjustType

        return (
            LongbridgeAdjustType.NoAdjust
            if adjust_type is AdjustType.NONE
            else LongbridgeAdjustType.ForwardAdjust
        )

    @staticmethod
    def _market(market: Market) -> object:
        from longbridge.openapi import Market as LongbridgeMarket

        if market is not Market.CN:
            raise ValueError(f"unsupported market: {market}")
        return LongbridgeMarket.CN
