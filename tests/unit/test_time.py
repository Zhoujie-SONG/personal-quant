from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from etf_quant.utils.time import provider_datetime, shanghai_session_times, shanghai_trade_date


def test_epoch_timestamp_converts_to_shanghai_trade_date() -> None:
    instant = datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)
    assert shanghai_trade_date(provider_datetime(instant.timestamp())) == date(2024, 1, 2)


def test_session_times_are_explicitly_zoned() -> None:
    session_open, session_close = shanghai_session_times(date(2024, 1, 2))
    assert session_open.isoformat().endswith("+08:00")
    assert session_close.hour == 15


def test_unknown_provider_timestamp_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        provider_datetime("2024-01-02")

