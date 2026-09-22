"""Versioned paper-fund epoch contracts.

Epoch 1 is immutable legacy history at 100 USDT.
Epoch 2 is the new current paper-program contract at 1,000 USDT.

This module deliberately does not mutate or reinterpret the legacy Stage 6C
FundCreationRecord. Epochs use separate ledger files so historical paper truth
remains replayable exactly as written.

Simulation only. REAL_CAPITAL remains 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.models import (
    INITIAL_CASH_USDT,
    REAL_CAPITAL,
    FundCreationRecord,
)

PAPER_EPOCH_SCHEMA_VERSION = "paper_epoch.schema.v1"

EPOCH_1_ID = "paper-epoch-1-legacy-100-usdt"
EPOCH_2_ID = "paper-epoch-2-current-1000-usdt"

EPOCH_1_STARTING_CASH_USDT = Decimal("100.00")
EPOCH_2_STARTING_CASH_USDT = Decimal("1000.00")

EPOCH_1_LEDGER_FILENAME = "paper_fund.sqlite3"
EPOCH_2_LEDGER_FILENAME = "paper_fund_epoch2.sqlite3"


class PaperEpochStatus(StrEnum):
    LEGACY = "LEGACY"
    CURRENT = "CURRENT"


class PaperVaultId(StrEnum):
    CORE = "CORE"
    TACTICAL = "TACTICAL"
    OPPORTUNITY_RESERVE = "OPPORTUNITY_RESERVE"


@dataclass(frozen=True, slots=True)
class PaperVaultAllocation:
    vault_id: PaperVaultId
    starting_cash_usdt: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.vault_id, PaperVaultId):
            raise TypeError("vault_id must be PaperVaultId")
        if not isinstance(self.starting_cash_usdt, Decimal):
            raise TypeError("vault starting cash must be Decimal")
        if (
            self.starting_cash_usdt.is_nan()
            or self.starting_cash_usdt.is_infinite()
            or self.starting_cash_usdt <= Decimal(0)
        ):
            raise ValueError("vault starting cash must be a positive finite Decimal")


@dataclass(frozen=True, slots=True)
class PaperFundEpochSpec:
    epoch_id: str
    status: PaperEpochStatus
    starting_cash_usdt: Decimal
    ledger_filename: str
    predecessor_epoch_id: str | None
    vault_allocations: tuple[PaperVaultAllocation, ...]
    canonical_for_new_activity: bool
    real_capital: int = REAL_CAPITAL
    leverage_allowed: bool = False
    borrowing_allowed: bool = False
    martingale_allowed: bool = False
    schema_version: str = PAPER_EPOCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.epoch_id.strip():
            raise ValueError("epoch_id must be non-empty")
        if not isinstance(self.status, PaperEpochStatus):
            raise TypeError("status must be PaperEpochStatus")
        if not isinstance(self.starting_cash_usdt, Decimal):
            raise TypeError("epoch starting cash must be Decimal")
        if (
            self.starting_cash_usdt.is_nan()
            or self.starting_cash_usdt.is_infinite()
            or self.starting_cash_usdt <= Decimal(0)
        ):
            raise ValueError("epoch starting cash must be a positive finite Decimal")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if any((self.leverage_allowed, self.borrowing_allowed, self.martingale_allowed)):
            raise ValueError(
                "canonical v1.1 paper epochs cannot enable leverage, borrowing or martingale"
            )
        if self.schema_version != PAPER_EPOCH_SCHEMA_VERSION:
            raise ValueError("unexpected paper epoch schema version")
        if (
            not self.ledger_filename
            or Path(self.ledger_filename).name != self.ledger_filename
        ):
            raise ValueError("epoch ledger filename must be a plain filename")
        if len({item.vault_id for item in self.vault_allocations}) != len(
            self.vault_allocations
        ):
            raise ValueError("epoch vault allocations must have unique vault ids")

        allocated = sum(
            (item.starting_cash_usdt for item in self.vault_allocations),
            start=Decimal(0),
        )
        if self.vault_allocations and allocated != self.starting_cash_usdt:
            raise ValueError("epoch vault allocations must sum to starting cash")
        if self.status is PaperEpochStatus.CURRENT:
            if not self.canonical_for_new_activity:
                raise ValueError("current epoch must be canonical for new activity")
            if not self.predecessor_epoch_id:
                raise ValueError("current epoch must identify its predecessor")
            if not self.vault_allocations:
                raise ValueError("current epoch must define vault allocations")
        if self.status is PaperEpochStatus.LEGACY and self.canonical_for_new_activity:
            raise ValueError("legacy epoch cannot be canonical for new activity")

    @property
    def epoch_identity(self) -> str:
        return canonical_sha256(
            {
                "borrowing_allowed": self.borrowing_allowed,
                "canonical_for_new_activity": self.canonical_for_new_activity,
                "epoch_id": self.epoch_id,
                "ledger_filename": self.ledger_filename,
                "leverage_allowed": self.leverage_allowed,
                "martingale_allowed": self.martingale_allowed,
                "predecessor_epoch_id": self.predecessor_epoch_id,
                "real_capital": self.real_capital,
                "schema_version": self.schema_version,
                "starting_cash_usdt": self.starting_cash_usdt,
                "status": self.status.value,
                "vault_allocations": [
                    {
                        "starting_cash_usdt": item.starting_cash_usdt,
                        "vault_id": item.vault_id.value,
                    }
                    for item in self.vault_allocations
                ],
            }
        )


EPOCH_1_SPEC = PaperFundEpochSpec(
    epoch_id=EPOCH_1_ID,
    status=PaperEpochStatus.LEGACY,
    starting_cash_usdt=EPOCH_1_STARTING_CASH_USDT,
    ledger_filename=EPOCH_1_LEDGER_FILENAME,
    predecessor_epoch_id=None,
    vault_allocations=(),
    canonical_for_new_activity=False,
)

EPOCH_2_SPEC = PaperFundEpochSpec(
    epoch_id=EPOCH_2_ID,
    status=PaperEpochStatus.CURRENT,
    starting_cash_usdt=EPOCH_2_STARTING_CASH_USDT,
    ledger_filename=EPOCH_2_LEDGER_FILENAME,
    predecessor_epoch_id=EPOCH_1_ID,
    vault_allocations=(
        PaperVaultAllocation(PaperVaultId.CORE, Decimal("600.00")),
        PaperVaultAllocation(PaperVaultId.TACTICAL, Decimal("300.00")),
        PaperVaultAllocation(PaperVaultId.OPPORTUNITY_RESERVE, Decimal("100.00")),
    ),
    canonical_for_new_activity=True,
)

PAPER_EPOCHS: tuple[PaperFundEpochSpec, ...] = (EPOCH_1_SPEC, EPOCH_2_SPEC)


def current_paper_epoch_spec() -> PaperFundEpochSpec:
    current = tuple(item for item in PAPER_EPOCHS if item.canonical_for_new_activity)
    if len(current) != 1:
        raise RuntimeError("paper epoch registry must have exactly one current epoch")
    return current[0]


def paper_epoch_spec(epoch_id: str) -> PaperFundEpochSpec:
    matches = tuple(item for item in PAPER_EPOCHS if item.epoch_id == epoch_id)
    if len(matches) != 1:
        raise KeyError(f"unknown paper epoch: {epoch_id}")
    return matches[0]


def paper_epoch_ledger_path(
    paper_runtime_dir: Path,
    *,
    epoch: PaperFundEpochSpec | None = None,
) -> Path:
    selected = current_paper_epoch_spec() if epoch is None else epoch
    return paper_runtime_dir / selected.ledger_filename


def assert_legacy_epoch1_fund_creation(record: FundCreationRecord) -> None:
    """Prove that an existing v1 creation still represents untouched Epoch 1."""
    if record.initial_cash_usdt != INITIAL_CASH_USDT:
        raise ValueError("legacy fund creation no longer matches v1 initial cash")
    if record.initial_cash_usdt != EPOCH_1_SPEC.starting_cash_usdt:
        raise ValueError("legacy fund creation no longer matches Epoch 1")
    if record.real_capital != REAL_CAPITAL:
        raise ValueError("REAL_CAPITAL must remain 0")
