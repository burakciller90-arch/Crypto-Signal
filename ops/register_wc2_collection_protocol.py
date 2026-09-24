from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    WC2CollectionProtocol,
    WC2CollectionProtocolStore,
    build_wc2_collection_protocol,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2PolicyStore,
    WC2UntouchedForwardPolicy,
)
from crypto_signal.paper.epoch2_accounting import (
    Epoch2ActivationRecord,
    read_epoch2_state_read_only,
)

DEFAULT_WC2_POLICY_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/wc2/"
    "wc2_forward_policy.sqlite3"
)
DEFAULT_WC2_EPOCH2_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/paper/"
    "paper_fund_epoch2.sqlite3"
)
DEFAULT_WC2_PROTOCOL_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/wc2/"
    "wc2_collection_protocol.wc2-collection-protocol.sqlite3"
)

FIFTEEN_MINUTES_MS = 900_000
COLLECTION_START_BUCKETS_AHEAD = 2
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class WC2ProtocolRegistrationResult:
    protocol: WC2CollectionProtocol
    inserted: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-db", type=Path, default=DEFAULT_WC2_POLICY_DB)
    parser.add_argument("--epoch2-db", type=Path, default=DEFAULT_WC2_EPOCH2_DB)
    parser.add_argument(
        "--protocol-db",
        type=Path,
        default=DEFAULT_WC2_PROTOCOL_DB,
    )
    return parser.parse_args()


def register_or_reuse_protocol(
    *,
    protocol_path: Path,
    review_policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    now_ms: int,
) -> WC2ProtocolRegistrationResult:
    if now_ms < 0:
        raise ValueError("WC2 protocol registration time cannot be negative")

    store = WC2CollectionProtocolStore(protocol_path)
    existing = store.latest()
    if existing is not None:
        if existing.review_policy_identity != review_policy.policy_identity:
            raise ValueError(
                "existing WC2 protocol binds another review policy"
            )
        if (
            existing.epoch2_activation_identity
            != activation.activation_identity
        ):
            raise ValueError(
                "existing WC2 protocol binds another Epoch2 activation"
            )
        if not store.quick_check():
            raise ValueError("existing WC2 protocol quick_check failed")
        return WC2ProtocolRegistrationResult(
            protocol=existing,
            inserted=False,
        )

    boundary_source_ms = max(
        now_ms,
        review_policy.collection_start_ms,
        activation.activated_at_ms,
    )
    collection_start_ms = (
        (boundary_source_ms // FIFTEEN_MINUTES_MS)
        + COLLECTION_START_BUCKETS_AHEAD
    ) * FIFTEEN_MINUTES_MS
    protocol = build_wc2_collection_protocol(
        review_policy=review_policy,
        activation=activation,
        preregistered_at_ms=now_ms,
        collection_start_ms=collection_start_ms,
    )
    inserted = store.append(protocol)
    if not inserted:
        raise ValueError(
            "WC2 initial collection protocol registration unexpectedly replayed"
        )
    if not store.quick_check():
        raise ValueError("WC2 collection protocol quick_check failed")
    persisted = store.latest()
    if persisted != protocol:
        raise ValueError("WC2 collection protocol readback mismatch")
    return WC2ProtocolRegistrationResult(
        protocol=protocol,
        inserted=True,
    )


def load_prerequisites(
    *,
    policy_path: Path,
    epoch2_path: Path,
) -> tuple[WC2UntouchedForwardPolicy, Epoch2ActivationRecord]:
    policy = WC2PolicyStore(policy_path).latest()
    if policy is None:
        raise ValueError("WC2 collection protocol requires review policy")
    state = read_epoch2_state_read_only(epoch2_path)
    if state is None:
        raise ValueError("WC2 collection protocol requires canonical Epoch2")
    if state.activation.real_capital != REAL_CAPITAL:
        raise ValueError("WC2 collection protocol requires REAL_CAPITAL=0")
    return policy, state.activation


def run(args: argparse.Namespace) -> int:
    paths = (args.policy_db, args.epoch2_db, args.protocol_db)
    if any(
        not str(path).startswith("/Volumes/Crypto-504/")
        for path in paths
    ):
        print(
            "WC2_PROTOCOL_ERROR=NON_CANONICAL_DB_PATH",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if not args.policy_db.is_file():
        print(
            "WC2_PROTOCOL_ERROR=POLICY_DB_MISSING",
            file=sys.stderr,
            flush=True,
        )
        return 3
    if not args.epoch2_db.is_file():
        print(
            "WC2_PROTOCOL_ERROR=EPOCH2_DB_MISSING",
            file=sys.stderr,
            flush=True,
        )
        return 4

    try:
        policy, activation = load_prerequisites(
            policy_path=args.policy_db,
            epoch2_path=args.epoch2_db,
        )
        result = register_or_reuse_protocol(
            protocol_path=args.protocol_db,
            review_policy=policy,
            activation=activation,
            now_ms=time.time_ns() // 1_000_000,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(
            "WC2_PROTOCOL_ERROR="
            f"{type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 5

    protocol = result.protocol
    print(
        "WC2_PROTOCOL_REGISTRATION "
        f"status={'INSERTED' if result.inserted else 'REUSED'} "
        f"protocol={protocol.protocol_identity} "
        f"review_policy={protocol.review_policy_identity} "
        f"epoch2_activation={protocol.epoch2_activation_identity} "
        f"preregistered_at_ms={protocol.preregistered_at_ms} "
        f"collection_start_ms={protocol.collection_start_ms} "
        f"coverage_plan={protocol.coverage_plan_version} "
        f"context_count={len(protocol.coverage_context_identities)} "
        f"maximum_issuance_delay_ms={protocol.maximum_issuance_delay_ms} "
        f"horizon_bars={protocol.horizon_bars_by_timeframe} "
        f"paper_action_mode={protocol.paper_action_mode} "
        f"probability_mode={protocol.probability_mode}",
        flush=True,
    )
    print(
        "WC2_PROTOCOL_PREREGISTERED_PASS=YES "
        "WC2_PROTOCOL_RETRY_SAFE_PASS=YES "
        "WC2_PROTOCOL_HISTORICAL_BACKFILL=NO "
        "WC2_PROTOCOL_AUTO_PROMOTION=NO "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
