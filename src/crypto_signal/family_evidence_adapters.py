from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyEvidence,
    build_confluence_family_evidence,
)
from crypto_signal.intelligence.derivatives_crowding import (
    DerivativesCrowdingEvidenceFreeze,
    DerivativesCrowdingStatus,
)
from crypto_signal.intelligence.derivatives_dynamics import (
    DEFAULT_DERIVATIVES_DYNAMICS_CONFIG,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.intelligence.exchange_flow import (
    DEFAULT_EXCHANGE_FLOW_CONFIG,
    ExchangeFlowEvidenceFreeze,
    ExchangeFlowStatus,
)
from crypto_signal.intelligence.large_transfer_clusters import (
    DEFAULT_LARGE_TRANSFER_CLUSTER_CONFIG,
    LargeTransferClusterEvidenceFreeze,
    LargeTransferStatus,
)
from crypto_signal.intelligence.liquidation_heatmap import (
    DEFAULT_LIQUIDATION_HEATMAP_CONFIG,
    LiquidationHeatmapEvidenceFreeze,
    LiquidationHeatmapStatus,
)
from crypto_signal.intelligence.liquidity_structure import (
    DEFAULT_LIQUIDITY_STRUCTURE_CONFIG,
    LiquidityStructureEvidenceFreeze,
    LiquidityStructureStatus,
)
from crypto_signal.intelligence.liquidity_sweep import (
    DEFAULT_LIQUIDITY_SWEEP_CONFIG,
    LiquiditySweepEvidenceFreeze,
    LiquiditySweepStatus,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.intelligence.order_flow_microstructure import (
    DEFAULT_ORDER_FLOW_MICROSTRUCTURE_CONFIG,
    OrderFlowMicrostructureEvidenceFreeze,
    OrderFlowMicrostructureLabel,
)
from crypto_signal.intelligence.temporal_order_flow import (
    DEFAULT_TEMPORAL_FLOW_CONFIG,
    TemporalFlowEvidenceFreeze,
    TemporalFlowStatus,
)
from crypto_signal.intelligence.wallet_cohorts import (
    WalletCohortEvidenceFreeze,
    WalletCohortStatus,
)
from crypto_signal.ledger.bundle import DecisionFreezeBundle, verify_bundle_identity
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
)
from crypto_signal.signals.models import SignalDirection
from research.alpha_factory.probability_calibration_gate import (
    CalibratedProbabilityEvidence,
)

_ONE = Decimal(1)
_ZERO = Decimal(0)
_Q = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class ProofEvidenceFragment:
    domain: ProofEvidenceDomain
    evidence_identities: tuple[str, ...]
    market_available_at_ms: int
    observed_at_ms: int
    freshness_0_1: Decimal
    source_quality: str
    verdict: ProofEvidenceVerdict
    summary_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.evidence_identities:
            raise ValueError("proof fragment requires evidence identities")
        if tuple(sorted(set(self.evidence_identities))) != self.evidence_identities:
            raise ValueError("proof fragment identities must be canonical")
        if self.market_available_at_ms < 0 or self.observed_at_ms < 0:
            raise ValueError("proof fragment timestamps must be non-negative")
        if self.market_available_at_ms > self.observed_at_ms:
            raise ValueError("proof fragment observed before market availability")
        _unit(self.freshness_0_1, "proof fragment freshness")
        if not self.source_quality.strip():
            raise ValueError("proof fragment source quality must be non-empty")
        if not self.summary_codes:
            raise ValueError("proof fragment requires summary codes")
        if self.verdict is ProofEvidenceVerdict.INSUFFICIENT:
            raise ValueError("available proof fragment cannot be insufficient")


@dataclass(frozen=True, slots=True)
class FamilyEvidenceAdapterResult:
    family_evidence: ConfluenceFamilyEvidence
    proof_fragments: tuple[ProofEvidenceFragment, ...]

    def __post_init__(self) -> None:
        covered = {
            identity
            for fragment in self.proof_fragments
            for identity in fragment.evidence_identities
        }
        if not set(self.family_evidence.source_evidence_identities).issubset(covered):
            raise ValueError(
                "family adapter source evidence must be covered by proof fragments"
            )


def adapt_geometry_bundle(
    bundle: DecisionFreezeBundle,
    *,
    regime: str,
    evidence_quality_0_1: Decimal,
    freshness_0_1: Decimal,
) -> FamilyEvidenceAdapterResult:
    """Adapt the immutable PA/Harmonic/Elliott decision bundle without re-analysis."""
    verify_bundle_identity(bundle)
    _unit(evidence_quality_0_1, "geometry evidence quality")
    _unit(freshness_0_1, "geometry freshness")
    signal = bundle.signal_decision
    direction = _signal_direction(signal.direction)
    if direction is None:
        raise ValueError("geometry adapter requires directional WATCH/ACTIVE signal")
    strength = _q(signal.agreement.confluence_score / Decimal(100))
    observed_at = max(
        item.ingested_at_ms
        for item in bundle.candles
    )
    market_available_at = max(
        item.close_time_ms
        for item in bundle.candles
    )
    family = build_confluence_family_evidence(
        family=ConfluenceFamily.GEOMETRY,
        asset=signal.symbol,
        timeframe=signal.timeframe,
        regime=regime,
        as_of_ms=signal.as_of_ms,
        state=MetaEvidenceState.OBSERVED,
        direction=direction,
        directional_strength_0_1=strength,
        evidence_quality_0_1=evidence_quality_0_1,
        freshness_0_1=freshness_0_1,
        market_available_at_ms=market_available_at,
        observed_at_ms=observed_at,
        source_engine_ids=("decision-freeze-bundle",),
        source_evidence_identities=(bundle.bundle_identity,),
        uncertainty_flags=signal.uncertainty_flags,
    )
    fragments = (
        ProofEvidenceFragment(
            domain=ProofEvidenceDomain.FROZEN_CHART,
            evidence_identities=(bundle.bundle_identity,),
            market_available_at_ms=market_available_at,
            observed_at_ms=observed_at,
            freshness_0_1=freshness_0_1,
            source_quality="accepted_decision_freeze_bundle",
            verdict=ProofEvidenceVerdict.SUPPORT,
            summary_codes=(
                "geometry_exact_decision_freeze_bundle",
                f"signal_state_{signal.state.value}",
            ),
        ),
        ProofEvidenceFragment(
            domain=ProofEvidenceDomain.CONSUMED_CANDLES,
            evidence_identities=(bundle.bundle_identity,),
            market_available_at_ms=market_available_at,
            observed_at_ms=observed_at,
            freshness_0_1=freshness_0_1,
            source_quality="gap_checked_closed_candles",
            verdict=ProofEvidenceVerdict.NEUTRAL,
            summary_codes=("consumed_candles_bound_to_decision_freeze",),
        ),
    )
    return FamilyEvidenceAdapterResult(family, fragments)


def adapt_liquidity_evidence(
    structure: LiquidityStructureEvidenceFreeze,
    sweep: LiquiditySweepEvidenceFreeze,
    *,
    timeframe: str,
    regime: str,
    liquidation: LiquidationHeatmapEvidenceFreeze | None = None,
) -> FamilyEvidenceAdapterResult:
    """M2 stays context-only here; no sweep is converted into a trade direction."""
    _require_same_symbol_asof(
        ("liquidity_structure", structure.analysis.symbol, structure.analysis.as_of_ms),
        ("liquidity_sweep", sweep.analysis.symbol, sweep.analysis.as_of_ms),
    )
    measured_fragments: list[ProofEvidenceFragment] = []
    source_ids: list[str] = []
    freshness_values: list[Decimal] = []
    observed_values: list[int] = []
    market_values: list[int] = []
    flags = set(structure.analysis.uncertainty_flags) | set(
        sweep.analysis.uncertainty_flags
    )

    structure_fresh = _freshness(
        structure.analysis.latest_snapshot_age_ms,
        DEFAULT_LIQUIDITY_STRUCTURE_CONFIG.max_snapshot_age_ms,
    )
    if structure.analysis.status is LiquidityStructureStatus.MEASURED:
        observed = structure.analysis.observed_at_ms
        market = structure.analysis.source_window_end_ms
        assert market is not None
        source_ids.append(structure.freeze_identity)
        freshness_values.append(structure_fresh)
        observed_values.append(observed)
        market_values.append(market)
        measured_fragments.extend(
            (
                ProofEvidenceFragment(
                    domain=ProofEvidenceDomain.ORDER_BOOK,
                    evidence_identities=(structure.freeze_identity,),
                    market_available_at_ms=market,
                    observed_at_ms=observed,
                    freshness_0_1=structure_fresh,
                    source_quality="m2_liquidity_structure_measured",
                    verdict=ProofEvidenceVerdict.NEUTRAL,
                    summary_codes=("persistent_book_structure_measured",),
                ),
                ProofEvidenceFragment(
                    domain=ProofEvidenceDomain.LIQUIDITY_MAP,
                    evidence_identities=(structure.freeze_identity,),
                    market_available_at_ms=market,
                    observed_at_ms=observed,
                    freshness_0_1=structure_fresh,
                    source_quality="m2_liquidity_structure_measured",
                    verdict=ProofEvidenceVerdict.NEUTRAL,
                    summary_codes=("liquidity_structure_context_only",),
                ),
            )
        )

    sweep_fresh = min(
        _freshness(
            sweep.analysis.latest_snapshot_age_ms,
            DEFAULT_LIQUIDITY_SWEEP_CONFIG.max_snapshot_age_ms,
        ),
        _freshness(
            sweep.analysis.latest_trade_age_ms,
            DEFAULT_LIQUIDITY_SWEEP_CONFIG.max_trade_age_ms,
        ),
    )
    if sweep.analysis.status is LiquiditySweepStatus.MEASURED:
        observed = sweep.analysis.observed_at_ms
        market = sweep.analysis.source_window_end_ms
        assert market is not None
        source_ids.append(sweep.freeze_identity)
        freshness_values.append(sweep_fresh)
        observed_values.append(observed)
        market_values.append(market)
        measured_fragments.append(
            ProofEvidenceFragment(
                domain=ProofEvidenceDomain.LIQUIDITY_MAP,
                evidence_identities=(sweep.freeze_identity,),
                market_available_at_ms=market,
                observed_at_ms=observed,
                freshness_0_1=sweep_fresh,
                source_quality="m2_liquidity_sweep_measured",
                verdict=ProofEvidenceVerdict.NEUTRAL,
                summary_codes=(
                    f"liquidity_sweep_{sweep.analysis.sweep_state.value}",
                    "sweep_candidate_not_trade_direction",
                ),
            )
        )

    if liquidation is not None:
        _require_same_symbol_asof(
            ("liquidity_structure", structure.analysis.symbol, structure.analysis.as_of_ms),
            ("liquidation_heatmap", liquidation.analysis.symbol, liquidation.analysis.as_of_ms),
        )
        flags.update(liquidation.analysis.uncertainty_flags)
        if liquidation.analysis.status is LiquidationHeatmapStatus.MEASURED:
            liquidation_fresh = _freshness(
                liquidation.analysis.latest_mark_age_ms,
                DEFAULT_LIQUIDATION_HEATMAP_CONFIG.max_mark_age_ms,
            )
            observed = max(
                liquidation.coverage.observed_at_ms,
                liquidation.mark_reference.ingested_at_ms,
                *(item.ingested_at_ms for item in liquidation.events),
            )
            market = max(
                liquidation.coverage.coverage_end_ms,
                liquidation.mark_reference.event_at_ms,
                *(item.event_at_ms for item in liquidation.events),
            )
            source_ids.append(liquidation.freeze_identity)
            freshness_values.append(liquidation_fresh)
            observed_values.append(observed)
            market_values.append(market)
            measured_fragments.append(
                ProofEvidenceFragment(
                    domain=ProofEvidenceDomain.LIQUIDATION_MAP,
                    evidence_identities=(liquidation.freeze_identity,),
                    market_available_at_ms=market,
                    observed_at_ms=observed,
                    freshness_0_1=liquidation_fresh,
                    source_quality="m2_observed_liquidations_measured",
                    verdict=ProofEvidenceVerdict.NEUTRAL,
                    summary_codes=(
                        f"observed_liquidations_{liquidation.analysis.observed_state.value}",
                        "observed_liquidations_not_future_risk_map",
                    ),
                )
            )

    if not source_ids:
        family = _unavailable_family(
            family=ConfluenceFamily.LIQUIDITY,
            asset=structure.analysis.symbol,
            timeframe=timeframe,
            regime=regime,
            as_of_ms=structure.analysis.as_of_ms,
            flags=tuple(sorted(flags | {"m2_liquidity_not_evaluable"})),
        )
        return FamilyEvidenceAdapterResult(family, ())

    family = build_confluence_family_evidence(
        family=ConfluenceFamily.LIQUIDITY,
        asset=structure.analysis.symbol,
        timeframe=timeframe,
        regime=regime,
        as_of_ms=structure.analysis.as_of_ms,
        state=MetaEvidenceState.ABSTAIN,
        direction=None,
        directional_strength_0_1=_ZERO,
        evidence_quality_0_1=_ONE,
        freshness_0_1=min(freshness_values),
        market_available_at_ms=max(market_values),
        observed_at_ms=max(observed_values),
        source_engine_ids=tuple(
            sorted(
                {
                    structure.analysis.engine_version,
                    sweep.analysis.engine_version,
                    *(
                        (liquidation.analysis.engine_version,)
                        if liquidation is not None
                        else ()
                    ),
                }
            )
        ),
        source_evidence_identities=tuple(sorted(set(source_ids))),
        uncertainty_flags=tuple(
            sorted(flags | {"liquidity_context_not_auto_directional"})
        ),
    )
    return FamilyEvidenceAdapterResult(family, tuple(measured_fragments))


def adapt_order_flow_evidence(
    microstructure: OrderFlowMicrostructureEvidenceFreeze,
    temporal_flow: TemporalFlowEvidenceFreeze,
    *,
    timeframe: str,
    regime: str,
    candidate_direction: MetaDirection,
) -> FamilyEvidenceAdapterResult:
    """Carry only upstream directional pressure; do not infer from raw OI/CVD context."""
    _require_same_symbol_asof(
        (
            "order_flow_microstructure",
            microstructure.analysis.symbol,
            microstructure.analysis.as_of_ms,
        ),
        (
            "temporal_order_flow",
            temporal_flow.analysis.symbol,
            temporal_flow.analysis.as_of_ms,
        ),
    )
    if candidate_direction not in {MetaDirection.BULLISH, MetaDirection.BEARISH}:
        raise ValueError("order-flow adapter candidate direction must be directional")

    micro = microstructure.analysis
    temporal = temporal_flow.analysis
    fragments: list[ProofEvidenceFragment] = []
    source_ids: list[str] = []
    freshness_values: list[Decimal] = []
    observed_values: list[int] = []
    market_values: list[int] = []
    flags = set(micro.uncertainty_flags) | set(temporal.uncertainty_flags)

    direction: MetaDirection | None = None
    strength = _ZERO
    if micro.label is not OrderFlowMicrostructureLabel.UNRESOLVED:
        assert micro.metrics is not None
        micro_fresh = min(
            _freshness(
                micro.as_of_ms - micro.book_event_at_ms
                if micro.book_event_at_ms is not None
                else None,
                DEFAULT_ORDER_FLOW_MICROSTRUCTURE_CONFIG.max_book_age_ms,
            ),
            _freshness(
                micro.as_of_ms - micro.latest_trade_event_at_ms
                if micro.latest_trade_event_at_ms is not None
                else None,
                DEFAULT_ORDER_FLOW_MICROSTRUCTURE_CONFIG.max_trade_age_ms,
            ),
        )
        direction = _microstructure_direction(micro.label)
        if direction in {MetaDirection.BULLISH, MetaDirection.BEARISH}:
            strength = _q(
                min(
                    abs(micro.metrics.book_imbalance),
                    abs(micro.metrics.taker_flow_imbalance),
                )
            )
        verdict = _relative_verdict(direction, candidate_direction)
        market = max(
            item.event_at_ms
            for item in (
                *((microstructure.orderbook,) if microstructure.orderbook else ()),
                *microstructure.trades,
            )
        )
        observed = micro.observed_at_ms
        source_ids.append(microstructure.freeze_identity)
        freshness_values.append(micro_fresh)
        observed_values.append(observed)
        market_values.append(market)
        fragments.append(
            ProofEvidenceFragment(
                domain=ProofEvidenceDomain.ORDER_BOOK,
                evidence_identities=(microstructure.freeze_identity,),
                market_available_at_ms=market,
                observed_at_ms=observed,
                freshness_0_1=micro_fresh,
                source_quality="m3_microstructure_resolved",
                verdict=verdict,
                summary_codes=(
                    f"microstructure_{micro.label.value}",
                    "direction_only_from_resolved_book_plus_taker_state",
                ),
            )
        )

    if temporal.status is TemporalFlowStatus.MEASURED:
        assert temporal.metrics is not None
        temporal_fresh = _freshness(
            temporal.latest_eligible_trade_age_ms,
            DEFAULT_TEMPORAL_FLOW_CONFIG.max_trade_age_ms,
        )
        market = temporal.window_end_ms
        assert market is not None
        observed = temporal.observed_at_ms
        source_ids.append(temporal_flow.freeze_identity)
        freshness_values.append(temporal_fresh)
        observed_values.append(observed)
        market_values.append(market)
        temporal_direction = (
            MetaDirection.BULLISH
            if temporal.metrics.taker_imbalance > 0
            else MetaDirection.BEARISH
            if temporal.metrics.taker_imbalance < 0
            else MetaDirection.NEUTRAL
        )
        fragments.append(
            ProofEvidenceFragment(
                domain=ProofEvidenceDomain.ORDER_FLOW_CVD,
                evidence_identities=(temporal_flow.freeze_identity,),
                market_available_at_ms=market,
                observed_at_ms=observed,
                freshness_0_1=temporal_fresh,
                source_quality="m3_temporal_flow_measured",
                verdict=_relative_verdict(temporal_direction, candidate_direction),
                summary_codes=(
                    "window_local_cvd_measured",
                    "cvd_fragment_not_independent_family_direction",
                ),
            )
        )
        if (
            direction in {MetaDirection.BULLISH, MetaDirection.BEARISH}
            and temporal_direction
            in {MetaDirection.BULLISH, MetaDirection.BEARISH}
            and temporal_direction is not direction
        ):
            flags.add("microstructure_temporal_flow_direction_conflict")

    if not source_ids:
        family = _unavailable_family(
            family=ConfluenceFamily.ORDER_FLOW,
            asset=micro.symbol,
            timeframe=timeframe,
            regime=regime,
            as_of_ms=micro.as_of_ms,
            flags=tuple(sorted(flags | {"m3_order_flow_not_evaluable"})),
        )
        return FamilyEvidenceAdapterResult(family, ())

    state = (
        MetaEvidenceState.OBSERVED
        if direction is not None
        else MetaEvidenceState.ABSTAIN
    )
    family = build_confluence_family_evidence(
        family=ConfluenceFamily.ORDER_FLOW,
        asset=micro.symbol,
        timeframe=timeframe,
        regime=regime,
        as_of_ms=micro.as_of_ms,
        state=state,
        direction=direction,
        directional_strength_0_1=strength,
        evidence_quality_0_1=_ONE,
        freshness_0_1=min(freshness_values),
        market_available_at_ms=max(market_values),
        observed_at_ms=max(observed_values),
        source_engine_ids=tuple(
            sorted({micro.engine_version, temporal.engine_version})
        ),
        source_evidence_identities=tuple(sorted(set(source_ids))),
        material_conflict_identities=(
            (temporal_flow.freeze_identity,)
            if "microstructure_temporal_flow_direction_conflict" in flags
            else ()
        ),
        uncertainty_flags=tuple(sorted(flags)),
    )
    return FamilyEvidenceAdapterResult(family, tuple(fragments))


def adapt_derivatives_evidence(
    crowding: DerivativesCrowdingEvidenceFreeze,
    *,
    timeframe: str,
    regime: str,
) -> FamilyEvidenceAdapterResult:
    """Derivatives crowding remains context. It never becomes long/short by itself."""
    analysis = crowding.analysis
    if analysis.status is not DerivativesCrowdingStatus.MEASURED:
        family = _unavailable_family(
            family=ConfluenceFamily.DERIVATIVES,
            asset=analysis.symbol,
            timeframe=timeframe,
            regime=regime,
            as_of_ms=analysis.as_of_ms,
            flags=tuple(
                sorted(
                    set(analysis.uncertainty_flags)
                    | {"m4_derivatives_not_evaluable"}
                )
            ),
        )
        return FamilyEvidenceAdapterResult(family, ())

    derivatives = crowding.derivatives_freeze.analysis
    liquidation = crowding.liquidation_freeze.analysis
    freshness = min(
        _freshness(
            derivatives.latest_observation_age_ms,
            DEFAULT_DERIVATIVES_DYNAMICS_CONFIG.max_observation_age_ms,
        ),
        _freshness(
            liquidation.latest_mark_age_ms,
            DEFAULT_LIQUIDATION_HEATMAP_CONFIG.max_mark_age_ms,
        ),
    )
    observed = max(
        derivatives.observed_at_ms,
        crowding.liquidation_freeze.coverage.observed_at_ms,
        crowding.liquidation_freeze.mark_reference.ingested_at_ms,
        *(item.ingested_at_ms for item in crowding.liquidation_freeze.events),
    )
    market = max(
        derivatives.source_window_end_ms,
        crowding.liquidation_freeze.coverage.coverage_end_ms,
        crowding.liquidation_freeze.mark_reference.event_at_ms,
        *(item.event_at_ms for item in crowding.liquidation_freeze.events),
    )
    fragment = ProofEvidenceFragment(
        domain=ProofEvidenceDomain.DERIVATIVES,
        evidence_identities=tuple(
            sorted(
                {
                    crowding.freeze_identity,
                    crowding.derivatives_freeze.freeze_identity,
                    crowding.liquidation_freeze.freeze_identity,
                }
            )
        ),
        market_available_at_ms=market,
        observed_at_ms=observed,
        freshness_0_1=freshness,
        source_quality="m4_crowding_measured",
        verdict=ProofEvidenceVerdict.NEUTRAL,
        summary_codes=(
            f"derivatives_crowding_{analysis.label.value}",
            "crowding_context_not_trade_direction",
        ),
    )
    family = build_confluence_family_evidence(
        family=ConfluenceFamily.DERIVATIVES,
        asset=analysis.symbol,
        timeframe=timeframe,
        regime=regime,
        as_of_ms=analysis.as_of_ms,
        state=MetaEvidenceState.ABSTAIN,
        direction=None,
        directional_strength_0_1=_ZERO,
        evidence_quality_0_1=_ONE,
        freshness_0_1=freshness,
        market_available_at_ms=market,
        observed_at_ms=observed,
        source_engine_ids=(analysis.engine_version,),
        source_evidence_identities=(crowding.freeze_identity,),
        uncertainty_flags=tuple(
            sorted(
                set(analysis.uncertainty_flags)
                | {"derivatives_context_not_auto_directional"}
            )
        ),
    )
    return FamilyEvidenceAdapterResult(family, (fragment,))


def adapt_onchain_evidence(
    exchange_flow: ExchangeFlowEvidenceFreeze,
    *,
    market_symbol: str,
    timeframe: str,
    regime: str,
    wallet_cohort: WalletCohortEvidenceFreeze | None = None,
    large_transfers: LargeTransferClusterEvidenceFreeze | None = None,
) -> FamilyEvidenceAdapterResult:
    """M5 context is preserved without equating exchange flow or whales with direction."""
    base_asset = exchange_flow.analysis.asset
    if not market_symbol.startswith(base_asset):
        raise ValueError("on-chain adapter market/base asset mismatch")
    as_of_ms = exchange_flow.analysis.as_of_ms
    available_ids: list[str] = []
    summary: list[str] = []
    flags = set(exchange_flow.analysis.uncertainty_flags)
    observed_values: list[int] = []
    market_values: list[int] = []
    freshness_values: list[Decimal] = []

    if exchange_flow.analysis.status is ExchangeFlowStatus.MEASURED:
        assert exchange_flow.analysis.observed_at_ms is not None
        assert exchange_flow.analysis.source_window_end_ms is not None
        exchange_fresh = _freshness(
            exchange_flow.analysis.latest_observation_age_ms,
            DEFAULT_EXCHANGE_FLOW_CONFIG.max_observation_age_ms,
        )
        available_ids.append(exchange_flow.freeze_identity)
        observed_values.append(exchange_flow.analysis.observed_at_ms)
        market_values.append(exchange_flow.analysis.source_window_end_ms)
        freshness_values.append(exchange_fresh)
        summary.extend(
            (
                f"exchange_flow_{exchange_flow.analysis.label.value}",
                "exchange_flow_context_not_price_direction",
            )
        )

    if wallet_cohort is not None:
        _require_base_asset_asof(
            "wallet_cohort",
            wallet_cohort.analysis.asset,
            wallet_cohort.analysis.as_of_ms,
            base_asset,
            as_of_ms,
        )
        flags.update(wallet_cohort.analysis.uncertainty_flags)
        if wallet_cohort.analysis.status is not WalletCohortStatus.UNRESOLVED:
            available_ids.append(wallet_cohort.freeze_identity)
            structural_time = (
                wallet_cohort.analysis.latest_forward_measurement_ms
                or wallet_cohort.analysis.latest_admission_ms
            )
            assert structural_time is not None
            observed_values.append(structural_time)
            market_values.append(structural_time)
            # Cohort membership is structural registry evidence, not a tick feed.
            freshness_values.append(_ONE)
            summary.extend(
                (
                    f"wallet_cohort_{wallet_cohort.analysis.status.value}",
                    "wallet_registry_structural_context_not_time_decayed",
                )
            )

    if large_transfers is not None:
        _require_base_asset_asof(
            "large_transfers",
            large_transfers.analysis.asset,
            large_transfers.analysis.as_of_ms,
            base_asset,
            as_of_ms,
        )
        flags.update(large_transfers.analysis.uncertainty_flags)
        if large_transfers.analysis.status is LargeTransferStatus.MEASURED:
            assert large_transfers.analysis.source_window_end_ms is not None
            assert large_transfers.analysis.observed_at_ms is not None
            large_fresh = _freshness(
                as_of_ms - large_transfers.analysis.source_window_end_ms,
                DEFAULT_LARGE_TRANSFER_CLUSTER_CONFIG.lookback_ms,
            )
            available_ids.append(large_transfers.freeze_identity)
            observed_values.append(large_transfers.analysis.observed_at_ms)
            market_values.append(large_transfers.analysis.source_window_end_ms)
            freshness_values.append(large_fresh)
            summary.extend(
                (
                    f"large_transfer_{large_transfers.analysis.label.value}",
                    "large_transfer_context_not_actor_intent",
                )
            )

    if not available_ids:
        family = _unavailable_family(
            family=ConfluenceFamily.ONCHAIN,
            asset=market_symbol,
            timeframe=timeframe,
            regime=regime,
            as_of_ms=as_of_ms,
            flags=tuple(sorted(flags | {"m5_onchain_not_evaluable"})),
        )
        return FamilyEvidenceAdapterResult(family, ())

    freshness = min(freshness_values)
    observed = max(observed_values)
    market = max(market_values)
    fragment = ProofEvidenceFragment(
        domain=ProofEvidenceDomain.ONCHAIN,
        evidence_identities=tuple(sorted(set(available_ids))),
        market_available_at_ms=market,
        observed_at_ms=observed,
        freshness_0_1=freshness,
        source_quality="m5_point_in_time_context",
        verdict=ProofEvidenceVerdict.NEUTRAL,
        summary_codes=tuple(sorted(set(summary))),
    )
    family = build_confluence_family_evidence(
        family=ConfluenceFamily.ONCHAIN,
        asset=market_symbol,
        timeframe=timeframe,
        regime=regime,
        as_of_ms=as_of_ms,
        state=MetaEvidenceState.ABSTAIN,
        direction=None,
        directional_strength_0_1=_ZERO,
        evidence_quality_0_1=_ONE,
        freshness_0_1=freshness,
        market_available_at_ms=market,
        observed_at_ms=observed,
        source_engine_ids=tuple(
            sorted(
                {
                    exchange_flow.analysis.engine_version,
                    *(
                        (wallet_cohort.analysis.engine_version,)
                        if wallet_cohort is not None
                        else ()
                    ),
                    *(
                        (large_transfers.analysis.engine_version,)
                        if large_transfers is not None
                        else ()
                    ),
                }
            )
        ),
        source_evidence_identities=tuple(sorted(set(available_ids))),
        uncertainty_flags=tuple(
            sorted(flags | {"onchain_context_not_auto_directional"})
        ),
    )
    return FamilyEvidenceAdapterResult(family, (fragment,))


def build_event_context_fragment(
    event_context: CircuitBreakerAnalysis,
) -> ProofEvidenceFragment:
    """Expose the exact circuit-breaker decision context without making it directional."""
    verdict = (
        ProofEvidenceVerdict.NEUTRAL
        if event_context.state is CircuitBreakerState.CLEAR
        else ProofEvidenceVerdict.CONTRADICT
    )
    identities = {
        event_context.evidence_identity,
        event_context.event_risk_identity,
        event_context.news_evidence_identity,
    }
    if event_context.market_quality_identity is not None:
        identities.add(event_context.market_quality_identity)
    return ProofEvidenceFragment(
        domain=ProofEvidenceDomain.EVENT_CONTEXT,
        evidence_identities=tuple(sorted(identities)),
        market_available_at_ms=event_context.as_of_ms,
        observed_at_ms=event_context.as_of_ms,
        freshness_0_1=_ONE,
        source_quality="accepted_event_risk_circuit_breaker",
        verdict=verdict,
        summary_codes=(
            f"event_context_{event_context.state.value}",
            "event_context_is_risk_gate_not_directional_vote",
        ),
    )


def build_probability_calibration_fragment(
    probability: CalibratedProbabilityEvidence,
) -> ProofEvidenceFragment:
    """Expose exact R19 authorization lineage; no uncalibrated probability is synthesized."""
    return ProofEvidenceFragment(
        domain=ProofEvidenceDomain.PROBABILITY_CALIBRATION,
        evidence_identities=tuple(
            sorted(
                {
                    probability.authorization_identity,
                    probability.calibration_evidence_identity,
                    probability.source_forecast_identity,
                    probability.source_prediction_identity,
                    probability.walk_forward_fit_identity,
                }
            )
        ),
        market_available_at_ms=probability.issued_at_ms,
        observed_at_ms=probability.issued_at_ms,
        freshness_0_1=_ONE,
        source_quality="accepted_walk_forward_probability_calibration",
        verdict=ProofEvidenceVerdict.SUPPORT,
        summary_codes=(
            "probability_calibrated_by_r19",
            "probability_is_authorized_calibration_not_raw_confidence",
        ),
    )


def compose_decision_proof_slices(
    results: Iterable[FamilyEvidenceAdapterResult],
    *,
    extra_fragments: Iterable[ProofEvidenceFragment] = (),
) -> tuple[DecisionProofEvidenceSlice, ...]:
    """Merge adapter fragments into the one-slice-per-domain R20.5 contract."""
    by_domain: dict[ProofEvidenceDomain, list[ProofEvidenceFragment]] = {
        domain: [] for domain in ProofEvidenceDomain
    }
    for result in results:
        for fragment in result.proof_fragments:
            by_domain[fragment.domain].append(fragment)
    for fragment in extra_fragments:
        by_domain[fragment.domain].append(fragment)

    slices: list[DecisionProofEvidenceSlice] = []
    for domain in ProofEvidenceDomain:
        if domain is ProofEvidenceDomain.METHODOLOGY:
            continue
        fragments = by_domain[domain]
        if not fragments:
            slices.append(
                build_decision_proof_evidence_slice(
                    domain=domain,
                    availability=ProofEvidenceAvailability.INSUFFICIENT,
                    verdict=ProofEvidenceVerdict.INSUFFICIENT,
                    summary_codes=(f"{domain.value}_not_available_from_family_adapters",),
                )
            )
            continue

        identities = tuple(
            sorted(
                {
                    identity
                    for fragment in fragments
                    for identity in fragment.evidence_identities
                }
            )
        )
        verdict = _merge_verdicts(fragment.verdict for fragment in fragments)
        slices.append(
            build_decision_proof_evidence_slice(
                domain=domain,
                availability=ProofEvidenceAvailability.AVAILABLE,
                verdict=verdict,
                evidence_identities=identities,
                market_available_at_ms=max(
                    fragment.market_available_at_ms for fragment in fragments
                ),
                observed_at_ms=max(fragment.observed_at_ms for fragment in fragments),
                freshness_0_1=min(
                    fragment.freshness_0_1 for fragment in fragments
                ),
                source_quality="+".join(
                    sorted({fragment.source_quality for fragment in fragments})
                ),
                summary_codes=tuple(
                    sorted(
                        {
                            code
                            for fragment in fragments
                            for code in fragment.summary_codes
                        }
                    )
                ),
            )
        )
    return tuple(slices)


def _unavailable_family(
    *,
    family: ConfluenceFamily,
    asset: str,
    timeframe: str,
    regime: str,
    as_of_ms: int,
    flags: tuple[str, ...],
) -> ConfluenceFamilyEvidence:
    return build_confluence_family_evidence(
        family=family,
        asset=asset,
        timeframe=timeframe,
        regime=regime,
        as_of_ms=as_of_ms,
        state=MetaEvidenceState.NOT_EVALUABLE,
        direction=None,
        directional_strength_0_1=None,
        evidence_quality_0_1=None,
        freshness_0_1=None,
        market_available_at_ms=None,
        observed_at_ms=None,
        uncertainty_flags=flags,
    )


def _relative_verdict(
    evidence_direction: MetaDirection | None,
    candidate_direction: MetaDirection,
) -> ProofEvidenceVerdict:
    if evidence_direction is None or evidence_direction is MetaDirection.NEUTRAL:
        return ProofEvidenceVerdict.NEUTRAL
    if evidence_direction is candidate_direction:
        return ProofEvidenceVerdict.SUPPORT
    return ProofEvidenceVerdict.CONTRADICT


def _microstructure_direction(
    label: OrderFlowMicrostructureLabel,
) -> MetaDirection | None:
    if label is OrderFlowMicrostructureLabel.BUY_PRESSURE:
        return MetaDirection.BULLISH
    if label is OrderFlowMicrostructureLabel.SELL_PRESSURE:
        return MetaDirection.BEARISH
    if label in {
        OrderFlowMicrostructureLabel.BALANCED,
        OrderFlowMicrostructureLabel.MIXED,
    }:
        return MetaDirection.NEUTRAL
    return None


def _signal_direction(direction: SignalDirection) -> MetaDirection | None:
    if direction is SignalDirection.BULLISH:
        return MetaDirection.BULLISH
    if direction is SignalDirection.BEARISH:
        return MetaDirection.BEARISH
    return None


def _freshness(age_ms: int | None, max_age_ms: int) -> Decimal:
    if age_ms is None or max_age_ms <= 0:
        return _ZERO
    if age_ms <= 0:
        return _ONE
    value = _ONE - (Decimal(age_ms) / Decimal(max_age_ms))
    return _q(max(_ZERO, min(_ONE, value)))


def _merge_verdicts(
    verdicts: Iterable[ProofEvidenceVerdict],
) -> ProofEvidenceVerdict:
    values = set(verdicts)
    if ProofEvidenceVerdict.SUPPORT in values and ProofEvidenceVerdict.CONTRADICT in values:
        return ProofEvidenceVerdict.NEUTRAL
    if ProofEvidenceVerdict.CONTRADICT in values:
        return ProofEvidenceVerdict.CONTRADICT
    if ProofEvidenceVerdict.SUPPORT in values:
        return ProofEvidenceVerdict.SUPPORT
    return ProofEvidenceVerdict.NEUTRAL


def _require_same_symbol_asof(
    first: tuple[str, str, int],
    second: tuple[str, str, int],
) -> None:
    if first[1:] != second[1:]:
        raise ValueError(
            f"family adapter context mismatch: {first[0]} vs {second[0]}"
        )


def _require_base_asset_asof(
    label: str,
    asset: str,
    as_of_ms: int,
    expected_asset: str,
    expected_as_of_ms: int,
) -> None:
    if (asset, as_of_ms) != (expected_asset, expected_as_of_ms):
        raise ValueError(f"family adapter context mismatch: {label}")


def _unit(value: Decimal, label: str) -> None:
    if value.is_nan() or value.is_infinite() or not _ZERO <= value <= _ONE:
        raise ValueError(f"{label} must be finite inside [0,1]")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_Q, rounding=ROUND_HALF_UP)
