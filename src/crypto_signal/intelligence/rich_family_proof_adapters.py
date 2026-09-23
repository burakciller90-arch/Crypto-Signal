"""R25 Slice 5: enrich accepted M2–M5 families with deeper accepted freezes.

The enrichments preserve the Slice 3 directional contract. Richer evidence is
context/proof unless a prior accepted directional rule already exists.
"""
from __future__ import annotations

from decimal import Decimal

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyEvidence,
    build_confluence_family_evidence,
)
from crypto_signal.intelligence.derivatives_crowding import (
    DerivativesCrowdingEvidenceFreeze,
    DerivativesCrowdingStatus,
)
from crypto_signal.intelligence.family_proof_adapters import (
    AcceptedFamilyAdapterBundle,
)
from crypto_signal.intelligence.large_transfer_clusters import (
    LargeTransferClusterEvidenceFreeze,
    LargeTransferStatus,
)
from crypto_signal.intelligence.liquidation_heatmap import (
    LiquidationHeatmapEvidenceFreeze,
    LiquidationHeatmapStatus,
    LiquidationSourceQuality,
)
from crypto_signal.intelligence.liquidity_dynamics import LiquiditySourceQuality
from crypto_signal.intelligence.liquidity_structure import (
    LiquidityStructureEvidenceFreeze,
    LiquidityStructureStatus,
)
from crypto_signal.intelligence.liquidity_sweep import (
    LiquiditySweepEvidenceFreeze,
    LiquiditySweepStatus,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.intelligence.order_flow_patterns import (
    AbsorptionEvidenceFreeze,
    DivergenceEvidenceFreeze,
    PatternStatus,
)
from crypto_signal.intelligence.wallet_cohorts import (
    WalletCohortEvidenceFreeze,
    WalletCohortStatus,
)
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
)

RICH_ADAPTER_VERSION = "r25-rich-evidence-adapters-v1/1"
_LIQUIDITY_MAX_AGE_MS = 30_000
_LIQUIDATION_MAX_AGE_MS = 60_000
_ORDER_FLOW_MAX_AGE_MS = 30_000
_DERIVATIVES_MAX_AGE_MS = 30 * 60_000
_ONCHAIN_MAX_AGE_MS = 6 * 60 * 60_000


def enrich_accepted_m2_m5(
    *,
    base: AcceptedFamilyAdapterBundle,
    symbol: str,
    base_asset: str,
    timeframe: str,
    regime: str,
    as_of_ms: int,
    liquidity_structure: LiquidityStructureEvidenceFreeze | None = None,
    liquidity_sweep: LiquiditySweepEvidenceFreeze | None = None,
    liquidation: LiquidationHeatmapEvidenceFreeze | None = None,
    absorption: AbsorptionEvidenceFreeze | None = None,
    divergence: DivergenceEvidenceFreeze | None = None,
    derivatives_crowding: DerivativesCrowdingEvidenceFreeze | None = None,
    wallet_cohorts: tuple[WalletCohortEvidenceFreeze, ...] = (),
    large_transfer_clusters: tuple[LargeTransferClusterEvidenceFreeze, ...] = (),
) -> AcceptedFamilyAdapterBundle:
    """Add richer accepted context without creating new directional shortcuts."""
    _validate_request(symbol, base_asset, timeframe, regime, as_of_ms)

    families = {item.family: item for item in base.families}
    proofs = {item.domain: item for item in base.proof_slices}

    liq_ids: list[str] = []
    liq_engines: list[str] = []
    liq_observed: list[int] = []
    liq_freshness: list[Decimal] = []
    liq_summaries: list[str] = []

    if liquidity_structure is not None:
        structure_analysis = liquidity_structure.analysis
        _require_market(structure_analysis.symbol, structure_analysis.as_of_ms, symbol, as_of_ms)
        if (
            structure_analysis.status is LiquidityStructureStatus.MEASURED
            and structure_analysis.source_quality is LiquiditySourceQuality.GOOD
            and structure_analysis.latest_snapshot_age_ms is not None
            and structure_analysis.latest_snapshot_age_ms <= _LIQUIDITY_MAX_AGE_MS
        ):
            liq_ids.append(liquidity_structure.freeze_identity)
            liq_engines.append(structure_analysis.engine_version)
            liq_observed.append(structure_analysis.observed_at_ms)
            liq_freshness.append(
                _freshness(structure_analysis.latest_snapshot_age_ms, _LIQUIDITY_MAX_AGE_MS)
            )
            liq_summaries.append("persistent_liquidity_structure_context")

    if liquidity_sweep is not None:
        sweep_analysis = liquidity_sweep.analysis
        _require_market(sweep_analysis.symbol, sweep_analysis.as_of_ms, symbol, as_of_ms)
        sweep_age = (
            max(sweep_analysis.latest_snapshot_age_ms, sweep_analysis.latest_trade_age_ms)
            if sweep_analysis.latest_snapshot_age_ms is not None
            and sweep_analysis.latest_trade_age_ms is not None
            else None
        )
        if (
            sweep_analysis.status is LiquiditySweepStatus.MEASURED
            and sweep_analysis.source_quality is LiquiditySourceQuality.GOOD
            and sweep_age is not None
            and sweep_age <= _LIQUIDITY_MAX_AGE_MS
        ):
            liq_ids.append(liquidity_sweep.freeze_identity)
            liq_engines.append(sweep_analysis.engine_version)
            liq_observed.append(sweep_analysis.observed_at_ms)
            liq_freshness.append(_freshness(sweep_age, _LIQUIDITY_MAX_AGE_MS))
            liq_summaries.append(f"liquidity_sweep_{sweep_analysis.sweep_state.value}")

    if liq_ids:
        families[ConfluenceFamily.LIQUIDITY] = _merge_family(
            families[ConfluenceFamily.LIQUIDITY],
            added_ids=tuple(liq_ids),
            added_engines=tuple(liq_engines),
            added_observed=tuple(liq_observed),
            added_freshness=tuple(liq_freshness),
        )
        proofs[ProofEvidenceDomain.LIQUIDITY_MAP] = _merge_proof(
            proofs[ProofEvidenceDomain.LIQUIDITY_MAP],
            added_ids=tuple(liq_ids),
            added_observed=tuple(liq_observed),
            added_freshness=tuple(liq_freshness),
            added_summaries=tuple(liq_summaries),
        )

    if liquidation is not None:
        liquidation_analysis = liquidation.analysis
        _require_market(liquidation_analysis.symbol, liquidation_analysis.as_of_ms, symbol, as_of_ms)
        liquidation_ok = (
            liquidation_analysis.status is LiquidationHeatmapStatus.MEASURED
            and liquidation_analysis.source_quality is LiquidationSourceQuality.GOOD
            and liquidation_analysis.latest_mark_age_ms is not None
            and liquidation_analysis.latest_mark_age_ms <= _LIQUIDATION_MAX_AGE_MS
        )
        if liquidation_ok:
            freshness = _freshness(
                liquidation_analysis.latest_mark_age_ms,
                _LIQUIDATION_MAX_AGE_MS,
            )
            # Liquidation is accepted context inside M2, not an automatic vote.
            families[ConfluenceFamily.LIQUIDITY] = _merge_family(
                families[ConfluenceFamily.LIQUIDITY],
                added_ids=(liquidation.freeze_identity,),
                added_engines=(liquidation_analysis.engine_version,),
                added_observed=(as_of_ms,),
                added_freshness=(freshness,),
            )
            proofs[ProofEvidenceDomain.LIQUIDATION_MAP] = _merge_proof(
                proofs[ProofEvidenceDomain.LIQUIDATION_MAP],
                added_ids=(liquidation.freeze_identity,),
                added_observed=(as_of_ms,),
                added_freshness=(freshness,),
                added_summaries=(
                    f"observed_liquidation_{liquidation_analysis.observed_state.value}",
                    "estimated_leverage_concentration_not_claimed",
                    "retail_stop_locations_not_claimed",
                ),
            )

    pattern_ids: list[str] = []
    pattern_engines: list[str] = []
    pattern_observed: list[int] = []
    pattern_freshness: list[Decimal] = []
    pattern_summaries: list[str] = []
    for pattern, label in (
        (absorption, "absorption"),
        (divergence, "price_cvd_divergence"),
    ):
        if pattern is None:
            continue
        pattern_analysis = pattern.analysis
        _require_market(
            pattern_analysis.symbol,
            pattern_analysis.as_of_ms,
            symbol,
            as_of_ms,
        )
        age = as_of_ms - pattern_analysis.observed_at_ms
        if (
            pattern_analysis.status is PatternStatus.MEASURED
            and 0 <= age <= _ORDER_FLOW_MAX_AGE_MS
        ):
            pattern_ids.append(pattern.freeze_identity)
            pattern_engines.append(pattern_analysis.engine_version)
            pattern_observed.append(pattern_analysis.observed_at_ms)
            pattern_freshness.append(_freshness(age, _ORDER_FLOW_MAX_AGE_MS))
            pattern_summaries.append(
                f"{label}_{'candidate_present' if pattern_analysis.candidates else 'none_observed'}"
            )

    if pattern_ids:
        # Preserve the Slice 3 direction/strength. Patterns are supporting context,
        # never a new long/short rule by themselves.
        families[ConfluenceFamily.ORDER_FLOW] = _merge_family(
            families[ConfluenceFamily.ORDER_FLOW],
            added_ids=tuple(pattern_ids),
            added_engines=tuple(pattern_engines),
            added_observed=tuple(pattern_observed),
            added_freshness=tuple(pattern_freshness),
        )
        proofs[ProofEvidenceDomain.ORDER_FLOW_CVD] = _merge_proof(
            proofs[ProofEvidenceDomain.ORDER_FLOW_CVD],
            added_ids=tuple(pattern_ids),
            added_observed=tuple(pattern_observed),
            added_freshness=tuple(pattern_freshness),
            added_summaries=tuple(pattern_summaries),
        )

    if derivatives_crowding is not None:
        a = derivatives_crowding.analysis
        _require_market(a.symbol, a.as_of_ms, symbol, as_of_ms)
        age = as_of_ms - a.observed_at_ms
        if (
            a.status is DerivativesCrowdingStatus.MEASURED
            and 0 <= age <= _DERIVATIVES_MAX_AGE_MS
        ):
            freshness = _freshness(age, _DERIVATIVES_MAX_AGE_MS)
            families[ConfluenceFamily.DERIVATIVES] = _merge_family(
                families[ConfluenceFamily.DERIVATIVES],
                added_ids=(derivatives_crowding.freeze_identity,),
                added_engines=(liquidation_analysis.engine_version,),
                added_observed=(a.observed_at_ms,),
                added_freshness=(freshness,),
            )
            proofs[ProofEvidenceDomain.DERIVATIVES] = _merge_proof(
                proofs[ProofEvidenceDomain.DERIVATIVES],
                added_ids=(derivatives_crowding.freeze_identity,),
                added_observed=(a.observed_at_ms,),
                added_freshness=(freshness,),
                added_summaries=(
                    f"derivatives_crowding_{a.label.value}",
                    f"crowded_side_{a.crowded_side.value}",
                    "crowding_context_not_directional_rule",
                ),
            )

    onchain_family_ids: list[str] = []
    onchain_family_engines: list[str] = []
    onchain_family_observed: list[int] = []
    onchain_family_freshness: list[Decimal] = []
    onchain_proof_ids: list[str] = []
    onchain_proof_observed: list[int] = []
    onchain_proof_freshness: list[Decimal] = []
    onchain_summaries: list[str] = []

    for cohort in wallet_cohorts:
        cohort_analysis = cohort.analysis
        _require_asset(
            cohort_analysis.asset,
            cohort_analysis.as_of_ms,
            base_asset,
            as_of_ms,
        )
        if cohort_analysis.status is WalletCohortStatus.UNRESOLVED:
            continue
        observed = (
            cohort_analysis.latest_forward_measurement_ms
            if cohort_analysis.latest_forward_measurement_ms is not None
            else as_of_ms
        )
        age = as_of_ms - observed
        if not 0 <= age <= _ONCHAIN_MAX_AGE_MS:
            continue
        freshness = _freshness(age, _ONCHAIN_MAX_AGE_MS)
        onchain_proof_ids.append(cohort.freeze_identity)
        onchain_proof_observed.append(observed)
        onchain_proof_freshness.append(freshness)
        onchain_summaries.append(f"wallet_cohort_{cohort_analysis.status.value}")
        # Registry-only is transparent proof context but does not count as
        # measured M6 family evidence.
        if cohort_analysis.status is WalletCohortStatus.MEASURED:
            onchain_family_ids.append(cohort.freeze_identity)
            onchain_family_engines.append(cohort_analysis.engine_version)
            onchain_family_observed.append(observed)
            onchain_family_freshness.append(freshness)

    for cluster in large_transfer_clusters:
        cluster_analysis = cluster.analysis
        _require_asset(
            cluster_analysis.asset,
            cluster_analysis.as_of_ms,
            base_asset,
            as_of_ms,
        )
        if (
            cluster_analysis.status is not LargeTransferStatus.MEASURED
            or cluster_analysis.observed_at_ms is None
        ):
            continue
        age = as_of_ms - cluster_analysis.observed_at_ms
        if not 0 <= age <= _ONCHAIN_MAX_AGE_MS:
            continue
        freshness = _freshness(age, _ONCHAIN_MAX_AGE_MS)
        onchain_family_ids.append(cluster.freeze_identity)
        onchain_family_engines.append(cluster_analysis.engine_version)
        onchain_family_observed.append(cluster_analysis.observed_at_ms)
        onchain_family_freshness.append(freshness)
        onchain_proof_ids.append(cluster.freeze_identity)
        onchain_proof_observed.append(cluster_analysis.observed_at_ms)
        onchain_proof_freshness.append(freshness)
        onchain_summaries.append(f"large_transfer_{cluster_analysis.label.value}")

    if onchain_family_ids:
        families[ConfluenceFamily.ONCHAIN] = _merge_family(
            families[ConfluenceFamily.ONCHAIN],
            added_ids=tuple(onchain_family_ids),
            added_engines=tuple(onchain_family_engines),
            added_observed=tuple(onchain_family_observed),
            added_freshness=tuple(onchain_family_freshness),
        )
    if onchain_proof_ids:
        proofs[ProofEvidenceDomain.ONCHAIN] = _merge_proof(
            proofs[ProofEvidenceDomain.ONCHAIN],
            added_ids=tuple(onchain_proof_ids),
            added_observed=tuple(onchain_proof_observed),
            added_freshness=tuple(onchain_proof_freshness),
            added_summaries=tuple(onchain_summaries),
        )

    return AcceptedFamilyAdapterBundle(
        families=tuple(sorted(families.values(), key=lambda item: item.family.value)),
        proof_slices=tuple(sorted(proofs.values(), key=lambda item: item.domain.value)),
    )


def _merge_family(
    base: ConfluenceFamilyEvidence,
    *,
    added_ids: tuple[str, ...],
    added_engines: tuple[str, ...],
    added_observed: tuple[int, ...],
    added_freshness: tuple[Decimal, ...],
) -> ConfluenceFamilyEvidence:
    if not added_ids:
        return base
    if not added_observed or not added_freshness:
        raise ValueError("rich family evidence requires time/freshness truth")

    identities = tuple(sorted({*base.source_evidence_identities, *added_ids}))
    engines = tuple(sorted({*base.source_engine_ids, *added_engines}))
    observed_values = (
        *((base.observed_at_ms,) if base.observed_at_ms is not None else ()),
        *added_observed,
    )
    available_values = (
        *((base.market_available_at_ms,) if base.market_available_at_ms is not None else ()),
        *added_observed,
    )
    freshness_values = (
        *((base.freshness_0_1,) if base.freshness_0_1 is not None else ()),
        *added_freshness,
    )
    quality = (
        base.evidence_quality_0_1
        if base.evidence_quality_0_1 is not None
        else Decimal(1)
    )
    direction = (
        base.direction
        if base.state is MetaEvidenceState.OBSERVED
        else MetaDirection.NEUTRAL
    )
    strength = (
        base.directional_strength_0_1
        if base.state is MetaEvidenceState.OBSERVED
        and base.directional_strength_0_1 is not None
        else Decimal(0)
    )
    return build_confluence_family_evidence(
        family=base.family,
        asset=base.asset,
        timeframe=base.timeframe,
        regime=base.regime,
        as_of_ms=base.as_of_ms,
        state=MetaEvidenceState.OBSERVED,
        direction=direction,
        directional_strength_0_1=strength,
        evidence_quality_0_1=quality,
        freshness_0_1=min(freshness_values),
        market_available_at_ms=max(available_values),
        observed_at_ms=max(observed_values),
        source_engine_ids=engines,
        source_evidence_identities=identities,
        material_conflict_identities=base.material_conflict_identities,
        uncertainty_flags=tuple(
            sorted(
                {
                    *(
                        base.uncertainty_flags
                        if base.state is MetaEvidenceState.OBSERVED
                        else ()
                    ),
                    "rich_context_not_trade_authority",
                }
            )
        ),
    )


def _merge_proof(
    base: DecisionProofEvidenceSlice,
    *,
    added_ids: tuple[str, ...],
    added_observed: tuple[int, ...],
    added_freshness: tuple[Decimal, ...],
    added_summaries: tuple[str, ...],
) -> DecisionProofEvidenceSlice:
    if not added_ids:
        return base
    if not added_observed or not added_freshness:
        raise ValueError("rich proof evidence requires time/freshness truth")
    identities = tuple(sorted({*base.evidence_identities, *added_ids}))
    observed_values = (
        *((base.observed_at_ms,) if base.observed_at_ms is not None else ()),
        *added_observed,
    )
    available_values = (
        *((base.market_available_at_ms,) if base.market_available_at_ms is not None else ()),
        *added_observed,
    )
    freshness_values = (
        *((base.freshness_0_1,) if base.freshness_0_1 is not None else ()),
        *added_freshness,
    )
    base_summaries = (
        base.summary_codes
        if base.availability is ProofEvidenceAvailability.AVAILABLE
        else ()
    )
    summaries = tuple(sorted({*base_summaries, *added_summaries}))
    return build_decision_proof_evidence_slice(
        domain=base.domain,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=(
            base.verdict
            if base.availability is ProofEvidenceAvailability.AVAILABLE
            else ProofEvidenceVerdict.NEUTRAL
        ),
        evidence_identities=identities,
        market_available_at_ms=max(available_values),
        observed_at_ms=max(observed_values),
        freshness_0_1=min(freshness_values),
        source_quality="accepted_versioned_rich_freeze_bundle",
        summary_codes=summaries,
    )


def _freshness(age_ms: int, cap_ms: int) -> Decimal:
    if age_ms < 0 or age_ms > cap_ms:
        raise ValueError("rich evidence is stale or future-dated")
    return Decimal(cap_ms - age_ms) / Decimal(cap_ms)


def _validate_request(
    symbol: str,
    base_asset: str,
    timeframe: str,
    regime: str,
    as_of_ms: int,
) -> None:
    if not symbol or symbol != symbol.upper() or not timeframe or not regime:
        raise ValueError("rich adapter requires exact uppercase market context")
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("rich adapter requires exact uppercase base asset")
    if not symbol.startswith(base_asset) or as_of_ms < 0:
        raise ValueError("rich adapter symbol/base asset/as-of mismatch")


def _require_market(
    actual_symbol: str,
    actual_as_of_ms: int,
    symbol: str,
    as_of_ms: int,
) -> None:
    if actual_symbol != symbol or actual_as_of_ms != as_of_ms:
        raise ValueError("rich adapter freeze market/PIT context mismatch")


def _require_asset(
    actual_asset: str,
    actual_as_of_ms: int,
    asset: str,
    as_of_ms: int,
) -> None:
    if actual_asset != asset or actual_as_of_ms != as_of_ms:
        raise ValueError("rich adapter onchain asset/PIT context mismatch")
