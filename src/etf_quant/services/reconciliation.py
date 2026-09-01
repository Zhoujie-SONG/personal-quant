from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from etf_quant.config.reconciliation import ReconciliationConfig
from etf_quant.domain.enums import ReconciliationStatus
from etf_quant.providers.dto import RawMarketBar
from etf_quant.utils.time import shanghai_trade_date


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    symbol: str
    trade_date: date
    status: ReconciliationStatus
    price_abs_difference: Decimal
    volume_relative_difference: Decimal
    turnover_relative_difference: Decimal


def reconcile_bars(
    primary: list[RawMarketBar],
    supplemental: list[RawMarketBar],
    config: ReconciliationConfig,
) -> list[ReconciliationResult]:
    primary_by_date = {shanghai_trade_date(item.provider_timestamp): item for item in primary}
    supplemental_by_date = {
        shanghai_trade_date(item.provider_timestamp): item for item in supplemental
    }
    results: list[ReconciliationResult] = []
    for trade_date in sorted(set(primary_by_date) | set(supplemental_by_date)):
        left = primary_by_date.get(trade_date)
        right = supplemental_by_date.get(trade_date)
        if left is None or right is None:
            results.append(
                ReconciliationResult(
                    symbol=(left or right).symbol,  # type: ignore[union-attr]
                    trade_date=trade_date,
                    status=ReconciliationStatus.FAIL,
                    price_abs_difference=Decimal("Infinity"),
                    volume_relative_difference=Decimal("Infinity"),
                    turnover_relative_difference=Decimal("Infinity"),
                )
            )
            continue
        price_difference = max(
            abs(Decimal(getattr(left, field)) - Decimal(getattr(right, field)))
            for field in ("open", "high", "low", "close")
        )
        volume_difference = _relative(Decimal(left.volume), Decimal(right.volume))
        turnover_difference = _relative(
            Decimal(left.turnover), Decimal(right.turnover)
        )
        ratios = (
            _ratio(price_difference, config.price_abs_tolerance),
            _ratio(volume_difference, config.volume_relative_tolerance),
            _ratio(turnover_difference, config.turnover_relative_tolerance),
        )
        worst = max(ratios)
        status = (
            ReconciliationStatus.PASS
            if worst <= 1
            else ReconciliationStatus.WARNING
            if worst <= config.warning_multiplier
            else ReconciliationStatus.FAIL
        )
        results.append(
            ReconciliationResult(
                symbol=left.symbol,
                trade_date=trade_date,
                status=status,
                price_abs_difference=price_difference,
                volume_relative_difference=volume_difference,
                turnover_relative_difference=turnover_difference,
            )
        )
    return results


def _relative(left: Decimal, right: Decimal) -> Decimal:
    denominator = max(abs(left), abs(right))
    if denominator == 0:
        return Decimal(0)
    return abs(left - right) / denominator


def _ratio(value: Decimal, tolerance: Decimal) -> Decimal:
    if tolerance == 0:
        return Decimal(0) if value == 0 else Decimal("Infinity")
    return value / tolerance
