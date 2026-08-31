from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from etf_quant.config.settings import Settings
from etf_quant.data.raw.cache import LongbridgeRawBarCache
from etf_quant.data.repositories.market_repository import ParquetMarketRepository
from etf_quant.domain.enums import AdjustType
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.exceptions import LongbridgeProviderError
from etf_quant.providers.longbridge.market_data import LongbridgeMarketDataProvider
from etf_quant.services.data_ingestion import MarketDataIngestionService


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and persist a small canonical daily-bar sample")
    parser.add_argument("--symbol", default="510300.SH")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--settings", type=Path, default=Path("configs/settings.example.yaml"))
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")

    settings = Settings.from_yaml(args.settings)
    try:
        client = LongbridgeClient.from_env(
            max_attempts=settings.longbridge.max_attempts,
            retry_base_seconds=settings.longbridge.retry_base_seconds,
        )
        provider = LongbridgeMarketDataProvider(
            client,
            raw_cache=LongbridgeRawBarCache(settings.raw_data_dir),
        )
        repository = ParquetMarketRepository(settings.canonical_data_dir)
        service = MarketDataIngestionService(provider, repository)
        end = date.today()
        count = service.ingest_daily_bars(
            args.symbol,
            end - timedelta(days=args.days),
            end,
            adjust_type=AdjustType.NONE,
        )
    except LongbridgeProviderError as exc:
        print(f"Longbridge fetch failed: {exc}")
        return 1
    print(f"Persisted {count} canonical bars for {args.symbol}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

