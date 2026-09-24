"""Append-only pre-issuance receipt for WC2 untouched-forward cycles.

The receipt is written before canonical R20 persistence. It freezes only the
already accepted PIT inputs and exact caller-owned runtime parameters required
to finish the same decision after a crash. It is not permission to backfill an
unprepared historical signal.
REAL_CAPITAL=0.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_signal.evaluation.live_untouched_forward_operational import (
    WC2LiveSourceInputs,
    adapt_same_cycle_legacy_bundle,
)
from crypto_signal.evaluation.untouched_forward_collection_protocol import (
    WC2CollectionProtocol,
)
from crypto_signal.evaluation.untouched_forward_policy import (
    WC2UntouchedForwardPolicy,
)
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyEvidence,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.intelligence.family_proof_adapters import (
    AcceptedFamilyAdapterBundle,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.ledger.bundle import DecisionFreezeBundle, verify_bundle_identity
from crypto_signal.ledger.deserialization import (
    parse_signal_decision,
    require_mapping,
)
from crypto_signal.ledger.serialization import (
    canonical_json,
    canonical_sha256,
    sha256_text,
)
from crypto_signal.paper.epoch2_accounting import Epoch2ActivationRecord
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.position_sizing_intelligence import PositionSizingPolicy
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
)
from crypto_signal.signals.models import SignalDecision, SignalDirection, SignalState

WC2_PREPARED_RECEIPT_SCHEMA_VERSION = "wc2-prepared-cycle-receipt-v1/2"
WC2_PREPARED_RECEIPT_ENGINE_VERSION = "wc2-prepared-cycle-receipt-v1/2"
WC2_PREPARED_RECEIPT_SUFFIX = ".wc2-prepared.sqlite3"
REAL_CAPITAL = 0

_RECORD_TABLE = "wc2_prepared_cycle_receipts"
_META_TABLE = "wc2_prepared_cycle_meta"
_ALLOWED_TABLES = {_RECORD_TABLE, _META_TABLE}


@dataclass(frozen=True, slots=True)
class WC2PreparedCycleReceipt:
    receipt_identity: str
    policy_identity: str
    activation_identity: str
    collection_protocol_identity: str
    signal: SignalDecision
    source_inputs: WC2LiveSourceInputs
    source_cutoff_open_time_ms: int
    source_frozen_at_ms: int
    issued_at_ms: int
    maximum_issuance_delay_ms: int
    horizon_bars: int
    target_label: str
    base_asset: str
    sizing_policy: PositionSizingPolicy | None
    vault_id: PaperVaultId
    capital_assessed_at_ms: int
    sized_at_ms: int
    previewed_at_ms: int
    indexed_at_ms: int
    schema_version: str = WC2_PREPARED_RECEIPT_SCHEMA_VERSION
    engine_version: str = WC2_PREPARED_RECEIPT_ENGINE_VERSION
    historical_backfill_authority: bool = False
    canonical_epoch2_write_authority: bool = False
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_identity, "WC2 prepared receipt"),
            (self.policy_identity, "WC2 prepared policy"),
            (self.activation_identity, "WC2 prepared activation"),
            (
                self.collection_protocol_identity,
                "WC2 prepared collection protocol",
            ),
        ):
            _require_sha256(value, label)
        if self.source_inputs.bundle_identity == "":
            raise ValueError("WC2 prepared source bundle missing")
        if self.signal.state not in {SignalState.WATCH, SignalState.ACTIVE}:
            raise ValueError("WC2 prepared receipt requires WATCH or ACTIVE")
        if self.signal.direction is SignalDirection.NONE or self.signal.geometry is None:
            raise ValueError("WC2 prepared receipt requires directional geometry")
        if self.source_cutoff_open_time_ms < 0:
            raise ValueError("WC2 prepared source cutoff cannot be negative")
        if self.source_frozen_at_ms < self.signal.as_of_ms:
            raise ValueError("WC2 prepared freeze predates signal as-of")
        if self.issued_at_ms < self.source_frozen_at_ms:
            raise ValueError("WC2 prepared issuance predates source freeze")
        if self.maximum_issuance_delay_ms <= 0:
            raise ValueError("WC2 prepared issuance delay must be positive")
        if (
            self.issued_at_ms - self.source_frozen_at_ms
            > self.maximum_issuance_delay_ms
        ):
            raise ValueError("WC2 prepared source exceeded issuance delay")
        if self.horizon_bars <= 0:
            raise ValueError("WC2 prepared horizon must be positive")
        if not self.target_label.strip():
            raise ValueError("WC2 prepared target label must be non-empty")
        if self.target_label not in {
            item.label for item in self.signal.geometry.targets
        }:
            raise ValueError("WC2 prepared target is not frozen geometry")
        if not self.base_asset or self.base_asset != self.base_asset.upper():
            raise ValueError("WC2 prepared base asset must be uppercase")
        if not self.signal.symbol.startswith(self.base_asset):
            raise ValueError("WC2 prepared base asset/signal mismatch")
        if self.source_inputs.geometry_family.asset != self.signal.symbol:
            raise ValueError("WC2 prepared geometry/signal market mismatch")
        if self.source_inputs.geometry_family.as_of_ms != self.signal.as_of_ms:
            raise ValueError("WC2 prepared geometry/signal PIT mismatch")
        if self.source_inputs.event_context.asset != self.base_asset:
            raise ValueError("WC2 prepared event/base asset mismatch")
        if self.source_inputs.event_context.as_of_ms != self.signal.as_of_ms:
            raise ValueError("WC2 prepared event/signal PIT mismatch")
        if self.vault_id is not PaperVaultId.CORE:
            raise ValueError("WC2 prepared Slice1 vault must be CORE")
        if self.sizing_policy is not None:
            if self.sizing_policy.production_authority:
                raise ValueError(
                    "WC2 prepared sizing policy has production authority"
                )
            if self.sizing_policy.real_capital != REAL_CAPITAL:
                raise ValueError(
                    "WC2 prepared sizing policy REAL_CAPITAL mismatch"
                )
        if not (
            self.issued_at_ms
            <= self.capital_assessed_at_ms
            <= self.sized_at_ms
            <= self.previewed_at_ms
            <= self.indexed_at_ms
        ):
            raise ValueError("WC2 prepared paper timestamps are not monotonic")
        if (
            self.historical_backfill_authority
            or self.canonical_epoch2_write_authority
            or self.production_authority
            or self.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 prepared receipt cannot grant authority")
        if self.schema_version != WC2_PREPARED_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported WC2 prepared receipt schema")
        if self.engine_version != WC2_PREPARED_RECEIPT_ENGINE_VERSION:
            raise ValueError("unsupported WC2 prepared receipt engine")
        if self.receipt_identity != canonical_sha256(_receipt_payload(self)):
            raise ValueError("WC2 prepared receipt identity mismatch")


def build_wc2_prepared_cycle_receipt(
    bundle: DecisionFreezeBundle,
    *,
    policy: WC2UntouchedForwardPolicy,
    activation: Epoch2ActivationRecord,
    protocol: WC2CollectionProtocol,
    sizing_policy: PositionSizingPolicy | None,
    source_frozen_at_ms: int,
    issued_at_ms: int,
    base_asset: str,
    capital_assessed_at_ms: int,
    sized_at_ms: int,
    previewed_at_ms: int,
    indexed_at_ms: int,
) -> WC2PreparedCycleReceipt:
    """Freeze exact pre-outcome inputs before any canonical R20 write."""
    verify_bundle_identity(bundle)
    signal = bundle.signal_decision
    if protocol.review_policy_identity != policy.policy_identity:
        raise ValueError("WC2 prepared protocol/policy identity mismatch")
    if protocol.epoch2_activation_identity != activation.activation_identity:
        raise ValueError("WC2 prepared protocol/Epoch2 identity mismatch")
    context_identity = (
        signal.exchange.value,
        signal.market_type.value,
        signal.symbol,
        signal.timeframe,
    )
    if context_identity not in protocol.coverage_context_identities:
        raise ValueError("WC2 prepared source context is outside protocol")
    if source_frozen_at_ms < protocol.collection_start_ms:
        raise ValueError("WC2 prepared source predates protocol collection")
    if issued_at_ms < protocol.collection_start_ms:
        raise ValueError("WC2 prepared issuance predates protocol collection")
    if activation.activated_at_ms > issued_at_ms:
        raise ValueError("WC2 Epoch2 activation must predate prepared issuance")
    maximum_issuance_delay_ms = protocol.maximum_issuance_delay_ms
    horizon_bars = protocol.horizon_bars_for(signal.timeframe)
    inputs = adapt_same_cycle_legacy_bundle(bundle, base_asset=base_asset)
    if signal.geometry is None or not signal.geometry.targets:
        raise ValueError("WC2 prepared cycle requires frozen target")
    target_label = signal.geometry.targets[0].label

    values: dict[str, object] = {
        "activation_identity": activation.activation_identity,
        "base_asset": base_asset,
        "canonical_epoch2_write_authority": False,
        "capital_assessed_at_ms": capital_assessed_at_ms,
        "collection_protocol_identity": protocol.protocol_identity,
        "engine_version": WC2_PREPARED_RECEIPT_ENGINE_VERSION,
        "historical_backfill_authority": False,
        "horizon_bars": horizon_bars,
        "indexed_at_ms": indexed_at_ms,
        "issued_at_ms": issued_at_ms,
        "maximum_issuance_delay_ms": maximum_issuance_delay_ms,
        "policy_identity": policy.policy_identity,
        "previewed_at_ms": previewed_at_ms,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
        "schema_version": WC2_PREPARED_RECEIPT_SCHEMA_VERSION,
        "signal": signal,
        "sized_at_ms": sized_at_ms,
        "sizing_policy": sizing_policy,
        "source_cutoff_open_time_ms": bundle.source_cutoff_open_time_ms,
        "source_frozen_at_ms": source_frozen_at_ms,
        "source_inputs": inputs,
        "target_label": target_label,
        "vault_id": PaperVaultId.CORE,
    }
    return WC2PreparedCycleReceipt(
        receipt_identity=canonical_sha256(values),
        policy_identity=policy.policy_identity,
        activation_identity=activation.activation_identity,
        collection_protocol_identity=protocol.protocol_identity,
        signal=signal,
        source_inputs=inputs,
        source_cutoff_open_time_ms=bundle.source_cutoff_open_time_ms,
        source_frozen_at_ms=source_frozen_at_ms,
        issued_at_ms=issued_at_ms,
        maximum_issuance_delay_ms=maximum_issuance_delay_ms,
        horizon_bars=horizon_bars,
        target_label=target_label,
        base_asset=base_asset,
        sizing_policy=sizing_policy,
        vault_id=PaperVaultId.CORE,
        capital_assessed_at_ms=capital_assessed_at_ms,
        sized_at_ms=sized_at_ms,
        previewed_at_ms=previewed_at_ms,
        indexed_at_ms=indexed_at_ms,
    )


class WC2PreparedCycleJournal:
    """Append-only durable proof that a WC2 cycle was prepared pre-outcome."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not str(path).endswith(WC2_PREPARED_RECEIPT_SUFFIX):
            raise ValueError(
                "WC2 prepared journal path must end with "
                f"{WC2_PREPARED_RECEIPT_SUFFIX}"
            )

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            }
            unexpected = existing - _ALLOWED_TABLES
            if unexpected:
                raise ValueError(
                    "WC2 prepared journal refuses database with non-WC2 tables"
                )
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )"""
            )
            db.execute(
                f"""CREATE TABLE IF NOT EXISTS {_RECORD_TABLE} (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_identity TEXT UNIQUE NOT NULL,
                    policy_identity TEXT NOT NULL,
                    activation_identity TEXT NOT NULL,
                    collection_protocol_identity TEXT NOT NULL,
                    signal_freeze_identity TEXT UNIQUE NOT NULL,
                    bundle_identity TEXT UNIQUE NOT NULL,
                    source_cutoff_open_time_ms INTEGER NOT NULL,
                    issued_at_ms INTEGER NOT NULL,
                    previewed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            expected = {
                "engine_version": WC2_PREPARED_RECEIPT_ENGINE_VERSION,
                "real_capital": str(REAL_CAPITAL),
                "schema_version": WC2_PREPARED_RECEIPT_SCHEMA_VERSION,
                "semantic": "preoutcome_recovery_authorization_not_backfill_authority",
            }
            for key, value in expected.items():
                row = db.execute(
                    f"SELECT value FROM {_META_TABLE} WHERE key=?",
                    (key,),
                ).fetchone()
                if row is None:
                    db.execute(
                        f"INSERT INTO {_META_TABLE}(key,value) VALUES (?,?)",
                        (key, value),
                    )
                elif str(row[0]) != value:
                    raise ValueError("WC2 prepared journal metadata mismatch")
            for table in (_META_TABLE, _RECORD_TABLE):
                for action in ("UPDATE", "DELETE"):
                    db.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        {table}_immutable_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN
                            SELECT RAISE(
                                ABORT,
                                'immutable WC2 prepared cycle journal'
                            );
                        END"""
                    )

    def append(self, receipt: WC2PreparedCycleReceipt) -> bool:
        self.initialize()
        payload = canonical_json(_receipt_payload(receipt))
        if sha256_text(payload) != receipt.receipt_identity:
            raise ValueError("WC2 prepared receipt payload digest mismatch")
        with closing(sqlite3.connect(self.path)) as db, db:
            existing = db.execute(
                f"""SELECT receipt_identity, payload_json
                FROM {_RECORD_TABLE}
                WHERE signal_freeze_identity=?
                   OR bundle_identity=?
                   OR receipt_identity=?""",
                (
                    receipt.signal.freeze_identity,
                    receipt.source_inputs.bundle_identity,
                    receipt.receipt_identity,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) == receipt.receipt_identity
                    and str(existing[1]) == payload
                ):
                    return False
                raise ValueError("WC2 prepared receipt identity conflict")
            db.execute(
                f"""INSERT INTO {_RECORD_TABLE}(
                    receipt_identity,
                    policy_identity,
                    activation_identity,
                    collection_protocol_identity,
                    signal_freeze_identity,
                    bundle_identity,
                    source_cutoff_open_time_ms,
                    issued_at_ms,
                    previewed_at_ms,
                    payload_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    receipt.receipt_identity,
                    receipt.policy_identity,
                    receipt.activation_identity,
                    receipt.collection_protocol_identity,
                    receipt.signal.freeze_identity,
                    receipt.source_inputs.bundle_identity,
                    receipt.source_cutoff_open_time_ms,
                    receipt.issued_at_ms,
                    receipt.previewed_at_ms,
                    payload,
                ),
            )
        return True

    def read_for_signal(
        self,
        signal_freeze_identity: str,
    ) -> WC2PreparedCycleReceipt | None:
        _require_sha256(signal_freeze_identity, "WC2 prepared signal lookup")
        if not self.path.is_file():
            return None
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                f"""SELECT payload_json FROM {_RECORD_TABLE}
                WHERE signal_freeze_identity=?""",
                (signal_freeze_identity,),
            ).fetchone()
        return None if row is None else _receipt_from_json(str(row[0]))

    def verify_read_only(self) -> int:
        if not self.path.is_file():
            raise ValueError("WC2 prepared journal missing")
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            unexpected = {
                str(row[0])
                for row in db.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'"""
                ).fetchall()
            } - _ALLOWED_TABLES
            if unexpected:
                raise ValueError(
                    "WC2 prepared journal contains non-WC2 tables"
                )
            quick = db.execute("PRAGMA quick_check").fetchone()
            if quick is None or str(quick[0]).lower() != "ok":
                raise ValueError("WC2 prepared journal quick_check failed")
            rows = db.execute(
                f"""SELECT receipt_identity, policy_identity,
                activation_identity, collection_protocol_identity,
                signal_freeze_identity, bundle_identity,
                source_cutoff_open_time_ms, issued_at_ms,
                previewed_at_ms, payload_json
                FROM {_RECORD_TABLE}
                ORDER BY sequence_id"""
            ).fetchall()
            for row in rows:
                receipt = _receipt_from_json(str(row[9]))
                expected = (
                    receipt.receipt_identity,
                    receipt.policy_identity,
                    receipt.activation_identity,
                    receipt.collection_protocol_identity,
                    receipt.signal.freeze_identity,
                    receipt.source_inputs.bundle_identity,
                    receipt.source_cutoff_open_time_ms,
                    receipt.issued_at_ms,
                    receipt.previewed_at_ms,
                )
                actual = (
                    str(row[0]),
                    str(row[1]),
                    str(row[2]),
                    str(row[3]),
                    str(row[4]),
                    str(row[5]),
                    int(row[6]),
                    int(row[7]),
                    int(row[8]),
                )
                if actual != expected:
                    raise ValueError("WC2 prepared journal row/payload mismatch")
        return len(rows)


def _receipt_payload(receipt: WC2PreparedCycleReceipt) -> dict[str, object]:
    return {
        "activation_identity": receipt.activation_identity,
        "base_asset": receipt.base_asset,
        "canonical_epoch2_write_authority": (
            receipt.canonical_epoch2_write_authority
        ),
        "capital_assessed_at_ms": receipt.capital_assessed_at_ms,
        "collection_protocol_identity": receipt.collection_protocol_identity,
        "engine_version": receipt.engine_version,
        "historical_backfill_authority": receipt.historical_backfill_authority,
        "horizon_bars": receipt.horizon_bars,
        "indexed_at_ms": receipt.indexed_at_ms,
        "issued_at_ms": receipt.issued_at_ms,
        "maximum_issuance_delay_ms": receipt.maximum_issuance_delay_ms,
        "policy_identity": receipt.policy_identity,
        "previewed_at_ms": receipt.previewed_at_ms,
        "production_authority": receipt.production_authority,
        "real_capital": receipt.real_capital,
        "schema_version": receipt.schema_version,
        "signal": receipt.signal,
        "sized_at_ms": receipt.sized_at_ms,
        "sizing_policy": receipt.sizing_policy,
        "source_cutoff_open_time_ms": receipt.source_cutoff_open_time_ms,
        "source_frozen_at_ms": receipt.source_frozen_at_ms,
        "source_inputs": receipt.source_inputs,
        "target_label": receipt.target_label,
        "vault_id": receipt.vault_id,
    }


def _receipt_from_json(payload_json: str) -> WC2PreparedCycleReceipt:
    raw = json.loads(payload_json)
    root = require_mapping(raw, "WC2 prepared receipt")
    signal = parse_signal_decision(root.get("signal"))
    source_inputs = _parse_source_inputs(root.get("source_inputs"))
    sizing_policy = _parse_optional_sizing_policy(
        root.get("sizing_policy")
    )
    receipt = WC2PreparedCycleReceipt(
        receipt_identity=canonical_sha256(root),
        policy_identity=_text(root, "policy_identity"),
        activation_identity=_text(root, "activation_identity"),
        collection_protocol_identity=_text(
            root,
            "collection_protocol_identity",
        ),
        signal=signal,
        source_inputs=source_inputs,
        source_cutoff_open_time_ms=_integer(
            root,
            "source_cutoff_open_time_ms",
        ),
        source_frozen_at_ms=_integer(root, "source_frozen_at_ms"),
        issued_at_ms=_integer(root, "issued_at_ms"),
        maximum_issuance_delay_ms=_integer(
            root,
            "maximum_issuance_delay_ms",
        ),
        horizon_bars=_integer(root, "horizon_bars"),
        target_label=_text(root, "target_label"),
        base_asset=_text(root, "base_asset"),
        sizing_policy=sizing_policy,
        vault_id=PaperVaultId(_text(root, "vault_id")),
        capital_assessed_at_ms=_integer(root, "capital_assessed_at_ms"),
        sized_at_ms=_integer(root, "sized_at_ms"),
        previewed_at_ms=_integer(root, "previewed_at_ms"),
        indexed_at_ms=_integer(root, "indexed_at_ms"),
        schema_version=_text(root, "schema_version"),
        engine_version=_text(root, "engine_version"),
        historical_backfill_authority=bool(
            root.get("historical_backfill_authority")
        ),
        canonical_epoch2_write_authority=bool(
            root.get("canonical_epoch2_write_authority")
        ),
        production_authority=bool(root.get("production_authority")),
        real_capital=_integer(root, "real_capital"),
    )
    if sha256_text(payload_json) != receipt.receipt_identity:
        raise ValueError("WC2 prepared receipt persisted digest mismatch")
    return receipt


def _parse_source_inputs(value: Any) -> WC2LiveSourceInputs:
    raw = require_mapping(value, "WC2 prepared source inputs")
    geometry = _parse_family(raw.get("geometry_family"))
    geometry_proofs = tuple(
        _parse_proof(item)
        for item in _list(raw, "geometry_proof_slices")
    )
    accepted_raw = require_mapping(
        raw.get("accepted_m2_m5"),
        "WC2 accepted M2-M5",
    )
    accepted = AcceptedFamilyAdapterBundle(
        families=tuple(
            _parse_family(item)
            for item in _list(accepted_raw, "families")
        ),
        proof_slices=tuple(
            _parse_proof(item)
            for item in _list(accepted_raw, "proof_slices")
        ),
        production_authority=bool(
            accepted_raw.get("production_authority")
        ),
        real_capital=_integer(accepted_raw, "real_capital"),
    )
    return WC2LiveSourceInputs(
        bundle_identity=_text(raw, "bundle_identity"),
        consumed_candles_identity=_text(raw, "consumed_candles_identity"),
        geometry_family=geometry,
        geometry_proof_slices=geometry_proofs,
        accepted_m2_m5=accepted,
        event_context=_parse_event(raw.get("event_context")),
        regime=_text(raw, "regime"),
        production_authority=bool(raw.get("production_authority")),
        real_capital=_integer(raw, "real_capital"),
    )


def _parse_family(value: Any) -> ConfluenceFamilyEvidence:
    raw = require_mapping(value, "WC2 family evidence")
    return ConfluenceFamilyEvidence(
        evidence_identity=_text(raw, "evidence_identity"),
        schema_version=_text(raw, "schema_version"),
        engine_version=_text(raw, "engine_version"),
        family=ConfluenceFamily(_text(raw, "family")),
        asset=_text(raw, "asset"),
        timeframe=_text(raw, "timeframe"),
        regime=_text(raw, "regime"),
        as_of_ms=_integer(raw, "as_of_ms"),
        state=MetaEvidenceState(_text(raw, "state")),
        direction=(
            None
            if raw.get("direction") is None
            else MetaDirection(_text(raw, "direction"))
        ),
        directional_strength_0_1=_optional_decimal(
            raw.get("directional_strength_0_1")
        ),
        evidence_quality_0_1=_optional_decimal(
            raw.get("evidence_quality_0_1")
        ),
        freshness_0_1=_optional_decimal(raw.get("freshness_0_1")),
        market_available_at_ms=_optional_int(
            raw.get("market_available_at_ms")
        ),
        observed_at_ms=_optional_int(raw.get("observed_at_ms")),
        source_engine_ids=_text_tuple(raw, "source_engine_ids"),
        source_evidence_identities=_text_tuple(
            raw,
            "source_evidence_identities",
        ),
        material_conflict_identities=_text_tuple(
            raw,
            "material_conflict_identities",
        ),
        uncertainty_flags=_text_tuple(raw, "uncertainty_flags"),
    )


def _parse_proof(value: Any) -> DecisionProofEvidenceSlice:
    raw = require_mapping(value, "WC2 proof slice")
    return DecisionProofEvidenceSlice(
        slice_identity=_text(raw, "slice_identity"),
        schema_version=_text(raw, "schema_version"),
        engine_version=_text(raw, "engine_version"),
        domain=ProofEvidenceDomain(_text(raw, "domain")),
        availability=ProofEvidenceAvailability(_text(raw, "availability")),
        verdict=ProofEvidenceVerdict(_text(raw, "verdict")),
        evidence_identities=_text_tuple(raw, "evidence_identities"),
        market_available_at_ms=_optional_int(
            raw.get("market_available_at_ms")
        ),
        observed_at_ms=_optional_int(raw.get("observed_at_ms")),
        freshness_0_1=_optional_decimal(raw.get("freshness_0_1")),
        source_quality=_optional_text(raw.get("source_quality")),
        summary_codes=_text_tuple(raw, "summary_codes"),
    )


def _parse_event(value: Any) -> CircuitBreakerAnalysis:
    raw = require_mapping(value, "WC2 event context")
    return CircuitBreakerAnalysis(
        evidence_identity=_text(raw, "evidence_identity"),
        engine_version=_text(raw, "engine_version"),
        policy_version=_text(raw, "policy_version"),
        asset=_text(raw, "asset"),
        as_of_ms=_integer(raw, "as_of_ms"),
        state=CircuitBreakerState(_text(raw, "state")),
        event_risk_identity=_text(raw, "event_risk_identity"),
        news_evidence_identity=_text(raw, "news_evidence_identity"),
        market_quality_identity=_optional_text(
            raw.get("market_quality_identity")
        ),
        triggers=_text_tuple(raw, "triggers"),
        uncertainty_flags=_text_tuple(raw, "uncertainty_flags"),
        real_capital=_integer(raw, "real_capital"),
    )


def _parse_optional_sizing_policy(
    value: Any,
) -> PositionSizingPolicy | None:
    if value is None:
        return None
    return _parse_sizing_policy(value)


def _parse_sizing_policy(value: Any) -> PositionSizingPolicy:
    raw = require_mapping(value, "WC2 sizing policy")
    return PositionSizingPolicy(
        policy_identity=_text(raw, "policy_identity"),
        schema_version=_text(raw, "schema_version"),
        engine_version=_text(raw, "engine_version"),
        policy_version=_text(raw, "policy_version"),
        fixed_fraction_of_vault=Decimal(_text(raw, "fixed_fraction_of_vault")),
        maximum_fraction_of_vault=Decimal(
            _text(raw, "maximum_fraction_of_vault")
        ),
        maximum_absolute_correlation=Decimal(
            _text(raw, "maximum_absolute_correlation")
        ),
        maximum_drawdown_fraction=Decimal(
            _text(raw, "maximum_drawdown_fraction")
        ),
        maximum_volatility_fraction=Decimal(
            _text(raw, "maximum_volatility_fraction")
        ),
        minimum_liquidity_score_0_1=Decimal(
            _text(raw, "minimum_liquidity_score_0_1")
        ),
        maximum_transaction_cost_r=Decimal(
            _text(raw, "maximum_transaction_cost_r")
        ),
        martingale_allowed=bool(raw.get("martingale_allowed")),
        automatic_method_selection=bool(
            raw.get("automatic_method_selection")
        ),
        canonical_notional_authority=bool(
            raw.get("canonical_notional_authority")
        ),
        production_authority=bool(raw.get("production_authority")),
        real_capital=_integer(raw, "real_capital"),
    )


def _list(raw: dict[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key} must be list")
    return value


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError("optional text must be non-empty when present")
    return value


def _integer(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be integer")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("optional integer invalid")
    return value


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional decimal must be canonical string")
    return Decimal(value)


def _text_tuple(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    values = _list(raw, key)
    result = tuple(values)
    if any(not isinstance(item, str) for item in result):
        raise TypeError(f"{key} must contain text")
    return result


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
