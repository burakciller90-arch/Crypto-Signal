from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    WC2CollectionProtocol,
    WC2CollectionProtocolStore,
)
from crypto_signal.evaluation.untouched_forward_execution_protocol import (
    WC2PaperExecutionProtocol,
    WC2PaperExecutionProtocolStore,
    build_wc2_paper_execution_protocol,
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
DEFAULT_WC2_COLLECTION_PROTOCOL_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/wc2/"
    "wc2_collection_protocol.wc2-collection-protocol.sqlite3"
)
DEFAULT_WC2_EPOCH2_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/paper/"
    "paper_fund_epoch2.sqlite3"
)
DEFAULT_WC2_EXECUTION_PROTOCOL_DB = Path(
    "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/wc2/"
    "wc2_paper_execution.wc2-paper-execution-protocol.sqlite3"
)

FIFTEEN_MINUTES_MS = 900_000
EXECUTION_START_BUCKETS_AHEAD = 2
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class WC2ExecutionProtocolRegistrationResult:
    protocol: WC2PaperExecutionProtocol
    inserted: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-db", type=Path, default=DEFAULT_WC2_POLICY_DB)
    parser.add_argument(
        "--collection-protocol-db",
        type=Path,
        default=DEFAULT_WC2_COLLECTION_PROTOCOL_DB,
    )
    parser.add_argument("--epoch2-db", type=Path, default=DEFAULT_WC2_EPOCH2_DB)
    parser.add_argument(
        "--execution-protocol-db",
        type=Path,
        default=DEFAULT_WC2_EXECUTION_PROTOCOL_DB,
    )
    return parser.parse_args()


def load_prerequisites(
    *,
    policy_path: Path,
    collection_protocol_path: Path,
    epoch2_path: Path,
) -> tuple[
    WC2UntouchedForwardPolicy,
    WC2CollectionProtocol,
    Epoch2ActivationRecord,
]:
    policy = WC2PolicyStore(policy_path).latest()
    if policy is None:
        raise ValueError("WC2 paper execution requires review policy")
    collection = WC2CollectionProtocolStore(
        collection_protocol_path
    ).latest()
    if collection is None:
        raise ValueError("WC2 paper execution requires collection protocol")
    state = read_epoch2_state_read_only(epoch2_path)
    if state is None:
        raise ValueError("WC2 paper execution requires canonical Epoch2")
    if state.activation.real_capital != REAL_CAPITAL:
        raise ValueError("WC2 paper execution requires REAL_CAPITAL=0")
    if collection.review_policy_identity != policy.policy_identity:
        raise ValueError("WC2 paper execution policy lineage mismatch")
    if (
        collection.epoch2_activation_identity
        != state.activation.activation_identity
    ):
        raise ValueError("WC2 paper execution Epoch2 lineage mismatch")
    return policy, collection, state.activation


def register_or_reuse_execution_protocol(
    *,
    protocol_path: Path,
    review_policy: WC2UntouchedForwardPolicy,
    collection_protocol: WC2CollectionProtocol,
    activation: Epoch2ActivationRecord,
    now_ms: int,
) -> WC2ExecutionProtocolRegistrationResult:
    if now_ms < 0:
        raise ValueError("WC2 execution protocol registration time cannot be negative")

    store = WC2PaperExecutionProtocolStore(protocol_path)
    existing = store.latest()
    if existing is not None:
        if existing.review_policy_identity != review_policy.policy_identity:
            raise ValueError("existing WC2 execution protocol review policy mismatch")
        if (
            existing.collection_protocol_identity
            != collection_protocol.protocol_identity
        ):
            raise ValueError("existing WC2 execution protocol collection mismatch")
        if (
            existing.epoch2_activation_identity
            != activation.activation_identity
        ):
            raise ValueError("existing WC2 execution protocol Epoch2 mismatch")
        if not store.quick_check():
            raise ValueError("existing WC2 execution protocol quick_check failed")
        return WC2ExecutionProtocolRegistrationResult(
            protocol=existing,
            inserted=False,
        )

    boundary_source_ms = max(
        now_ms,
        review_policy.collection_start_ms,
        collection_protocol.collection_start_ms,
        activation.activated_at_ms,
    )
    execution_start_ms = (
        (boundary_source_ms // FIFTEEN_MINUTES_MS)
        + EXECUTION_START_BUCKETS_AHEAD
    ) * FIFTEEN_MINUTES_MS
    protocol = build_wc2_paper_execution_protocol(
        review_policy=review_policy,
        collection_protocol=collection_protocol,
        activation=activation,
        preregistered_at_ms=now_ms,
        execution_start_ms=execution_start_ms,
    )
    inserted = store.append(protocol)
    if not inserted:
        raise ValueError(
            "WC2 initial paper execution protocol unexpectedly replayed"
        )
    if not store.quick_check():
        raise ValueError("WC2 paper execution protocol quick_check failed")
    persisted = store.latest()
    if persisted != protocol:
        raise ValueError("WC2 paper execution protocol readback mismatch")
    return WC2ExecutionProtocolRegistrationResult(
        protocol=protocol,
        inserted=True,
    )


def run(args: argparse.Namespace) -> int:
    paths = (
        args.policy_db,
        args.collection_protocol_db,
        args.epoch2_db,
        args.execution_protocol_db,
    )
    if any(not str(path).startswith("/Volumes/Crypto-504/") for path in paths):
        print(
            "WC2_EXECUTION_PROTOCOL_ERROR=NON_CANONICAL_DB_PATH",
            file=sys.stderr,
            flush=True,
        )
        return 2
    for path, code in (
        (args.policy_db, "POLICY_DB_MISSING"),
        (args.collection_protocol_db, "COLLECTION_PROTOCOL_DB_MISSING"),
        (args.epoch2_db, "EPOCH2_DB_MISSING"),
    ):
        if not path.is_file():
            print(
                f"WC2_EXECUTION_PROTOCOL_ERROR={code}",
                file=sys.stderr,
                flush=True,
            )
            return 3

    try:
        policy, collection, activation = load_prerequisites(
            policy_path=args.policy_db,
            collection_protocol_path=args.collection_protocol_db,
            epoch2_path=args.epoch2_db,
        )
        result = register_or_reuse_execution_protocol(
            protocol_path=args.execution_protocol_db,
            review_policy=policy,
            collection_protocol=collection,
            activation=activation,
            now_ms=time.time_ns() // 1_000_000,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(
            "WC2_EXECUTION_PROTOCOL_ERROR="
            f"{type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 4

    protocol = result.protocol
    print(
        "WC2_EXECUTION_PROTOCOL_REGISTRATION "
        f"status={'INSERTED' if result.inserted else 'REUSED'} "
        f"protocol={protocol.protocol_identity} "
        f"review_policy={protocol.review_policy_identity} "
        f"collection_protocol={protocol.collection_protocol_identity} "
        f"epoch2_activation={protocol.epoch2_activation_identity} "
        f"preregistered_at_ms={protocol.preregistered_at_ms} "
        f"execution_start_ms={protocol.execution_start_ms} "
        f"decision_mode={protocol.decision_mode} "
        f"autonomy_policy={protocol.autonomy_policy_version} "
        f"sizing_policy={protocol.position_sizing_policy_version} "
        f"execution_input_policy={protocol.execution_input_policy_version} "
        f"cost_policy={protocol.simulated_cost_policy_version} "
        f"fee_rate={protocol.simulated_fee_rate} "
        f"spread_rate={protocol.simulated_spread_rate} "
        f"slippage_rate={protocol.simulated_slippage_rate} "
        f"execution_policy={protocol.execution_policy_version}",
        flush=True,
    )
    print(
        "WC2_EXECUTION_PROTOCOL_PREREGISTERED_PASS=YES "
        "WC2_EXECUTION_PROTOCOL_RETRY_SAFE_PASS=YES "
        "WC2_EXECUTION_PROTOCOL_HISTORICAL_BACKFILL=NO "
        "WC2_EXECUTION_PROTOCOL_REAL_ORDER_AUTHORITY=NO "
        "WC2_EXECUTION_PROTOCOL_ZERO_TRADE_ECONOMIC_CLAIM=NO "
        "REAL_CAPITAL=0",
        flush=True,
    )
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
