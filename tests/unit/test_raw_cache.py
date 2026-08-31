from __future__ import annotations

from datetime import date, datetime, timezone

from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.domain.enums import AdjustType
from etf_quant.providers.dto import RawMarketBar


def raw_bar(day: int) -> RawMarketBar:
    return RawMarketBar(
        symbol="510300.SH",
        open="3.5",
        high="3.6",
        low="3.4",
        close="3.55",
        volume=100,
        turnover="355",
        provider_timestamp=datetime(2024, 1, day, tzinfo=timezone.utc),
        retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        provider="longbridge",
        sdk_version="test",
        provider_payload={"close": "3.55"},
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


def test_raw_cache_prevents_repeat_and_supports_incremental_ranges(tmp_path) -> None:
    cache = LongbridgeRawBarCache(tmp_path)
    retrieved_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
    cache.save(
        "510300.SH",
        date(2024, 1, 1),
        date(2024, 1, 10),
        AdjustType.NONE,
        [raw_bar(2), raw_bar(3)],
        retrieved_at=retrieved_at,
        sdk_version="test",
    )
    assert cache.missing_ranges(
        "510300.SH", date(2024, 1, 1), date(2024, 1, 10), AdjustType.NONE
    ) == []
    assert cache.missing_ranges(
        "510300.SH", date(2024, 1, 1), date(2024, 1, 15), AdjustType.NONE
    ) == [(date(2024, 1, 11), date(2024, 1, 15))]
    loaded = cache.load(
        "510300.SH", date(2024, 1, 1), date(2024, 1, 10), AdjustType.NONE
    )
    assert [item.close for item in loaded] == ["3.55", "3.55"]
    assert loaded[0].provider_payload == {"close": "3.55"}

