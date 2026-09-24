#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ops.run_live_evidence_clock import WC2ClockConfig, run

REAL_CAPITAL = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal-ledger", type=Path, required=True)
    parser.add_argument("--candle-cache", type=Path, required=True)
    parser.add_argument("--provider-divergence", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--epoch2", type=Path, required=True)
    parser.add_argument("--collection-protocol", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--decision-evidence", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--shadow-intent", type=Path, required=True)
    parser.add_argument("--shadow-cycle", type=Path, required=True)
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> WC2ClockConfig:
    return WC2ClockConfig(
        enabled=True,
        policy_path=args.policy,
        epoch2_path=args.epoch2,
        collection_protocol_path=args.collection_protocol,
        prepared_path=args.prepared,
        decision_evidence_path=args.decision_evidence,
        cohort_path=args.cohort,
        shadow_intent_path=args.shadow_intent,
        shadow_cycle_path=args.shadow_cycle,
    )


def run_once(args: argparse.Namespace) -> int:
    config = build_config(args)
    status = asyncio.run(
        run(
            args.signal_ledger,
            candle_cache_path=args.candle_cache,
            provider_divergence_path=args.provider_divergence,
            wc2_config=config,
        )
    )
    print(
        "WC2_ONE_SHOT_COMPLETE "
        f"status={status} "
        "PERIODIC_SERVICE_ACTIVATED=NO "
        "HISTORICAL_FORECAST_BACKFILL=NO "
        f"REAL_CAPITAL={REAL_CAPITAL}",
        flush=True,
    )
    return status


def main() -> int:
    return run_once(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
