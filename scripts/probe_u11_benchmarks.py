from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from etf_quant.providers.csindex.research_benchmarks import CSIResearchBenchmarkProvider
from etf_quant.providers.longbridge.client import LongbridgeClient
from etf_quant.providers.longbridge.research_benchmarks import LongbridgeResearchBenchmarkProvider
from etf_quant.research.universe_diagnostic import (
    OfficialSymbolProbeAttempt,
    evaluate_official_symbol_probe,
)


CANDIDATES = {
    "SEMI": {"official_code": "H30184", "base_date": date(2004, 12, 31)},
    "BOND_LONG": {"official_code": "H11077", "base_date": date(2008, 12, 31)},
    "BOND_MED": {"official_code": "H00140", "base_date": date(2007, 12, 31)},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe official U1.1 benchmark symbols")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/universe_diagnostic_u1/benchmark_probe_results.json"),
    )
    args = parser.parse_args()
    longbridge = LongbridgeResearchBenchmarkProvider(LongbridgeClient.from_env(max_attempts=1))
    csindex = CSIResearchBenchmarkProvider()
    results: dict[str, object] = {
        "probed_at": datetime.now(UTC).isoformat(),
        "history_probe_window": {"start": "2025-01-01", "end": "2025-12-31"},
        "assets": {},
    }
    for asset_id, config in CANDIDATES.items():
        official_code = str(config["official_code"])
        attempts = []
        decisions = []
        for suffix in ("SH", "SZ"):
            symbol = f"{official_code}.{suffix}"
            probe = longbridge.probe_symbol(
                symbol,
                history_start=date(2025, 1, 1),
                history_end=date(2025, 12, 31),
            )
            attempts.append(
                {
                    "symbol": symbol,
                    "static_returned": probe.static_returned,
                    "static_symbol": probe.static_symbol,
                    "static_name": probe.static_name,
                    "history_count": probe.history_count,
                    "history_error": probe.history_error,
                }
            )
            returned_code = probe.static_symbol.split(".", 1)[0] if probe.static_symbol else None
            decisions.append(
                OfficialSymbolProbeAttempt(
                    symbol=symbol,
                    static_verified=probe.static_returned,
                    history_verified=probe.history_count > 0,
                    returned_official_code=returned_code,
                )
            )
        longbridge_decision = evaluate_official_symbol_probe(official_code, decisions)
        supplemental = csindex.get_daily_levels(
            official_code,
            config["base_date"],
            date(2026, 9, 1),
        )
        first_payload = supplemental[0].provider_payload
        results["assets"][asset_id] = {  # type: ignore[index]
            "official_code": official_code,
            "longbridge_status": longbridge_decision.status,
            "longbridge_resolved_symbol": longbridge_decision.resolved_symbol,
            "longbridge_attempts": attempts,
            "supplemental_provider": "csindex",
            "supplemental_status": "RESOLVED",
            "supplemental_exact_code_verified": supplemental[0].symbol == official_code,
            "supplemental_index_name_en": first_payload.get("index_name_en_all"),
            "supplemental_first_date": supplemental[0].observation_date.isoformat(),
            "supplemental_last_date": supplemental[-1].observation_date.isoformat(),
            "supplemental_n_obs": len(supplemental),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
