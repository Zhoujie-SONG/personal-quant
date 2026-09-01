from __future__ import annotations

import json
from datetime import date, datetime, timezone

from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.domain.enums import AdjustType, HistoricalDataSemantics
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.dto import RawMarketBar
from etf_quant.utils.time import shanghai_session_times


def raw_bar(trade_date: date, *, retrieved_at: datetime | None = None) -> RawMarketBar:
    return RawMarketBar(
        symbol="510300.SH",
        open="3.5",
        high="3.6",
        low="3.4",
        close="3.55",
        volume=100,
        turnover="355",
        provider_timestamp=datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc),
        retrieved_at=retrieved_at or datetime(2024, 2, 1, tzinfo=timezone.utc),
        provider="longbridge",
        sdk_version="test",
        historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
        provider_payload={"close": "3.55"},
    )


def save(
    cache: LongbridgeRawBarCache,
    start_date: date,
    end_date: date,
    bars: list[RawMarketBar],
    expected: set[date],
    *,
    retrieved_at: datetime = datetime(2024, 2, 1, tzinfo=timezone.utc),
) -> None:
    policy = DailyBarAvailabilityPolicy()
    cache.save(
        "510300.SH",
        start_date,
        end_date,
        AdjustType.NONE,
        bars,
        expected_trading_dates=expected,
        finalization_cutoffs={
            value: policy.available_at(shanghai_session_times(value)[1])
            for value in expected
        },
        retrieved_at=retrieved_at,
        sdk_version="test",
    )


def missing(
    cache: LongbridgeRawBarCache,
    start_date: date,
    end_date: date,
    expected: set[date],
) -> list[tuple[date, date]]:
    return cache.missing_ranges(
        "510300.SH",
        start_date,
        end_date,
        AdjustType.NONE,
        expected_trading_dates=expected,
    )


def test_raw_cache_request_key_is_stable_and_input_sensitive() -> None:
    first = LongbridgeRawBarCache.request_key(
        "510300.SH", date(2024, 1, 1), date(2024, 1, 31), AdjustType.NONE
    )
    second = LongbridgeRawBarCache.request_key(
        "510300.sh", date(2024, 1, 1), date(2024, 1, 31), AdjustType.NONE
    )
    changed = LongbridgeRawBarCache.request_key(
        "510300.SH", date(2024, 1, 1), date(2024, 2, 1), AdjustType.NONE
    )
    assert first == second
    assert first != changed


def test_weekend_without_bars_is_complete_when_expected_days_exist(tmp_path) -> None:
    cache = LongbridgeRawBarCache(tmp_path)
    friday = date(2024, 1, 5)
    monday = date(2024, 1, 8)
    expected = {friday, monday}
    save(cache, friday, monday, [raw_bar(friday), raw_bar(monday)], expected)
    assert missing(cache, friday, monday, expected) == []


def test_missing_trading_day_remains_incomplete(tmp_path) -> None:
    cache = LongbridgeRawBarCache(tmp_path)
    tuesday = date(2024, 1, 2)
    wednesday = date(2024, 1, 3)
    expected = {tuesday, wednesday}
    save(cache, tuesday, wednesday, [raw_bar(tuesday)], expected)
    assert missing(cache, tuesday, wednesday, expected) == [(wednesday, wednesday)]

    manifest_path = (
        tmp_path / "longbridge" / "bars" / "510300.SH" / "none" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["requested_coverage"]
    assert manifest["finalized_dates"] == [tuesday.isoformat()]
    assert manifest["provisional_dates"] == []


def test_unfinalized_current_trading_day_is_requested_again(tmp_path) -> None:
    cache = LongbridgeRawBarCache(tmp_path)
    current_trade_date = date(2024, 1, 4)
    save(cache, current_trade_date, current_trade_date, [], {current_trade_date})
    assert missing(
        cache, current_trade_date, current_trade_date, {current_trade_date}
    ) == [(current_trade_date, current_trade_date)]


def test_verified_dates_prevent_repeat_and_increment_incrementally(tmp_path) -> None:
    cache = LongbridgeRawBarCache(tmp_path)
    first = date(2024, 1, 2)
    second = date(2024, 1, 3)
    third = date(2024, 1, 4)
    save(cache, first, second, [raw_bar(first), raw_bar(second)], {first, second})
    assert missing(cache, first, second, {first, second}) == []
    assert missing(cache, first, third, {first, second, third}) == [(third, third)]
    loaded = cache.load("510300.SH", first, second, AdjustType.NONE)
    assert [item.close for item in loaded] == ["3.55", "3.55"]
    assert loaded[0].provider_payload == {"close": "3.55"}


def test_current_day_bar_before_cutoff_remains_provisional_and_retryable(tmp_path) -> None:
    cache = LongbridgeRawBarCache(tmp_path)
    trade_date = date(2024, 1, 4)
    pre_cutoff = datetime(2024, 1, 4, 7, 3, tzinfo=timezone.utc)
    save(
        cache,
        trade_date,
        trade_date,
        [raw_bar(trade_date, retrieved_at=pre_cutoff)],
        {trade_date},
        retrieved_at=pre_cutoff,
    )
    assert missing(cache, trade_date, trade_date, {trade_date}) == [
        (trade_date, trade_date)
    ]


def test_current_day_bar_after_cutoff_becomes_finalized(tmp_path) -> None:
    cache = LongbridgeRawBarCache(tmp_path)
    trade_date = date(2024, 1, 4)
    post_cutoff = datetime(2024, 1, 4, 7, 16, tzinfo=timezone.utc)
    save(
        cache,
        trade_date,
        trade_date,
        [raw_bar(trade_date, retrieved_at=post_cutoff)],
        {trade_date},
        retrieved_at=post_cutoff,
    )
    assert missing(cache, trade_date, trade_date, {trade_date}) == []
