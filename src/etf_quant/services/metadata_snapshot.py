from __future__ import annotations

from typing import Protocol

from etf_quant.data.canonical.normalizers import normalize_etf_metadata
from etf_quant.data.repositories.metadata_repository import MetadataRepository
from etf_quant.domain.enums import DataAvailabilityClass
from etf_quant.providers.dto import RawETFMetadataObservation


class ETFSnapshotProvider(Protocol):
    def get_etf_snapshots(self) -> list[RawETFMetadataObservation]: ...

    def get_szse_scale_snapshots(self) -> list[RawETFMetadataObservation]: ...


class MetadataSnapshotService:
    def __init__(self, provider: ETFSnapshotProvider, repository: MetadataRepository) -> None:
        self._provider = provider
        self._repository = repository

    def snapshot(self) -> int:
        raw = [
            *self._provider.get_etf_snapshots(),
            *self._provider.get_szse_scale_snapshots(),
        ]
        observations = [
            normalize_etf_metadata(
                item,
                availability_class=DataAvailabilityClass.FORWARD_COLLECTED_PIT,
            )
            for item in raw
        ]
        return self._repository.append_etf_metadata(observations)
