from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from crypto_signal.ledger.serialization import canonical_sha256, sha256_text
from crypto_signal.product.intelligence_stream_evidence_contract import (
    StreamEvidenceResolutionState,
    resolution_state_for_visual_state,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamReadModelError,
)
from crypto_signal.product.intelligence_stream_visual_proof import (
    IntelligenceStreamVisualProofReadModel,
    StreamVisualProofError,
)

STREAM_EXACT_EVIDENCE_SCHEMA_VERSION = "intelligence-stream-exact-evidence-v1/1"
REAL_CAPITAL = 0
_MAX_OBJECTS_PER_DOMAIN = 12


class StreamExactEvidenceError(ValueError):
    """Raised when F6 exact evidence cannot be trusted."""


class IntelligenceStreamExactEvidenceReadModel:
    """Read-only F6 evidence resolver over exact persisted Stream/source truth."""

    def __init__(
        self,
        *,
        stream_ledger_path: Path,
        signal_ledger_path: Path | None = None,
        decision_evidence_path: Path | None = None,
        market_tape_path: Path | None = None,
        event_source_runtime_path: Path | None = None,
        provider_divergence_path: Path | None = None,
    ) -> None:
        self.stream_ledger_path = stream_ledger_path
        self.signal_ledger_path = signal_ledger_path
        self.decision_evidence_path = decision_evidence_path
        self.market_tape_path = market_tape_path
        self.event_source_runtime_path = event_source_runtime_path
        self.provider_divergence_path = provider_divergence_path

    def read_for_narrative(
        self,
        narrative_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(narrative_identity, "exact evidence narrative identity")
        try:
            detail = IntelligenceStreamReadModel(
                self.stream_ledger_path
            ).read_message_detail(narrative_identity)
        except StreamReadModelError as exc:
            raise StreamExactEvidenceError(str(exc)) from exc
        if detail is None:
            return None

        if any(
            key in detail
            for key in (
                "capital_story",
                "capital_decision",
                "capital_sizing",
                "capital_lifecycle",
            )
        ):
            return self._capital_projection(
                narrative_identity=narrative_identity,
                detail=detail,
            )

        fact = _mapping(
            detail.get("fact_bundle"),
            "exact evidence fact bundle",
        )
        if isinstance(fact.get("projector_id"), str):
            return self._family_projection(
                narrative_identity=narrative_identity,
                detail=detail,
                fact=fact,
            )
        return self._decision_projection(
            narrative_identity=narrative_identity,
            detail=detail,
            fact=fact,
        )

    def read_reference(
        self,
        *,
        narrative_identity: str,
        evidence_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(narrative_identity, "exact evidence narrative identity")
        _require_sha256(evidence_identity, "exact evidence reference identity")
        projection = self.read_for_narrative(narrative_identity)
        if projection is None:
            return None
        references = projection.get("reference_resolutions")
        if not isinstance(references, (list, tuple)):
            raise StreamExactEvidenceError(
                "exact evidence reference manifest is invalid"
            )
        selected = next(
            (
                item
                for item in references
                if isinstance(item, dict)
                and item.get("evidence_identity") == evidence_identity
            ),
            None,
        )
        if selected is None:
            return {
                "schema_version": STREAM_EXACT_EVIDENCE_SCHEMA_VERSION,
                "status": "unavailable",
                "narrative_identity": narrative_identity,
                "evidence_identity": evidence_identity,
                "resolution_state": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "reason": "evidence_identity_not_bound_to_message",
                "read_only": True,
                "production_authority": False,
                "real_capital": REAL_CAPITAL,
            }

        source_as_of_ms = _optional_non_negative_int(
            projection.get("source_as_of_ms")
        )
        raw_index = self._resolve_exact_objects(
            tuple(
                str(item["evidence_identity"])
                for item in references
                if isinstance(item, dict)
                and isinstance(item.get("evidence_identity"), str)
            ),
            source_as_of_ms=source_as_of_ms,
        )
        raw = raw_index.get(evidence_identity)
        return {
            "schema_version": STREAM_EXACT_EVIDENCE_SCHEMA_VERSION,
            "status": "ready",
            "narrative_identity": narrative_identity,
            "evidence_identity": evidence_identity,
            "resolution_state": selected.get("resolution_state"),
            "reason": selected.get("reason"),
            "object_kind": (
                None if raw is None else raw.get("object_kind")
            ),
            "exact_object": (
                None if raw is None else raw.get("payload")
            ),
            "current_data_substitution": False,
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }

    def _family_projection(
        self,
        *,
        narrative_identity: str,
        detail: dict[str, Any],
        fact: dict[str, Any],
    ) -> dict[str, Any]:
        evidence_identities = _identity_tuple(
            fact.get("evidence_identities"),
            "family exact evidence identity",
        )
        source_as_of_ms = _required_non_negative_int(
            fact.get("source_as_of_ms"),
            "family exact evidence source as-of",
        )
        raw_index = self._resolve_exact_objects(
            evidence_identities,
            source_as_of_ms=source_as_of_ms,
        )
        components = _state_components(fact.get("state_components"))
        domains = _text_tuple(
            fact.get("available_evidence_domains"),
            "family exact evidence domain",
        )
        resolutions = tuple(
            self._family_domain_resolution(
                domain=domain,
                fact=fact,
                components=components,
                evidence_identities=evidence_identities,
                raw_index=raw_index,
            )
            for domain in domains
        )
        references = _reference_resolutions(
            evidence_identities,
            raw_index,
        )
        return _projection_envelope(
            narrative_identity=narrative_identity,
            detail=detail,
            source_as_of_ms=source_as_of_ms,
            resolutions=resolutions,
            references=references,
        )

    def _family_domain_resolution(
        self,
        *,
        domain: str,
        fact: dict[str, Any],
        components: dict[str, str],
        evidence_identities: tuple[str, ...],
        raw_index: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        selected_objects = _objects_for_domain(
            domain,
            evidence_identities,
            raw_index,
        )
        selected_kinds = {
            str(item.get("object_kind"))
            for item in selected_objects
        }
        state = StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT
        reason = "exact_identity_bound_without_domain_object_projection"
        capabilities: dict[str, str] = {}

        if domain == "geometry":
            coordinate_keys = {
                "entry_zone_low",
                "entry_zone_high",
                "invalidation_price",
            }
            if coordinate_keys.issubset(components):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_geometry_coordinates_frozen_in_stream_fact"
                capabilities = {
                    "trigger_or_entry_zone": state.value,
                    "invalidation": state.value,
                    "targets": (
                        StreamEvidenceResolutionState.READY_EXACT.value
                        if any(
                            key.startswith("target_") and key.endswith("_price")
                            for key in components
                        )
                        else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                    ),
                    "structure_level": (
                        StreamEvidenceResolutionState.READY_EXACT.value
                        if "structure_level" in components
                        else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                    ),
                }
        elif domain == "frozen_chart":
            if "decision_freeze_bundle" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_immutable_signal_freeze_bundle_resolved"
            capabilities = {
                "historical_chart_source": state.value,
                "current_data_substitution": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
            }
        elif domain == "signal_lifecycle":
            if {"from_state", "to_state", "lifecycle_reason"}.issubset(components):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_lifecycle_transition_frozen_in_stream_fact"
        elif domain == "order_book":
            if "market_tape_orderbook" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_orderbook_snapshot_resolved"
            capabilities = {
                "bids_asks_quantities": state.value,
                "provider_event_source_ingested_timestamps": state.value,
                "imbalance_measurement": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if "book_pressure" in components
                    else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
            }
        elif domain == "public_trades":
            if "market_tape_trade" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_public_trades_resolved"
        elif domain == "liquidity":
            if "market_tape_orderbook" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_liquidity_state_and_source_orderbooks_resolved"
            capabilities = {
                "source_orderbook_levels": state.value,
                "canonical_liquidity_zone_coordinates": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "sweep_point": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
            }
        elif domain == "order_flow":
            if selected_kinds.intersection(
                {"market_tape_orderbook", "market_tape_trade"}
            ) and {"book_pressure", "taker_flow"}.intersection(components):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_microstructure_state_and_sources_resolved"
            capabilities = {
                "microstructure_measurement": state.value,
                "cvd_series": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "divergence_relation": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "absorption_evidence": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
            }
        elif domain == "derivatives":
            if "market_tape_derivatives" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_derivatives_observations_resolved"
            capabilities = {
                "funding_open_interest_basis": state.value,
                "source_snapshot": state.value,
            }
        elif domain == "event_calendar":
            if selected_kinds.intersection(
                {"event_calendar_coverage", "structured_event_observation"}
            ):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_event_calendar_records_resolved"
        elif domain == "event_risk":
            if selected_kinds.intersection(
                {"event_calendar_coverage", "structured_event_observation"}
            ) and "risk_state" in components:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_event_risk_state_and_temporal_source_resolved"
            capabilities = {
                "event_record": state.value,
                "temporal_relationship": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if "nearest_event_scheduled_at_ms" in components
                    else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
            }
        elif domain in {"provider_divergence", "data_quality"}:
            if "provider_divergence_snapshot" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_provider_divergence_snapshot_resolved"
        customer_projection = {
            "projector_id": fact.get("projector_id"),
            "family": fact.get("family"),
            "state_label": fact.get("state_label"),
            "state_components": components,
            "direction": fact.get("direction"),
            "source_quality": fact.get("source_quality"),
            "uncertainty_flags": fact.get("uncertainty_flags"),
            "event_at_ms": fact.get("event_at_ms"),
            "source_as_of_ms": fact.get("source_as_of_ms"),
            "exact_source_objects": tuple(
                item.get("payload")
                for item in selected_objects[:_MAX_OBJECTS_PER_DOMAIN]
            ),
            "exact_source_object_count": len(selected_objects),
        }
        return {
            "domain": domain,
            "resolution_state": state.value,
            "reason": reason,
            "evidence_identities": evidence_identities,
            "capabilities": capabilities,
            "customer_projection": customer_projection,
            "current_data_substitution": False,
        }

    def _decision_projection(
        self,
        *,
        narrative_identity: str,
        detail: dict[str, Any],
        fact: dict[str, Any],
    ) -> dict[str, Any]:
        source_as_of_ms = _optional_non_negative_int(
            fact.get("source_as_of_ms")
        )
        resolutions: list[dict[str, Any]] = []
        evidence_ids: set[str] = set()
        visual: dict[str, Any] | None = None

        if (
            self.signal_ledger_path is not None
            and self.decision_evidence_path is not None
        ):
            try:
                visual = IntelligenceStreamVisualProofReadModel(
                    stream_ledger_path=self.stream_ledger_path,
                    signal_ledger_path=self.signal_ledger_path,
                    decision_evidence_path=self.decision_evidence_path,
                ).read_for_narrative(narrative_identity)
            except StreamVisualProofError as exc:
                raise StreamExactEvidenceError(str(exc)) from exc

        if visual is not None:
            raw_domains = visual.get("domain_evidence")
            if isinstance(raw_domains, (list, tuple)):
                for raw_domain in raw_domains:
                    domain_row = _mapping(
                        raw_domain,
                        "decision exact evidence domain",
                    )
                    identities = _identity_tuple(
                        domain_row.get("evidence_identities"),
                        "decision exact evidence identity",
                        allow_empty=True,
                    )
                    evidence_ids.update(identities)
                    visual_state = str(
                        domain_row.get("visual_state") or "unavailable"
                    )
                    state = resolution_state_for_visual_state(
                        visual_state
                    )
                    customer_projection: dict[str, Any] = {
                        "market_available_at_ms": domain_row.get(
                            "market_available_at_ms"
                        ),
                        "observed_at_ms": domain_row.get("observed_at_ms"),
                        "freshness_0_1": domain_row.get("freshness_0_1"),
                        "source_quality": domain_row.get("source_quality"),
                        "summary_codes": domain_row.get("summary_codes"),
                    }
                    if (
                        state is StreamEvidenceResolutionState.READY_EXACT
                        and str(domain_row.get("domain"))
                        in {"frozen_chart", "consumed_candles"}
                    ):
                        customer_projection.update(
                            {
                                "provenance": visual.get("provenance"),
                                "candles": visual.get("candles"),
                                "annotations": visual.get("annotations"),
                            }
                        )
                    resolutions.append(
                        {
                            "domain": domain_row.get("domain"),
                            "resolution_state": state.value,
                            "reason": domain_row.get("visual_reason"),
                            "evidence_identities": identities,
                            "capabilities": {},
                            "customer_projection": customer_projection,
                            "current_data_substitution": False,
                        }
                    )

        if not resolutions:
            domains = _text_tuple(
                fact.get("available_evidence_domains"),
                "decision exact evidence domain",
                allow_empty=True,
            )
            for domain_name in domains:
                resolutions.append(
                    {
                        "domain": domain_name,
                        "resolution_state": (
                            StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT.value
                        ),
                        "reason": (
                            "exact_decision_fact_exists_but_bound_visual_resolver_unavailable"
                        ),
                        "evidence_identities": (),
                        "capabilities": {},
                        "customer_projection": {
                            "source_as_of_ms": source_as_of_ms,
                        },
                        "current_data_substitution": False,
                    }
                )

        raw_index = self._resolve_exact_objects(
            tuple(sorted(evidence_ids)),
            source_as_of_ms=source_as_of_ms,
        )
        references = _reference_resolutions(
            tuple(sorted(evidence_ids)),
            raw_index,
        )
        return _projection_envelope(
            narrative_identity=narrative_identity,
            detail=detail,
            source_as_of_ms=source_as_of_ms,
            resolutions=tuple(resolutions),
            references=references,
        )

    def _capital_projection(
        self,
        *,
        narrative_identity: str,
        detail: dict[str, Any],
    ) -> dict[str, Any]:
        narrative = _mapping(
            detail.get("narrative"),
            "capital exact evidence narrative",
        )
        references = _capital_reference_identities(narrative)
        source_as_of_ms = _optional_non_negative_int(
            narrative.get("source_as_of_ms")
        )
        if source_as_of_ms is None:
            source_as_of_ms = _optional_non_negative_int(
                narrative.get("event_at_ms")
            )
        resolution_state = (
            StreamEvidenceResolutionState.READY_EXACT
            if references
            else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
        )
        customer_projection = {
            key: value
            for key, value in narrative.items()
            if key
            not in {
                "text",
                "collapsed_text",
                "simple_text",
                "technical_text",
                "intelligence_text",
                "decision_text",
                "capital_text",
            }
        }
        resolutions = (
            {
                "domain": "capital",
                "resolution_state": resolution_state.value,
                "reason": (
                    "exact_immutable_capital_message_and_lineage_resolved"
                    if references
                    else "capital_message_contains_no_exact_lineage"
                ),
                "evidence_identities": references,
                "capabilities": {
                    "eligibility_identity": _capability_for_keys(
                        narrative,
                        "eligibility_proof_identity",
                        "decision_identity",
                        "allocator_assessment_identity",
                    ),
                    "sizing_identity": _capability_for_keys(
                        narrative,
                        "sizing_event_identity",
                        "selection_identity",
                    ),
                    "intent_fill_identity": _capability_for_keys(
                        narrative,
                        "intent_identity",
                        "fill_identity",
                        "bundle_identity",
                    ),
                    "accounting_identity": _capability_for_keys(
                        narrative,
                        "before_vault_snapshot_identity",
                        "after_vault_snapshot_identity",
                        "before_consolidated_snapshot_identity",
                        "after_consolidated_snapshot_identity",
                        "outcome_identity",
                    ),
                },
                "customer_projection": customer_projection,
                "current_data_substitution": False,
            },
        )
        reference_resolutions = tuple(
            {
                "evidence_identity": identity,
                "resolution_state": (
                    StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT.value
                ),
                "reason": "exact_capital_lineage_identity_bound_to_immutable_message",
                "object_kind": "capital_lineage_identity",
            }
            for identity in references
        )
        return _projection_envelope(
            narrative_identity=narrative_identity,
            detail=detail,
            source_as_of_ms=source_as_of_ms,
            resolutions=resolutions,
            references=reference_resolutions,
        )

    def _resolve_exact_objects(
        self,
        evidence_identities: tuple[str, ...],
        *,
        source_as_of_ms: int | None,
    ) -> dict[str, dict[str, Any]]:
        if not evidence_identities:
            return {}
        resolved: dict[str, dict[str, Any]] = {}
        if self.signal_ledger_path is not None and self.signal_ledger_path.exists():
            resolved.update(
                _resolve_signal_objects(
                    self.signal_ledger_path,
                    evidence_identities,
                    source_as_of_ms=source_as_of_ms,
                )
            )
        if self.market_tape_path is not None and self.market_tape_path.exists():
            resolved.update(
                _resolve_market_tape_objects(
                    self.market_tape_path,
                    evidence_identities,
                    source_as_of_ms=source_as_of_ms,
                )
            )
        if (
            self.event_source_runtime_path is not None
            and self.event_source_runtime_path.exists()
        ):
            resolved.update(
                _resolve_event_source_objects(
                    self.event_source_runtime_path,
                    evidence_identities,
                    source_as_of_ms=source_as_of_ms,
                )
            )
        if (
            self.provider_divergence_path is not None
            and self.provider_divergence_path.exists()
        ):
            resolved.update(
                _resolve_provider_divergence_objects(
                    self.provider_divergence_path,
                    evidence_identities,
                    source_as_of_ms=source_as_of_ms,
                )
            )
        return resolved


def _projection_envelope(
    *,
    narrative_identity: str,
    detail: dict[str, Any],
    source_as_of_ms: int | None,
    resolutions: tuple[dict[str, Any], ...],
    references: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    counts = Counter(
        str(item.get("resolution_state"))
        for item in resolutions
    )
    narrative = detail.get("narrative")
    category = narrative.get("category") if isinstance(narrative, dict) else None
    subtype = narrative.get("subtype") if isinstance(narrative, dict) else None
    return {
        "schema_version": STREAM_EXACT_EVIDENCE_SCHEMA_VERSION,
        "status": "ready",
        "narrative_identity": narrative_identity,
        "category": category,
        "subtype": subtype,
        "source_as_of_ms": source_as_of_ms,
        "resolution_counts": {
            state.value: counts.get(state.value, 0)
            for state in StreamEvidenceResolutionState
        },
        "resolutions": resolutions,
        "reference_resolutions": references,
        "current_data_substitution": False,
        "read_only": True,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }


def _reference_resolutions(
    evidence_identities: tuple[str, ...],
    raw_index: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    rows = []
    for identity in evidence_identities:
        raw = raw_index.get(identity)
        rows.append(
            {
                "evidence_identity": identity,
                "resolution_state": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if raw is not None
                    else StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT.value
                ),
                "reason": (
                    "exact_persisted_source_object_resolved"
                    if raw is not None
                    else "exact_identity_bound_but_source_object_resolver_not_available"
                ),
                "object_kind": (
                    None if raw is None else raw.get("object_kind")
                ),
            }
        )
    return tuple(rows)


def _objects_for_domain(
    domain: str,
    evidence_identities: tuple[str, ...],
    raw_index: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    allowed = {
        "geometry": {"signal_freeze", "decision_freeze_bundle"},
        "frozen_chart": {"signal_freeze", "decision_freeze_bundle"},
        "signal_lifecycle": {"signal_freeze", "decision_freeze_bundle"},
        "order_book": {"market_tape_orderbook"},
        "public_trades": {"market_tape_trade"},
        "liquidity": {"market_tape_orderbook"},
        "order_flow": {"market_tape_orderbook", "market_tape_trade"},
        "derivatives": {"market_tape_derivatives"},
        "event_calendar": {
            "event_calendar_coverage",
            "structured_event_observation",
        },
        "event_risk": {
            "event_calendar_coverage",
            "structured_event_observation",
        },
        "provider_divergence": {"provider_divergence_snapshot"},
        "data_quality": {"provider_divergence_snapshot"},
    }.get(domain)
    if allowed is None:
        return ()
    rows = []
    for identity in evidence_identities:
        item = raw_index.get(identity)
        if item is None:
            continue
        if allowed is not None and item.get("object_kind") not in allowed:
            continue
        rows.append(item)
    return tuple(rows)


def _resolve_signal_objects(
    path: Path,
    evidence_identities: tuple[str, ...],
    *,
    source_as_of_ms: int | None,
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.DatabaseError as exc:
        raise StreamExactEvidenceError(str(exc)) from exc
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        table = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='signal_freezes'
            """
        ).fetchone()
        if table is None:
            return {}

        resolved: dict[str, dict[str, Any]] = {}
        for batch in _batches(evidence_identities, size=300):
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"""
                SELECT
                    bundle_identity,
                    signal_freeze_identity,
                    exchange,
                    market_type,
                    symbol,
                    timeframe,
                    as_of_ms,
                    source_cutoff_open_time_ms,
                    frozen_at_ms,
                    bundle_json
                FROM signal_freezes
                WHERE signal_freeze_identity IN ({placeholders})
                   OR bundle_identity IN ({placeholders})
                """,
                (*batch, *batch),
            ).fetchall()
            for row in rows:
                bundle_identity = str(row["bundle_identity"])
                signal_identity = str(row["signal_freeze_identity"])
                bundle_json = str(row["bundle_json"])
                if sha256_text(bundle_json) != bundle_identity:
                    raise StreamExactEvidenceError(
                        "exact evidence signal freeze bundle digest mismatch"
                    )
                as_of_ms = int(row["as_of_ms"])
                if source_as_of_ms is not None and as_of_ms > source_as_of_ms:
                    raise StreamExactEvidenceError(
                        "exact evidence signal freeze is future evidence"
                    )
                bundle = _json_object(
                    bundle_json,
                    "exact evidence signal freeze bundle",
                )
                freeze_projection = {
                    "signal_freeze_identity": signal_identity,
                    "decision_freeze_bundle_identity": bundle_identity,
                    "exchange": str(row["exchange"]),
                    "market_type": str(row["market_type"]),
                    "symbol": str(row["symbol"]),
                    "timeframe": str(row["timeframe"]),
                    "as_of_ms": as_of_ms,
                    "frozen_at_ms": int(row["frozen_at_ms"]),
                    "source_cutoff_open_time_ms": int(
                        row["source_cutoff_open_time_ms"]
                    ),
                    "bundle": bundle,
                }
                resolved[signal_identity] = {
                    "object_kind": "signal_freeze",
                    "payload": freeze_projection,
                }
                resolved[bundle_identity] = {
                    "object_kind": "decision_freeze_bundle",
                    "payload": freeze_projection,
                }
        return resolved
    except sqlite3.DatabaseError as exc:
        raise StreamExactEvidenceError(str(exc)) from exc
    finally:
        connection.close()

def _resolve_market_tape_objects(
    path: Path,
    evidence_identities: tuple[str, ...],
    *,
    source_as_of_ms: int | None,
) -> dict[str, dict[str, Any]]:
    table_specs = (
        (
            "market_tape_orderbooks",
            "snapshot_identity",
            "market_tape_orderbook",
        ),
        (
            "market_tape_trades",
            "trade_identity",
            "market_tape_trade",
        ),
        (
            "market_tape_derivatives",
            "observation_identity",
            "market_tape_derivatives",
        ),
    )
    return _resolve_sqlite_payload_objects(
        path,
        evidence_identities,
        table_specs=table_specs,
        source_as_of_ms=source_as_of_ms,
        identity_payload_key_by_kind={
            "market_tape_orderbook": "snapshot_identity",
            "market_tape_trade": "trade_identity",
            "market_tape_derivatives": "observation_identity",
        },
    )


def _resolve_event_source_objects(
    path: Path,
    evidence_identities: tuple[str, ...],
    *,
    source_as_of_ms: int | None,
) -> dict[str, dict[str, Any]]:
    table_specs = (
        (
            "event_calendar_coverages",
            "coverage_identity",
            "event_calendar_coverage",
        ),
        (
            "structured_event_observations",
            "event_identity",
            "structured_event_observation",
        ),
    )
    resolved = _resolve_sqlite_payload_objects(
        path,
        evidence_identities,
        table_specs=table_specs,
        source_as_of_ms=source_as_of_ms,
        identity_payload_key_by_kind={},
    )
    for identity, item in resolved.items():
        payload = _mapping(
            item.get("payload"),
            "event source exact payload",
        )
        if canonical_sha256(payload) != identity:
            raise StreamExactEvidenceError(
                "event source exact payload identity mismatch"
            )
    return resolved


def _resolve_provider_divergence_objects(
    path: Path,
    evidence_identities: tuple[str, ...],
    *,
    source_as_of_ms: int | None,
) -> dict[str, dict[str, Any]]:
    resolved = _resolve_sqlite_payload_objects(
        path,
        evidence_identities,
        table_specs=(
            (
                "provider_divergence_snapshots",
                "snapshot_identity",
                "provider_divergence_snapshot",
            ),
        ),
        source_as_of_ms=source_as_of_ms,
        identity_payload_key_by_kind={},
    )
    for identity, item in resolved.items():
        payload = _mapping(
            item.get("payload"),
            "provider divergence exact payload",
        )
        if canonical_sha256(payload) != identity:
            raise StreamExactEvidenceError(
                "provider divergence exact payload identity mismatch"
            )
    return resolved


def _resolve_sqlite_payload_objects(
    path: Path,
    evidence_identities: tuple[str, ...],
    *,
    table_specs: tuple[tuple[str, str, str], ...],
    source_as_of_ms: int | None,
    identity_payload_key_by_kind: dict[str, str],
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.DatabaseError as exc:
        raise StreamExactEvidenceError(str(exc)) from exc
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        resolved: dict[str, dict[str, Any]] = {}
        for table, identity_column, object_kind in table_specs:
            if table not in tables:
                continue
            for batch in _batches(evidence_identities, size=400):
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"""
                    SELECT {identity_column}, payload_json
                    FROM {table}
                    WHERE {identity_column} IN ({placeholders})
                    """,
                    batch,
                ).fetchall()
                for row in rows:
                    identity = str(row[0])
                    payload = _json_object(
                        str(row[1]),
                        f"{object_kind} payload",
                    )
                    payload_identity_key = identity_payload_key_by_kind.get(
                        object_kind
                    )
                    if (
                        payload_identity_key is not None
                        and payload.get(payload_identity_key) != identity
                    ):
                        raise StreamExactEvidenceError(
                            f"{object_kind} row/payload identity mismatch"
                        )
                    _verify_not_future(
                        payload,
                        source_as_of_ms=source_as_of_ms,
                        label=object_kind,
                    )
                    resolved[identity] = {
                        "object_kind": object_kind,
                        "payload": payload,
                    }
        return resolved
    except sqlite3.DatabaseError as exc:
        raise StreamExactEvidenceError(str(exc)) from exc
    finally:
        connection.close()


def _verify_not_future(
    payload: dict[str, Any],
    *,
    source_as_of_ms: int | None,
    label: str,
) -> None:
    if source_as_of_ms is None:
        return
    for key in (
        "event_at_ms",
        "source_timestamp_ms",
        "ingested_at_ms",
        "observed_at_ms",
    ):
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise StreamExactEvidenceError(
                f"{label} {key} must be non-negative integer"
            )
        if value > source_as_of_ms:
            raise StreamExactEvidenceError(
                f"{label} contains future evidence: {key}"
            )


def _capital_reference_identities(
    narrative: dict[str, Any],
) -> tuple[str, ...]:
    values: set[str] = set()
    raw_refs = narrative.get("capital_reference_identities")
    if isinstance(raw_refs, (list, tuple)):
        values.update(
            str(item)
            for item in raw_refs
            if isinstance(item, str) and _is_sha256(item)
        )
    for key, value in narrative.items():
        if (
            key.endswith("_identity")
            and key
            not in {
                "narrative_identity",
                "source_event_identity",
                "stream_event_identity",
                "story_identity",
            }
            and isinstance(value, str)
            and _is_sha256(value)
        ):
            values.add(value)
    return tuple(sorted(values))


def _capability_for_keys(
    payload: dict[str, Any],
    *keys: str,
) -> str:
    if any(
        isinstance(payload.get(key), str)
        and _is_sha256(str(payload.get(key)))
        for key in keys
    ):
        return StreamEvidenceResolutionState.READY_EXACT.value
    return StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value


def _state_components(value: object) -> dict[str, str]:
    if not isinstance(value, (list, tuple)):
        return {}
    components: dict[str, str] = {}
    for item in value:
        if isinstance(item, dict):
            name = item.get("name")
            raw_value = item.get("value")
        elif (
            isinstance(item, (list, tuple))
            and len(item) == 2
        ):
            name, raw_value = item
        else:
            continue
        if isinstance(name, str) and name.strip():
            components[name] = str(raw_value)
    return dict(sorted(components.items()))


def _identity_tuple(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if value is None and allow_empty:
        return ()
    if not isinstance(value, (list, tuple)):
        raise StreamExactEvidenceError(f"{label} must be array")
    identities = tuple(str(item) for item in value)
    if identities != tuple(sorted(set(identities))):
        raise StreamExactEvidenceError(
            f"{label} must be sorted and unique"
        )
    if not identities and not allow_empty:
        raise StreamExactEvidenceError(f"{label} cannot be empty")
    for identity in identities:
        _require_sha256(identity, label)
    return identities


def _text_tuple(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if value is None and allow_empty:
        return ()
    if not isinstance(value, (list, tuple)):
        raise StreamExactEvidenceError(f"{label} must be array")
    items = tuple(str(item) for item in value)
    if items != tuple(sorted(set(items))):
        raise StreamExactEvidenceError(
            f"{label} must be sorted and unique"
        )
    if not items and not allow_empty:
        raise StreamExactEvidenceError(f"{label} cannot be empty")
    if any(not item.strip() for item in items):
        raise StreamExactEvidenceError(f"{label} cannot contain blank values")
    return items


def _required_non_negative_int(value: object, label: str) -> int:
    parsed = _optional_non_negative_int(value)
    if parsed is None:
        raise StreamExactEvidenceError(f"{label} missing")
    return parsed


def _optional_non_negative_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StreamExactEvidenceError(
            "exact evidence timestamp must be non-negative integer"
        )
    return value


def _json_object(value: str, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise StreamExactEvidenceError(f"{label} is invalid JSON") from exc
    if not isinstance(raw, dict):
        raise StreamExactEvidenceError(f"{label} must be object")
    return raw


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StreamExactEvidenceError(f"{label} must be object")
    return value


def _batches(
    values: tuple[str, ...],
    *,
    size: int,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        values[index : index + size]
        for index in range(0, len(values), size)
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )


def _require_sha256(value: str, label: str) -> None:
    if not _is_sha256(value):
        raise StreamExactEvidenceError(
            f"{label} must be lowercase SHA256"
        )
