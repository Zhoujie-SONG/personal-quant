from __future__ import annotations

import argparse
from pathlib import Path

from etf_quant.config.settings import Settings
from etf_quant.data.repositories.metadata_repository import MetadataRepository
from etf_quant.providers.akshare import AkShareSupplementalProvider
from etf_quant.providers.akshare.exceptions import AkShareProviderError
from etf_quant.services.metadata_snapshot import MetadataSnapshotService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Persist today's real ETF metadata observations as forward-collected PIT"
    )
    parser.add_argument("--settings", type=Path, default=Path("configs/settings.example.yaml"))
    args = parser.parse_args()
    settings = Settings.from_yaml(args.settings)
    service = MetadataSnapshotService(
        AkShareSupplementalProvider(),
        MetadataRepository(settings.canonical_data_dir),
    )
    try:
        inserted = service.snapshot()
    except AkShareProviderError as exc:
        print(f"ETF metadata snapshot failed: {exc}")
        return 1
    print(f"Inserted {inserted} immutable ETF metadata observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
