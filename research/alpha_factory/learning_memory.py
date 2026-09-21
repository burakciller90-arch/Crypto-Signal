"""Versioned append-only Learning Memory; evidence only, never production authority."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256

LEARNING_MEMORY_ENGINE_VERSION = "alpha-factory-learning-memory-v1/1"
LEARNING_MEMORY_SCHEMA_VERSION = "alpha-factory-learning-memory-schema-v1/1"
REAL_CAPITAL = 0


class LearningEvidenceClass(StrEnum):
    INTELLIGENCE_ENGINE = "intelligence_engine"
    ALPHA_FACTORY = "alpha_factory"
    PAPER_FORWARD = "paper_forward"
    POLICY_SHADOW = "policy_shadow"


class LearningOutcomeState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    MIXED = "mixed"
    ABSTENTION = "abstention"
    NO_EVIDENCE = "no_evidence"
    NOT_EVALUABLE = "not_evaluable"


class LearningUncertaintyState(StrEnum):
    NOT_ASSESSED = "not_assessed"
    EVIDENCE_LIMITED = "evidence_limited"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    STABLE_UNDER_ACCEPTED_TESTS = "stable_under_accepted_tests"


class LearningRelationKind(StrEnum):
    REDUNDANT = "redundant"
    OVERLAPPING = "overlapping"
    COMPLEMENTARY = "complementary"
    CONTRADICTORY = "contradictory"


class LearningChangeKind(StrEnum):
    MODEL_VERSION = "model_version"
    POLICY_VERSION = "policy_version"
    FEATURE_CONTRACT = "feature_contract"
    DATA_CONTRACT = "data_contract"


@dataclass(frozen=True, slots=True)
class LearningMemoryRecord:
    record_identity: str
    schema_version: str
    engine_version: str
    evidence_class: LearningEvidenceClass
    method_id: str
    method_version: str
    asset: str
    timeframe: str
    regime: str
    observed_from_ms: int
    observed_to_ms: int
    outcome_state: LearningOutcomeState
    evidence_identities: tuple[str, ...]
    uncertainty_state: LearningUncertaintyState
    uncertainty_evidence_identities: tuple[str, ...]
    gross_r_total: Decimal | None = None
    explicit_cost_r_total: Decimal | None = None
    net_r_total: Decimal | None = None
    production_contribution: int = 0
    production_authority: bool = False
    automatic_promotion: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.record_identity, "learning record identity")
        if self.schema_version != LEARNING_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported learning-memory record schema")
        if self.engine_version != LEARNING_MEMORY_ENGINE_VERSION:
            raise ValueError("unsupported learning-memory record engine")
        for value, label in (
            (self.method_id, "learning method id"),
            (self.method_version, "learning method version"),
            (self.asset, "learning asset"),
            (self.timeframe, "learning timeframe"),
            (self.regime, "learning regime"),
        ):
            _require_text(value, label)
        if self.observed_from_ms < 0:
            raise ValueError("learning observation start must be non-negative")
        if self.observed_to_ms < self.observed_from_ms:
            raise ValueError("learning observation end cannot predate start")
        _require_identity_tuple(
            self.evidence_identities,
            "learning evidence identity",
            require_non_empty=True,
        )
        _require_identity_tuple(
            self.uncertainty_evidence_identities,
            "learning uncertainty evidence identity",
            require_non_empty=False,
        )
        _validate_optional_metrics(
            gross_r_total=self.gross_r_total,
            explicit_cost_r_total=self.explicit_cost_r_total,
            net_r_total=self.net_r_total,
        )
        if self.production_contribution != 0:
            raise ValueError("Learning Memory production contribution must remain 0")
        if self.production_authority:
            raise ValueError("Learning Memory has no production authority")
        if self.automatic_promotion:
            raise ValueError("Learning Memory cannot automatically promote")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.record_identity != canonical_sha256(_record_payload(self)):
            raise ValueError("learning record identity mismatch")


@dataclass(frozen=True, slots=True)
class LearningRedundancyLink:
    link_identity: str
    schema_version: str
    engine_version: str
    left_record_identity: str
    right_record_identity: str
    relation: LearningRelationKind
    basis_evidence_identity: str
    production_authority: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.link_identity, "learning relation identity"),
            (self.left_record_identity, "learning left record identity"),
            (self.right_record_identity, "learning right record identity"),
            (self.basis_evidence_identity, "learning relation evidence identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != LEARNING_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported learning relation schema")
        if self.engine_version != LEARNING_MEMORY_ENGINE_VERSION:
            raise ValueError("unsupported learning relation engine")
        if self.left_record_identity >= self.right_record_identity:
            raise ValueError(
                "learning relation endpoints must be canonical and distinct"
            )
        if self.production_authority:
            raise ValueError("learning relations have no production authority")
        if self.link_identity != canonical_sha256(_redundancy_payload(self)):
            raise ValueError("learning relation identity mismatch")


@dataclass(frozen=True, slots=True)
class LearningLineageLink:
    link_identity: str
    schema_version: str
    engine_version: str
    predecessor_record_identity: str
    successor_record_identity: str
    change_kind: LearningChangeKind
    change_identity: str
    production_authority: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.link_identity, "learning lineage identity"),
            (
                self.predecessor_record_identity,
                "learning predecessor identity",
            ),
            (self.successor_record_identity, "learning successor identity"),
            (self.change_identity, "learning change identity"),
        ):
            _require_sha256(value, label)
        if self.schema_version != LEARNING_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported learning lineage schema")
        if self.engine_version != LEARNING_MEMORY_ENGINE_VERSION:
            raise ValueError("unsupported learning lineage engine")
        if self.predecessor_record_identity == self.successor_record_identity:
            raise ValueError("learning lineage requires distinct records")
        if self.production_authority:
            raise ValueError("learning lineage has no production authority")
        if self.link_identity != canonical_sha256(_lineage_payload(self)):
            raise ValueError("learning lineage identity mismatch")


@dataclass(frozen=True, slots=True)
class LearningMemorySnapshot:
    snapshot_identity: str
    schema_version: str
    engine_version: str
    built_at_ms: int
    parent_snapshot_identity: str | None
    record_identities: tuple[str, ...]
    redundancy_link_identities: tuple[str, ...]
    lineage_link_identities: tuple[str, ...]
    append_only: bool = True
    production_weighting_authority: bool = False
    champion_write_authority: bool = False
    deploy_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "learning snapshot identity")
        if self.parent_snapshot_identity is not None:
            _require_sha256(
                self.parent_snapshot_identity,
                "learning parent snapshot identity",
            )
            if self.parent_snapshot_identity == self.snapshot_identity:
                raise ValueError("learning snapshot cannot parent itself")
        if self.schema_version != LEARNING_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported learning snapshot schema")
        if self.engine_version != LEARNING_MEMORY_ENGINE_VERSION:
            raise ValueError("unsupported learning snapshot engine")
        if self.built_at_ms < 0:
            raise ValueError("learning snapshot time must be non-negative")
        _require_identity_tuple(
            self.record_identities,
            "learning snapshot record identity",
            require_non_empty=True,
        )
        _require_identity_tuple(
            self.redundancy_link_identities,
            "learning snapshot relation identity",
            require_non_empty=False,
        )
        _require_identity_tuple(
            self.lineage_link_identities,
            "learning snapshot lineage identity",
            require_non_empty=False,
        )
        if not self.append_only:
            raise ValueError("Learning Memory is append-only")
        if (
            self.production_weighting_authority
            or self.champion_write_authority
            or self.deploy_authority
        ):
            raise ValueError(
                "Learning Memory snapshot has no weighting/write/deploy authority"
            )
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("learning snapshot identity mismatch")


@dataclass(frozen=True, slots=True)
class LearningMemorySummary:
    summary_identity: str
    schema_version: str
    engine_version: str
    snapshot_identity: str
    outcome_counts: tuple[tuple[str, int], ...]
    method_version_counts: tuple[tuple[str, str, int], ...]
    context_counts: tuple[tuple[str, str, str, int], ...]
    winner_selected: bool = False
    production_weight_changed: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.summary_identity, "learning summary identity")
        _require_sha256(self.snapshot_identity, "learning snapshot identity")
        if self.schema_version != LEARNING_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported learning summary schema")
        if self.engine_version != LEARNING_MEMORY_ENGINE_VERSION:
            raise ValueError("unsupported learning summary engine")
        for _, count in self.outcome_counts:
            if count <= 0:
                raise ValueError("learning outcome counts must be positive")
        for _, _, count in self.method_version_counts:
            if count <= 0:
                raise ValueError("learning method counts must be positive")
        for _, _, _, count in self.context_counts:
            if count <= 0:
                raise ValueError("learning context counts must be positive")
        if self.winner_selected:
            raise ValueError("Learning Memory cannot select a winner")
        if self.production_weight_changed:
            raise ValueError("Learning Memory cannot change production weights")
        if self.summary_identity != canonical_sha256(_summary_payload(self)):
            raise ValueError("learning summary identity mismatch")


def build_learning_memory_record(
    *,
    evidence_class: LearningEvidenceClass,
    method_id: str,
    method_version: str,
    asset: str,
    timeframe: str,
    regime: str,
    observed_from_ms: int,
    observed_to_ms: int,
    outcome_state: LearningOutcomeState,
    evidence_identities: Sequence[str],
    uncertainty_state: LearningUncertaintyState,
    uncertainty_evidence_identities: Sequence[str] = (),
    gross_r_total: Decimal | None = None,
    explicit_cost_r_total: Decimal | None = None,
    net_r_total: Decimal | None = None,
) -> LearningMemoryRecord:
    normalized_evidence = tuple(sorted(set(evidence_identities)))
    normalized_uncertainty = tuple(
        sorted(set(uncertainty_evidence_identities))
    )
    payload = {
        "automatic_promotion": False,
        "asset": asset,
        "engine_version": LEARNING_MEMORY_ENGINE_VERSION,
        "evidence_class": evidence_class,
        "evidence_identities": normalized_evidence,
        "explicit_cost_r_total": explicit_cost_r_total,
        "gross_r_total": gross_r_total,
        "method_id": method_id,
        "method_version": method_version,
        "net_r_total": net_r_total,
        "observed_from_ms": observed_from_ms,
        "observed_to_ms": observed_to_ms,
        "outcome_state": outcome_state,
        "production_authority": False,
        "production_contribution": 0,
        "real_capital": REAL_CAPITAL,
        "regime": regime,
        "schema_version": LEARNING_MEMORY_SCHEMA_VERSION,
        "timeframe": timeframe,
        "uncertainty_evidence_identities": normalized_uncertainty,
        "uncertainty_state": uncertainty_state,
    }
    return LearningMemoryRecord(
        record_identity=canonical_sha256(payload),
        schema_version=LEARNING_MEMORY_SCHEMA_VERSION,
        engine_version=LEARNING_MEMORY_ENGINE_VERSION,
        evidence_class=evidence_class,
        method_id=method_id,
        method_version=method_version,
        asset=asset,
        timeframe=timeframe,
        regime=regime,
        observed_from_ms=observed_from_ms,
        observed_to_ms=observed_to_ms,
        outcome_state=outcome_state,
        evidence_identities=normalized_evidence,
        uncertainty_state=uncertainty_state,
        uncertainty_evidence_identities=normalized_uncertainty,
        gross_r_total=gross_r_total,
        explicit_cost_r_total=explicit_cost_r_total,
        net_r_total=net_r_total,
    )


def build_learning_redundancy_link(
    left_record_identity: str,
    right_record_identity: str,
    *,
    relation: LearningRelationKind,
    basis_evidence_identity: str,
) -> LearningRedundancyLink:
    left, right = sorted((left_record_identity, right_record_identity))
    if left == right:
        raise ValueError("learning relation requires distinct records")
    payload = {
        "basis_evidence_identity": basis_evidence_identity,
        "engine_version": LEARNING_MEMORY_ENGINE_VERSION,
        "left_record_identity": left,
        "production_authority": False,
        "relation": relation,
        "right_record_identity": right,
        "schema_version": LEARNING_MEMORY_SCHEMA_VERSION,
    }
    return LearningRedundancyLink(
        link_identity=canonical_sha256(payload),
        schema_version=LEARNING_MEMORY_SCHEMA_VERSION,
        engine_version=LEARNING_MEMORY_ENGINE_VERSION,
        left_record_identity=left,
        right_record_identity=right,
        relation=relation,
        basis_evidence_identity=basis_evidence_identity,
    )


def build_learning_lineage_link(
    predecessor_record_identity: str,
    successor_record_identity: str,
    *,
    change_kind: LearningChangeKind,
    change_identity: str,
) -> LearningLineageLink:
    payload = {
        "change_identity": change_identity,
        "change_kind": change_kind,
        "engine_version": LEARNING_MEMORY_ENGINE_VERSION,
        "predecessor_record_identity": predecessor_record_identity,
        "production_authority": False,
        "schema_version": LEARNING_MEMORY_SCHEMA_VERSION,
        "successor_record_identity": successor_record_identity,
    }
    return LearningLineageLink(
        link_identity=canonical_sha256(payload),
        schema_version=LEARNING_MEMORY_SCHEMA_VERSION,
        engine_version=LEARNING_MEMORY_ENGINE_VERSION,
        predecessor_record_identity=predecessor_record_identity,
        successor_record_identity=successor_record_identity,
        change_kind=change_kind,
        change_identity=change_identity,
    )


def build_learning_memory_snapshot(
    records: Sequence[LearningMemoryRecord],
    redundancy_links: Sequence[LearningRedundancyLink] = (),
    lineage_links: Sequence[LearningLineageLink] = (),
    *,
    built_at_ms: int,
    parent_snapshot_identity: str | None = None,
) -> LearningMemorySnapshot:
    ordered_records = tuple(sorted(records, key=lambda item: item.record_identity))
    ordered_relations = tuple(
        sorted(redundancy_links, key=lambda item: item.link_identity)
    )
    ordered_lineage = tuple(
        sorted(lineage_links, key=lambda item: item.link_identity)
    )
    record_ids = tuple(item.record_identity for item in ordered_records)
    if not record_ids:
        raise ValueError("Learning Memory snapshot requires records")
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("Learning Memory snapshot records must be unique")
    known = set(record_ids)
    for relation in ordered_relations:
        if (
            relation.left_record_identity not in known
            or relation.right_record_identity not in known
        ):
            raise ValueError("learning relation references missing record")
    for lineage in ordered_lineage:
        if (
            lineage.predecessor_record_identity not in known
            or lineage.successor_record_identity not in known
        ):
            raise ValueError("learning lineage references missing record")

    payload = {
        "append_only": True,
        "built_at_ms": built_at_ms,
        "champion_write_authority": False,
        "deploy_authority": False,
        "engine_version": LEARNING_MEMORY_ENGINE_VERSION,
        "lineage_link_identities": tuple(
            item.link_identity for item in ordered_lineage
        ),
        "parent_snapshot_identity": parent_snapshot_identity,
        "production_weighting_authority": False,
        "real_capital": REAL_CAPITAL,
        "record_identities": record_ids,
        "redundancy_link_identities": tuple(
            item.link_identity for item in ordered_relations
        ),
        "schema_version": LEARNING_MEMORY_SCHEMA_VERSION,
    }
    return LearningMemorySnapshot(
        snapshot_identity=canonical_sha256(payload),
        schema_version=LEARNING_MEMORY_SCHEMA_VERSION,
        engine_version=LEARNING_MEMORY_ENGINE_VERSION,
        built_at_ms=built_at_ms,
        parent_snapshot_identity=parent_snapshot_identity,
        record_identities=record_ids,
        redundancy_link_identities=tuple(
            item.link_identity for item in ordered_relations
        ),
        lineage_link_identities=tuple(
            item.link_identity for item in ordered_lineage
        ),
    )


def summarize_learning_memory(
    snapshot: LearningMemorySnapshot,
    records: Sequence[LearningMemoryRecord],
) -> LearningMemorySummary:
    by_identity = {item.record_identity: item for item in records}
    if set(by_identity) != set(snapshot.record_identities):
        raise ValueError("learning summary requires exact snapshot records")
    ordered = tuple(by_identity[item] for item in snapshot.record_identities)
    outcome_counter = Counter(item.outcome_state.value for item in ordered)
    method_counter = Counter(
        (item.method_id, item.method_version) for item in ordered
    )
    context_counter = Counter(
        (item.asset, item.timeframe, item.regime) for item in ordered
    )
    outcome_counts = tuple(sorted(outcome_counter.items()))
    method_counts = tuple(
        (method, version, count)
        for (method, version), count in sorted(method_counter.items())
    )
    context_counts = tuple(
        (asset, timeframe, regime, count)
        for (asset, timeframe, regime), count in sorted(context_counter.items())
    )
    payload = {
        "context_counts": context_counts,
        "engine_version": LEARNING_MEMORY_ENGINE_VERSION,
        "method_version_counts": method_counts,
        "outcome_counts": outcome_counts,
        "production_weight_changed": False,
        "schema_version": LEARNING_MEMORY_SCHEMA_VERSION,
        "snapshot_identity": snapshot.snapshot_identity,
        "winner_selected": False,
    }
    return LearningMemorySummary(
        summary_identity=canonical_sha256(payload),
        schema_version=LEARNING_MEMORY_SCHEMA_VERSION,
        engine_version=LEARNING_MEMORY_ENGINE_VERSION,
        snapshot_identity=snapshot.snapshot_identity,
        outcome_counts=outcome_counts,
        method_version_counts=method_counts,
        context_counts=context_counts,
    )


class LearningMemoryStore:
    """Append-only SQLite persistence for research Learning Memory."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS learning_memory_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS learning_memory_records (
                    record_identity TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS learning_memory_relations (
                    link_identity TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS learning_memory_lineage (
                    link_identity TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS learning_memory_snapshots (
                    snapshot_identity TEXT PRIMARY KEY,
                    built_at_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO learning_memory_meta(key, value)
                VALUES('schema_version', ?)
                """,
                (LEARNING_MEMORY_SCHEMA_VERSION,),
            )
            row = connection.execute(
                """
                SELECT value FROM learning_memory_meta
                WHERE key = 'schema_version'
                """
            ).fetchone()
            if row is None or row[0] != LEARNING_MEMORY_SCHEMA_VERSION:
                raise ValueError("Learning Memory store schema mismatch")

    def append_record(self, record: LearningMemoryRecord) -> None:
        self._append_payload(
            table="learning_memory_records",
            identity_column="record_identity",
            identity=record.record_identity,
            payload=canonical_json(_record_payload(record)),
        )

    def append_redundancy_link(self, link: LearningRedundancyLink) -> None:
        self._require_records(
            (link.left_record_identity, link.right_record_identity)
        )
        self._append_payload(
            table="learning_memory_relations",
            identity_column="link_identity",
            identity=link.link_identity,
            payload=canonical_json(_redundancy_payload(link)),
        )

    def append_lineage_link(self, link: LearningLineageLink) -> None:
        self._require_records(
            (
                link.predecessor_record_identity,
                link.successor_record_identity,
            )
        )
        self._append_payload(
            table="learning_memory_lineage",
            identity_column="link_identity",
            identity=link.link_identity,
            payload=canonical_json(_lineage_payload(link)),
        )

    def capture_snapshot(
        self,
        *,
        built_at_ms: int,
        parent_snapshot_identity: str | None = None,
    ) -> LearningMemorySnapshot:
        records = self.list_records()
        relations = self.list_redundancy_links()
        lineage = self.list_lineage_links()
        if parent_snapshot_identity is not None:
            self.load_snapshot(parent_snapshot_identity)
        snapshot = build_learning_memory_snapshot(
            records,
            relations,
            lineage,
            built_at_ms=built_at_ms,
            parent_snapshot_identity=parent_snapshot_identity,
        )
        payload = canonical_json(_snapshot_payload(snapshot))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO learning_memory_snapshots(
                    snapshot_identity, built_at_ms, payload
                ) VALUES(?, ?, ?)
                """,
                (snapshot.snapshot_identity, snapshot.built_at_ms, payload),
            )
            row = connection.execute(
                """
                SELECT payload FROM learning_memory_snapshots
                WHERE snapshot_identity = ?
                """,
                (snapshot.snapshot_identity,),
            ).fetchone()
            if row is None or row[0] != payload:
                raise ValueError("Learning Memory snapshot identity collision")
        return snapshot

    def list_records(self) -> tuple[LearningMemoryRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM learning_memory_records
                ORDER BY record_identity
                """
            ).fetchall()
        return tuple(_record_from_json(str(row[0])) for row in rows)

    def list_redundancy_links(self) -> tuple[LearningRedundancyLink, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM learning_memory_relations
                ORDER BY link_identity
                """
            ).fetchall()
        return tuple(_redundancy_from_json(str(row[0])) for row in rows)

    def list_lineage_links(self) -> tuple[LearningLineageLink, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM learning_memory_lineage
                ORDER BY link_identity
                """
            ).fetchall()
        return tuple(_lineage_from_json(str(row[0])) for row in rows)

    def load_snapshot(self, snapshot_identity: str) -> LearningMemorySnapshot:
        _require_sha256(snapshot_identity, "learning snapshot identity")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM learning_memory_snapshots
                WHERE snapshot_identity = ?
                """,
                (snapshot_identity,),
            ).fetchone()
        if row is None:
            raise KeyError(snapshot_identity)
        return _snapshot_from_json(str(row[0]))

    def _append_payload(
        self,
        *,
        table: str,
        identity_column: str,
        identity: str,
        payload: str,
    ) -> None:
        allowed = {
            ("learning_memory_records", "record_identity"),
            ("learning_memory_relations", "link_identity"),
            ("learning_memory_lineage", "link_identity"),
        }
        if (table, identity_column) not in allowed:
            raise ValueError("unsupported Learning Memory append target")
        with self._connect() as connection:
            connection.execute(
                f"INSERT OR IGNORE INTO {table}({identity_column}, payload) "
                "VALUES(?, ?)",
                (identity, payload),
            )
            row = connection.execute(
                f"SELECT payload FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if row is None or row[0] != payload:
                raise ValueError("Learning Memory identity collision")

    def _require_records(self, identities: Sequence[str]) -> None:
        with self._connect() as connection:
            for identity in identities:
                row = connection.execute(
                    """
                    SELECT 1 FROM learning_memory_records
                    WHERE record_identity = ?
                    """,
                    (identity,),
                ).fetchone()
                if row is None:
                    raise ValueError("Learning Memory link references missing record")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _record_payload(record: LearningMemoryRecord) -> dict[str, object]:
    return {
        "automatic_promotion": record.automatic_promotion,
        "asset": record.asset,
        "engine_version": record.engine_version,
        "evidence_class": record.evidence_class,
        "evidence_identities": record.evidence_identities,
        "explicit_cost_r_total": record.explicit_cost_r_total,
        "gross_r_total": record.gross_r_total,
        "method_id": record.method_id,
        "method_version": record.method_version,
        "net_r_total": record.net_r_total,
        "observed_from_ms": record.observed_from_ms,
        "observed_to_ms": record.observed_to_ms,
        "outcome_state": record.outcome_state,
        "production_authority": record.production_authority,
        "production_contribution": record.production_contribution,
        "real_capital": record.real_capital,
        "regime": record.regime,
        "schema_version": record.schema_version,
        "timeframe": record.timeframe,
        "uncertainty_evidence_identities": record.uncertainty_evidence_identities,
        "uncertainty_state": record.uncertainty_state,
    }


def _redundancy_payload(link: LearningRedundancyLink) -> dict[str, object]:
    return {
        "basis_evidence_identity": link.basis_evidence_identity,
        "engine_version": link.engine_version,
        "left_record_identity": link.left_record_identity,
        "production_authority": link.production_authority,
        "relation": link.relation,
        "right_record_identity": link.right_record_identity,
        "schema_version": link.schema_version,
    }


def _lineage_payload(link: LearningLineageLink) -> dict[str, object]:
    return {
        "change_identity": link.change_identity,
        "change_kind": link.change_kind,
        "engine_version": link.engine_version,
        "predecessor_record_identity": link.predecessor_record_identity,
        "production_authority": link.production_authority,
        "schema_version": link.schema_version,
        "successor_record_identity": link.successor_record_identity,
    }


def _snapshot_payload(snapshot: LearningMemorySnapshot) -> dict[str, object]:
    return {
        "append_only": snapshot.append_only,
        "built_at_ms": snapshot.built_at_ms,
        "champion_write_authority": snapshot.champion_write_authority,
        "deploy_authority": snapshot.deploy_authority,
        "engine_version": snapshot.engine_version,
        "lineage_link_identities": snapshot.lineage_link_identities,
        "parent_snapshot_identity": snapshot.parent_snapshot_identity,
        "production_weighting_authority": (
            snapshot.production_weighting_authority
        ),
        "real_capital": snapshot.real_capital,
        "record_identities": snapshot.record_identities,
        "redundancy_link_identities": snapshot.redundancy_link_identities,
        "schema_version": snapshot.schema_version,
    }


def _summary_payload(summary: LearningMemorySummary) -> dict[str, object]:
    return {
        "context_counts": summary.context_counts,
        "engine_version": summary.engine_version,
        "method_version_counts": summary.method_version_counts,
        "outcome_counts": summary.outcome_counts,
        "production_weight_changed": summary.production_weight_changed,
        "schema_version": summary.schema_version,
        "snapshot_identity": summary.snapshot_identity,
        "winner_selected": summary.winner_selected,
    }


def _record_from_json(payload: str) -> LearningMemoryRecord:
    data = _load_object(payload)
    return LearningMemoryRecord(
        record_identity=canonical_sha256(data),
        schema_version=_string(data, "schema_version"),
        engine_version=_string(data, "engine_version"),
        evidence_class=LearningEvidenceClass(_string(data, "evidence_class")),
        method_id=_string(data, "method_id"),
        method_version=_string(data, "method_version"),
        asset=_string(data, "asset"),
        timeframe=_string(data, "timeframe"),
        regime=_string(data, "regime"),
        observed_from_ms=_integer(data, "observed_from_ms"),
        observed_to_ms=_integer(data, "observed_to_ms"),
        outcome_state=LearningOutcomeState(_string(data, "outcome_state")),
        evidence_identities=_string_tuple(data, "evidence_identities"),
        uncertainty_state=LearningUncertaintyState(
            _string(data, "uncertainty_state")
        ),
        uncertainty_evidence_identities=_string_tuple(
            data,
            "uncertainty_evidence_identities",
        ),
        gross_r_total=_optional_decimal(data.get("gross_r_total")),
        explicit_cost_r_total=_optional_decimal(
            data.get("explicit_cost_r_total")
        ),
        net_r_total=_optional_decimal(data.get("net_r_total")),
        production_contribution=_integer(data, "production_contribution"),
        production_authority=_boolean(data, "production_authority"),
        automatic_promotion=_boolean(data, "automatic_promotion"),
        real_capital=_integer(data, "real_capital"),
    )


def _redundancy_from_json(payload: str) -> LearningRedundancyLink:
    data = _load_object(payload)
    return LearningRedundancyLink(
        link_identity=canonical_sha256(data),
        schema_version=_string(data, "schema_version"),
        engine_version=_string(data, "engine_version"),
        left_record_identity=_string(data, "left_record_identity"),
        right_record_identity=_string(data, "right_record_identity"),
        relation=LearningRelationKind(_string(data, "relation")),
        basis_evidence_identity=_string(data, "basis_evidence_identity"),
        production_authority=_boolean(data, "production_authority"),
    )


def _lineage_from_json(payload: str) -> LearningLineageLink:
    data = _load_object(payload)
    return LearningLineageLink(
        link_identity=canonical_sha256(data),
        schema_version=_string(data, "schema_version"),
        engine_version=_string(data, "engine_version"),
        predecessor_record_identity=_string(
            data,
            "predecessor_record_identity",
        ),
        successor_record_identity=_string(
            data,
            "successor_record_identity",
        ),
        change_kind=LearningChangeKind(_string(data, "change_kind")),
        change_identity=_string(data, "change_identity"),
        production_authority=_boolean(data, "production_authority"),
    )


def _snapshot_from_json(payload: str) -> LearningMemorySnapshot:
    data = _load_object(payload)
    return LearningMemorySnapshot(
        snapshot_identity=canonical_sha256(data),
        schema_version=_string(data, "schema_version"),
        engine_version=_string(data, "engine_version"),
        built_at_ms=_integer(data, "built_at_ms"),
        parent_snapshot_identity=_optional_string(
            data.get("parent_snapshot_identity")
        ),
        record_identities=_string_tuple(data, "record_identities"),
        redundancy_link_identities=_string_tuple(
            data,
            "redundancy_link_identities",
        ),
        lineage_link_identities=_string_tuple(
            data,
            "lineage_link_identities",
        ),
        append_only=_boolean(data, "append_only"),
        production_weighting_authority=_boolean(
            data,
            "production_weighting_authority",
        ),
        champion_write_authority=_boolean(
            data,
            "champion_write_authority",
        ),
        deploy_authority=_boolean(data, "deploy_authority"),
        real_capital=_integer(data, "real_capital"),
    )


def _load_object(payload: str) -> dict[str, Any]:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise TypeError("Learning Memory payload must be an object")
    return value


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise TypeError(f"Learning Memory {key} must be string")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Learning Memory optional value must be string")
    return value


def _integer(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Learning Memory {key} must be integer")
    return value


def _boolean(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Learning Memory {key} must be boolean")
    return value


def _string_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"Learning Memory {key} must be list[str]")
    return tuple(value)


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Learning Memory Decimal must be canonical string")
    return Decimal(value)


def _validate_optional_metrics(
    *,
    gross_r_total: Decimal | None,
    explicit_cost_r_total: Decimal | None,
    net_r_total: Decimal | None,
) -> None:
    metrics = (gross_r_total, explicit_cost_r_total, net_r_total)
    present = tuple(item is not None for item in metrics)
    if any(present) and not all(present):
        raise ValueError("learning R metrics must be all present or all absent")
    if not all(present):
        return
    assert gross_r_total is not None
    assert explicit_cost_r_total is not None
    assert net_r_total is not None
    if explicit_cost_r_total < 0:
        raise ValueError("learning explicit cost cannot be negative")
    if net_r_total != gross_r_total - explicit_cost_r_total:
        raise ValueError("learning net-R accounting mismatch")


def _require_identity_tuple(
    identities: tuple[str, ...],
    label: str,
    *,
    require_non_empty: bool,
) -> None:
    if require_non_empty and not identities:
        raise ValueError(f"{label} cannot be empty")
    if tuple(sorted(set(identities))) != identities:
        raise ValueError(f"{label} values must be sorted and unique")
    for identity in identities:
        _require_sha256(identity, label)


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be sha256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be sha256 hex") from exc


def _require_text(value: str, label: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be non-empty trimmed text")
