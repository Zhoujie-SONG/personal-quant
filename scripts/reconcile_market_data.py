from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from etf_quant.config.reconciliation import ReconciliationConfig
from etf_quant.config.settings import Settings
from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.domain.enums import AdjustType
from etf_quant.domain.policies import DailyBarAvailabilityPolicy
from etf_quant.providers.akshare import AkShareSupplementalProvider
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.market_data import LongbridgeMarketDataProvider
from etf_quant.services.reconciliation import reconcile_bars


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-check unadjusted ETF bars; never writes canonical market data")
    parser.add_argument("--settings", type=Path, default=Path("configs/settings.example.yaml"))
    parser.add_argument("--config", type=Path, default=Path("configs/reconciliation.yaml"))
    parser.add_argument("--days", type=int, default=10)
    args = parser.parse_args()
    settings = Settings.from_yaml(args.settings)
    config = ReconciliationConfig.from_yaml(args.config)
    policy = DailyBarAvailabilityPolicy(
        eod_delay=timedelta(minutes=settings.daily_bar_availability.eod_delay_minutes)
    )
    primary = LongbridgeMarketDataProvider(
        LongbridgeClient.from_env(
            max_attempts=settings.longbridge.max_attempts,
            retry_base_seconds=settings.longbridge.retry_base_seconds,
        ),
        availability_policy=policy,
        raw_cache=LongbridgeRawBarCache(settings.raw_data_dir),
    )
    supplemental = AkShareSupplementalProvider()
    end = date.today()
    start = end - timedelta(days=args.days)
    exit_code = 0
    for symbol in config.symbols:
        results = reconcile_bars(
            primary.get_daily_bars(symbol, start, end, AdjustType.NONE),
            supplemental.get_daily_bars(symbol, start, end, AdjustType.NONE),
            config,
        )
        for item in results:
            print(
                item.status.value,
                item.symbol,
                item.trade_date,
                f"price_abs={item.price_abs_difference}",
                f"volume_rel={item.volume_relative_difference}",
                f"turnover_rel={item.turnover_relative_difference}",
            )
            if item.status.value == "FAIL":
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
