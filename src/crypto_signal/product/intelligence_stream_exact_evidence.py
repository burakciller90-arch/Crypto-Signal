from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from crypto_signal.ledger.serialization import canonical_sha256, sha256_text
from crypto_signal.product.frozen_proof_store import (
    FrozenProofConflictError,
    FrozenProofStore,
)
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
        frozen_proof_store_path: Path | None = None,
        options_surface_path: Path | None = None,
        onchain_capital_flow_path: Path | None = None,
        onchain_source_contract_path: Path | None = None,
    ) -> None:
        self.stream_ledger_path = stream_ledger_path
        self.signal_ledger_path = signal_ledger_path
        self.decision_evidence_path = decision_evidence_path
        self.market_tape_path = market_tape_path
        self.event_source_runtime_path = event_source_runtime_path
        self.provider_divergence_path = provider_divergence_path
        self.frozen_proof_store_path = frozen_proof_store_path
        self.options_surface_path = options_surface_path
        self.onchain_capital_flow_path = onchain_capital_flow_path
        self.onchain_source_contract_path = onchain_source_contract_path

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
        if "geometry" in domains:
            linked_geometry_proofs = tuple(
                identity
                for identity, item in raw_index.items()
                if item.get("object_kind") == "geometry_proof"
            )
            evidence_identities = tuple(
                sorted({*evidence_identities, *linked_geometry_proofs})
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
            full_proof_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "geometry_proof" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            if full_proof_state is StreamEvidenceResolutionState.READY_EXACT:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_geometry_proof_resolved"
            elif coordinate_keys.issubset(components):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_geometry_coordinates_frozen_in_stream_fact"
            capabilities = {
                "full_geometry_proof": full_proof_state.value,
                "methodology_states": full_proof_state.value,
                "annotations": full_proof_state.value,
                "conflict_flags": full_proof_state.value,
                "trigger_or_entry_zone": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if {"entry_zone_low", "entry_zone_high"}.issubset(components)
                    else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "invalidation": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if "invalidation_price" in components
                    else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
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
            dynamics_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "liquidity_dynamics_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            structure_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "liquidity_structure_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            sweep_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "liquidity_sweep_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            source_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "market_tape_orderbook" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            if (
                dynamics_state is StreamEvidenceResolutionState.READY_EXACT
                or structure_state is StreamEvidenceResolutionState.READY_EXACT
                or sweep_state is StreamEvidenceResolutionState.READY_EXACT
            ):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_liquidity_derived_proof_resolved"
            elif source_state is StreamEvidenceResolutionState.READY_EXACT:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_liquidity_state_and_source_orderbooks_resolved"
            capabilities = {
                "source_orderbook_levels": source_state.value,
                "dynamics_measurement": dynamics_state.value,
                "canonical_liquidity_zone_coordinates": structure_state.value,
                "sweep_point": sweep_state.value,
            }
        elif domain == "liquidity_structure":
            if "liquidity_structure_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_liquidity_structure_proof_resolved"
            capabilities = {
                "levels_and_candidate_labels": state.value,
                "appearance_cancellation_rates": state.value,
            }
        elif domain == "liquidity_sweep":
            if "liquidity_sweep_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_liquidity_sweep_proof_resolved"
            capabilities = {
                "sweep_candidates": state.value,
                "persistent_pool_dependency": state.value,
            }
        elif domain == "order_flow":
            micro_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "order_flow_microstructure_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            temporal_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "temporal_order_flow_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            absorption_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "absorption_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            divergence_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "price_cvd_divergence_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            if (
                micro_state is StreamEvidenceResolutionState.READY_EXACT
                or temporal_state is StreamEvidenceResolutionState.READY_EXACT
                or absorption_state is StreamEvidenceResolutionState.READY_EXACT
                or divergence_state is StreamEvidenceResolutionState.READY_EXACT
            ):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_order_flow_derived_proof_resolved"
            elif selected_kinds.intersection(
                {"market_tape_orderbook", "market_tape_trade"}
            ) and {"book_pressure", "taker_flow"}.intersection(components):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_microstructure_state_and_sources_resolved"
                micro_state = state
            capabilities = {
                "microstructure_measurement": micro_state.value,
                "cvd_series": temporal_state.value,
                "divergence_relation": divergence_state.value,
                "absorption_evidence": absorption_state.value,
            }
        elif domain in {"temporal_order_flow", "window_local_cvd"}:
            if "temporal_order_flow_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_temporal_order_flow_proof_resolved"
            capabilities = {
                "window_metrics": state.value,
                "cvd_series": state.value,
                "trade_velocity": state.value,
                "large_trade_candidates": state.value,
            }
        elif domain == "absorption":
            if "absorption_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_absorption_proof_resolved"
            capabilities = {
                "absorption_candidates": state.value,
                "flow_structure_dependency": state.value,
            }
        elif domain == "price_cvd_divergence":
            if "price_cvd_divergence_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_price_cvd_divergence_proof_resolved"
            capabilities = {
                "divergence_candidates": state.value,
                "candle_flow_relationship": state.value,
            }
        elif domain == "derivatives":
            raw_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "market_tape_derivatives" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            context_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "derivatives_context_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            dynamics_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "derivatives_dynamics_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            heatmap_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "liquidation_heatmap_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            crowding_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "derivatives_crowding_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            options_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "options_volatility_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            if (
                context_state is StreamEvidenceResolutionState.READY_EXACT
                or dynamics_state is StreamEvidenceResolutionState.READY_EXACT
                or heatmap_state is StreamEvidenceResolutionState.READY_EXACT
                or crowding_state is StreamEvidenceResolutionState.READY_EXACT
                or options_state is StreamEvidenceResolutionState.READY_EXACT
            ):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_derivatives_derived_proof_resolved"
            elif raw_state is StreamEvidenceResolutionState.READY_EXACT:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_derivatives_observations_resolved"
            capabilities = {
                "raw_mark_index_open_interest_funding": raw_state.value,
                "context_measurement": context_state.value,
                "price_oi_funding_dynamics": dynamics_state.value,
                "funding_open_interest_basis": context_state.value,
                "observed_liquidation_heatmap": heatmap_state.value,
                "crowding_context": crowding_state.value,
                "options_volatility_context": options_state.value,
                "source_snapshot": raw_state.value,
            }
        elif domain == "derivatives_context":
            if "derivatives_context_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_derivatives_context_proof_resolved"
            capabilities = {
                "funding_state": state.value,
                "open_interest_state": state.value,
                "basis_state": state.value,
                "context_metrics": state.value,
            }
        elif domain == "derivatives_dynamics":
            if "derivatives_dynamics_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_derivatives_dynamics_proof_resolved"
            capabilities = {
                "price_oi_state": state.value,
                "funding_percentile": state.value,
                "funding_acceleration": state.value,
                "basis_change": state.value,
            }
        elif domain == "observed_liquidation_events":
            if "market_tape_liquidation" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_liquidation_events_resolved"
            capabilities = {
                "liquidation_event_rows": state.value,
            }
        elif domain == "liquidation_event_coverage":
            if "market_tape_liquidation_coverage" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_liquidation_coverage_resolved"
            capabilities = {
                "coverage_interval": state.value,
                "coverage_observed_at_knowledge_time": state.value,
            }
        elif domain == "observed_liquidation_heatmap":
            if "liquidation_heatmap_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_liquidation_heatmap_proof_resolved"
            capabilities = {
                "observed_bins": state.value,
                "observed_cluster_count": state.value,
                "zero_event_state": state.value,
                "mark_reference": state.value,
                "future_liquidation_risk_estimate": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
            }
        elif domain == "derivatives_crowding":
            if "derivatives_crowding_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_derivatives_crowding_proof_resolved"
            capabilities = {
                "crowding_context": state.value,
                "crowded_side": state.value,
                "squeeze_context": state.value,
                "upstream_dependency_lineage": state.value,
            }
        elif domain == "options_surface":
            surface_objects = tuple(
                item
                for item in selected_objects
                if item.get("object_kind") == "options_surface_observation"
            )
            metadata_objects = tuple(
                item
                for item in selected_objects
                if item.get("object_kind") == "options_instrument_metadata"
            )
            quote_objects = tuple(
                item
                for item in selected_objects
                if item.get("object_kind") == "options_contract_quote"
            )
            expected_quote_count = sum(
                len(contracts)
                for item in surface_objects
                if isinstance(item.get("payload"), dict)
                for contracts in (item["payload"].get("contracts"),)
                if isinstance(contracts, list)
            )
            surface_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if surface_objects
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            metadata_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if surface_objects
                and len(metadata_objects) == len(surface_objects)
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            quote_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if expected_quote_count > 0
                and len(quote_objects) == expected_quote_count
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            volatility_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if "options_volatility_freeze" in selected_kinds
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            if (
                surface_state is StreamEvidenceResolutionState.READY_EXACT
                and metadata_state is StreamEvidenceResolutionState.READY_EXACT
                and quote_state is StreamEvidenceResolutionState.READY_EXACT
            ):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_canonical_options_surface_lineage_resolved"
            capabilities = {
                "surface_snapshot": surface_state.value,
                "instrument_metadata_lineage": metadata_state.value,
                "contract_quote_lineage": quote_state.value,
                "volatility_freeze_link": volatility_state.value,
            }
        elif domain == "options_volatility":
            if "options_volatility_freeze" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_persisted_options_volatility_proof_resolved"
            capabilities = {
                "atm_iv_term_structure": state.value,
                "risk_reversal_25d": state.value,
                "open_interest_by_expiry": state.value,
                "volume_by_expiry": state.value,
                "expiry_concentration": state.value,
                "volatility_index": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "dealer_gamma_position": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "max_pain": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
            }
        elif domain in {"onchain", "stablecoin_capital_flow"}:
            freeze_objects = tuple(
                item
                for item in selected_objects
                if item.get("object_kind") == "stablecoin_capital_flow_freeze"
            )
            normalized_objects = tuple(
                item
                for item in selected_objects
                if item.get("object_kind") == "stablecoin_supply_observation"
            )
            raw_objects = tuple(
                item
                for item in selected_objects
                if item.get("object_kind") == "source_raw_payload"
            )
            envelope_objects = tuple(
                item
                for item in selected_objects
                if item.get("object_kind") == "source_envelope"
            )
            coverage_objects = tuple(
                item
                for item in selected_objects
                if item.get("object_kind") == "source_coverage"
            )
            required_source_ids: set[str] = set()
            for item in freeze_objects:
                proof = item.get("payload")
                if not isinstance(proof, dict):
                    continue
                source_ids = proof.get("source_object_identities")
                if not isinstance(source_ids, (list, tuple)):
                    continue
                required_source_ids.update(
                    str(value)
                    for value in source_ids
                    if isinstance(value, str)
                )
            lineage_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if required_source_ids
                and all(
                    identity in raw_index
                    for identity in required_source_ids
                )
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            freeze_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if freeze_objects
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            normalized_state = (
                StreamEvidenceResolutionState.READY_EXACT
                if normalized_objects
                else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT
            )
            if (
                freeze_state is StreamEvidenceResolutionState.READY_EXACT
                and lineage_state is StreamEvidenceResolutionState.READY_EXACT
            ):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = (
                    "exact_persisted_stablecoin_proof_and_lineage_resolved"
                )
            explicit_unavailable = (
                StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
            )
            capabilities = {
                "stablecoin_capital_flow_freeze": freeze_state.value,
                "normalized_supply_observations": normalized_state.value,
                "source_lineage": lineage_state.value,
                "source_raw_payloads": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if raw_objects
                    else explicit_unavailable
                ),
                "source_envelopes": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if envelope_objects
                    else explicit_unavailable
                ),
                "source_coverage": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if coverage_objects
                    else explicit_unavailable
                ),
                "exchange_flow": (
                    explicit_unavailable
                    if components.get("exchange_flow_status") == "unavailable"
                    else StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT.value
                ),
                "large_transfer": (
                    explicit_unavailable
                    if components.get("large_transfer_status") == "unavailable"
                    else StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT.value
                ),
                "wallet_cohort": (
                    explicit_unavailable
                    if components.get("wallet_cohort_status") == "unavailable"
                    else StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT.value
                ),
                "stablecoin_bridge": (
                    explicit_unavailable
                    if (
                        components.get("stablecoin_bridge_status")
                        == "unavailable"
                    )
                    else StreamEvidenceResolutionState.IDENTITY_ONLY_EXACT.value
                ),
                "directional_inference": explicit_unavailable,
            }
        elif domain == "stablecoin_supply":
            has_freeze = "stablecoin_capital_flow_freeze" in selected_kinds
            has_observation = "stablecoin_supply_observation" in selected_kinds
            has_raw = "source_raw_payload" in selected_kinds
            has_envelope = "source_envelope" in selected_kinds
            has_coverage = "source_coverage" in selected_kinds
            if (
                has_freeze
                and has_observation
                and has_raw
                and has_envelope
                and has_coverage
            ):
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_stablecoin_supply_and_source_lineage_resolved"
            capabilities = {
                "supply_measurement": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if has_observation
                    else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "derived_supply_change": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if has_freeze
                    else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "source_lineage": (
                    StreamEvidenceResolutionState.READY_EXACT.value
                    if has_raw and has_envelope and has_coverage
                    else StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
                "directional_inference": (
                    StreamEvidenceResolutionState.UNAVAILABLE_EXPLICIT.value
                ),
            }
        elif domain == "source_raw_payload":
            if "source_raw_payload" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_canonical_source_raw_payload_resolved"
        elif domain == "source_envelope":
            if "source_envelope" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_canonical_source_envelope_resolved"
        elif domain == "source_coverage":
            if "source_coverage" in selected_kinds:
                state = StreamEvidenceResolutionState.READY_EXACT
                reason = "exact_canonical_source_coverage_resolved"
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
            "source_scope": fact.get("source_scope"),
            "asset": fact.get("asset"),
            "symbol": fact.get("symbol"),
            "market": fact.get("market"),
            "timeframe": fact.get("timeframe"),
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
            self.frozen_proof_store_path is not None
            and self.frozen_proof_store_path.exists()
        ):
            resolved.update(
                _resolve_frozen_proof_objects(
                    self.frozen_proof_store_path,
                    evidence_identities,
                    source_as_of_ms=source_as_of_ms,
                )
            )
        if (
            self.options_surface_path is not None
            and self.options_surface_path.exists()
        ):
            resolved.update(
                _resolve_options_surface_objects(
                    self.options_surface_path,
                    evidence_identities,
                    source_as_of_ms=source_as_of_ms,
                )
            )
        if (
            self.onchain_capital_flow_path is not None
            and self.onchain_capital_flow_path.exists()
        ):
            resolved.update(
                _resolve_onchain_capital_flow_objects(
                    self.onchain_capital_flow_path,
                    evidence_identities,
                    source_as_of_ms=source_as_of_ms,
                )
            )
        if (
            self.onchain_source_contract_path is not None
            and self.onchain_source_contract_path.exists()
        ):
            resolved.update(
                _resolve_source_contract_objects(
                    self.onchain_source_contract_path,
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
        "geometry": {
            "signal_freeze",
            "decision_freeze_bundle",
            "geometry_proof",
        },
        "frozen_chart": {"signal_freeze", "decision_freeze_bundle"},
        "signal_lifecycle": {"signal_freeze", "decision_freeze_bundle"},
        "order_book": {"market_tape_orderbook"},
        "public_trades": {"market_tape_trade"},
        "liquidity": {
            "market_tape_orderbook",
            "liquidity_dynamics_freeze",
            "liquidity_structure_freeze",
            "liquidity_sweep_freeze",
        },
        "liquidity_structure": {"liquidity_structure_freeze"},
        "liquidity_sweep": {"liquidity_sweep_freeze"},
        "order_flow": {
            "market_tape_orderbook",
            "market_tape_trade",
            "order_flow_microstructure_freeze",
            "temporal_order_flow_freeze",
            "absorption_freeze",
            "price_cvd_divergence_freeze",
        },
        "temporal_order_flow": {"temporal_order_flow_freeze"},
        "window_local_cvd": {"temporal_order_flow_freeze"},
        "absorption": {"absorption_freeze"},
        "price_cvd_divergence": {"price_cvd_divergence_freeze"},
        "derivatives": {
            "market_tape_derivatives",
            "derivatives_context_freeze",
            "derivatives_dynamics_freeze",
            "liquidation_heatmap_freeze",
            "derivatives_crowding_freeze",
            "options_volatility_freeze",
        },
        "derivatives_context": {"derivatives_context_freeze"},
        "derivatives_dynamics": {"derivatives_dynamics_freeze"},
        "observed_liquidation_events": {"market_tape_liquidation"},
        "liquidation_event_coverage": {
            "market_tape_liquidation_coverage",
        },
        "observed_liquidation_heatmap": {"liquidation_heatmap_freeze"},
        "derivatives_crowding": {"derivatives_crowding_freeze"},
        "options_surface": {
            "options_surface_observation",
            "options_instrument_metadata",
            "options_contract_quote",
            "options_volatility_freeze",
        },
        "options_volatility": {"options_volatility_freeze"},
        "onchain": {
            "stablecoin_capital_flow_freeze",
            "stablecoin_supply_observation",
            "source_raw_payload",
            "source_envelope",
            "source_coverage",
        },
        "stablecoin_capital_flow": {
            "stablecoin_capital_flow_freeze",
            "stablecoin_supply_observation",
            "source_raw_payload",
            "source_envelope",
            "source_coverage",
        },
        "stablecoin_supply": {
            "stablecoin_capital_flow_freeze",
            "stablecoin_supply_observation",
            "source_raw_payload",
            "source_envelope",
            "source_coverage",
        },
        "source_raw_payload": {"source_raw_payload"},
        "source_envelope": {"source_envelope"},
        "source_coverage": {"source_coverage"},
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


def _resolve_frozen_proof_objects(
    path: Path,
    evidence_identities: tuple[str, ...],
    *,
    source_as_of_ms: int | None,
) -> dict[str, dict[str, Any]]:
    store = FrozenProofStore(path)
    resolved: dict[str, dict[str, Any]] = {}
    for identity in evidence_identities:
        try:
            proof = store.read_exact(identity)
        except FrozenProofConflictError as exc:
            raise StreamExactEvidenceError(str(exc)) from exc
        if proof is None:
            continue
        if source_as_of_ms is not None and proof.as_of_ms > source_as_of_ms:
            raise StreamExactEvidenceError(
                "exact frozen derived proof is future evidence"
            )
        payload = _json_object(
            proof.payload_json,
            "exact frozen derived proof payload",
        )
        visualization = (
            None
            if proof.visualization_json is None
            else _json_object(
                proof.visualization_json,
                "exact frozen derived proof visualization",
            )
        )
        resolved[identity] = {
            "object_kind": proof.object_kind,
            "payload": {
                "object_identity": proof.object_identity,
                "analysis_identity": proof.analysis_identity,
                "object_kind": proof.object_kind,
                "family": proof.family,
                "domains": proof.domains,
                "asset": proof.asset,
                "symbol": proof.symbol,
                "network": proof.network,
                "timeframe": proof.timeframe,
                "as_of_ms": proof.as_of_ms,
                "market_available_at_ms": proof.market_available_at_ms,
                "observed_at_ms": proof.observed_at_ms,
                "source_provider": proof.source_provider,
                "source_quality": proof.source_quality,
                "freshness_state": proof.freshness_state,
                "freshness_age_ms": proof.freshness_age_ms,
                "uncertainty_flags": proof.uncertainty_flags,
                "source_object_identities": proof.source_object_identities,
                "depends_on_evidence_identities": (
                    proof.depends_on_evidence_identities
                ),
                "payload": payload,
                "visualization": visualization,
                "renderer_contract_version": proof.renderer_contract_version,
                "persisted_at_ms": proof.persisted_at_ms,
                "schema_version": proof.schema_version,
            },
        }
    return resolved


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

        geometry_table = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='geometry_proofs'
            """
        ).fetchone()
        if geometry_table is not None:
            for batch in _batches(evidence_identities, size=300):
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"""
                    SELECT
                        proof_identity,
                        bundle_identity,
                        signal_freeze_identity,
                        as_of_ms,
                        source_cutoff_open_time_ms,
                        proof_json,
                        persisted_at_ms
                    FROM geometry_proofs
                    WHERE proof_identity IN ({placeholders})
                       OR bundle_identity IN ({placeholders})
                       OR signal_freeze_identity IN ({placeholders})
                    """,
                    (*batch, *batch, *batch),
                ).fetchall()
                for row in rows:
                    proof_identity = str(row["proof_identity"])
                    bundle_identity = str(row["bundle_identity"])
                    signal_identity = str(row["signal_freeze_identity"])
                    proof_json = str(row["proof_json"])
                    if sha256_text(proof_json) != proof_identity:
                        raise StreamExactEvidenceError(
                            "exact evidence Geometry Proof digest mismatch"
                        )
                    as_of_ms = int(row["as_of_ms"])
                    if (
                        source_as_of_ms is not None
                        and as_of_ms > source_as_of_ms
                    ):
                        raise StreamExactEvidenceError(
                            "exact evidence Geometry Proof is future evidence"
                        )
                    proof = _json_object(
                        proof_json,
                        "exact evidence Geometry Proof",
                    )
                    expected_parent = (
                        bundle_identity,
                        signal_identity,
                        as_of_ms,
                        int(row["source_cutoff_open_time_ms"]),
                    )
                    observed_parent = (
                        proof.get("bundle_identity"),
                        proof.get("signal_freeze_identity"),
                        proof.get("as_of_ms"),
                        proof.get("source_cutoff_open_time_ms"),
                    )
                    if observed_parent != expected_parent:
                        raise StreamExactEvidenceError(
                            "exact evidence Geometry Proof parent mismatch"
                        )
                    resolved[proof_identity] = {
                        "object_kind": "geometry_proof",
                        "payload": {
                            "proof_identity": proof_identity,
                            "persisted_at_ms": int(row["persisted_at_ms"]),
                            **proof,
                        },
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
        (
            "market_tape_liquidations",
            "liquidation_identity",
            "market_tape_liquidation",
        ),
        (
            "market_tape_liquidation_coverage",
            "coverage_identity",
            "market_tape_liquidation_coverage",
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
            "market_tape_liquidation": "liquidation_identity",
            "market_tape_liquidation_coverage": "coverage_identity",
        },
    )


def _resolve_options_surface_objects(
    path: Path,
    evidence_identities: tuple[str, ...],
    *,
    source_as_of_ms: int | None,
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    uri = f"{path.resolve().as_uri()}?mode=ro"
    requested = set(evidence_identities)
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
        required_tables = {
            "option_surface_snapshots",
            "option_instrument_metadata",
            "option_instrument_specs",
        }
        if not required_tables.issubset(tables):
            return {}

        resolved: dict[str, dict[str, Any]] = {}
        surface_payloads: list[dict[str, Any]] = []
        for batch in _batches(evidence_identities, size=400):
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"""
                SELECT surface_identity, payload_json
                FROM option_surface_snapshots
                WHERE surface_identity IN ({placeholders})
                """,
                batch,
            ).fetchall()
            for row in rows:
                surface_identity = str(row["surface_identity"])
                payload = _json_object(
                    str(row["payload_json"]),
                    "options surface exact payload",
                )
                if payload.get("surface_identity") != surface_identity:
                    raise StreamExactEvidenceError(
                        "options surface row/payload identity mismatch"
                    )
                contracts = payload.get("contracts")
                if not isinstance(contracts, list) or not contracts:
                    raise StreamExactEvidenceError(
                        "options surface exact payload has no contracts"
                    )
                contract_quote_identities: list[str] = []
                for contract_raw in contracts:
                    contract = _mapping(
                        contract_raw,
                        "options contract quote exact payload",
                    )
                    quote_identity = contract.get("quote_identity")
                    if not isinstance(quote_identity, str):
                        raise StreamExactEvidenceError(
                            "options contract quote identity is invalid"
                        )
                    quote_payload = {
                        key: value
                        for key, value in contract.items()
                        if key != "quote_identity"
                    }
                    if canonical_sha256(quote_payload) != quote_identity:
                        raise StreamExactEvidenceError(
                            "options contract quote identity mismatch"
                        )
                    _verify_not_future(
                        contract,
                        source_as_of_ms=source_as_of_ms,
                        label="options_contract_quote",
                    )
                    contract_quote_identities.append(quote_identity)
                    if quote_identity in requested:
                        resolved[quote_identity] = {
                            "object_kind": "options_contract_quote",
                            "payload": contract,
                        }

                identity_payload = {
                    "adapter_version": payload.get("adapter_version"),
                    "base_coin": payload.get("base_coin"),
                    "contract_quote_identities": tuple(
                        contract_quote_identities
                    ),
                    "exchange": payload.get("exchange"),
                    "ingested_at_ms": payload.get("ingested_at_ms"),
                    "instrument_metadata_identity": payload.get(
                        "instrument_metadata_identity"
                    ),
                    "observed_at_ms": payload.get("observed_at_ms"),
                    "source": payload.get("source"),
                    "source_timestamp_ms": payload.get(
                        "source_timestamp_ms"
                    ),
                }
                if canonical_sha256(identity_payload) != surface_identity:
                    raise StreamExactEvidenceError(
                        "options surface exact identity mismatch"
                    )
                _verify_not_future(
                    payload,
                    source_as_of_ms=source_as_of_ms,
                    label="options_surface_observation",
                )
                resolved[surface_identity] = {
                    "object_kind": "options_surface_observation",
                    "payload": payload,
                }
                surface_payloads.append(payload)

        metadata_identities = {
            str(payload["instrument_metadata_identity"])
            for payload in surface_payloads
            if isinstance(payload.get("instrument_metadata_identity"), str)
            and payload["instrument_metadata_identity"] in requested
        }
        for metadata_identity in sorted(metadata_identities):
            row = connection.execute(
                """
                SELECT payload_json
                FROM option_instrument_metadata
                WHERE metadata_identity=?
                """,
                (metadata_identity,),
            ).fetchone()
            if row is None:
                continue
            metadata = _json_object(
                str(row["payload_json"]),
                "options instrument metadata exact payload",
            )
            instrument_identities = metadata.get("instrument_identities")
            if not isinstance(instrument_identities, list):
                raise StreamExactEvidenceError(
                    "options instrument metadata identities are invalid"
                )
            expected_metadata_identity = canonical_sha256(
                {
                    "base_coin": metadata.get("base_coin"),
                    "exchange": metadata.get("exchange"),
                    "instrument_identities": tuple(
                        str(value) for value in instrument_identities
                    ),
                    "version": "options-instrument-metadata-v1/1",
                }
            )
            if expected_metadata_identity != metadata_identity:
                raise StreamExactEvidenceError(
                    "options instrument metadata identity mismatch"
                )

            specs: list[dict[str, Any]] = []
            for instrument_identity_raw in instrument_identities:
                instrument_identity = str(instrument_identity_raw)
                spec_row = connection.execute(
                    """
                    SELECT payload_json
                    FROM option_instrument_specs
                    WHERE instrument_identity=?
                    """,
                    (instrument_identity,),
                ).fetchone()
                if spec_row is None:
                    raise StreamExactEvidenceError(
                        "options instrument metadata references missing instrument"
                    )
                spec = _json_object(
                    str(spec_row["payload_json"]),
                    "options instrument exact payload",
                )
                if spec.get("instrument_identity") != instrument_identity:
                    raise StreamExactEvidenceError(
                        "options instrument row/payload identity mismatch"
                    )
                spec_identity_payload = {
                    key: value
                    for key, value in spec.items()
                    if key != "instrument_identity"
                }
                if canonical_sha256(spec_identity_payload) != instrument_identity:
                    raise StreamExactEvidenceError(
                        "options instrument identity mismatch"
                    )
                _verify_not_future(
                    spec,
                    source_as_of_ms=source_as_of_ms,
                    label="options_instrument_spec",
                )
                specs.append(spec)
            resolved[metadata_identity] = {
                "object_kind": "options_instrument_metadata",
                "payload": {
                    "metadata_identity": metadata_identity,
                    **metadata,
                    "instrument_specs": specs,
                },
            }
        return resolved
    except sqlite3.DatabaseError as exc:
        raise StreamExactEvidenceError(str(exc)) from exc
    finally:
        connection.close()


def _resolve_onchain_capital_flow_objects(
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
            WHERE type='table' AND name='stablecoin_supply_observations'
            """
        ).fetchone()
        if table is None:
            return {}
        resolved: dict[str, dict[str, Any]] = {}
        for batch in _batches(evidence_identities, size=400):
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"""
                SELECT observation_identity, payload_json
                FROM stablecoin_supply_observations
                WHERE observation_identity IN ({placeholders})
                """,
                batch,
            ).fetchall()
            for row in rows:
                identity = str(row["observation_identity"])
                payload = _json_object(
                    str(row["payload_json"]),
                    "stablecoin supply exact payload",
                )
                if payload.get("observation_identity") != identity:
                    raise StreamExactEvidenceError(
                        "stablecoin supply row/payload identity mismatch"
                    )
                identity_payload = {
                    key: value
                    for key, value in payload.items()
                    if key != "observation_identity"
                }
                if canonical_sha256(identity_payload) != identity:
                    raise StreamExactEvidenceError(
                        "stablecoin supply exact identity mismatch"
                    )
                _verify_not_future(
                    payload,
                    source_as_of_ms=source_as_of_ms,
                    label="stablecoin_supply_observation",
                )
                resolved[identity] = {
                    "object_kind": "stablecoin_supply_observation",
                    "payload": payload,
                }
        return resolved
    except sqlite3.DatabaseError as exc:
        raise StreamExactEvidenceError(str(exc)) from exc
    finally:
        connection.close()


def _resolve_source_contract_objects(
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
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        resolved: dict[str, dict[str, Any]] = {}
        for batch in _batches(evidence_identities, size=300):
            placeholders = ",".join("?" for _ in batch)
            if "source_raw_payloads" in tables:
                rows = connection.execute(
                    f"""
                    SELECT raw_identity, provider, source, channel,
                           symbol, payload_json
                    FROM source_raw_payloads
                    WHERE raw_identity IN ({placeholders})
                    """,
                    batch,
                ).fetchall()
                for row in rows:
                    identity = str(row["raw_identity"])
                    payload_json = str(row["payload_json"])
                    expected_identity = canonical_sha256(
                        {
                            "schema_version": "source-contract-v1/1",
                            "provider": str(row["provider"]),
                            "source": str(row["source"]),
                            "channel": str(row["channel"]),
                            "symbol": str(row["symbol"]),
                            "payload_json": payload_json,
                            "production_authority": False,
                            "real_capital": 0,
                        }
                    )
                    if expected_identity != identity:
                        raise StreamExactEvidenceError(
                            "source raw payload exact identity mismatch"
                        )
                    resolved[identity] = {
                        "object_kind": "source_raw_payload",
                        "payload": {
                            "raw_identity": identity,
                            "provider": str(row["provider"]),
                            "source": str(row["source"]),
                            "channel": str(row["channel"]),
                            "symbol": str(row["symbol"]),
                            "payload": _json_object(
                                payload_json,
                                "source raw exact payload",
                            ),
                        },
                    }

            if "source_envelopes" in tables:
                rows = connection.execute(
                    f"""
                    SELECT envelope_identity, payload_json
                    FROM source_envelopes
                    WHERE envelope_identity IN ({placeholders})
                    """,
                    batch,
                ).fetchall()
                for row in rows:
                    identity = str(row["envelope_identity"])
                    payload = _json_object(
                        str(row["payload_json"]),
                        "source envelope exact payload",
                    )
                    if canonical_sha256(payload) != identity:
                        raise StreamExactEvidenceError(
                            "source envelope exact identity mismatch"
                        )
                    _verify_not_future(
                        payload,
                        source_as_of_ms=source_as_of_ms,
                        label="source_envelope",
                    )
                    resolved[identity] = {
                        "object_kind": "source_envelope",
                        "payload": {
                            "envelope_identity": identity,
                            **payload,
                        },
                    }

            if "source_coverage_events" in tables:
                rows = connection.execute(
                    f"""
                    SELECT coverage_event_identity, payload_json
                    FROM source_coverage_events
                    WHERE coverage_event_identity IN ({placeholders})
                    """,
                    batch,
                ).fetchall()
                for row in rows:
                    identity = str(row["coverage_event_identity"])
                    payload = _json_object(
                        str(row["payload_json"]),
                        "source coverage exact payload",
                    )
                    if canonical_sha256(payload) != identity:
                        raise StreamExactEvidenceError(
                            "source coverage exact identity mismatch"
                        )
                    _verify_not_future(
                        payload,
                        source_as_of_ms=source_as_of_ms,
                        label="source_coverage",
                    )
                    resolved[identity] = {
                        "object_kind": "source_coverage",
                        "payload": {
                            "coverage_event_identity": identity,
                            **payload,
                        },
                    }
        return resolved
    except sqlite3.DatabaseError as exc:
        raise StreamExactEvidenceError(str(exc)) from exc
    finally:
        connection.close()


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
