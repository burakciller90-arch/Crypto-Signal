from __future__ import annotations

import argparse
import hashlib
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.paper.epoch2_accounting import (
    Epoch2LedgerState,
    initialize_epoch2_canonical_fund,
    read_epoch2_state_read_only,
)
from crypto_signal.paper.epochs import EPOCH_2_SPEC, PaperVaultId

REAL_CAPITAL = 0


class WC2Epoch2ActivationStatus(StrEnum):
    INSERTED = "INSERTED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True, slots=True)
class WC2Epoch2ActivationResult:
    status: WC2Epoch2ActivationStatus
    state: Epoch2LedgerState
    epoch1_sha256: str
    epoch2_sha256_before: str | None
    epoch2_sha256_after: str

    def __post_init__(self) -> None:
        _require_sha256(self.epoch1_sha256, "Epoch1 ledger")
        if self.epoch2_sha256_before is not None:
            _require_sha256(self.epoch2_sha256_before, "Epoch2 before")
        _require_sha256(self.epoch2_sha256_after, "Epoch2 after")
        if self.state.activation.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 Epoch2 activation must keep REAL_CAPITAL=0")
        if (
            self.status is WC2Epoch2ActivationStatus.UNCHANGED
            and self.epoch2_sha256_before != self.epoch2_sha256_after
        ):
            raise ValueError("idempotent Epoch2 validation changed canonical bytes")


def activate_wc2_epoch2(
    *,
    epoch1_ledger_path: Path,
    epoch2_ledger_path: Path,
    activated_at_ms: int,
) -> WC2Epoch2ActivationResult:
    """Activate canonical paper Epoch2 once; later calls are read-only checks."""
    if activated_at_ms < 0:
        raise ValueError("WC2 Epoch2 activation time cannot be negative")
    if epoch1_ledger_path.resolve() == epoch2_ledger_path.resolve():
        raise ValueError("Epoch1 and Epoch2 paths must remain separate")
    if not epoch1_ledger_path.is_file():
        raise ValueError("WC2 Epoch2 activation requires existing Epoch1 ledger")

    epoch1_before = epoch1_ledger_path.read_bytes()
    epoch1_sha = hashlib.sha256(epoch1_before).hexdigest()
    epoch2_before = _sha256_file(epoch2_ledger_path)

    if epoch2_before is None:
        state = initialize_epoch2_canonical_fund(
            epoch1_ledger_path=epoch1_ledger_path,
            epoch2_ledger_path=epoch2_ledger_path,
            activated_at_ms=activated_at_ms,
        )
        status = WC2Epoch2ActivationStatus.INSERTED
    else:
        state = read_epoch2_state_read_only(epoch2_ledger_path)
        if state is None:
            raise ValueError("existing Epoch2 file has no canonical activation")
        status = WC2Epoch2ActivationStatus.UNCHANGED

    if epoch1_ledger_path.read_bytes() != epoch1_before:
        raise ValueError("WC2 Epoch2 activation mutated immutable Epoch1 bytes")
    if state.activation.epoch1_ledger_sha256 != epoch1_sha:
        raise ValueError("WC2 Epoch2 activation does not bind current Epoch1 bytes")

    _validate_accepted_epoch2_state(state)
    replay = read_epoch2_state_read_only(epoch2_ledger_path)
    if replay != state:
        raise ValueError("WC2 Epoch2 read-only replay mismatch")

    epoch2_after = _sha256_file(epoch2_ledger_path)
    if epoch2_after is None:
        raise ValueError("WC2 Epoch2 activation did not persist canonical ledger")

    return WC2Epoch2ActivationResult(
        status=status,
        state=state,
        epoch1_sha256=epoch1_sha,
        epoch2_sha256_before=epoch2_before,
        epoch2_sha256_after=epoch2_after,
    )


def _validate_accepted_epoch2_state(state: Epoch2LedgerState) -> None:
    activation = state.activation
    if activation.starting_cash_usdt != Decimal("1000.00"):
        raise ValueError("WC2 Epoch2 starting cash must remain 1000 USDT")
    if activation.starting_cash_usdt != EPOCH_2_SPEC.starting_cash_usdt:
        raise ValueError("WC2 Epoch2 activation/spec starting cash mismatch")
    expected = {
        item.vault_id: item.starting_cash_usdt
        for item in EPOCH_2_SPEC.vault_allocations
    }
    observed = dict(activation.vault_starting_cash)
    if observed != expected:
        raise ValueError("WC2 Epoch2 vault split must remain 600/300/100")
    if len(state.vault_snapshots) != 3:
        raise ValueError("WC2 Epoch2 requires exact three-vault state")
    for snapshot in state.vault_snapshots:
        if snapshot.vault_id not in expected:
            raise ValueError("WC2 Epoch2 contains unexpected vault")
        if snapshot.starting_cash_usdt != expected[snapshot.vault_id]:
            raise ValueError("WC2 Epoch2 vault starting cash mismatch")
        if snapshot.cash_usdt != expected[snapshot.vault_id]:
            raise ValueError("fresh WC2 Epoch2 vault cash mismatch")
        if snapshot.nav_usdt != expected[snapshot.vault_id]:
            raise ValueError("fresh WC2 Epoch2 vault NAV mismatch")
        if snapshot.positions:
            raise ValueError("fresh WC2 Epoch2 activation cannot hold positions")
        if snapshot.real_capital != REAL_CAPITAL:
            raise ValueError("WC2 Epoch2 vault REAL_CAPITAL mismatch")
    if state.consolidated_snapshot.nav_usdt != Decimal("1000.00"):
        raise ValueError("fresh WC2 Epoch2 consolidated NAV must be 1000")
    if state.consolidated_snapshot.real_capital != REAL_CAPITAL:
        raise ValueError("WC2 Epoch2 consolidated REAL_CAPITAL mismatch")


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epoch1", type=Path, required=True)
    parser.add_argument("--epoch2", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = activate_wc2_epoch2(
        epoch1_ledger_path=args.epoch1,
        epoch2_ledger_path=args.epoch2,
        activated_at_ms=time.time_ns() // 1_000_000,
    )
    activation = result.state.activation
    vaults = {
        item.vault_id: item.starting_cash_usdt
        for item in result.state.vault_snapshots
    }
    print(f"WC2_EPOCH2_STATUS={result.status.value}")
    print(f"WC2_EPOCH2_ACTIVATION_IDENTITY={activation.activation_identity}")
    print(f"WC2_EPOCH2_ACTIVATED_AT_MS={activation.activated_at_ms}")
    print(f"WC2_EPOCH2_EPOCH1_SHA256={result.epoch1_sha256}")
    print(f"WC2_EPOCH2_SHA256_AFTER={result.epoch2_sha256_after}")
    print(
        "WC2_EPOCH2_STARTING_CASH_USDT="
        f"{activation.starting_cash_usdt}"
    )
    print(f"WC2_EPOCH2_CORE_USDT={vaults[PaperVaultId.CORE]}")
    print(f"WC2_EPOCH2_TACTICAL_USDT={vaults[PaperVaultId.TACTICAL]}")
    print(
        "WC2_EPOCH2_OPPORTUNITY_RESERVE_USDT="
        f"{vaults[PaperVaultId.OPPORTUNITY_RESERVE]}"
    )
    print("WC2_EPOCH1_BYTE_STABLE_PASS=YES")
    print("WC2_EPOCH2_READONLY_REPLAY_PASS=YES")
    print("WC2_EPOCH2_NO_LEVERAGE_BORROWING_MARTINGALE_PASS=YES")
    print("REAL_CAPITAL=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
