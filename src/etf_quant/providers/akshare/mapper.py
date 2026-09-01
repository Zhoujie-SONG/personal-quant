from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from etf_quant.domain.enums import DataAvailabilityClass, HistoricalDataSemantics
from etf_quant.providers.akshare.exceptions import AkShareDataError, AkShareSchemaError
from etf_quant.providers.dto import RawETFMetadataObservation, RawMarketBar

SHANGHAI = ZoneInfo("Asia/Shanghai")
SPOT_REQUIRED = {"代码", "名称", "数据日期", "更新时间"}
SPOT_OPTIONAL = {"IOPV实时估值", "最新份额"}
SCALE_REQUIRED = {
    "基金代码", "基金简称", "基金类别", "上市日期", "基金份额", "基金管理人", "净值"
}
HISTORY_REQUIRED = {"日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"}
ETF_SPOT_SOURCE = "akshare:fund_etf_spot_em"
SZSE_SCALE_SOURCE = "akshare:fund_etf_scale_szse"


def map_etf_spot_frame(frame: Any, *, retrieved_at: datetime) -> list[RawETFMetadataObservation]:
    _require_columns(frame, SPOT_REQUIRED, "fund_etf_spot_em")
    result: list[RawETFMetadataObservation] = []
    for row in _records(frame):
        code = _required_text(row.get("代码"), "代码")
        _required_date(row.get("数据日期"), "数据日期")
        snapshot_at = _aware_datetime(row.get("更新时间"), "更新时间")
        payload = _payload(row, SPOT_REQUIRED | SPOT_OPTIONAL)
        result.append(
            RawETFMetadataObservation(
                symbol=_etf_symbol(code),
                fund_name=_optional_text(row.get("名称")),
                tracking_index=None,
                list_date=None,
                delist_date=None,
                fund_type="ETF",
                fund_company=None,
                nav=None,
                iopv=_optional_decimal_text(row.get("IOPV实时估值"), "IOPV实时估值"),
                shares=_optional_decimal_text(row.get("最新份额"), "最新份额"),
                aum=None,
                snapshot_at=snapshot_at,
                available_time=snapshot_at,
                retrieved_at=retrieved_at,
                provider=ETF_SPOT_SOURCE,
                availability_class=DataAvailabilityClass.SNAPSHOT_ONLY,
                provider_payload_hash=_payload_hash(payload),
                provider_payload=payload,
            )
        )
    return result


def map_szse_scale_frame(frame: Any, *, retrieved_at: datetime) -> list[RawETFMetadataObservation]:
    _require_columns(frame, SCALE_REQUIRED, "fund_etf_scale_szse")
    result: list[RawETFMetadataObservation] = []
    snapshot_at = datetime.combine(retrieved_at.astimezone(SHANGHAI).date(), time(), tzinfo=SHANGHAI)
    for row in _records(frame):
        if _optional_text(row.get("基金类别")) != "ETF":
            continue
        payload = _payload(row, SCALE_REQUIRED)
        result.append(
            RawETFMetadataObservation(
                symbol=_etf_symbol(_required_text(row.get("基金代码"), "基金代码")),
                fund_name=_optional_text(row.get("基金简称")),
                tracking_index=None,
                list_date=_optional_date_text(row.get("上市日期"), "上市日期"),
                delist_date=None,
                fund_type="ETF",
                fund_company=_optional_text(row.get("基金管理人")),
                nav=_optional_decimal_text(row.get("净值"), "净值"),
                iopv=None,
                shares=_optional_decimal_text(row.get("基金份额"), "基金份额"),
                aum=None,
                snapshot_at=snapshot_at,
                available_time=retrieved_at,
                retrieved_at=retrieved_at,
                provider=SZSE_SCALE_SOURCE,
                availability_class=DataAvailabilityClass.SNAPSHOT_ONLY,
                provider_payload_hash=_payload_hash(payload),
                provider_payload=payload,
            )
        )
    return result


def map_etf_history_frame(
    frame: Any,
    *,
    symbol: str,
    retrieved_at: datetime,
    sdk_version: str,
) -> list[RawMarketBar]:
    _require_columns(frame, HISTORY_REQUIRED, "fund_etf_hist_em")
    result: list[RawMarketBar] = []
    for row in _records(frame):
        trade_date = _required_date(row.get("日期"), "日期")
        volume_lots = _required_decimal(row.get("成交量"), "成交量")
        volume_shares = volume_lots * Decimal(100)
        if volume_shares != volume_shares.to_integral_value():
            raise AkShareDataError("成交量 lots cannot be converted to integral shares")
        result.append(
            RawMarketBar(
                symbol=symbol,
                open=str(_required_decimal(row.get("开盘"), "开盘")),
                high=str(_required_decimal(row.get("最高"), "最高")),
                low=str(_required_decimal(row.get("最低"), "最低")),
                close=str(_required_decimal(row.get("收盘"), "收盘")),
                volume=int(volume_shares),
                turnover=str(_required_decimal(row.get("成交额"), "成交额")),
                provider_timestamp=datetime.combine(trade_date, time(15), tzinfo=SHANGHAI),
                retrieved_at=retrieved_at,
                provider="akshare",
                sdk_version=sdk_version,
                historical_data_semantics=HistoricalDataSemantics.HISTORICAL_LATEST,
                provider_payload=_payload(row, HISTORY_REQUIRED),
            )
        )
    return result


def _require_columns(frame: Any, required: set[str], endpoint: str) -> None:
    columns = set(getattr(frame, "columns", []))
    missing = required - columns
    if missing:
        raise AkShareSchemaError(f"{endpoint} missing required columns: {sorted(missing)}")


def _records(frame: Any) -> list[Mapping[str, Any]]:
    method = getattr(frame, "to_dict", None)
    if method is None:
        raise AkShareSchemaError("AkShare response is not a DataFrame-like table")
    records = method(orient="records")
    if not isinstance(records, list):
        raise AkShareSchemaError("AkShare table could not be converted to row records")
    return records


def _missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() in {"", "--", "---", "None", "nan", "NaT"}


def _required_text(value: object, field: str) -> str:
    result = _optional_text(value)
    if result is None:
        raise AkShareDataError(f"missing {field}")
    return result


def _optional_text(value: object) -> str | None:
    return None if _missing(value) else str(value).strip()


def _required_decimal(value: object, field: str) -> Decimal:
    if _missing(value):
        raise AkShareDataError(f"missing {field}")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise AkShareDataError(f"invalid {field}") from exc
    if not result.is_finite():
        raise AkShareDataError(f"non-finite {field}")
    return result


def _optional_decimal_text(value: object, field: str) -> str | None:
    return None if _missing(value) else str(_required_decimal(value, field))


def _required_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_required_text(value, field)[:10])
    except ValueError as exc:
        raise AkShareDataError(f"invalid {field}") from exc


def _optional_date_text(value: object, field: str) -> str | None:
    return None if _missing(value) else _required_date(value, field).isoformat()


def _aware_datetime(value: object, field: str) -> datetime:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(_required_text(value, field))
        except ValueError as exc:
            raise AkShareDataError(f"invalid {field}") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=SHANGHAI)
    return value


def _etf_symbol(code: str) -> str:
    if len(code) != 6 or not code.isdigit():
        raise AkShareDataError(f"invalid ETF code: {code!r}")
    if code.startswith("5"):
        return f"{code}.SH"
    if code.startswith("1"):
        return f"{code}.SZ"
    raise AkShareDataError(f"unsupported ETF exchange for code: {code}")


def _payload(row: Mapping[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {
        field: _json_value(row.get(field))
        for field in sorted(fields)
        if field in row
    }


def _json_value(value: object) -> object:
    if _missing(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
