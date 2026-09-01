from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Callable

from etf_quant.config.settings import Settings
from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.domain.enums import AdjustType, Market
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.exceptions import (
    LongbridgeAuthenticationError,
    LongbridgePermissionError,
    LongbridgeProviderError,
)
from etf_quant.providers.longbridge.market_data import LongbridgeMarketDataProvider
from etf_quant.utils.logging import redact_secrets


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NO_PERMISSION = "NO_PERMISSION"
    NO_CREDENTIAL = "NO_CREDENTIAL"


@dataclass(frozen=True, slots=True)
class Result:
    label: str
    status: Status
    detail: str = ""


def check(label: str, operation: Callable[[], object]) -> Result:
    try:
        value = operation()
        if hasattr(value, "__len__") and len(value) == 0:  # type: ignore[arg-type]
            return Result(label, Status.FAIL, "API returned no records")
        return Result(label, Status.PASS)
    except LongbridgePermissionError as exc:
        return Result(label, Status.NO_PERMISSION, str(exc))
    except LongbridgeAuthenticationError as exc:
        status = (
            Status.NO_CREDENTIAL
            if "missing required Longbridge environment variables" in str(exc)
            else Status.FAIL
        )
        print(f"Longbridge capability gate: {status.value} ({exc})")
        return 2
    except LongbridgeProviderError as exc:
        return Result(label, Status.FAIL, str(exc))
    except Exception as exc:
        return Result(label, Status.FAIL, redact_secrets(f"{type(exc).__name__}: {exc}"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Longbridge A-share data capabilities")
    parser.add_argument("--settings", type=Path, default=Path("configs/settings.example.yaml"))
    args = parser.parse_args()
    settings = Settings.from_yaml(args.settings)
    try:
        client = LongbridgeClient.from_env(
            max_attempts=settings.longbridge.max_attempts,
            retry_base_seconds=settings.longbridge.retry_base_seconds,
        )
    except LongbridgeProviderError as exc:
        print(f"Longbridge client initialization failed: {exc}")
        print("Set the credential environment variables listed in .env.example.")
        return 2

    provider = LongbridgeMarketDataProvider(
        client,
        availability_policy=DailyBarAvailabilityPolicy(
            eod_delay=timedelta(
                minutes=settings.daily_bar_availability.eod_delay_minutes
            )
        ),
        raw_cache=LongbridgeRawBarCache(settings.raw_data_dir),
    )
    end = date.today()
    start = end - timedelta(days=12)
    calendar_start = end - timedelta(days=20)
    results = [
        check("A-share ETF static", lambda: provider.get_static_info(["510300.SH"])),
        check(
            "A-share ETF daily bars",
            lambda: provider.get_daily_bars("510300.SH", start, end, AdjustType.NONE),
        ),
        check(
            "A-share index bars",
            lambda: provider.get_daily_bars("000300.SH", start, end, AdjustType.NONE),
        ),
        check(
            "Trading calendar",
            lambda: provider.get_trading_days(Market.CN, calendar_start, end),
        ),
        check("Realtime quote", lambda: provider.get_quote(["510300.SH"])),
    ]

    print("Longbridge capabilities")
    print("-" * 72)
    for result in results:
        print(f"{result.label:<30} {result.status.value:<14} {result.detail}")
    print("-" * 72)
    return 0 if all(result.status is Status.PASS for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
