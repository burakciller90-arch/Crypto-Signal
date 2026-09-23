from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.data.market_quality_risk import MarketQualityRiskObservation
from crypto_signal.intelligence.event_risk import EventRiskAnalysis, EventRiskState
from crypto_signal.intelligence.news_event_risk import (
    NewsEvidenceAnalysis,
    NewsEvidenceState,
)
from crypto_signal.ledger.serialization import canonical_sha256

CIRCUIT_BREAKER_ENGINE_VERSION = "event-risk-circuit-breaker-v1-slice3/1"
CIRCUIT_BREAKER_POLICY_SCHEMA_VERSION = "event-risk-circuit-breaker-policy-v1/1"
REAL_CAPITAL = 0


class CircuitBreakerState(StrEnum):
    CLEAR = "clear"
    CAUTION = "caution"
    EVENT_BLOCK = "event_block"
    DEGRADED_DATA = "degraded_data"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    policy_version: str
    max_market_quality_age_ms: int
    max_spread_bps: Decimal
    max_depth_loss_fraction: Decimal
    max_feed_delay_ms: int
    max_price_gap_fraction: Decimal
    max_provider_disagreement_bps: Decimal

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("circuit-breaker policy_version must be non-empty")
        if self.max_market_quality_age_ms <= 0 or self.max_feed_delay_ms <= 0:
            raise ValueError("circuit-breaker age/delay thresholds must be positive")
        for value, label in (
            (self.max_spread_bps, "max_spread_bps"),
            (self.max_depth_loss_fraction, "max_depth_loss_fraction"),
            (self.max_price_gap_fraction, "max_price_gap_fraction"),
            (
                self.max_provider_disagreement_bps,
                "max_provider_disagreement_bps",
            ),
        ):
            if value.is_nan() or value.is_infinite() or value <= Decimal(0):
                raise ValueError(f"{label} must be finite and positive")
        if self.max_depth_loss_fraction > Decimal(1):
            raise ValueError("max_depth_loss_fraction must be inside (0,1]")


@dataclass(frozen=True, slots=True)
class CircuitBreakerAnalysis:
    evidence_identity: str
    engine_version: str
    policy_version: str
    asset: str
    as_of_ms: int
    state: CircuitBreakerState
    event_risk_identity: str
    news_evidence_identity: str
    market_quality_identity: str | None
    triggers: tuple[str, ...]
    uncertainty_flags: tuple[str, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.evidence_identity, "circuit-breaker evidence identity")
        _require_sha256(self.event_risk_identity, "circuit-breaker event-risk identity")
        _require_sha256(self.news_evidence_identity, "circuit-breaker news identity")
        if self.market_quality_identity is not None:
            _require_sha256(
                self.market_quality_identity,
                "circuit-breaker market-quality identity",
            )
        if self.engine_version != CIRCUIT_BREAKER_ENGINE_VERSION:
            raise ValueError("unsupported circuit-breaker engine version")
        if not self.policy_version.strip():
            raise ValueError("circuit-breaker policy_version must be non-empty")
        if not self.asset or self.asset != self.asset.upper():
            raise ValueError("circuit-breaker asset must be non-empty uppercase")
        if self.as_of_ms < 0:
            raise ValueError("circuit-breaker as_of_ms must be non-negative")
        if tuple(sorted(set(self.triggers))) != self.triggers:
            raise ValueError("circuit-breaker triggers must be unique and sorted")
        if tuple(sorted(set(self.uncertainty_flags))) != self.uncertainty_flags:
            raise ValueError("circuit-breaker uncertainty flags must be unique and sorted")
        if self.state is not CircuitBreakerState.CLEAR and not self.triggers:
            raise ValueError("non-clear circuit-breaker state requires triggers")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("circuit-breaker evidence identity mismatch")


def evaluate_circuit_breaker(
    event_risk: EventRiskAnalysis,
    news_evidence: NewsEvidenceAnalysis,
    market_quality: MarketQualityRiskObservation | None,
    *,
    config: CircuitBreakerConfig,
) -> CircuitBreakerAnalysis:
    if event_risk.asset != news_evidence.asset:
        raise ValueError("circuit-breaker source assets must match")
    if event_risk.as_of_ms != news_evidence.as_of_ms:
        raise ValueError("circuit-breaker source as_of values must match")

    asset = event_risk.asset
    as_of_ms = event_risk.as_of_ms
    triggers: set[str] = set()
    uncertainty: set[str] = {
        "circuit_breaker_is_versioned_research_policy_not_universal_law",
        "circuit_breaker_has_no_trade_or_order_authority",
    }

    degraded = False
    abstain = False

    if event_risk.state is EventRiskState.DEGRADED_DATA:
        degraded = True
        triggers.add("event_risk_degraded_data")
    elif event_risk.state is EventRiskState.EVENT_BLOCK:
        triggers.add("structured_event_block")
    elif event_risk.state is EventRiskState.PRE_EVENT_CAUTION:
        triggers.add("structured_event_pre_caution")
    elif event_risk.state is EventRiskState.POST_EVENT_STABILIZATION:
        triggers.add("structured_event_post_stabilization")

    if news_evidence.state is NewsEvidenceState.PROVIDER_DISAGREEMENT:
        abstain = True
        triggers.add("news_provider_disagreement")
    elif news_evidence.state is NewsEvidenceState.DEGRADED_DATA:
        degraded = True
        triggers.add("news_evidence_degraded_data")
    elif news_evidence.state is NewsEvidenceState.UNRESOLVED:
        degraded = True
        triggers.add("news_evidence_unresolved")
    elif news_evidence.state is NewsEvidenceState.SINGLE_SOURCE_CONTEXT:
        triggers.add("news_single_source_context")

    market_identity: str | None = None
    if market_quality is None:
        degraded = True
        triggers.add("market_quality_unavailable")
    else:
        if market_quality.asset != asset:
            raise ValueError("circuit-breaker market-quality asset mismatch")
        if market_quality.observed_at_ms > as_of_ms:
            raise ValueError("circuit-breaker market-quality evidence is from the future")
        market_identity = market_quality.observation_identity
        age_ms = as_of_ms - market_quality.observed_at_ms
        if age_ms > config.max_market_quality_age_ms:
            degraded = True
            triggers.add("market_quality_stale")
        if not market_quality.complete:
            degraded = True
            triggers.add("market_quality_incomplete")
        else:
            assert market_quality.spread_bps is not None
            assert market_quality.depth_loss_fraction is not None
            assert market_quality.feed_delay_ms is not None
            assert market_quality.price_gap_fraction is not None
            assert market_quality.provider_disagreement_bps is not None

            if market_quality.spread_bps > config.max_spread_bps:
                abstain = True
                triggers.add("abnormal_spread")
            if (
                market_quality.depth_loss_fraction
                > config.max_depth_loss_fraction
            ):
                abstain = True
                triggers.add("depth_loss")
            if market_quality.feed_delay_ms > config.max_feed_delay_ms:
                abstain = True
                triggers.add("feed_delay")
            if market_quality.price_gap_fraction > config.max_price_gap_fraction:
                abstain = True
                triggers.add("price_gap")
            if (
                market_quality.provider_disagreement_bps
                > config.max_provider_disagreement_bps
            ):
                abstain = True
                triggers.add("market_provider_disagreement")

    if abstain:
        state = CircuitBreakerState.ABSTAIN
    elif event_risk.state is EventRiskState.EVENT_BLOCK:
        state = CircuitBreakerState.EVENT_BLOCK
    elif degraded:
        state = CircuitBreakerState.DEGRADED_DATA
    elif (
        event_risk.state
        in {
            EventRiskState.PRE_EVENT_CAUTION,
            EventRiskState.POST_EVENT_STABILIZATION,
        }
        or news_evidence.state is NewsEvidenceState.SINGLE_SOURCE_CONTEXT
    ):
        state = CircuitBreakerState.CAUTION
    else:
        state = CircuitBreakerState.CLEAR

    if state is CircuitBreakerState.CLEAR:
        triggers.clear()

    ordered_triggers = tuple(sorted(triggers))
    ordered_uncertainty = tuple(sorted(uncertainty))
    payload = {
        "as_of_ms": as_of_ms,
        "asset": asset,
        "engine_version": CIRCUIT_BREAKER_ENGINE_VERSION,
        "event_risk_identity": event_risk.evidence_identity,
        "market_quality_identity": market_identity,
        "news_evidence_identity": news_evidence.evidence_identity,
        "policy_version": config.policy_version,
        "real_capital": REAL_CAPITAL,
        "state": state,
        "triggers": ordered_triggers,
        "uncertainty_flags": ordered_uncertainty,
    }
    return CircuitBreakerAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=CIRCUIT_BREAKER_ENGINE_VERSION,
        policy_version=config.policy_version,
        asset=asset,
        as_of_ms=as_of_ms,
        state=state,
        event_risk_identity=event_risk.evidence_identity,
        news_evidence_identity=news_evidence.evidence_identity,
        market_quality_identity=market_identity,
        triggers=ordered_triggers,
        uncertainty_flags=ordered_uncertainty,
    )


def _analysis_payload(analysis: CircuitBreakerAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "asset": analysis.asset,
        "engine_version": analysis.engine_version,
        "event_risk_identity": analysis.event_risk_identity,
        "market_quality_identity": analysis.market_quality_identity,
        "news_evidence_identity": analysis.news_evidence_identity,
        "policy_version": analysis.policy_version,
        "real_capital": analysis.real_capital,
        "state": analysis.state,
        "triggers": analysis.triggers,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
