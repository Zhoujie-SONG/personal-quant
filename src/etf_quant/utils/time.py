from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def provider_datetime(value: object) -> datetime:
    """Convert an SDK timestamp to an aware datetime without losing the instant."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    raise ValueError(f"unsupported provider timestamp type: {type(value).__name__}")


def shanghai_session_times(trade_date: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(trade_date, time(9, 30), tzinfo=SHANGHAI_TZ),
        datetime.combine(trade_date, time(15, 0), tzinfo=SHANGHAI_TZ),
    )


def shanghai_trade_date(value: datetime) -> date:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(SHANGHAI_TZ).date()

