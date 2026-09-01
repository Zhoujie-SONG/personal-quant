from __future__ import annotations

from enum import StrEnum


class Exchange(StrEnum):
    SHANGHAI = "SH"
    SHENZHEN = "SZ"
    UNKNOWN = "UNKNOWN"


class InstrumentType(StrEnum):
    ETF = "ETF"
    INDEX = "INDEX"
    STOCK = "STOCK"
    UNKNOWN = "UNKNOWN"


class AssetClass(StrEnum):
    EQUITY = "equity"
    BOND = "bond"
    COMMODITY = "commodity"
    OVERSEAS = "overseas"
    CASH = "cash"
    UNKNOWN = "unknown"


class AdjustType(StrEnum):
    NONE = "none"
    FORWARD = "forward"


class PITQueryMode(StrEnum):
    ECONOMIC = "economic"
    SYSTEM_REPLAY = "system_replay"


class CanonicalMarketSource(StrEnum):
    LONGBRIDGE = "longbridge"


class HistoricalDataSemantics(StrEnum):
    HISTORICAL_LATEST = "historical_latest"
    TRUE_HISTORICAL_VINTAGE = "true_historical_vintage"


class DataAvailabilityClass(StrEnum):
    TRUE_HISTORICAL_VINTAGE = "true_historical_vintage"
    HISTORICAL_LATEST = "historical_latest"
    SNAPSHOT_ONLY = "snapshot_only"
    FORWARD_COLLECTED_PIT = "forward_collected_pit"


class IndexHistoryStatus(StrEnum):
    BACKFILLED = "backfilled"
    LIVE = "live"


class ReconciliationStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class ResolvedFieldStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONFLICT = "CONFLICT"


class MetadataFreshness(StrEnum):
    FRESH = "FRESH"
    EXPIRED = "EXPIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Market(StrEnum):
    CN = "CN"


class Sleeve(StrEnum):
    EQUITY_BROAD = "equity_broad"
    EQUITY_INDUSTRY = "equity_industry"
    OVERSEAS_EQUITY = "overseas_equity"
    COMMODITY = "commodity"
    DEFENSIVE = "defensive"
