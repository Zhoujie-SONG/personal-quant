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


class Market(StrEnum):
    CN = "CN"


class Sleeve(StrEnum):
    EQUITY_BROAD = "equity_broad"
    EQUITY_INDUSTRY = "equity_industry"
    OVERSEAS_EQUITY = "overseas_equity"
    COMMODITY = "commodity"
    DEFENSIVE = "defensive"
