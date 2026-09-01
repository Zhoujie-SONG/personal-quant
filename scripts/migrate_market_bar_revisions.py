from __future__ import annotations

import argparse
from pathlib import Path

from etf_quant.data.repositories.market_repository import ParquetMarketRepository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explicitly migrate canonical market-bar partitions to revision schema v3"
    )
    parser.add_argument(
        "--canonical-root",
        type=Path,
        default=Path("data/canonical"),
        help="Canonical data root containing market_bars/",
    )
    args = parser.parse_args()
    repository = ParquetMarketRepository(args.canonical_root)
    before = repository.schema_versions()
    migrated = repository.migrate_to_latest_schema()
    after = repository.schema_versions()
    print(f"Partitions inspected: {len(before)}")
    print(f"Partitions migrated: {migrated}")
    print(f"Resulting schemas: {sorted(set(after.values()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
