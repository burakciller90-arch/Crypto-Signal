"""Immutable Paper Vault V3 constitution and append-only lifecycle store.

FP2 final-product contract only. This module does not replace Epoch 1/2,
execute trades, mutate R21/R22, or grant real-capital/production authority.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.paper.epochs import (
    EPOCH_1_LEDGER_FILENAME,
    EPOCH_2_LEDGER_FILENAME,
)
from crypto_signal.paper.models import (
    PAPER_EXECUTION_POLICY_VERSION,
    PAPER_RISK_POLICY_VERSION,
    REAL_CAPITAL,
    PaperSymbol,
)

PAPER_VAULT_V3_SCHEMA_VERSION = "paper-vault-v3.schema.v1"
PAPER_VAULT_V3_ENGINE_VERSION = "paper-vault-v3-constitution-engine-v1/1"
PAPER_VAULT_V3_STORE_SCHEMA_VERSION = "paper-vault-v3-store-v1/1"
PAPER_VAULT_V3_CONSTITUTION_POLICY_VERSION = (
    "paper-vault-v3-constitution-policy-v1/1"
)
PAPER_VAULT_V3_ALLOCATION_POLICY_VERSION = (
    "paper-vault-v3-allocation-policy-v1/1"
)
DEFAULT_PAPER_VAULT_V3_STARTING_CAPITAL_USDT = Decimal("10000.00")

_LEGACY_LEDGER_FILENAMES = frozenset(
    {EPOCH_1_LEDGER_FILENAME, EPOCH_2_LEDGER_FILENAME}
)


class PaperVaultV3Book(StrEnum):
    CORE = "CORE"
    TACTICAL = "TACTICAL"
    OPPORTUNITY = "OPPORTUNITY"
    CASH = "CASH"


class PaperVaultV3Status(StrEnum):
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    ARCHIVED = "ARCHIVED"


class PaperVaultV3LifecycleAction(StrEnum):
    STOP = "STOP"
    ARCHIVE = "ARCHIVE"


@dataclass(frozen=True, slots=True)
class PaperVaultV3EvidencePolicyVersion:
    domain: str
    version: str

    def __post_init__(self) -> None:
        if not self.domain.strip() or self.domain != self.domain.strip().lower():
            raise ValueError(
                "Paper Vault V3 evidence-policy domain must be canonical lowercase"
            )
        if any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
            for character in self.domain
        ):
            raise ValueError("Paper Vault V3 evidence-policy domain is invalid")
        if not self.version.strip():
            raise ValueError("Paper Vault V3 evidence-policy version must be non-empty")


@dataclass(frozen=True, slots=True)
class PaperVaultV3AllocationPolicy:
    policy_identity: str
    version: str
    permitted_books: tuple[PaperVaultV3Book, ...]
    minimum_market_exposure_fraction: Decimal
    maximum_market_exposure_fraction: Decimal
    cash_is_valid: bool = True
    cross_vault_borrowing_allowed: bool = False
    forced_deployment: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.policy_identity, "Paper Vault V3 allocation policy")
        if self.version != PAPER_VAULT_V3_ALLOCATION_POLICY_VERSION:
            raise ValueError("unsupported Paper Vault V3 allocation policy version")
        if not self.permitted_books:
            raise ValueError("Paper Vault V3 allocation policy requires books")
        canonical_books = tuple(
            sorted(set(self.permitted_books), key=lambda value: value.value)
        )
        if self.permitted_books != canonical_books:
            raise ValueError(
                "Paper Vault V3 permitted books must be sorted and unique"
            )
        if PaperVaultV3Book.CASH not in self.permitted_books:
            raise ValueError("Paper Vault V3 allocation policy must permit cash")
        _require_fraction(
            self.minimum_market_exposure_fraction,
            "Paper Vault V3 minimum market exposure",
        )
        _require_fraction(
            self.maximum_market_exposure_fraction,
            "Paper Vault V3 maximum market exposure",
        )
        if self.minimum_market_exposure_fraction != Decimal(0):
            raise ValueError("Paper Vault V3 cannot force minimum market exposure")
        if self.maximum_market_exposure_fraction <= Decimal(0):
            raise ValueError("Paper Vault V3 maximum market exposure must be positive")
        if (
            self.minimum_market_exposure_fraction
            > self.maximum_market_exposure_fraction
        ):
            raise ValueError("Paper Vault V3 allocation exposure bounds are invalid")
        if not self.cash_is_valid:
            raise ValueError("Paper Vault V3 must allow 100% cash")
        if self.cross_vault_borrowing_allowed:
            raise ValueError("Paper Vault V3 cross-vault borrowing is forbidden")
        if self.forced_deployment:
            raise ValueError("Paper Vault V3 forced deployment is forbidden")
        if self.production_authority:
            raise ValueError("Paper Vault V3 cannot grant production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.policy_identity != canonical_sha256(
            _allocation_policy_identity_payload(self)
        ):
            raise ValueError("Paper Vault V3 allocation policy identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperVaultV3Constitution:
    vault_identity: str
    created_at_ms: int
    starting_virtual_capital_usdt: Decimal
    constitution_policy_version: str
    permitted_instruments: tuple[PaperSymbol, ...]
    execution_policy_version: str
    risk_policy_version: str
    allocation_policy: PaperVaultV3AllocationPolicy
    evidence_policy_versions: tuple[PaperVaultV3EvidencePolicyVersion, ...]
    cross_vault_borrowing_allowed: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = PAPER_VAULT_V3_SCHEMA_VERSION
    engine_version: str = PAPER_VAULT_V3_ENGINE_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.vault_identity, "Paper Vault V3 identity")
        if self.created_at_ms < 0:
            raise ValueError("Paper Vault V3 creation time must be non-negative")
        _require_positive_money(
            self.starting_virtual_capital_usdt,
            "Paper Vault V3 starting capital",
        )
        if (
            self.constitution_policy_version
            != PAPER_VAULT_V3_CONSTITUTION_POLICY_VERSION
        ):
            raise ValueError("unsupported Paper Vault V3 constitution policy")
        if not self.permitted_instruments:
            raise ValueError("Paper Vault V3 requires permitted instruments")
        if not all(
            isinstance(value, PaperSymbol) for value in self.permitted_instruments
        ):
            raise TypeError(
                "Paper Vault V3 permitted instruments must be PaperSymbol values"
            )
        canonical_instruments = tuple(
            sorted(set(self.permitted_instruments), key=lambda value: value.value)
        )
        if self.permitted_instruments != canonical_instruments:
            raise ValueError(
                "Paper Vault V3 instruments must be sorted and unique"
            )
        if not self.execution_policy_version.strip():
            raise ValueError("Paper Vault V3 execution policy version is required")
        if not self.risk_policy_version.strip():
            raise ValueError("Paper Vault V3 risk policy version is required")
        if not isinstance(self.allocation_policy, PaperVaultV3AllocationPolicy):
            raise TypeError(
                "Paper Vault V3 allocation policy must be canonical V3 policy"
            )
        if not self.evidence_policy_versions:
            raise ValueError("Paper Vault V3 requires evidence-policy versions")
        if not all(
            isinstance(value, PaperVaultV3EvidencePolicyVersion)
            for value in self.evidence_policy_versions
        ):
            raise TypeError("Paper Vault V3 evidence-policy references are invalid")
        canonical_evidence = tuple(
            sorted(
                self.evidence_policy_versions,
                key=lambda value: value.domain,
            )
        )
        if self.evidence_policy_versions != canonical_evidence:
            raise ValueError(
                "Paper Vault V3 evidence-policy references must be sorted"
            )
        domains = tuple(value.domain for value in self.evidence_policy_versions)
        if len(set(domains)) != len(domains):
            raise ValueError(
                "Paper Vault V3 evidence-policy domains must be unique"
            )
        if self.cross_vault_borrowing_allowed:
            raise ValueError("Paper Vault V3 cross-vault borrowing is forbidden")
        if self.production_authority:
            raise ValueError("Paper Vault V3 cannot grant production authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.schema_version != PAPER_VAULT_V3_SCHEMA_VERSION:
            raise ValueError("unsupported Paper Vault V3 schema version")
        if self.engine_version != PAPER_VAULT_V3_ENGINE_VERSION:
            raise ValueError("unsupported Paper Vault V3 engine version")
        if self.vault_identity != canonical_sha256(
            _constitution_identity_payload(self)
        ):
            raise ValueError("Paper Vault V3 constitution identity mismatch")


@dataclass(frozen=True, slots=True)
class PaperVaultV3LifecycleEvent:
    event_identity: str
    vault_identity: str
    action: PaperVaultV3LifecycleAction
    event_at_ms: int
    previous_status: PaperVaultV3Status
    new_status: PaperVaultV3Status
    reason: str
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL
    schema_version: str = PAPER_VAULT_V3_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.event_identity, "Paper Vault V3 lifecycle event")
        _require_sha256(self.vault_identity, "Paper Vault V3 lifecycle vault")
        if not isinstance(self.action, PaperVaultV3LifecycleAction):
            raise TypeError("Paper Vault V3 lifecycle action is invalid")
        if not isinstance(self.previous_status, PaperVaultV3Status):
            raise TypeError("Paper Vault V3 previous status is invalid")
        if not isinstance(self.new_status, PaperVaultV3Status):
            raise TypeError("Paper Vault V3 new status is invalid")
        if self.event_at_ms < 0:
            raise ValueError("Paper Vault V3 lifecycle time must be non-negative")
        if not self.reason.strip():
            raise ValueError("Paper Vault V3 lifecycle reason is required")
        if self.action is PaperVaultV3LifecycleAction.STOP:
            if (
                self.previous_status is not PaperVaultV3Status.ACTIVE
                or self.new_status is not PaperVaultV3Status.STOPPED
            ):
                raise ValueError("Paper Vault V3 STOP transition is invalid")
        elif self.action is PaperVaultV3LifecycleAction.ARCHIVE:
            if (
                self.previous_status
                not in {
                    PaperVaultV3Status.ACTIVE,
                    PaperVaultV3Status.STOPPED,
                }
                or self.new_status is not PaperVaultV3Status.ARCHIVED
            ):
                raise ValueError("Paper Vault V3 ARCHIVE transition is invalid")
        if self.production_authority:
            raise ValueError("Paper Vault V3 lifecycle cannot grant authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.schema_version != PAPER_VAULT_V3_SCHEMA_VERSION:
            raise ValueError("unsupported Paper Vault V3 lifecycle schema")
        if self.event_identity != canonical_sha256(
            _lifecycle_event_identity_payload(self)
        ):
            raise ValueError("Paper Vault V3 lifecycle identity mismatch")


def build_paper_vault_v3_allocation_policy(
    *,
    permitted_books: tuple[PaperVaultV3Book, ...] = tuple(
        sorted(PaperVaultV3Book, key=lambda value: value.value)
    ),
    version: str = PAPER_VAULT_V3_ALLOCATION_POLICY_VERSION,
) -> PaperVaultV3AllocationPolicy:
    normalized_books = tuple(
        sorted(set(permitted_books), key=lambda value: value.value)
    )
    payload = {
        "cash_is_valid": True,
        "cross_vault_borrowing_allowed": False,
        "forced_deployment": False,
        "maximum_market_exposure_fraction": Decimal(1),
        "minimum_market_exposure_fraction": Decimal(0),
        "permitted_books": normalized_books,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "version": version,
    }
    return PaperVaultV3AllocationPolicy(
        policy_identity=canonical_sha256(payload),
        version=version,
        permitted_books=normalized_books,
        minimum_market_exposure_fraction=Decimal(0),
        maximum_market_exposure_fraction=Decimal(1),
    )


def build_paper_vault_v3_constitution(
    *,
    created_at_ms: int,
    evidence_policy_versions: tuple[PaperVaultV3EvidencePolicyVersion, ...],
    starting_virtual_capital_usdt: Decimal = (
        DEFAULT_PAPER_VAULT_V3_STARTING_CAPITAL_USDT
    ),
    permitted_instruments: tuple[PaperSymbol, ...] = tuple(
        sorted(PaperSymbol, key=lambda value: value.value)
    ),
    constitution_policy_version: str = (
        PAPER_VAULT_V3_CONSTITUTION_POLICY_VERSION
    ),
    execution_policy_version: str = PAPER_EXECUTION_POLICY_VERSION,
    risk_policy_version: str = PAPER_RISK_POLICY_VERSION,
    allocation_policy: PaperVaultV3AllocationPolicy | None = None,
) -> PaperVaultV3Constitution:
    selected_allocation = (
        build_paper_vault_v3_allocation_policy()
        if allocation_policy is None
        else allocation_policy
    )
    normalized_instruments = tuple(
        sorted(set(permitted_instruments), key=lambda value: value.value)
    )
    normalized_evidence = tuple(
        sorted(evidence_policy_versions, key=lambda value: value.domain)
    )
    provisional = {
        "allocation_policy": selected_allocation,
        "constitution_policy_version": constitution_policy_version,
        "created_at_ms": created_at_ms,
        "cross_vault_borrowing_allowed": False,
        "engine_version": PAPER_VAULT_V3_ENGINE_VERSION,
        "evidence_policy_versions": normalized_evidence,
        "execution_policy_version": execution_policy_version,
        "permitted_instruments": normalized_instruments,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "risk_policy_version": risk_policy_version,
        "schema_version": PAPER_VAULT_V3_SCHEMA_VERSION,
        "starting_virtual_capital_usdt": starting_virtual_capital_usdt,
    }
    return PaperVaultV3Constitution(
        vault_identity=canonical_sha256(provisional),
        created_at_ms=created_at_ms,
        starting_virtual_capital_usdt=starting_virtual_capital_usdt,
        constitution_policy_version=constitution_policy_version,
        permitted_instruments=normalized_instruments,
        execution_policy_version=execution_policy_version,
        risk_policy_version=risk_policy_version,
        allocation_policy=selected_allocation,
        evidence_policy_versions=normalized_evidence,
    )


def build_paper_vault_v3_lifecycle_event(
    *,
    vault_identity: str,
    action: PaperVaultV3LifecycleAction,
    event_at_ms: int,
    previous_status: PaperVaultV3Status,
    reason: str,
) -> PaperVaultV3LifecycleEvent:
    if action is PaperVaultV3LifecycleAction.STOP:
        new_status = PaperVaultV3Status.STOPPED
    elif action is PaperVaultV3LifecycleAction.ARCHIVE:
        new_status = PaperVaultV3Status.ARCHIVED
    else:
        raise ValueError("unsupported Paper Vault V3 lifecycle action")
    payload = {
        "action": action,
        "event_at_ms": event_at_ms,
        "new_status": new_status,
        "previous_status": previous_status,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "reason": reason,
        "schema_version": PAPER_VAULT_V3_SCHEMA_VERSION,
        "vault_identity": vault_identity,
    }
    return PaperVaultV3LifecycleEvent(
        event_identity=canonical_sha256(payload),
        vault_identity=vault_identity,
        action=action,
        event_at_ms=event_at_ms,
        previous_status=previous_status,
        new_status=new_status,
        reason=reason,
    )


class PaperVaultV3Store:
    """Separate append-only persistence for final-product Paper Vault V3 truth."""

    def __init__(self, path: Path) -> None:
        if path.name in _LEGACY_LEDGER_FILENAMES:
            raise ValueError("Paper Vault V3 store cannot use an Epoch 1/2 ledger path")
        self.path = path

    def initialize(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_vault_v3_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_vault_v3_constitutions (
                    vault_identity TEXT PRIMARY KEY,
                    created_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_vault_v3_lifecycle_events (
                    event_identity TEXT PRIMARY KEY,
                    vault_identity TEXT NOT NULL,
                    event_at_ms INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    previous_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    UNIQUE(vault_identity, event_at_ms, action),
                    FOREIGN KEY(vault_identity)
                        REFERENCES paper_vault_v3_constitutions(vault_identity)
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO paper_vault_v3_meta(key, value)
                VALUES ('schema_version', ?)
                """,
                (PAPER_VAULT_V3_STORE_SCHEMA_VERSION,),
            )
            row = connection.execute(
                """
                SELECT value FROM paper_vault_v3_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if row is None or str(row[0]) != PAPER_VAULT_V3_STORE_SCHEMA_VERSION:
                raise ValueError("Paper Vault V3 store schema mismatch")
            for table in (
                "paper_vault_v3_constitutions",
                "paper_vault_v3_lifecycle_events",
            ):
                for operation in ("UPDATE", "DELETE"):
                    trigger = (
                        f"{table}_immutable_{operation.lower()}"
                    )
                    connection.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {trigger}
                        BEFORE {operation} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable Paper Vault V3 truth'
                            );
                        END
                        """
                    )

    def append_constitution(self, value: PaperVaultV3Constitution) -> bool:
        if not isinstance(value, PaperVaultV3Constitution):
            raise TypeError("Paper Vault V3 store requires a constitution")
        self.initialize()
        payload_json = canonical_json(_constitution_storage_payload(value))
        payload_sha256 = sha256_text(payload_json)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            _require_store_schema(connection)
            row = connection.execute(
                """
                SELECT vault_identity, created_at_ms, payload_json, payload_sha256
                FROM paper_vault_v3_constitutions
                WHERE vault_identity = ?
                """,
                (value.vault_identity,),
            ).fetchone()
            if row is not None:
                existing = _verified_constitution_row(row)
                if canonical_json(_constitution_storage_payload(existing)) != payload_json:
                    raise ValueError("Paper Vault V3 constitution identity conflict")
                return False
            connection.execute(
                """
                INSERT INTO paper_vault_v3_constitutions(
                    vault_identity,
                    created_at_ms,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    value.vault_identity,
                    value.created_at_ms,
                    payload_json,
                    payload_sha256,
                ),
            )
        return True

    def read_constitution(
        self,
        vault_identity: str,
    ) -> PaperVaultV3Constitution | None:
        _require_sha256(vault_identity, "Paper Vault V3 constitution lookup")
        if not self.path.is_file():
            return None
        with closing(_connect_read_only(self.path)) as connection:
            _require_store_schema(connection)
            row = connection.execute(
                """
                SELECT vault_identity, created_at_ms, payload_json, payload_sha256
                FROM paper_vault_v3_constitutions
                WHERE vault_identity = ?
                """,
                (vault_identity,),
            ).fetchone()
            return None if row is None else _verified_constitution_row(row)

    def list_constitutions(self) -> tuple[PaperVaultV3Constitution, ...]:
        if not self.path.is_file():
            return ()
        with closing(_connect_read_only(self.path)) as connection:
            _require_store_schema(connection)
            rows = connection.execute(
                """
                SELECT vault_identity, created_at_ms, payload_json, payload_sha256
                FROM paper_vault_v3_constitutions
                ORDER BY created_at_ms, vault_identity
                """
            ).fetchall()
            return tuple(_verified_constitution_row(row) for row in rows)

    def append_lifecycle_event(
        self,
        event: PaperVaultV3LifecycleEvent,
    ) -> bool:
        if not isinstance(event, PaperVaultV3LifecycleEvent):
            raise TypeError("Paper Vault V3 store requires a lifecycle event")
        self.initialize()
        payload_json = canonical_json(_lifecycle_storage_payload(event))
        payload_sha256 = sha256_text(payload_json)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            _require_store_schema(connection)
            duplicate = connection.execute(
                """
                SELECT event_identity, vault_identity, event_at_ms, action,
                       previous_status, new_status, payload_json, payload_sha256
                FROM paper_vault_v3_lifecycle_events
                WHERE event_identity = ?
                """,
                (event.event_identity,),
            ).fetchone()
            if duplicate is not None:
                existing = _verified_lifecycle_row(duplicate)
                if canonical_json(_lifecycle_storage_payload(existing)) != payload_json:
                    raise ValueError("Paper Vault V3 lifecycle identity conflict")
                return False

            constitution_row = connection.execute(
                """
                SELECT vault_identity, created_at_ms, payload_json, payload_sha256
                FROM paper_vault_v3_constitutions
                WHERE vault_identity = ?
                """,
                (event.vault_identity,),
            ).fetchone()
            if constitution_row is None:
                raise ValueError("Paper Vault V3 lifecycle requires constitution")
            constitution = _verified_constitution_row(constitution_row)

            event_rows = connection.execute(
                """
                SELECT event_identity, vault_identity, event_at_ms, action,
                       previous_status, new_status, payload_json, payload_sha256
                FROM paper_vault_v3_lifecycle_events
                WHERE vault_identity = ?
                ORDER BY event_at_ms, event_identity
                """,
                (event.vault_identity,),
            ).fetchall()
            events = tuple(_verified_lifecycle_row(row) for row in event_rows)
            current = _derive_status(constitution, events)
            if event.previous_status is not current:
                raise ValueError("Paper Vault V3 lifecycle previous status mismatch")
            if event.event_at_ms < constitution.created_at_ms:
                raise ValueError("Paper Vault V3 lifecycle predates constitution")
            if events and event.event_at_ms <= events[-1].event_at_ms:
                raise ValueError("Paper Vault V3 lifecycle cannot backfill or fork time")

            connection.execute(
                """
                INSERT INTO paper_vault_v3_lifecycle_events(
                    event_identity,
                    vault_identity,
                    event_at_ms,
                    action,
                    previous_status,
                    new_status,
                    payload_json,
                    payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_identity,
                    event.vault_identity,
                    event.event_at_ms,
                    event.action.value,
                    event.previous_status.value,
                    event.new_status.value,
                    payload_json,
                    payload_sha256,
                ),
            )
        return True

    def read_lifecycle_events(
        self,
        vault_identity: str,
    ) -> tuple[PaperVaultV3LifecycleEvent, ...]:
        _require_sha256(vault_identity, "Paper Vault V3 lifecycle lookup")
        if not self.path.is_file():
            return ()
        with closing(_connect_read_only(self.path)) as connection:
            _require_store_schema(connection)
            rows = connection.execute(
                """
                SELECT event_identity, vault_identity, event_at_ms, action,
                       previous_status, new_status, payload_json, payload_sha256
                FROM paper_vault_v3_lifecycle_events
                WHERE vault_identity = ?
                ORDER BY event_at_ms, event_identity
                """,
                (vault_identity,),
            ).fetchall()
            return tuple(_verified_lifecycle_row(row) for row in rows)

    def current_status(
        self,
        vault_identity: str,
    ) -> PaperVaultV3Status | None:
        constitution = self.read_constitution(vault_identity)
        if constitution is None:
            return None
        return _derive_status(
            constitution,
            self.read_lifecycle_events(vault_identity),
        )


def _allocation_policy_identity_payload(
    value: PaperVaultV3AllocationPolicy,
) -> dict[str, object]:
    return {
        "cash_is_valid": value.cash_is_valid,
        "cross_vault_borrowing_allowed": value.cross_vault_borrowing_allowed,
        "forced_deployment": value.forced_deployment,
        "maximum_market_exposure_fraction": (
            value.maximum_market_exposure_fraction
        ),
        "minimum_market_exposure_fraction": (
            value.minimum_market_exposure_fraction
        ),
        "permitted_books": value.permitted_books,
        "production_authority": value.production_authority,
        "real_capital": value.real_capital,
        "version": value.version,
    }


def _constitution_identity_payload(
    value: PaperVaultV3Constitution,
) -> dict[str, object]:
    return {
        "allocation_policy": value.allocation_policy,
        "constitution_policy_version": value.constitution_policy_version,
        "created_at_ms": value.created_at_ms,
        "cross_vault_borrowing_allowed": value.cross_vault_borrowing_allowed,
        "engine_version": value.engine_version,
        "evidence_policy_versions": value.evidence_policy_versions,
        "execution_policy_version": value.execution_policy_version,
        "permitted_instruments": value.permitted_instruments,
        "production_authority": value.production_authority,
        "real_capital": value.real_capital,
        "risk_policy_version": value.risk_policy_version,
        "schema_version": value.schema_version,
        "starting_virtual_capital_usdt": value.starting_virtual_capital_usdt,
    }


def _constitution_storage_payload(
    value: PaperVaultV3Constitution,
) -> dict[str, object]:
    return {
        "vault_identity": value.vault_identity,
        **_constitution_identity_payload(value),
    }


def _lifecycle_event_identity_payload(
    value: PaperVaultV3LifecycleEvent,
) -> dict[str, object]:
    return {
        "action": value.action,
        "event_at_ms": value.event_at_ms,
        "new_status": value.new_status,
        "previous_status": value.previous_status,
        "production_authority": value.production_authority,
        "real_capital": value.real_capital,
        "reason": value.reason,
        "schema_version": value.schema_version,
        "vault_identity": value.vault_identity,
    }


def _lifecycle_storage_payload(
    value: PaperVaultV3LifecycleEvent,
) -> dict[str, object]:
    return {
        "event_identity": value.event_identity,
        **_lifecycle_event_identity_payload(value),
    }


def _verified_constitution_row(row: sqlite3.Row) -> PaperVaultV3Constitution:
    payload_json = str(row["payload_json"])
    expected_digest = str(row["payload_sha256"])
    if sha256_text(payload_json) != expected_digest:
        raise ValueError("Paper Vault V3 constitution payload digest mismatch")
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("Paper Vault V3 constitution payload must be object")
    allocation_raw = raw.get("allocation_policy")
    if not isinstance(allocation_raw, dict):
        raise TypeError("Paper Vault V3 allocation policy payload must be object")
    allocation = PaperVaultV3AllocationPolicy(
        policy_identity=str(allocation_raw.get("policy_identity", "")),
        version=str(allocation_raw.get("version", "")),
        permitted_books=tuple(
            PaperVaultV3Book(str(value))
            for value in _required_list(
                allocation_raw.get("permitted_books"),
                "Paper Vault V3 permitted books",
            )
        ),
        minimum_market_exposure_fraction=Decimal(
            str(allocation_raw.get("minimum_market_exposure_fraction", ""))
        ),
        maximum_market_exposure_fraction=Decimal(
            str(allocation_raw.get("maximum_market_exposure_fraction", ""))
        ),
        cash_is_valid=_required_bool(
            allocation_raw.get("cash_is_valid"),
            "Paper Vault V3 cash-valid flag",
        ),
        cross_vault_borrowing_allowed=_required_bool(
            allocation_raw.get("cross_vault_borrowing_allowed"),
            "Paper Vault V3 borrowing flag",
        ),
        forced_deployment=_required_bool(
            allocation_raw.get("forced_deployment"),
            "Paper Vault V3 forced-deployment flag",
        ),
        production_authority=_required_bool(
            allocation_raw.get("production_authority"),
            "Paper Vault V3 allocation authority",
        ),
        real_capital=_required_int(
            allocation_raw.get("real_capital"),
            "Paper Vault V3 allocation REAL_CAPITAL",
        ),
    )
    evidence_raw = _required_list(
        raw.get("evidence_policy_versions"),
        "Paper Vault V3 evidence policies",
    )
    evidence: list[PaperVaultV3EvidencePolicyVersion] = []
    for item in evidence_raw:
        if not isinstance(item, dict):
            raise TypeError("Paper Vault V3 evidence policy must be object")
        evidence.append(
            PaperVaultV3EvidencePolicyVersion(
                domain=str(item.get("domain", "")),
                version=str(item.get("version", "")),
            )
        )
    value = PaperVaultV3Constitution(
        vault_identity=str(raw.get("vault_identity", "")),
        created_at_ms=_required_int(
            raw.get("created_at_ms"),
            "Paper Vault V3 creation time",
        ),
        starting_virtual_capital_usdt=Decimal(
            str(raw.get("starting_virtual_capital_usdt", ""))
        ),
        constitution_policy_version=str(
            raw.get("constitution_policy_version", "")
        ),
        permitted_instruments=tuple(
            PaperSymbol(str(item))
            for item in _required_list(
                raw.get("permitted_instruments"),
                "Paper Vault V3 instruments",
            )
        ),
        execution_policy_version=str(raw.get("execution_policy_version", "")),
        risk_policy_version=str(raw.get("risk_policy_version", "")),
        allocation_policy=allocation,
        evidence_policy_versions=tuple(evidence),
        cross_vault_borrowing_allowed=_required_bool(
            raw.get("cross_vault_borrowing_allowed"),
            "Paper Vault V3 constitution borrowing",
        ),
        production_authority=_required_bool(
            raw.get("production_authority"),
            "Paper Vault V3 constitution authority",
        ),
        real_capital=_required_int(
            raw.get("real_capital"),
            "Paper Vault V3 constitution REAL_CAPITAL",
        ),
        schema_version=str(raw.get("schema_version", "")),
        engine_version=str(raw.get("engine_version", "")),
    )
    if str(row["vault_identity"]) != value.vault_identity:
        raise ValueError("Paper Vault V3 constitution row identity mismatch")
    if int(row["created_at_ms"]) != value.created_at_ms:
        raise ValueError("Paper Vault V3 constitution row time mismatch")
    return value


def _verified_lifecycle_row(row: sqlite3.Row) -> PaperVaultV3LifecycleEvent:
    payload_json = str(row["payload_json"])
    expected_digest = str(row["payload_sha256"])
    if sha256_text(payload_json) != expected_digest:
        raise ValueError("Paper Vault V3 lifecycle payload digest mismatch")
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise TypeError("Paper Vault V3 lifecycle payload must be object")
    value = PaperVaultV3LifecycleEvent(
        event_identity=str(raw.get("event_identity", "")),
        vault_identity=str(raw.get("vault_identity", "")),
        action=PaperVaultV3LifecycleAction(str(raw.get("action", ""))),
        event_at_ms=_required_int(
            raw.get("event_at_ms"),
            "Paper Vault V3 lifecycle time",
        ),
        previous_status=PaperVaultV3Status(
            str(raw.get("previous_status", ""))
        ),
        new_status=PaperVaultV3Status(str(raw.get("new_status", ""))),
        reason=str(raw.get("reason", "")),
        production_authority=_required_bool(
            raw.get("production_authority"),
            "Paper Vault V3 lifecycle authority",
        ),
        real_capital=_required_int(
            raw.get("real_capital"),
            "Paper Vault V3 lifecycle REAL_CAPITAL",
        ),
        schema_version=str(raw.get("schema_version", "")),
    )
    row_pairs = (
        ("event_identity", value.event_identity),
        ("vault_identity", value.vault_identity),
        ("event_at_ms", value.event_at_ms),
        ("action", value.action.value),
        ("previous_status", value.previous_status.value),
        ("new_status", value.new_status.value),
    )
    for key, expected in row_pairs:
        actual = row[key]
        if isinstance(expected, int):
            if int(actual) != expected:
                raise ValueError(f"Paper Vault V3 lifecycle row mismatch: {key}")
        elif str(actual) != expected:
            raise ValueError(f"Paper Vault V3 lifecycle row mismatch: {key}")
    return value


def _derive_status(
    constitution: PaperVaultV3Constitution,
    events: tuple[PaperVaultV3LifecycleEvent, ...],
) -> PaperVaultV3Status:
    status = PaperVaultV3Status.ACTIVE
    last_event_at_ms: int | None = None
    for event in events:
        if event.vault_identity != constitution.vault_identity:
            raise ValueError("Paper Vault V3 lifecycle vault mismatch")
        if event.event_at_ms < constitution.created_at_ms:
            raise ValueError("Paper Vault V3 lifecycle predates constitution")
        if last_event_at_ms is not None and event.event_at_ms <= last_event_at_ms:
            raise ValueError("Paper Vault V3 lifecycle ordering is invalid")
        if event.previous_status is not status:
            raise ValueError("Paper Vault V3 lifecycle chain is invalid")
        status = event.new_status
        last_event_at_ms = event.event_at_ms
    return status


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _require_store_schema(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table'
            """
        ).fetchall()
    }
    required = {
        "paper_vault_v3_meta",
        "paper_vault_v3_constitutions",
        "paper_vault_v3_lifecycle_events",
    }
    if not required.issubset(tables):
        raise ValueError("Paper Vault V3 store required table missing")
    row = connection.execute(
        """
        SELECT value FROM paper_vault_v3_meta
        WHERE key='schema_version'
        """
    ).fetchone()
    if row is None or str(row[0]) != PAPER_VAULT_V3_STORE_SCHEMA_VERSION:
        raise ValueError("Paper Vault V3 store schema mismatch")


def _required_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be array")
    return value


def _required_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be bool")
    return value


def _required_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be int")
    return value


def _require_fraction(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not value.is_finite() or value < Decimal(0) or value > Decimal(1):
        raise ValueError(f"{label} must be inside 0..1")


def _require_positive_money(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not value.is_finite() or value <= Decimal(0):
        raise ValueError(f"{label} must be positive and finite")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be SHA256")
