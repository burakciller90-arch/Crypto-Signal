from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from crypto_signal.intelligence.derivatives_dynamics import (
    DerivativesDynamicsEvidenceFreeze,
    DerivativesDynamicsStatus,
    OiPriceState,
)
from crypto_signal.intelligence.liquidation_heatmap import (
    LiquidationHeatmapEvidenceFreeze,
    LiquidationHeatmapStatus,
    ObservedLiquidationState,
)
from crypto_signal.ledger.serialization import canonical_sha256

DERIVATIVES_CROWDING_ENGINE_VERSION = "derivatives-crowding-v2-slice2/1"
DERIVATIVES_CROWDING_FREEZE_SCHEMA_VERSION = "derivatives-crowding-freeze-v1/1"
_BPS = Decimal(10_000)


class DerivativesCrowdingStatus(StrEnum):
    MEASURED = "measured"
    UNRESOLVED = "unresolved"


class DerivativesCrowdingLabel(StrEnum):
    LONG_CROWDING = "long_crowding"
    SHORT_CROWDING = "short_crowding"
    SQUEEZE_RISK = "squeeze_risk"
    DELEVERAGING = "deleveraging"
    BALANCED = "balanced"
    MIXED = "mixed"
    UNRESOLVED = "unresolved"


class CrowdedSide(StrEnum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DerivativesCrowdingConfig:
    funding_extreme_bps: Decimal = Decimal(5)
    funding_percentile_high: Decimal = Decimal("0.80")
    funding_percentile_low: Decimal = Decimal("0.20")
    basis_extreme_bps: Decimal = Decimal(25)
    oi_change_min_fraction: Decimal = Decimal("0.05")
    liquidation_dominance_share: Decimal = Decimal("0.60")
    elevated_mark_movement_bps: Decimal = Decimal(100)

    def __post_init__(self) -> None:
        for label, value in (
            ("funding_extreme_bps", self.funding_extreme_bps),
            ("basis_extreme_bps", self.basis_extreme_bps),
            ("oi_change_min_fraction", self.oi_change_min_fraction),
            ("elevated_mark_movement_bps", self.elevated_mark_movement_bps),
        ):
            if value.is_nan() or value.is_infinite() or value <= 0:
                raise ValueError(f"{label} must be a positive finite Decimal")
        for label, value in (
            ("funding_percentile_high", self.funding_percentile_high),
            ("funding_percentile_low", self.funding_percentile_low),
            ("liquidation_dominance_share", self.liquidation_dominance_share),
        ):
            if value.is_nan() or value.is_infinite() or not Decimal(0) <= value <= Decimal(1):
                raise ValueError(f"{label} must be inside [0,1]")
        if self.funding_percentile_low >= self.funding_percentile_high:
            raise ValueError("funding percentile low must be below high")


DEFAULT_DERIVATIVES_CROWDING_CONFIG = DerivativesCrowdingConfig()


@dataclass(frozen=True, slots=True)
class DerivativesCrowdingMetrics:
    funding_bps: Decimal | None
    funding_percentile_0_1: Decimal | None
    open_interest_change_fraction: Decimal | None
    basis_bps: Decimal | None
    total_liquidation_notional: Decimal
    long_liquidation_share: Decimal | None
    short_liquidation_share: Decimal | None
    mean_abs_mark_return_bps: Decimal | None
    max_abs_mark_return_bps: Decimal | None
    mark_return_count: int

    def __post_init__(self) -> None:
        for label, value in (
            ("funding_bps", self.funding_bps),
            ("funding_percentile_0_1", self.funding_percentile_0_1),
            ("open_interest_change_fraction", self.open_interest_change_fraction),
            ("basis_bps", self.basis_bps),
            ("total_liquidation_notional", self.total_liquidation_notional),
            ("long_liquidation_share", self.long_liquidation_share),
            ("short_liquidation_share", self.short_liquidation_share),
            ("mean_abs_mark_return_bps", self.mean_abs_mark_return_bps),
            ("max_abs_mark_return_bps", self.max_abs_mark_return_bps),
        ):
            if value is not None and (value.is_nan() or value.is_infinite()):
                raise ValueError(f"{label} must be finite")
        if self.total_liquidation_notional < 0 or self.mark_return_count < 0:
            raise ValueError("crowding metrics cannot have negative counts/notional")
        for value in (self.long_liquidation_share, self.short_liquidation_share):
            if value is not None and not Decimal(0) <= value <= Decimal(1):
                raise ValueError("liquidation shares must be inside [0,1]")
        if (
            self.long_liquidation_share is not None
            and self.short_liquidation_share is not None
            and self.long_liquidation_share + self.short_liquidation_share != Decimal(1)
        ):
            raise ValueError("liquidation shares must sum to one")


@dataclass(frozen=True, slots=True)
class DerivativesCrowdingAnalysis:
    evidence_identity: str
    engine_version: str
    exchange: str
    symbol: str
    as_of_ms: int
    observed_at_ms: int
    derivatives_evidence_identity: str
    derivatives_freeze_identity: str
    liquidation_evidence_identity: str
    liquidation_freeze_identity: str
    status: DerivativesCrowdingStatus
    label: DerivativesCrowdingLabel
    crowded_side: CrowdedSide
    squeeze_risk_side: CrowdedSide
    metrics: DerivativesCrowdingMetrics | None
    uncertainty_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.evidence_identity, "crowding evidence identity"),
            (self.derivatives_evidence_identity, "derivatives evidence identity"),
            (self.derivatives_freeze_identity, "derivatives freeze identity"),
            (self.liquidation_evidence_identity, "liquidation evidence identity"),
            (self.liquidation_freeze_identity, "liquidation freeze identity"),
        ):
            _require_sha256(value, label)
        if self.engine_version != DERIVATIVES_CROWDING_ENGINE_VERSION:
            raise ValueError("unsupported derivatives crowding engine version")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("crowding symbol must be uppercase")
        if not 0 <= self.observed_at_ms <= self.as_of_ms:
            raise ValueError("crowding observed_at outside PIT boundary")
        if self.status is DerivativesCrowdingStatus.UNRESOLVED:
            if self.label is not DerivativesCrowdingLabel.UNRESOLVED:
                raise ValueError("unresolved crowding must use unresolved label")
            if self.crowded_side is not CrowdedSide.UNAVAILABLE:
                raise ValueError("unresolved crowding side must be unavailable")
            if self.squeeze_risk_side is not CrowdedSide.UNAVAILABLE:
                raise ValueError("unresolved squeeze side must be unavailable")
            if self.metrics is not None or not self.uncertainty_flags:
                raise ValueError("unresolved crowding requires uncertainty only")
        elif self.metrics is None:
            raise ValueError("measured crowding requires metrics")
        if self.evidence_identity != canonical_sha256(_analysis_payload(self)):
            raise ValueError("derivatives crowding evidence identity mismatch")


@dataclass(frozen=True, slots=True)
class DerivativesCrowdingEvidenceFreeze:
    freeze_identity: str
    schema_version: str
    analysis: DerivativesCrowdingAnalysis
    derivatives_freeze: DerivativesDynamicsEvidenceFreeze
    liquidation_freeze: LiquidationHeatmapEvidenceFreeze

    def __post_init__(self) -> None:
        _require_sha256(self.freeze_identity, "crowding freeze identity")
        if self.schema_version != DERIVATIVES_CROWDING_FREEZE_SCHEMA_VERSION:
            raise ValueError("unsupported crowding freeze schema")
        if self.derivatives_freeze.freeze_identity != self.analysis.derivatives_freeze_identity:
            raise ValueError("crowding derivatives freeze mismatch")
        if self.liquidation_freeze.freeze_identity != self.analysis.liquidation_freeze_identity:
            raise ValueError("crowding liquidation freeze mismatch")
        expected = canonical_sha256(
            {
                "analysis_identity": self.analysis.evidence_identity,
                "derivatives_freeze_identity": self.derivatives_freeze.freeze_identity,
                "liquidation_freeze_identity": self.liquidation_freeze.freeze_identity,
                "schema_version": DERIVATIVES_CROWDING_FREEZE_SCHEMA_VERSION,
            }
        )
        if self.freeze_identity != expected:
            raise ValueError("derivatives crowding freeze identity mismatch")


def analyze_derivatives_crowding(
    derivatives_freeze: DerivativesDynamicsEvidenceFreeze,
    liquidation_freeze: LiquidationHeatmapEvidenceFreeze,
    *,
    config: DerivativesCrowdingConfig = DEFAULT_DERIVATIVES_CROWDING_CONFIG,
) -> DerivativesCrowdingAnalysis:
    return build_derivatives_crowding_evidence_freeze(
        derivatives_freeze,
        liquidation_freeze,
        config=config,
    ).analysis


def build_derivatives_crowding_evidence_freeze(
    derivatives_freeze: DerivativesDynamicsEvidenceFreeze,
    liquidation_freeze: LiquidationHeatmapEvidenceFreeze,
    *,
    config: DerivativesCrowdingConfig = DEFAULT_DERIVATIVES_CROWDING_CONFIG,
) -> DerivativesCrowdingEvidenceFreeze:
    da = derivatives_freeze.analysis
    la = liquidation_freeze.analysis
    if da.exchange.value != la.exchange.value or da.symbol != la.symbol:
        raise ValueError("crowding upstream market context mismatch")
    if da.instrument_type is not liquidation_freeze.coverage.instrument_type:
        raise ValueError("crowding upstream instrument type mismatch")
    if da.as_of_ms != la.as_of_ms:
        raise ValueError("crowding upstream as-of mismatch")

    if (
        da.status is DerivativesDynamicsStatus.UNRESOLVED
        or la.status is LiquidationHeatmapStatus.UNRESOLVED
    ):
        analysis = _unresolved(
            derivatives_freeze,
            liquidation_freeze,
            flags=(
                "derivatives_upstream_unresolved"
                if da.status is DerivativesDynamicsStatus.UNRESOLVED
                else "liquidation_upstream_unresolved",
            ),
        )
    else:
        analysis = _measured(
            derivatives_freeze,
            liquidation_freeze,
            config=config,
        )

    freeze_identity = canonical_sha256(
        {
            "analysis_identity": analysis.evidence_identity,
            "derivatives_freeze_identity": derivatives_freeze.freeze_identity,
            "liquidation_freeze_identity": liquidation_freeze.freeze_identity,
            "schema_version": DERIVATIVES_CROWDING_FREEZE_SCHEMA_VERSION,
        }
    )
    return DerivativesCrowdingEvidenceFreeze(
        freeze_identity=freeze_identity,
        schema_version=DERIVATIVES_CROWDING_FREEZE_SCHEMA_VERSION,
        analysis=analysis,
        derivatives_freeze=derivatives_freeze,
        liquidation_freeze=liquidation_freeze,
    )


def _measured(
    derivatives_freeze: DerivativesDynamicsEvidenceFreeze,
    liquidation_freeze: LiquidationHeatmapEvidenceFreeze,
    *,
    config: DerivativesCrowdingConfig,
) -> DerivativesCrowdingAnalysis:
    da = derivatives_freeze.analysis
    la = liquidation_freeze.analysis
    dm = da.metrics
    assert dm is not None

    total = la.total_bankruptcy_notional or Decimal(0)
    long_notional = la.long_liquidation_notional or Decimal(0)
    short_notional = la.short_liquidation_notional or Decimal(0)
    long_share = None if total == 0 else long_notional / total
    short_share = None if total == 0 else short_notional / total
    mean_move, max_move, return_count = _mark_movement(derivatives_freeze)

    metrics = DerivativesCrowdingMetrics(
        funding_bps=dm.latest_funding_bps,
        funding_percentile_0_1=dm.funding_percentile_0_1,
        open_interest_change_fraction=dm.open_interest_change_fraction,
        basis_bps=dm.latest_basis_bps,
        total_liquidation_notional=total,
        long_liquidation_share=long_share,
        short_liquidation_share=short_share,
        mean_abs_mark_return_bps=mean_move,
        max_abs_mark_return_bps=max_move,
        mark_return_count=return_count,
    )
    label, crowded_side, squeeze_side, flags = _classify(
        da.oi_price_state,
        la.observed_state,
        metrics,
        config,
    )
    payload = {
        "as_of_ms": da.as_of_ms,
        "crowded_side": crowded_side,
        "derivatives_evidence_identity": da.evidence_identity,
        "derivatives_freeze_identity": derivatives_freeze.freeze_identity,
        "engine_version": DERIVATIVES_CROWDING_ENGINE_VERSION,
        "exchange": da.exchange.value,
        "label": label,
        "liquidation_evidence_identity": la.evidence_identity,
        "liquidation_freeze_identity": liquidation_freeze.freeze_identity,
        "metrics": metrics,
        "observed_at_ms": max(da.observed_at_ms, liquidation_freeze.coverage.observed_at_ms),
        "squeeze_risk_side": squeeze_side,
        "status": DerivativesCrowdingStatus.MEASURED,
        "symbol": da.symbol,
        "uncertainty_flags": flags,
    }
    return DerivativesCrowdingAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=DERIVATIVES_CROWDING_ENGINE_VERSION,
        exchange=da.exchange.value,
        symbol=da.symbol,
        as_of_ms=da.as_of_ms,
        observed_at_ms=max(da.observed_at_ms, liquidation_freeze.coverage.observed_at_ms),
        derivatives_evidence_identity=da.evidence_identity,
        derivatives_freeze_identity=derivatives_freeze.freeze_identity,
        liquidation_evidence_identity=la.evidence_identity,
        liquidation_freeze_identity=liquidation_freeze.freeze_identity,
        status=DerivativesCrowdingStatus.MEASURED,
        label=label,
        crowded_side=crowded_side,
        squeeze_risk_side=squeeze_side,
        metrics=metrics,
        uncertainty_flags=flags,
    )


def _classify(
    oi_price_state: OiPriceState,
    liquidation_state: ObservedLiquidationState,
    metrics: DerivativesCrowdingMetrics,
    config: DerivativesCrowdingConfig,
) -> tuple[DerivativesCrowdingLabel, CrowdedSide, CrowdedSide, tuple[str, ...]]:
    funding = metrics.funding_bps
    percentile = metrics.funding_percentile_0_1
    oi = metrics.open_interest_change_fraction
    basis = metrics.basis_bps

    oi_expanding = oi is not None and oi >= config.oi_change_min_fraction
    oi_contracting = oi is not None and oi <= -config.oi_change_min_fraction

    long_crowded = (
        oi_expanding
        and funding is not None
        and funding >= config.funding_extreme_bps
        and percentile is not None
        and percentile >= config.funding_percentile_high
        and basis is not None
        and basis >= config.basis_extreme_bps
    )
    short_crowded = (
        oi_expanding
        and funding is not None
        and funding <= -config.funding_extreme_bps
        and percentile is not None
        and percentile <= config.funding_percentile_low
        and basis is not None
        and basis <= -config.basis_extreme_bps
    )
    elevated_move = (
        metrics.mean_abs_mark_return_bps is not None
        and metrics.mean_abs_mark_return_bps >= config.elevated_mark_movement_bps
    )
    long_liq_dominant = (
        metrics.long_liquidation_share is not None
        and metrics.long_liquidation_share >= config.liquidation_dominance_share
    )
    short_liq_dominant = (
        metrics.short_liquidation_share is not None
        and metrics.short_liquidation_share >= config.liquidation_dominance_share
    )

    if long_crowded and long_liq_dominant and elevated_move:
        return (
            DerivativesCrowdingLabel.SQUEEZE_RISK,
            CrowdedSide.LONG,
            CrowdedSide.LONG,
            (
                "squeeze_risk_is_context_not_forecast",
                "observed_liquidations_do_not_estimate_future_liquidation_zones",
            ),
        )
    if short_crowded and short_liq_dominant and elevated_move:
        return (
            DerivativesCrowdingLabel.SQUEEZE_RISK,
            CrowdedSide.SHORT,
            CrowdedSide.SHORT,
            (
                "squeeze_risk_is_context_not_forecast",
                "observed_liquidations_do_not_estimate_future_liquidation_zones",
            ),
        )
    if oi_contracting and liquidation_state is ObservedLiquidationState.OBSERVED:
        return (
            DerivativesCrowdingLabel.DELEVERAGING,
            CrowdedSide.NONE,
            CrowdedSide.NONE,
            ("deleveraging_context_does_not_identify_actor_or_direction",),
        )
    if long_crowded:
        return (
            DerivativesCrowdingLabel.LONG_CROWDING,
            CrowdedSide.LONG,
            CrowdedSide.NONE,
            ("crowding_context_is_not_trade_command",),
        )
    if short_crowded:
        return (
            DerivativesCrowdingLabel.SHORT_CROWDING,
            CrowdedSide.SHORT,
            CrowdedSide.NONE,
            ("crowding_context_is_not_trade_command",),
        )

    neutral = (
        funding is not None
        and abs(funding) < config.funding_extreme_bps
        and oi is not None
        and abs(oi) < config.oi_change_min_fraction
        and basis is not None
        and abs(basis) < config.basis_extreme_bps
    )
    if neutral and liquidation_state is ObservedLiquidationState.NONE_OBSERVED:
        return (
            DerivativesCrowdingLabel.BALANCED,
            CrowdedSide.NONE,
            CrowdedSide.NONE,
            (),
        )

    flags: list[str] = ["derivatives_components_not_aligned_for_strong_label"]
    if percentile is None:
        flags.append("funding_percentile_unavailable")
    if metrics.mark_return_count == 0:
        flags.append("mark_return_history_unavailable")
    return (
        DerivativesCrowdingLabel.MIXED,
        CrowdedSide.NONE,
        CrowdedSide.NONE,
        tuple(flags),
    )


def _mark_movement(
    freeze: DerivativesDynamicsEvidenceFreeze,
) -> tuple[Decimal | None, Decimal | None, int]:
    prices = tuple(
        item.mark_price
        for item in freeze.observations
        if item.mark_price is not None
    )
    if len(prices) < 2:
        return None, None, 0

    returns = tuple(
        abs((right - left) / left * _BPS)
        for left, right in zip(prices, prices[1:], strict=True)
    )
    return (
        sum(returns, start=Decimal(0)) / Decimal(len(returns)),
        max(returns),
        len(returns),
    )


def _unresolved(
    derivatives_freeze: DerivativesDynamicsEvidenceFreeze,
    liquidation_freeze: LiquidationHeatmapEvidenceFreeze,
    *,
    flags: tuple[str, ...],
) -> DerivativesCrowdingAnalysis:
    da = derivatives_freeze.analysis
    la = liquidation_freeze.analysis
    payload = {
        "as_of_ms": da.as_of_ms,
        "crowded_side": CrowdedSide.UNAVAILABLE,
        "derivatives_evidence_identity": da.evidence_identity,
        "derivatives_freeze_identity": derivatives_freeze.freeze_identity,
        "engine_version": DERIVATIVES_CROWDING_ENGINE_VERSION,
        "exchange": da.exchange.value,
        "label": DerivativesCrowdingLabel.UNRESOLVED,
        "liquidation_evidence_identity": la.evidence_identity,
        "liquidation_freeze_identity": liquidation_freeze.freeze_identity,
        "metrics": None,
        "observed_at_ms": max(da.observed_at_ms, liquidation_freeze.coverage.observed_at_ms),
        "squeeze_risk_side": CrowdedSide.UNAVAILABLE,
        "status": DerivativesCrowdingStatus.UNRESOLVED,
        "symbol": da.symbol,
        "uncertainty_flags": flags,
    }
    return DerivativesCrowdingAnalysis(
        evidence_identity=canonical_sha256(payload),
        engine_version=DERIVATIVES_CROWDING_ENGINE_VERSION,
        exchange=da.exchange.value,
        symbol=da.symbol,
        as_of_ms=da.as_of_ms,
        observed_at_ms=max(da.observed_at_ms, liquidation_freeze.coverage.observed_at_ms),
        derivatives_evidence_identity=da.evidence_identity,
        derivatives_freeze_identity=derivatives_freeze.freeze_identity,
        liquidation_evidence_identity=la.evidence_identity,
        liquidation_freeze_identity=liquidation_freeze.freeze_identity,
        status=DerivativesCrowdingStatus.UNRESOLVED,
        label=DerivativesCrowdingLabel.UNRESOLVED,
        crowded_side=CrowdedSide.UNAVAILABLE,
        squeeze_risk_side=CrowdedSide.UNAVAILABLE,
        metrics=None,
        uncertainty_flags=flags,
    )


def _analysis_payload(analysis: DerivativesCrowdingAnalysis) -> dict[str, object]:
    return {
        "as_of_ms": analysis.as_of_ms,
        "crowded_side": analysis.crowded_side,
        "derivatives_evidence_identity": analysis.derivatives_evidence_identity,
        "derivatives_freeze_identity": analysis.derivatives_freeze_identity,
        "engine_version": analysis.engine_version,
        "exchange": analysis.exchange,
        "label": analysis.label,
        "liquidation_evidence_identity": analysis.liquidation_evidence_identity,
        "liquidation_freeze_identity": analysis.liquidation_freeze_identity,
        "metrics": analysis.metrics,
        "observed_at_ms": analysis.observed_at_ms,
        "squeeze_risk_side": analysis.squeeze_risk_side,
        "status": analysis.status,
        "symbol": analysis.symbol,
        "uncertainty_flags": analysis.uncertainty_flags,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
