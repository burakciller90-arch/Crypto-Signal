"""R25 Slice 3: accepted M2–M5 freezes -> exact-PIT M6 and Decision Proof.

This is a research adapter, not a live collector or order engine. Liquidity, OI,
funding and exchange inflows are context, never fabricated directional votes.
Only agreeing observed order-book AND taker flow AND window-local CVD can
produce the bounded M3 directional vote. All unavailable inputs fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyEvidence,
    build_confluence_family_evidence,
)
from crypto_signal.intelligence.derivatives_dynamics import (
    DerivativesDynamicsEvidenceFreeze,
    DerivativesDynamicsStatus,
)
from crypto_signal.intelligence.exchange_flow import (
    ExchangeFlowEvidenceFreeze,
    ExchangeFlowStatus,
)
from crypto_signal.intelligence.liquidity_dynamics import (
    LiquidityDynamicsEvidenceFreeze,
    LiquidityDynamicsStatus,
    LiquiditySourceQuality,
)
from crypto_signal.intelligence.meta_intelligence import MetaDirection, MetaEvidenceState
from crypto_signal.intelligence.order_flow_microstructure import (
    OrderFlowMicrostructureEvidenceFreeze,
    OrderFlowMicrostructureLabel,
)
from crypto_signal.intelligence.temporal_order_flow import (
    TemporalFlowEvidenceFreeze,
    TemporalFlowQuality,
    TemporalFlowStatus,
)
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
)

ADAPTER_VERSION = "r25-m2-m5-pit-proof-adapters-v1/1"
# Versioned source-age policies are not measured model accuracy or universal feed SLAs.
_MAX_AGE_MS = {
    ConfluenceFamily.LIQUIDITY: 30_000,
    ConfluenceFamily.ORDER_FLOW: 30_000,
    ConfluenceFamily.DERIVATIVES: 30 * 60_000,
    ConfluenceFamily.ONCHAIN: 6 * 60 * 60_000,
}


@dataclass(frozen=True, slots=True)
class AcceptedFamilyAdapterBundle:
    """Four M6 families and six proof domains; geometry/event/R19 remain external."""

    families: tuple[ConfluenceFamilyEvidence, ...]
    proof_slices: tuple[DecisionProofEvidenceSlice, ...]
    production_authority: bool = False
    real_capital: int = 0

    def __post_init__(self) -> None:
        if tuple(item.family for item in self.families) != tuple(
            family for family in sorted(ConfluenceFamily, key=lambda x: x.value)
            if family is not ConfluenceFamily.GEOMETRY
        ):
            raise ValueError("adapter bundle requires four canonical M2–M5 families")
        expected = {
            ProofEvidenceDomain.ORDER_BOOK,
            ProofEvidenceDomain.LIQUIDITY_MAP,
            ProofEvidenceDomain.LIQUIDATION_MAP,
            ProofEvidenceDomain.ORDER_FLOW_CVD,
            ProofEvidenceDomain.DERIVATIVES,
            ProofEvidenceDomain.ONCHAIN,
        }
        if {item.domain for item in self.proof_slices} != expected or (
            len(self.proof_slices) != len(expected)
        ):
            raise ValueError("adapter bundle requires six exact proof domains")
        if self.production_authority or self.real_capital != 0:
            raise ValueError("adapter bundle cannot grant production/real-capital authority")


def adapt_accepted_m2_m5(
    *,
    symbol: str,
    base_asset: str,
    timeframe: str,
    regime: str,
    as_of_ms: int,
    liquidity: LiquidityDynamicsEvidenceFreeze | None = None,
    microstructure: OrderFlowMicrostructureEvidenceFreeze | None = None,
    temporal_flow: TemporalFlowEvidenceFreeze | None = None,
    derivatives: DerivativesDynamicsEvidenceFreeze | None = None,
    exchange_flow: ExchangeFlowEvidenceFreeze | None = None,
) -> AcceptedFamilyAdapterBundle:
    """Adapt exact accepted freezes; never manufacture a missing domain.

    The calling orchestrator must add accepted Geometry, Event Risk and R19
    proof slices before passing the result to issue_unified_decision.
    """
    if not symbol or symbol != symbol.upper() or not timeframe or not regime:
        raise ValueError("adapter requires exact uppercase symbol/timeframe/regime")
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("adapter requires exact uppercase base asset")
    if not symbol.startswith(base_asset) or as_of_ms < 0:
        raise ValueError("adapter symbol/base asset/as-of mismatch")

    for item in (liquidity, microstructure, temporal_flow, derivatives):
        if item is None:
            continue
        analysis = item.analysis
        if analysis.symbol != symbol or analysis.as_of_ms != as_of_ms:
            raise ValueError("adapter freeze market/PIT context mismatch")
        if analysis.observed_at_ms > as_of_ms:
            raise ValueError("adapter freeze contains future observation")
    if exchange_flow is not None:
        chain_context = exchange_flow.analysis
        if (
            chain_context.asset != base_asset
            or chain_context.as_of_ms != as_of_ms
        ):
            raise ValueError("adapter onchain asset/PIT context mismatch")
    if liquidity is not None and microstructure is not None and (
        liquidity.analysis.exchange != microstructure.analysis.exchange
        or liquidity.analysis.market_type != microstructure.analysis.market_type
    ):
        raise ValueError("adapter orderbook source market mismatch")
    if microstructure is not None and temporal_flow is not None and (
        microstructure.analysis.exchange != temporal_flow.analysis.exchange
        or microstructure.analysis.market_type != temporal_flow.analysis.market_type
    ):
        raise ValueError("adapter order flow source market mismatch")

    families: list[ConfluenceFamilyEvidence] = []
    proofs: dict[ProofEvidenceDomain, DecisionProofEvidenceSlice] = {}

    liq = liquidity.analysis if liquidity is not None else None
    liq_ok = (
        liq is not None
        and liq.status is LiquidityDynamicsStatus.MEASURED
        and liq.source_quality is LiquiditySourceQuality.GOOD
        and liq.latest_snapshot_age_ms is not None
        and liq.latest_snapshot_age_ms <= _MAX_AGE_MS[ConfluenceFamily.LIQUIDITY]
    )
    liq_ids = (
        tuple(
            sorted(
                {
                    liquidity.freeze_identity,
                    *(
                        (liquidity.snapshots[-1].snapshot_identity,)
                        if liquidity.snapshots
                        else ()
                    ),
                }
            )
        )
        if liq_ok and liquidity is not None
        else ()
    )
    liq_age = liq.latest_snapshot_age_ms if liq_ok and liq is not None else None
    families.append(
        _family(
            ConfluenceFamily.LIQUIDITY, symbol, timeframe, regime, as_of_ms,
            liq_ids, () if liq is None else (liq.engine_version,),
            None if liq is None else liq.observed_at_ms, liq_age,
        )
    )
    proofs[ProofEvidenceDomain.LIQUIDITY_MAP] = _proof(
        ProofEvidenceDomain.LIQUIDITY_MAP, liq_ids,
        None if liq is None else liq.observed_at_ms, liq_age,
        "accepted_liquidity_dynamics" if liq_ok else "liquidity_not_measured_or_stale",
    )
    # An order-book sample is not evidence of observed liquidations.
    proofs[ProofEvidenceDomain.LIQUIDATION_MAP] = _proof(
        ProofEvidenceDomain.LIQUIDATION_MAP, (), None, None,
        "no_exact_liquidation_freeze_in_slice3",
    )

    micro = microstructure.analysis if microstructure is not None else None
    micro_age = (
        max(
            as_of_ms - micro.book_event_at_ms,
            as_of_ms - micro.latest_trade_event_at_ms,
        )
        if micro is not None and micro.book_event_at_ms is not None
        and micro.latest_trade_event_at_ms is not None
        else None
    )
    micro_ok = (
        micro is not None
        and micro.metrics is not None
        and micro.label is not OrderFlowMicrostructureLabel.UNRESOLVED
        and micro_age is not None
        and micro_age <= _MAX_AGE_MS[ConfluenceFamily.ORDER_FLOW]
    )
    micro_ids = (
        tuple(
            sorted(
                {
                    microstructure.freeze_identity,
                    *(
                        (microstructure.orderbook.snapshot_identity,)
                        if microstructure.orderbook is not None
                        else ()
                    ),
                }
            )
        )
        if micro_ok and microstructure is not None
        else ()
    )
    flow = temporal_flow.analysis if temporal_flow is not None else None
    flow_ok = (
        flow is not None
        and flow.status is TemporalFlowStatus.MEASURED
        and flow.quality is TemporalFlowQuality.GOOD
        and flow.metrics is not None
        and flow.latest_eligible_trade_age_ms is not None
        and flow.latest_eligible_trade_age_ms <= _MAX_AGE_MS[ConfluenceFamily.ORDER_FLOW]
    )
    flow_ids = (
        (temporal_flow.freeze_identity,)
        if flow_ok and temporal_flow is not None else ()
    )
    flow_age = (
        flow.latest_eligible_trade_age_ms
        if flow_ok and flow is not None else None
    )
    flow_observed = flow.observed_at_ms if flow_ok and flow is not None else None

    order_book_ids = tuple(
        sorted(
            {
                *(
                    (liquidity.snapshots[-1].snapshot_identity,)
                    if liq_ok and liquidity is not None and liquidity.snapshots
                    else ()
                ),
                *(
                    (
                        *micro_ids,
                    )
                    if micro_ok and microstructure is not None
                    and microstructure.orderbook is not None else ()
                ),
            }
        )
    )
    book_observed = max(
        (
            *(
                (liq.observed_at_ms,)
                if liq_ok and liq is not None else ()
            ),
            *(
                (micro.observed_at_ms,)
                if micro_ok and micro is not None else ()
            ),
        ),
        default=None,
    )
    book_ages = tuple(
        age for age in (liq_age, micro_age) if age is not None
    )
    proofs[ProofEvidenceDomain.ORDER_BOOK] = _proof(
        ProofEvidenceDomain.ORDER_BOOK, order_book_ids,
        book_observed, max(book_ages) if book_ages else None,
        "accepted_frozen_orderbook" if order_book_ids else "no_fresh_orderbook",
    )
    proofs[ProofEvidenceDomain.ORDER_FLOW_CVD] = _proof(
        ProofEvidenceDomain.ORDER_FLOW_CVD, flow_ids,
        flow_observed, flow_age,
        "window_local_cvd_only" if flow_ids else "no_fresh_window_local_cvd",
    )
    direction: MetaDirection | None = None
    strength = Decimal(0)
    if micro_ok and flow_ok and micro is not None and flow is not None:
        assert micro.metrics is not None
        assert flow.metrics is not None
        if (
            micro.label is OrderFlowMicrostructureLabel.BUY_PRESSURE
            and flow.metrics.delta_notional > 0
        ):
            direction = MetaDirection.BULLISH
        elif (
            micro.label is OrderFlowMicrostructureLabel.SELL_PRESSURE
            and flow.metrics.delta_notional < 0
        ):
            direction = MetaDirection.BEARISH
        if direction is not None:
            strength = min(
                abs(micro.metrics.book_imbalance),
                abs(micro.metrics.taker_flow_imbalance),
                abs(flow.metrics.taker_imbalance),
            )
            if strength == 0:
                direction = None

    of_ids = tuple(sorted((*micro_ids, *flow_ids)))
    of_ages = tuple(age for age in (micro_age if micro_ok else None, flow_age) if age is not None)
    of_observed = max(
        (
            *(
                (micro.observed_at_ms,)
                if micro_ok and micro is not None else ()
            ),
            *((flow_observed,) if flow_observed is not None else ()),
        ),
        default=None,
    )
    families.append(
        _family(
            ConfluenceFamily.ORDER_FLOW, symbol, timeframe, regime, as_of_ms,
            of_ids,
            tuple(
                engine for engine in (
                    micro.engine_version if micro_ok and micro is not None else None,
                    flow.engine_version if flow_ok and flow is not None else None,
                ) if engine is not None
            ),
            of_observed, max(of_ages) if of_ages else None,
            direction=direction, strength=strength,
        )
    )

    deriv = derivatives.analysis if derivatives is not None else None
    deriv_ok = (
        deriv is not None
        and deriv.status is DerivativesDynamicsStatus.MEASURED
        and deriv.latest_observation_age_ms <= _MAX_AGE_MS[ConfluenceFamily.DERIVATIVES]
    )
    deriv_ids = (
        (derivatives.freeze_identity,)
        if deriv_ok and derivatives is not None else ()
    )
    deriv_age = (
        deriv.latest_observation_age_ms if deriv_ok and deriv is not None else None
    )
    families.append(
        _family(
            ConfluenceFamily.DERIVATIVES, symbol, timeframe, regime, as_of_ms,
            deriv_ids, () if deriv is None else (deriv.engine_version,),
            None if deriv is None else deriv.observed_at_ms, deriv_age,
        )
    )
    proofs[ProofEvidenceDomain.DERIVATIVES] = _proof(
        ProofEvidenceDomain.DERIVATIVES, deriv_ids,
        deriv.observed_at_ms if deriv_ok and deriv is not None else None,
        deriv_age, "observed_oi_funding_basis_context" if deriv_ok
        else "derivatives_not_measured_or_stale",
    )

    chain = exchange_flow.analysis if exchange_flow is not None else None
    chain_ok = (
        chain is not None
        and chain.status is ExchangeFlowStatus.MEASURED
        and chain.latest_observation_age_ms is not None
        and chain.latest_observation_age_ms <= _MAX_AGE_MS[ConfluenceFamily.ONCHAIN]
        and chain.observed_at_ms is not None
    )
    chain_ids = (
        (exchange_flow.freeze_identity,)
        if chain_ok and exchange_flow is not None else ()
    )
    chain_age = (
        chain.latest_observation_age_ms if chain_ok and chain is not None else None
    )
    families.append(
        _family(
            ConfluenceFamily.ONCHAIN, symbol, timeframe, regime, as_of_ms,
            chain_ids, () if chain is None else (chain.engine_version,),
            chain.observed_at_ms if chain_ok and chain is not None else None,
            chain_age,
        )
    )
    proofs[ProofEvidenceDomain.ONCHAIN] = _proof(
        ProofEvidenceDomain.ONCHAIN, chain_ids,
        chain.observed_at_ms if chain_ok and chain is not None else None,
        chain_age, "observed_exchange_flow_context" if chain_ok
        else "onchain_not_measured_or_stale",
    )

    return AcceptedFamilyAdapterBundle(
        families=tuple(sorted(families, key=lambda item: item.family.value)),
        proof_slices=tuple(sorted(proofs.values(), key=lambda item: item.domain.value)),
    )


def _freshness(age: int, family: ConfluenceFamily) -> Decimal:
    cap = _MAX_AGE_MS[family]
    if age < 0 or age > cap:
        raise ValueError("accepted adapter evidence is stale or future-dated")
    return Decimal(cap - age) / Decimal(cap)


def _family(
    family: ConfluenceFamily,
    symbol: str,
    timeframe: str,
    regime: str,
    as_of_ms: int,
    identities: tuple[str, ...],
    engines: tuple[str, ...],
    observed: int | None,
    age: int | None,
    *,
    direction: MetaDirection | None = None,
    strength: Decimal = Decimal(0),
) -> ConfluenceFamilyEvidence:
    if not identities:
        return build_confluence_family_evidence(
            family=family, asset=symbol, timeframe=timeframe, regime=regime,
            as_of_ms=as_of_ms, state=MetaEvidenceState.NO_EVIDENCE,
            direction=None, directional_strength_0_1=None,
            evidence_quality_0_1=None, freshness_0_1=None,
            market_available_at_ms=None, observed_at_ms=None,
            uncertainty_flags=("accepted_family_evidence_missing_or_stale",),
        )
    assert observed is not None and age is not None
    # A neutral OBSERVED contribution records accepted context without a vote.
    return build_confluence_family_evidence(
        family=family, asset=symbol, timeframe=timeframe, regime=regime,
        as_of_ms=as_of_ms, state=MetaEvidenceState.OBSERVED,
        direction=direction or MetaDirection.NEUTRAL,
        directional_strength_0_1=strength,
        # 1 means accepted deterministic source completeness, not model accuracy.
        evidence_quality_0_1=Decimal(1),
        freshness_0_1=_freshness(age, family),
        market_available_at_ms=observed,
        observed_at_ms=observed,
        source_engine_ids=engines,
        source_evidence_identities=identities,
        uncertainty_flags=("context_not_trade_authority",),
    )


def _proof(
    domain: ProofEvidenceDomain,
    identities: tuple[str, ...],
    observed: int | None,
    age: int | None,
    summary: str,
) -> DecisionProofEvidenceSlice:
    if not identities:
        return build_decision_proof_evidence_slice(
            domain=domain,
            availability=ProofEvidenceAvailability.INSUFFICIENT,
            verdict=ProofEvidenceVerdict.INSUFFICIENT,
            summary_codes=(summary,),
        )
    assert observed is not None and age is not None
    # Domain-specific age policy; no claim of universal latency.
    family = {
        ProofEvidenceDomain.ORDER_BOOK: ConfluenceFamily.LIQUIDITY,
        ProofEvidenceDomain.LIQUIDITY_MAP: ConfluenceFamily.LIQUIDITY,
        ProofEvidenceDomain.ORDER_FLOW_CVD: ConfluenceFamily.ORDER_FLOW,
        ProofEvidenceDomain.DERIVATIVES: ConfluenceFamily.DERIVATIVES,
        ProofEvidenceDomain.ONCHAIN: ConfluenceFamily.ONCHAIN,
    }[domain]
    return build_decision_proof_evidence_slice(
        domain=domain,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=ProofEvidenceVerdict.NEUTRAL,
        evidence_identities=identities,
        market_available_at_ms=observed,
        observed_at_ms=observed,
        freshness_0_1=_freshness(age, family),
        source_quality="accepted_versioned_freeze",
        summary_codes=(summary,),
    )
