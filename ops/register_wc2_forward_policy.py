from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2PolicyStore,
    WC2UntouchedForwardPolicy,
    build_wc2_untouched_forward_policy,
)

DEFAULT_WC2_POLICY_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/wc2/"
    "wc2_forward_policy.sqlite3"
)
FIFTEEN_MINUTES_MS = 900_000
COLLECTION_START_BUCKETS_AHEAD = 2


@dataclass(frozen=True, slots=True)
class WC2PolicyRegistrationResult:
    policy: WC2UntouchedForwardPolicy
    inserted: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_WC2_POLICY_DB)
    return parser.parse_args()


def register_or_reuse_policy(
    *,
    db_path: Path,
    now_ms: int,
) -> WC2PolicyRegistrationResult:
    if now_ms < 0:
        raise ValueError("WC2 policy registration time cannot be negative")

    store = WC2PolicyStore(db_path)
    existing = store.latest()
    if existing is not None:
        return WC2PolicyRegistrationResult(
            policy=existing,
            inserted=False,
        )

    collection_start_ms = (
        (now_ms // FIFTEEN_MINUTES_MS)
        + COLLECTION_START_BUCKETS_AHEAD
    ) * FIFTEEN_MINUTES_MS
    policy = build_wc2_untouched_forward_policy(
        preregistered_at_ms=now_ms,
        collection_start_ms=collection_start_ms,
    )
    inserted = store.append(policy)
    if not inserted:
        raise ValueError("WC2 initial policy registration unexpectedly replayed")
    if not store.quick_check():
        raise ValueError("WC2 policy registry quick_check failed")

    persisted = store.latest()
    if persisted != policy:
        raise ValueError("WC2 persisted policy readback mismatch")
    return WC2PolicyRegistrationResult(
        policy=policy,
        inserted=True,
    )


def run(args: argparse.Namespace) -> int:
    if not str(args.db).startswith("/Volumes/Crypto-504/"):
        print(
            "WC2_POLICY_ERROR=NON_CANONICAL_DB_PATH",
            file=sys.stderr,
            flush=True,
        )
        return 2
    try:
        result = register_or_reuse_policy(
            db_path=args.db,
            now_ms=time.time_ns() // 1_000_000,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(
            "WC2_POLICY_ERROR="
            f"{type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 3

    policy = result.policy
    print(
        "WC2_POLICY_REGISTRATION "
        f"status={'INSERTED' if result.inserted else 'REUSED'} "
        f"policy={policy.policy_identity} "
        f"preregistered_at_ms={policy.preregistered_at_ms} "
        f"collection_start_ms={policy.collection_start_ms} "
        f"minimum_total_decisive_n={policy.minimum_total_decisive_n} "
        f"minimum_decisive_per_asset={policy.minimum_decisive_per_asset} "
        f"minimum_qualifying_regimes={policy.minimum_qualifying_regimes} "
        f"minimum_decisive_per_regime={policy.minimum_decisive_per_regime} "
        f"minimum_calendar_days={policy.minimum_calendar_days}",
        flush=True,
    )
    print(
        "WC2_POLICY_PREREGISTERED_PASS=YES "
        "WC2_POLICY_RETRY_SAFE_PASS=YES "
        "WC2_POLICY_AUTO_PROMOTION=NO "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
