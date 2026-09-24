"""WC2 live-source adapter for same-cycle untouched-forward R20 issuance.

This module never reconstructs historical outcomes, never backdates issuance and
never creates missing M2-M5 or Event Risk measurements. It adapts only the exact
immutable legacy decision bundle available in the current live freeze cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.exact_decision_composition import compose_exact_decision
from crypto_signal.forecast_stream import ForecastVersionRef
from crypto_signal.intelligence.confluence_matrix_v2 import (
    ConfluenceFamily,
    ConfluenceFamilyEvidence,
    build_confluence_family_evidence,
)
from crypto_signal.intelligence.event_risk import (
    build_event_risk_evidence_freeze,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CIRCUIT_BREAKER_ENGINE_VERSION,
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.intelligence.family_proof_adapters import (
    AcceptedFamilyAdapterBundle,
    adapt_accepted_m2_m5,
)
from crypto_signal.intelligence.meta_intelligence import (
    MetaDirection,
    MetaEvidenceState,
)
from crypto_signal.intelligence.news_event_risk import (
    build_news_evidence_freeze,
)
from crypto_signal.ledger.bundle import (
    DecisionFreezeBundle,
    verify_bundle_identity,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.product.decision_proof import (
    DecisionProofEvidenceSlice,
    ProofEvidenceAvailability,
    ProofEvidenceDomain,
    ProofEvidenceVerdict,
    build_decision_proof_evidence_slice,
)
from crypto_signal.signals.models import SignalDecision, SignalDirection, SignalState
from crypto_signal.unified_decision_runtime import UnifiedDecisionIssuance

WC2_LIVE_SOURCE_ADAPTER_VERSION = "wc2-live-source-adapter-v1/1"
WC2_COLLECTION_PROTOCOL_VERSION_COMPONENT = "wc2_collection_protocol"
WC2_MISSING_CONTEXT_POLICY_VERSION = (
    "wc2-missing-pit-context-fail-closed-v1/1"
)
WC2_UNMEASURED_REGIME = "NOT_MEASURED"
REAL_CAPITAL = 0


@dataclass(frozen=True, slots=True)
class WC2LiveSourceInputs:
    bundle_identity: str
    consumed_candles_identity: str
    geometry_family: ConfluenceFamilyEvidence
    geometry_proof_slices: tuple[DecisionProofEvidenceSlice, ...]
    accepted_m2_m5: AcceptedFamilyAdapterBundle
    event_context: CircuitBreakerAnalysis
    regime: str = WC2_UNMEASURED_REGIME
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.bundle_identity, "WC2 source bundle")
        _require_sha256(
            self.consumed_candles_identity,
            "WC2 consumed candles",
        )
        if self.geometry_family.family is not ConfluenceFamily.GEOMETRY:
            raise ValueError("WC2 live source requires GEOMETRY family")
        domains = tuple(
            sorted(item.domain.value for item in self.geometry_proof_slices)
        )
        expected = tuple(
            sorted(
                (
                    ProofEvidenceDomain.FROZEN_CHART.value,
                    ProofEvidenceDomain.CONSUMED_CANDLES.value,
                )
            )
        )
        if domains != expected:
            raise ValueError(
                "WC2 live source requires exact chart and candle proof"
            )
        required_geometry_sources = {
            self.bundle_identity,
            self.consumed_candles_identity,
        }
        if set(self.geometry_family.source_evidence_identities) != (
            required_geometry_sources
        ):
            raise ValueError("WC2 geometry source lineage mismatch")
        if self.regime != WC2_UNMEASURED_REGIME:
            raise ValueError("WC2 live source cannot invent regime truth")
        if self.event_context.state is not CircuitBreakerState.DEGRADED_DATA:
            raise ValueError(
                "WC2 missing-context source must fail closed to DEGRADED_DATA"
            )
        if (
            self.production_authority
            or self.real_capital != REAL_CAPITAL
            or self.accepted_m2_m5.production_authority
            or self.accepted_m2_m5.real_capital != REAL_CAPITAL
        ):
            raise ValueError("WC2 live source cannot grant authority")


def adapt_same_cycle_legacy_bundle(
    bundle: DecisionFreezeBundle,
    *,
    base_asset: str,
) -> WC2LiveSourceInputs:
    """Adapt exact immutable live bundle without adding unavailable evidence."""
    verify_bundle_identity(bundle)
    signal = bundle.signal_decision
    if signal.state not in {SignalState.WATCH, SignalState.ACTIVE}:
        raise ValueError(
            "WC2 R20 source requires fresh WATCH or ACTIVE signal"
        )
    if signal.geometry is None or signal.direction is SignalDirection.NONE:
        raise ValueError("WC2 R20 source requires frozen directional geometry")
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("WC2 base asset must be uppercase")
    if not signal.symbol.startswith(base_asset):
        raise ValueError("WC2 signal/base asset mismatch")

    candles_identity = canonical_sha256(bundle.candles)
    source_ids = tuple(
        sorted((bundle.bundle_identity, candles_identity))
    )
    engine_ids = tuple(
        sorted(
            {
                f"legacy_signal:{signal.signal_version}",
                *(
                    f"{item.methodology.value}:{item.version}"
                    for item in signal.methodology_versions
                ),
            }
        )
    )

    has_opposition = signal.agreement.opposing_method_count > 0
    direction = (
        None
        if has_opposition
        else _meta_direction(signal.direction)
    )
    state = (
        MetaEvidenceState.ABSTAIN
        if has_opposition
        else MetaEvidenceState.OBSERVED
    )
    strength = (
        signal.agreement.confluence_score / Decimal(100)
    )
    quality = (
        Decimal(signal.agreement.resolved_method_count)
        / Decimal(signal.agreement.total_methodology_slots)
    )
    uncertainty = {
        "legacy_geometry_source_is_not_probability",
        "same_pit_snapshot_freshness_not_predictive_quality",
        "regime_not_measured",
    }
    if has_opposition:
        uncertainty.add("legacy_methodology_opposition_forces_geometry_abstain")

    geometry = build_confluence_family_evidence(
        family=ConfluenceFamily.GEOMETRY,
        asset=signal.symbol,
        timeframe=signal.timeframe,
        regime=WC2_UNMEASURED_REGIME,
        as_of_ms=signal.as_of_ms,
        state=state,
        direction=direction,
        directional_strength_0_1=strength,
        evidence_quality_0_1=quality,
        freshness_0_1=Decimal(1),
        market_available_at_ms=signal.as_of_ms,
        observed_at_ms=signal.as_of_ms,
        source_engine_ids=engine_ids,
        source_evidence_identities=source_ids,
        uncertainty_flags=tuple(sorted(uncertainty)),
    )

    chart = build_decision_proof_evidence_slice(
        domain=ProofEvidenceDomain.FROZEN_CHART,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=ProofEvidenceVerdict.NEUTRAL,
        evidence_identities=(bundle.bundle_identity,),
        market_available_at_ms=signal.as_of_ms,
        observed_at_ms=signal.as_of_ms,
        freshness_0_1=Decimal(1),
        source_quality="exact_immutable_legacy_freeze",
        summary_codes=(
            "legacy_bundle_exact_identity",
            "same_pit_snapshot_not_predictive_quality",
        ),
    )
    candles = build_decision_proof_evidence_slice(
        domain=ProofEvidenceDomain.CONSUMED_CANDLES,
        availability=ProofEvidenceAvailability.AVAILABLE,
        verdict=ProofEvidenceVerdict.NEUTRAL,
        evidence_identities=(candles_identity,),
        market_available_at_ms=signal.as_of_ms,
        observed_at_ms=signal.as_of_ms,
        freshness_0_1=Decimal(1),
        source_quality="exact_immutable_consumed_candles",
        summary_codes=(
            "consumed_candle_content_digest",
            "same_pit_snapshot_not_predictive_quality",
        ),
    )

    accepted = adapt_accepted_m2_m5(
        symbol=signal.symbol,
        base_asset=base_asset,
        timeframe=signal.timeframe,
        regime=WC2_UNMEASURED_REGIME,
        as_of_ms=signal.as_of_ms,
    )
    event_context = build_missing_pit_event_context(
        asset=base_asset,
        as_of_ms=signal.as_of_ms,
    )
    return WC2LiveSourceInputs(
        bundle_identity=bundle.bundle_identity,
        consumed_candles_identity=candles_identity,
        geometry_family=geometry,
        geometry_proof_slices=(chart, candles),
        accepted_m2_m5=accepted,
        event_context=event_context,
    )


def build_missing_pit_event_context(
    *,
    asset: str,
    as_of_ms: int,
) -> CircuitBreakerAnalysis:
    """Fail closed when exact PIT Event Source/market quality is not wired."""
    event = build_event_risk_evidence_freeze(
        (),
        coverage=None,
        asset=asset,
        as_of_ms=as_of_ms,
    ).analysis
    news = build_news_evidence_freeze(
        (),
        asset=asset,
        as_of_ms=as_of_ms,
    ).analysis
    triggers = tuple(
        sorted(
            (
                "event_risk_degraded_data",
                "market_quality_unavailable",
                "news_evidence_unresolved",
            )
        )
    )
    uncertainty = tuple(
        sorted(
            (
                "circuit_breaker_has_no_trade_or_order_authority",
                "missing_pit_context_forces_degraded_data",
                "no_quantitative_market_quality_threshold_asserted",
            )
        )
    )
    payload = {
        "as_of_ms": as_of_ms,
        "asset": asset,
        "engine_version": CIRCUIT_BREAKER_ENGINE_VERSION,
        "event_risk_identity": event.evidence_identity,
        "market_quality_identity": None,
        "news_evidence_identity": news.evidence_identity,
        "policy_version": WC2_MISSING_CONTEXT_POLICY_VERSION,
        "real_capital": REAL_CAPITAL,
        "state": CircuitBreakerState.DEGRADED_DATA,
        "triggers": triggers,
        "uncertainty_flags": uncertainty,
    }
    return CircuitBreakerAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=CIRCUIT_BREAKER_ENGINE_VERSION,
        policy_version=WC2_MISSING_CONTEXT_POLICY_VERSION,
        asset=asset,
        as_of_ms=as_of_ms,
        state=CircuitBreakerState.DEGRADED_DATA,
        event_risk_identity=event.evidence_identity,
        news_evidence_identity=news.evidence_identity,
        market_quality_identity=None,
        triggers=triggers,
        uncertainty_flags=uncertainty,
    )


def issue_accepted_wc2_live_source(
    signal: SignalDecision,
    inputs: WC2LiveSourceInputs,
    *,
    issued_at_ms: int,
    horizon_bars: int,
    target_label: str,
    base_asset: str,
    ledger: ImmutableDecisionEvidenceLedger,
    collection_protocol_identity: str | None = None,
) -> UnifiedDecisionIssuance:
    """Issue exact R20 from already accepted WC2 PIT inputs.

    This entry point exists for crash recovery from a durable pre-issuance
    receipt. It accepts no market reads and cannot alter the original PIT
    source or issuance timestamp.
    """
    if issued_at_ms < signal.as_of_ms:
        raise ValueError("WC2 issuance cannot predate signal as-of")
    if horizon_bars <= 0:
        raise ValueError("WC2 horizon bars must be positive")
    if not target_label.strip():
        raise ValueError("WC2 target label must be non-empty")
    if not base_asset or base_asset != base_asset.upper():
        raise ValueError("WC2 base asset must be uppercase")
    if not signal.symbol.startswith(base_asset):
        raise ValueError("WC2 signal/base asset mismatch")
    if signal.geometry is None:
        raise ValueError("WC2 accepted source requires frozen geometry")
    if target_label not in {item.label for item in signal.geometry.targets}:
        raise ValueError("WC2 accepted source target is not frozen geometry")
    if collection_protocol_identity is not None:
        _require_sha256(
            collection_protocol_identity,
            "WC2 collection protocol",
        )

    version_refs = [
        ForecastVersionRef(
            "wc2_live_source_adapter",
            WC2_LIVE_SOURCE_ADAPTER_VERSION,
        ),
    ]
    if collection_protocol_identity is not None:
        version_refs.append(
            ForecastVersionRef(
                WC2_COLLECTION_PROTOCOL_VERSION_COMPONENT,
                collection_protocol_identity,
            )
        )

    return compose_exact_decision(
        signal=signal,
        base_asset=base_asset,
        regime=inputs.regime,
        geometry_family=inputs.geometry_family,
        geometry_proof_slices=inputs.geometry_proof_slices,
        accepted_m2_m5=inputs.accepted_m2_m5,
        event_context=inputs.event_context,
        issued_at_ms=issued_at_ms,
        horizon_bars=horizon_bars,
        target_label=target_label,
        ledger=ledger,
        forecast_version_refs=tuple(version_refs),
        forecast_source_evidence_identities=(
            ()
            if collection_protocol_identity is None
            else (collection_protocol_identity,)
        ),
    )


def issue_same_cycle_untouched_forward_forecast(
    bundle: DecisionFreezeBundle,
    *,
    frozen_at_ms: int,
    issued_at_ms: int,
    maximum_issuance_delay_ms: int,
    horizon_bars: int,
    base_asset: str,
    ledger: ImmutableDecisionEvidenceLedger,
    collection_protocol_identity: str | None = None,
) -> UnifiedDecisionIssuance:
    """Issue R20 only from a fresh same-cycle immutable bundle.

    Target selection is the first target already frozen in the source geometry.
    Horizon and maximum issuance delay are explicit caller-owned preregistration
    inputs; this function deliberately provides no defaults.
    """
    if maximum_issuance_delay_ms <= 0:
        raise ValueError("WC2 maximum issuance delay must be positive")
    if horizon_bars <= 0:
        raise ValueError("WC2 horizon bars must be positive")

    verify_bundle_identity(bundle)
    signal = bundle.signal_decision
    if frozen_at_ms < signal.as_of_ms:
        raise ValueError("WC2 source freeze timestamp predates signal as-of")
    if issued_at_ms < frozen_at_ms:
        raise ValueError("WC2 issuance cannot be backdated before freeze")
    if issued_at_ms - frozen_at_ms > maximum_issuance_delay_ms:
        raise ValueError(
            "WC2 fresh source exceeded preregistered issuance delay"
        )
    if signal.geometry is None or not signal.geometry.targets:
        raise ValueError("WC2 forecast requires frozen geometry target")

    inputs = adapt_same_cycle_legacy_bundle(
        bundle,
        base_asset=base_asset,
    )
    first_target = signal.geometry.targets[0]
    return issue_accepted_wc2_live_source(
        signal,
        inputs,
        issued_at_ms=issued_at_ms,
        horizon_bars=horizon_bars,
        target_label=first_target.label,
        base_asset=base_asset,
        ledger=ledger,
        collection_protocol_identity=collection_protocol_identity,
    )


def _meta_direction(direction: SignalDirection) -> MetaDirection:
    if direction is SignalDirection.BULLISH:
        return MetaDirection.BULLISH
    if direction is SignalDirection.BEARISH:
        return MetaDirection.BEARISH
    raise ValueError("WC2 live source requires directional signal")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase SHA256")
