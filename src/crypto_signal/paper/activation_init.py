"""One-time persistent PAPER/STABLE activation watermark initialization.

This boundary captures a consistent read-only production signal-ledger baseline
and persists the immutable activation singleton into the existing paper SQLite
database. It grants no trade authority and requires the virtual 100 USDT fund
to remain pristine (one fund-creation record, no decisions/fills/mutations/NAV).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from crypto_signal.paper.activation import (
    PaperActivationError,
    PaperActivationState,
    activate_paper_policy,
    load_paper_activation,
)
from crypto_signal.paper.ledger import (
    PaperFundLedger,
    PaperLedgerWriteDisposition,
)
from crypto_signal.paper.models import INITIAL_CASH_USDT, REAL_CAPITAL
from crypto_signal.paper.state import reconstruct_paper_fund_state

__all__ = [
    "PAPER_ACTIVATION_INIT_VERSION",
    "REAL_CAPITAL",
    "PaperActivationBaseline",
    "PaperActivationInitError",
    "PaperActivationInitResult",
    "initialize_paper_activation_watermark",
    "read_signal_activation_baseline",
]

PAPER_ACTIVATION_INIT_VERSION = "paper_activation_init.v1"


class PaperActivationInitError(RuntimeError):
    """Raised when activation cannot be initialized from pristine current truth."""


@dataclass(frozen=True, slots=True)
class PaperActivationBaseline:
    freeze_count: int
    latest_signal_freeze_identity: str | None
    latest_frozen_at_ms: int | None

    def __post_init__(self) -> None:
        if self.freeze_count < 0:
            raise ValueError("activation baseline freeze_count cannot be negative")
        if self.freeze_count == 0:
            if (
                self.latest_signal_freeze_identity is not None
                or self.latest_frozen_at_ms is not None
            ):
                raise ValueError("empty activation baseline cannot expose latest metadata")
            return
        if (
            self.latest_signal_freeze_identity is None
            or self.latest_frozen_at_ms is None
        ):
            raise ValueError("non-empty activation baseline requires latest metadata")
        _require_sha256(
            self.latest_signal_freeze_identity,
            "latest_signal_freeze_identity",
        )
        if self.latest_frozen_at_ms < 0:
            raise ValueError("latest_frozen_at_ms must be non-negative")


@dataclass(frozen=True, slots=True)
class PaperActivationInitResult:
    version: str
    disposition: PaperLedgerWriteDisposition
    activation: PaperActivationState
    baseline: PaperActivationBaseline
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.version != PAPER_ACTIVATION_INIT_VERSION:
            raise ValueError("unsupported activation init version")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.activation.real_capital != REAL_CAPITAL:
            raise ValueError("activation must remain REAL_CAPITAL=0")
        if (
            self.activation.baseline_signal_freeze_count
            != self.baseline.freeze_count
            or self.activation.baseline_latest_signal_freeze_identity
            != self.baseline.latest_signal_freeze_identity
            or self.activation.baseline_latest_frozen_at_ms
            != self.baseline.latest_frozen_at_ms
        ):
            raise ValueError("activation/baseline lineage mismatch")


def read_signal_activation_baseline(path: Path) -> PaperActivationBaseline:
    """Read count/latest freeze from one consistent immutable SQLite snapshot."""
    if not path.exists():
        raise PaperActivationInitError("immutable signal ledger does not exist")
    uri = f"file:{path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            table = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'signal_freezes'
                """
            ).fetchone()
            if table is None:
                raise PaperActivationInitError(
                    "immutable signal ledger missing signal_freezes"
                )
            count_row = connection.execute(
                "SELECT COUNT(*) AS count FROM signal_freezes"
            ).fetchone()
            latest = connection.execute(
                """
                SELECT signal_freeze_identity, frozen_at_ms
                FROM signal_freezes
                ORDER BY frozen_at_ms DESC, signal_freeze_identity DESC
                LIMIT 1
                """
            ).fetchone()
            connection.execute("ROLLBACK")
    except sqlite3.Error as exc:
        raise PaperActivationInitError(
            f"failed to read immutable signal activation baseline: {exc}"
        ) from exc

    count = 0 if count_row is None else int(count_row["count"])
    if latest is None:
        return PaperActivationBaseline(
            freeze_count=count,
            latest_signal_freeze_identity=None,
            latest_frozen_at_ms=None,
        )
    return PaperActivationBaseline(
        freeze_count=count,
        latest_signal_freeze_identity=str(latest["signal_freeze_identity"]),
        latest_frozen_at_ms=int(latest["frozen_at_ms"]),
    )


def initialize_paper_activation_watermark(
    *,
    paper_ledger_path: Path,
    signal_ledger_path: Path,
    activated_at_ms: int,
) -> PaperActivationInitResult:
    """Create the activation singleton once; exact later invocations are no-ops."""
    if activated_at_ms < 0:
        raise PaperActivationInitError("activated_at_ms must be non-negative")
    ledger = PaperFundLedger(paper_ledger_path)
    state = reconstruct_paper_fund_state(ledger)
    _require_pristine_fund(state)

    existing = load_paper_activation(ledger)
    if existing is not None:
        if existing.fund_identity != state.fund_identity:
            raise PaperActivationInitError(
                "persistent activation fund identity mismatch"
            )
        baseline = PaperActivationBaseline(
            freeze_count=existing.baseline_signal_freeze_count,
            latest_signal_freeze_identity=(
                existing.baseline_latest_signal_freeze_identity
            ),
            latest_frozen_at_ms=existing.baseline_latest_frozen_at_ms,
        )
        return PaperActivationInitResult(
            version=PAPER_ACTIVATION_INIT_VERSION,
            disposition=PaperLedgerWriteDisposition.UNCHANGED,
            activation=existing,
            baseline=baseline,
            real_capital=REAL_CAPITAL,
        )

    baseline = read_signal_activation_baseline(signal_ledger_path)
    if (
        baseline.latest_frozen_at_ms is not None
        and baseline.latest_frozen_at_ms > activated_at_ms
    ):
        raise PaperActivationInitError(
            "activation timestamp predates latest observed signal freeze"
        )
    try:
        disposition, activation = activate_paper_policy(
            ledger=ledger,
            state=state,
            activated_at_ms=activated_at_ms,
            baseline_signal_freeze_count=baseline.freeze_count,
            baseline_latest_signal_freeze_identity=(
                baseline.latest_signal_freeze_identity
            ),
            baseline_latest_frozen_at_ms=baseline.latest_frozen_at_ms,
        )
    except PaperActivationError as exc:
        raise PaperActivationInitError(str(exc)) from exc

    after = reconstruct_paper_fund_state(ledger)
    if after != state:
        raise PaperActivationInitError(
            "activation initialization changed paper fund replay state"
        )
    return PaperActivationInitResult(
        version=PAPER_ACTIVATION_INIT_VERSION,
        disposition=disposition,
        activation=activation,
        baseline=baseline,
        real_capital=REAL_CAPITAL,
    )


def _require_pristine_fund(state) -> None:
    if state.real_capital != REAL_CAPITAL:
        raise PaperActivationInitError("REAL_CAPITAL must remain 0")
    if (
        state.replayed_record_count != 1
        or state.cash_usdt != INITIAL_CASH_USDT
        or state.positions
    ):
        raise PaperActivationInitError(
            "activation initialization requires pristine 100 USDT paper fund"
        )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
