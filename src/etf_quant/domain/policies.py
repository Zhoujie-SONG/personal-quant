from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from etf_quant.domain.exceptions import DataValidationError


@dataclass(frozen=True, slots=True)
class DailyBarAvailabilityPolicy:
    """Conservative policy for completed daily-bar availability.

    The delay is an internal research policy, not an exchange guarantee.
    """

    eod_delay: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        if self.eod_delay < timedelta(0):
            raise DataValidationError("daily-bar EOD delay cannot be negative")

    def available_at(self, session_close: datetime) -> datetime:
        if session_close.tzinfo is None or session_close.utcoffset() is None:
            raise DataValidationError("session_close must be timezone-aware")
        return session_close + self.eod_delay
