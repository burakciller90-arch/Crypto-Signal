"""R24 Performance & Trust Center.

Deterministic read-only projections over accepted immutable evidence. Backtest,
walk-forward and live untouched-forward cohorts remain explicitly separated.
Unavailable metrics stay unavailable; no performance number is invented.
REAL_CAPITAL=0.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum

from crypto_signal.confluence.models import PairRelation
from crypto_signal.forecast_stream import (
    ForecastResolutionState,
    ForecastStreamSnapshot,
    ImmutableForecast,
)
from crypto_signal.intelligence.event_risk_circuit_breaker import (
    CircuitBreakerAnalysis,
    CircuitBreakerState,
)
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.outcomes.models import EvidenceClass
from crypto_signal.paper.epoch2_accounting import (
    Epoch2ConsolidatedAccountingSnapshot,
    Epoch2LedgerState,
    Epoch2MetricsStatus,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.transaction_tape import (
    R22FinancialOutcome,
    PaperTapeFill,
)
from crypto_signal.signals.models import SignalDecision, SignalState

R24_SCHEMA_VERSION = "r24-performance-trust-center-v1/1"
R24_ENGINE_VERSION = "r24-performance-trust-center-v1/1"
REAL_CAPITAL = 0

_DECISIVE_ACCURACY_SEMANTIC = (
    "hit_target_fraction_among_hit_target_or_invalidated_only"
)
_CALIBRATION_SEMANTIC = (
    "descriptive_live_untouched_forward_decisive_only_not_probability_authorization"
)
_RISK_REASON = (
    "risk_adjusted_metrics_not_defined_without_accepted_fixed_period_return_series"
)
_EVENT_EFFECTIVENESS_REASON = (
    "event_block_counterfactual_effectiveness_not_measured_by_current_accepted_evidence"
)


class R24MetricStatus(StrEnum):
    AVAILABLE = "available"
    NOT_YET_MEASURED = "not_yet_measured"
    UNDEFINED = "undefined"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class R24ForecastCohortMetrics:
    evidence_class: EvidenceClass
    resolved_n: int
    hit_target_n: int
    invalidated_n: int
    expired_n: int
    ambiguous_n: int
    not_evaluable_n: int
    cancelled_n: int
    decisive_n: int
    decisive_accuracy_fraction: Decimal | None
    accuracy_semantic: str = _DECISIVE_ACCURACY_SEMANTIC

    def __post_init__(self) -> None:
        counts = (
            self.resolved_n,
            self.hit_target_n,
            self.invalidated_n,
            self.expired_n,
            self.ambiguous_n,
            self.not_evaluable_n,
            self.cancelled_n,
            self.decisive_n,
        )
        if min(counts) < 0:
            raise ValueError("R24 forecast cohort counts cannot be negative")
        if self.resolved_n != (
            self.hit_target_n
            + self.invalidated_n
            + self.expired_n
            + self.ambiguous_n
            + self.not_evaluable_n
            + self.cancelled_n
        ):
            raise ValueError("R24 forecast cohort resolution counts do not reconcile")
        if self.decisive_n != self.hit_target_n + self.invalidated_n:
            raise ValueError("R24 decisive forecast count mismatch")
        expected = (
            None
            if self.decisive_n == 0
            else Decimal(self.hit_target_n) / Decimal(self.decisive_n)
        )
        if self.decisive_accuracy_fraction != expected:
            raise ValueError("R24 decisive forecast accuracy mismatch")
        if self.accuracy_semantic != _DECISIVE_ACCURACY_SEMANTIC:
            raise ValueError("R24 accuracy semantic mismatch")


@dataclass(frozen=True, slots=True)
class R24ForecastTrustMetrics:
    total_forecast_n: int
    resolved_forecast_n: int
    unresolved_forecast_n: int
    cohorts: tuple[R24ForecastCohortMetrics, ...]

    def __post_init__(self) -> None:
        if min(
            self.total_forecast_n,
            self.resolved_forecast_n,
            self.unresolved_forecast_n,
        ) < 0:
            raise ValueError("R24 forecast counts cannot be negative")
        if self.total_forecast_n != (
            self.resolved_forecast_n + self.unresolved_forecast_n
        ):
            raise ValueError("R24 total forecast count mismatch")
        expected_classes = tuple(EvidenceClass)
        if tuple(item.evidence_class for item in self.cohorts) != expected_classes:
            raise ValueError(
                "R24 must keep retrospective/walk-forward/untouched-forward separate"
            )
        if sum(item.resolved_n for item in self.cohorts) != self.resolved_forecast_n:
            raise ValueError("R24 cohort resolution count mismatch")


@dataclass(frozen=True, slots=True)
class R24ReliabilityPoint:
    predicted_probability_0_1: Decimal
    sample_count: int
    hit_target_count: int
    observed_hit_fraction: Decimal
    absolute_calibration_gap: Decimal

    def __post_init__(self) -> None:
        for value in (
            self.predicted_probability_0_1,
            self.observed_hit_fraction,
            self.absolute_calibration_gap,
        ):
            _require_unit_interval(value, "R24 reliability value")
        if self.sample_count <= 0:
            raise ValueError("R24 reliability point requires samples")
        if not 0 <= self.hit_target_count <= self.sample_count:
            raise ValueError("R24 reliability hit count is invalid")
        if (
            self.observed_hit_fraction
            != Decimal(self.hit_target_count) / Decimal(self.sample_count)
        ):
            raise ValueError("R24 reliability observed fraction mismatch")
        if self.absolute_calibration_gap != abs(
            self.predicted_probability_0_1 - self.observed_hit_fraction
        ):
            raise ValueError("R24 reliability gap mismatch")


@dataclass(frozen=True, slots=True)
class R24CalibrationTrustMetrics:
    status: R24MetricStatus
    evidence_class: EvidenceClass
    sample_count: int
    brier_score: Decimal | None
    mean_absolute_calibration_gap: Decimal | None
    reliability_points: tuple[R24ReliabilityPoint, ...]
    semantic: str = _CALIBRATION_SEMANTIC

    def __post_init__(self) -> None:
        if self.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
            raise ValueError("R24 calibration trust accepts untouched-forward only")
        if self.sample_count < 0:
            raise ValueError("R24 calibration sample count cannot be negative")
        if self.semantic != _CALIBRATION_SEMANTIC:
            raise ValueError("R24 calibration semantic mismatch")
        if self.status is R24MetricStatus.NOT_YET_MEASURED:
            if self.sample_count != 0:
                raise ValueError("R24 unmeasured calibration requires zero samples")
            if self.brier_score is not None or self.mean_absolute_calibration_gap is not None:
                raise ValueError("R24 unmeasured calibration cannot carry metrics")
            if self.reliability_points:
                raise ValueError("R24 unmeasured calibration cannot carry reliability")
            return
        if self.status is not R24MetricStatus.AVAILABLE:
            raise ValueError("R24 calibration status must be AVAILABLE or NOT_YET_MEASURED")
        if self.sample_count <= 0:
            raise ValueError("R24 available calibration requires samples")
        if self.brier_score is None or self.mean_absolute_calibration_gap is None:
            raise ValueError("R24 available calibration requires diagnostics")
        _require_unit_interval(self.brier_score, "R24 Brier score")
        _require_unit_interval(
            self.mean_absolute_calibration_gap,
            "R24 calibration gap",
        )
        if not self.reliability_points:
            raise ValueError("R24 available calibration requires reliability points")
        if sum(item.sample_count for item in self.reliability_points) != self.sample_count:
            raise ValueError("R24 reliability sample count mismatch")


@dataclass(frozen=True, slots=True)
class R24DecisionBehaviorMetrics:
    total_decision_n: int
    abstain_n: int
    conflict_n: int
    ambiguous_n: int
    abstain_rate_fraction: Decimal | None
    conflict_rate_fraction: Decimal | None
    ambiguous_rate_fraction: Decimal | None

    def __post_init__(self) -> None:
        counts = (
            self.total_decision_n,
            self.abstain_n,
            self.conflict_n,
            self.ambiguous_n,
        )
        if min(counts) < 0:
            raise ValueError("R24 decision counts cannot be negative")
        if max(self.abstain_n, self.conflict_n, self.ambiguous_n) > self.total_decision_n:
            raise ValueError("R24 decision subtype count exceeds population")
        expected = (
            (None, None, None)
            if self.total_decision_n == 0
            else (
                Decimal(self.abstain_n) / Decimal(self.total_decision_n),
                Decimal(self.conflict_n) / Decimal(self.total_decision_n),
                Decimal(self.ambiguous_n) / Decimal(self.total_decision_n),
            )
        )
        actual = (
            self.abstain_rate_fraction,
            self.conflict_rate_fraction,
            self.ambiguous_rate_fraction,
        )
        if actual != expected:
            raise ValueError("R24 decision behavior rates mismatch")


@dataclass(frozen=True, slots=True)
class R24VersionOutcomeMetrics:
    evidence_class: EvidenceClass
    version_key: tuple[str, ...]
    resolved_n: int
    hit_target_n: int
    invalidated_n: int
    expired_n: int
    ambiguous_n: int
    not_evaluable_n: int
    cancelled_n: int

    def __post_init__(self) -> None:
        if not self.version_key or any(not item.strip() for item in self.version_key):
            raise ValueError("R24 version cohort requires a version key")
        if self.version_key != tuple(sorted(set(self.version_key))):
            raise ValueError("R24 version key must be sorted and unique")
        counts = (
            self.resolved_n,
            self.hit_target_n,
            self.invalidated_n,
            self.expired_n,
            self.ambiguous_n,
            self.not_evaluable_n,
            self.cancelled_n,
        )
        if min(counts) < 0:
            raise ValueError("R24 version cohort counts cannot be negative")
        if self.resolved_n != sum(counts[1:]):
            raise ValueError("R24 version cohort counts do not reconcile")


@dataclass(frozen=True, slots=True)
class R24EventBlockMetrics:
    analysis_n: int
    event_block_n: int
    caution_n: int
    degraded_data_n: int
    abstain_n: int
    event_block_rate_fraction: Decimal | None
    effectiveness_status: R24MetricStatus
    effectiveness_fraction: Decimal | None
    effectiveness_reason: str

    def __post_init__(self) -> None:
        counts = (
            self.analysis_n,
            self.event_block_n,
            self.caution_n,
            self.degraded_data_n,
            self.abstain_n,
        )
        if min(counts) < 0:
            raise ValueError("R24 event-block counts cannot be negative")
        if sum(counts[1:]) > self.analysis_n:
            raise ValueError("R24 event-block state counts exceed analyses")
        expected_rate = (
            None
            if self.analysis_n == 0
            else Decimal(self.event_block_n) / Decimal(self.analysis_n)
        )
        if self.event_block_rate_fraction != expected_rate:
            raise ValueError("R24 event-block rate mismatch")
        if self.effectiveness_status is not R24MetricStatus.NOT_YET_MEASURED:
            raise ValueError("R24 event-block effectiveness requires counterfactual evidence")
        if self.effectiveness_fraction is not None:
            raise ValueError("R24 unmeasured event-block effectiveness cannot carry a rate")
        if self.effectiveness_reason != _EVENT_EFFECTIVENESS_REASON:
            raise ValueError("R24 event-block effectiveness reason mismatch")


@dataclass(frozen=True, slots=True)
class R24VaultPerformance:
    vault_id: PaperVaultId
    snapshot_identity: str
    nav_usdt: Decimal
    realized_pnl_usdt: Decimal
    unrealized_pnl_usdt: Decimal
    current_drawdown_fraction: Decimal
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    turnover_fraction: Decimal
    closed_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    expectancy_usdt_per_closed_trade: Decimal | None
    metrics_status: Epoch2MetricsStatus

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "R24 vault snapshot identity")
        for value in (
            self.nav_usdt,
            self.current_drawdown_fraction,
            self.fee_usdt,
            self.spread_usdt,
            self.slippage_usdt,
            self.turnover_fraction,
        ):
            if not value.is_finite() or value < Decimal(0):
                raise ValueError("R24 vault non-negative metric is invalid")
        for value in (self.realized_pnl_usdt, self.unrealized_pnl_usdt):
            if not value.is_finite():
                raise ValueError("R24 vault PnL must be finite")
        counts = (
            self.closed_trade_count,
            self.win_count,
            self.loss_count,
            self.breakeven_count,
        )
        if min(counts) < 0:
            raise ValueError("R24 vault counts cannot be negative")
        if self.closed_trade_count != sum(counts[1:]):
            raise ValueError("R24 vault outcome counts do not reconcile")


@dataclass(frozen=True, slots=True)
class R24PaperCapitalMetrics:
    activation_identity: str
    consolidated_snapshot_identity: str
    nav_usdt: Decimal
    realized_pnl_usdt: Decimal
    unrealized_pnl_usdt: Decimal
    max_drawdown_fraction: Decimal
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    turnover_fraction: Decimal
    closed_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    expectancy_usdt_per_closed_trade: Decimal | None
    profit_factor_status: R24MetricStatus
    gross_profit_usdt: Decimal | None
    gross_loss_usdt: Decimal | None
    profit_factor: Decimal | None
    vaults: tuple[R24VaultPerformance, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.activation_identity, "R24 activation identity")
        _require_sha256(
            self.consolidated_snapshot_identity,
            "R24 consolidated snapshot identity",
        )
        for value in (
            self.nav_usdt,
            self.max_drawdown_fraction,
            self.fee_usdt,
            self.spread_usdt,
            self.slippage_usdt,
            self.turnover_fraction,
        ):
            if not value.is_finite() or value < Decimal(0):
                raise ValueError("R24 paper non-negative metric is invalid")
        for value in (self.realized_pnl_usdt, self.unrealized_pnl_usdt):
            if not value.is_finite():
                raise ValueError("R24 paper PnL must be finite")
        counts = (
            self.closed_trade_count,
            self.win_count,
            self.loss_count,
            self.breakeven_count,
        )
        if min(counts) < 0 or self.closed_trade_count != sum(counts[1:]):
            raise ValueError("R24 paper trade counts do not reconcile")
        if tuple(item.vault_id for item in self.vaults) != tuple(PaperVaultId):
            raise ValueError("R24 paper metrics require exactly all canonical vaults")
        if self.closed_trade_count == 0:
            if self.profit_factor_status is not R24MetricStatus.NOT_YET_MEASURED:
                raise ValueError("R24 empty paper history must not claim profit factor")
            if any(
                item is not None
                for item in (self.gross_profit_usdt, self.gross_loss_usdt, self.profit_factor)
            ):
                raise ValueError("R24 empty paper history cannot carry profit metrics")
        else:
            if self.gross_profit_usdt is None or self.gross_loss_usdt is None:
                raise ValueError("R24 measured paper history requires gross PnL sides")
            if self.gross_profit_usdt < 0 or self.gross_loss_usdt < 0:
                raise ValueError("R24 gross profit/loss must be non-negative")
            if self.gross_loss_usdt == 0:
                if self.profit_factor_status is not R24MetricStatus.UNDEFINED:
                    raise ValueError("R24 zero gross loss makes profit factor undefined")
                if self.profit_factor is not None:
                    raise ValueError("R24 undefined profit factor must be None")
            else:
                if self.profit_factor_status is not R24MetricStatus.AVAILABLE:
                    raise ValueError("R24 measured profit factor must be available")
                if self.profit_factor != self.gross_profit_usdt / self.gross_loss_usdt:
                    raise ValueError("R24 profit factor mismatch")


@dataclass(frozen=True, slots=True)
class R24RiskAdjustedMetrics:
    status: R24MetricStatus
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    reason: str

    def __post_init__(self) -> None:
        if self.status is not R24MetricStatus.NOT_YET_MEASURED:
            raise ValueError("R24 risk-adjusted metrics require an accepted return-series policy")
        if self.sharpe_ratio is not None or self.sortino_ratio is not None:
            raise ValueError("R24 cannot fabricate Sharpe/Sortino")
        if self.reason != _RISK_REASON:
            raise ValueError("R24 risk-adjusted reason mismatch")


@dataclass(frozen=True, slots=True)
class R24PerformanceTrustCenter:
    center_identity: str
    schema_version: str
    engine_version: str
    observed_at_ms: int
    forecast_stream_identity: str
    epoch2_activation_identity: str
    source_evidence_identities: tuple[str, ...]
    forecast: R24ForecastTrustMetrics
    calibration: R24CalibrationTrustMetrics
    decisions: R24DecisionBehaviorMetrics
    version_cohorts: tuple[R24VersionOutcomeMetrics, ...]
    event_block: R24EventBlockMetrics
    paper_capital: R24PaperCapitalMetrics
    risk_adjusted: R24RiskAdjustedMetrics
    winners_and_losers_visible_together: bool = True
    evidence_classes_merged_for_accuracy: bool = False
    private_reasoning_exposed: bool = False
    read_only: bool = True
    production_authority: bool = False
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.center_identity, "R24 center identity")
        _require_sha256(self.forecast_stream_identity, "R24 forecast stream identity")
        _require_sha256(self.epoch2_activation_identity, "R24 Epoch2 activation identity")
        if self.schema_version != R24_SCHEMA_VERSION:
            raise ValueError("unsupported R24 schema")
        if self.engine_version != R24_ENGINE_VERSION:
            raise ValueError("unsupported R24 engine")
        if self.observed_at_ms < 0:
            raise ValueError("R24 observation time must be non-negative")
        if self.source_evidence_identities != tuple(
            sorted(set(self.source_evidence_identities))
        ):
            raise ValueError("R24 source identities must be sorted and unique")
        for identity in self.source_evidence_identities:
            _require_sha256(identity, "R24 source evidence identity")
        if not self.winners_and_losers_visible_together:
            raise ValueError("R24 must expose winners and losers together")
        if self.evidence_classes_merged_for_accuracy:
            raise ValueError("R24 may not merge backtest and forward accuracy")
        if self.private_reasoning_exposed:
            raise ValueError("R24 must not expose private reasoning")
        if not self.read_only:
            raise ValueError("R24 must remain read-only")
        if self.production_authority:
            raise ValueError("R24 has no production/order authority")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.center_identity != canonical_sha256(_center_payload(self)):
            raise ValueError("R24 center identity mismatch")


def build_performance_trust_center(
    *,
    observed_at_ms: int,
    forecast_stream: ForecastStreamSnapshot,
    signal_decisions: tuple[SignalDecision, ...],
    epoch2_state: Epoch2LedgerState,
    consolidated_history: tuple[Epoch2ConsolidatedAccountingSnapshot, ...],
    transaction_fills: tuple[PaperTapeFill, ...] = (),
    event_analyses: tuple[CircuitBreakerAnalysis, ...] = (),
) -> R24PerformanceTrustCenter:
    if observed_at_ms < 0:
        raise ValueError("R24 observation time must be non-negative")
    _validate_source_times(
        observed_at_ms,
        forecast_stream,
        signal_decisions,
        consolidated_history,
        transaction_fills,
        event_analyses,
    )
    _validate_consolidated_history(epoch2_state, consolidated_history)
    _validate_transaction_fills(epoch2_state, transaction_fills)

    forecast_metrics = _forecast_metrics(forecast_stream)
    calibration = _calibration_metrics(forecast_stream)
    decision_metrics = _decision_metrics(signal_decisions)
    versions = _version_metrics(forecast_stream)
    event_metrics = _event_block_metrics(event_analyses)
    paper = _paper_metrics(
        epoch2_state,
        consolidated_history,
        transaction_fills,
    )
    risk_adjusted = R24RiskAdjustedMetrics(
        status=R24MetricStatus.NOT_YET_MEASURED,
        sharpe_ratio=None,
        sortino_ratio=None,
        reason=_RISK_REASON,
    )
    sources = {
        forecast_stream.stream_identity,
        epoch2_state.activation.activation_identity,
        *(item.snapshot_identity for item in consolidated_history),
        *(item.freeze_identity for item in signal_decisions),
        *(item.fill_identity for item in transaction_fills),
        *(item.evidence_identity for item in event_analyses),
    }
    payload: dict[str, object] = {
        "calibration": calibration,
        "decisions": decision_metrics,
        "engine_version": R24_ENGINE_VERSION,
        "epoch2_activation_identity": epoch2_state.activation.activation_identity,
        "event_block": event_metrics,
        "evidence_classes_merged_for_accuracy": False,
        "forecast": forecast_metrics,
        "forecast_stream_identity": forecast_stream.stream_identity,
        "observed_at_ms": observed_at_ms,
        "paper_capital": paper,
        "private_reasoning_exposed": False,
        "production_authority": False,
        "read_only": True,
        "real_capital": REAL_CAPITAL,
        "risk_adjusted": risk_adjusted,
        "schema_version": R24_SCHEMA_VERSION,
        "source_evidence_identities": tuple(sorted(sources)),
        "version_cohorts": versions,
        "winners_and_losers_visible_together": True,
    }
    return R24PerformanceTrustCenter(
        center_identity=canonical_sha256(payload),
        schema_version=R24_SCHEMA_VERSION,
        engine_version=R24_ENGINE_VERSION,
        observed_at_ms=observed_at_ms,
        forecast_stream_identity=forecast_stream.stream_identity,
        epoch2_activation_identity=epoch2_state.activation.activation_identity,
        source_evidence_identities=tuple(sorted(sources)),
        forecast=forecast_metrics,
        calibration=calibration,
        decisions=decision_metrics,
        version_cohorts=versions,
        event_block=event_metrics,
        paper_capital=paper,
        risk_adjusted=risk_adjusted,
    )


def _forecast_metrics(stream: ForecastStreamSnapshot) -> R24ForecastTrustMetrics:
    grouped = {evidence_class: [] for evidence_class in EvidenceClass}
    for resolution in stream.resolutions:
        grouped[resolution.evidence_class].append(resolution.state)
    cohorts = tuple(
        _forecast_cohort(evidence_class, tuple(grouped[evidence_class]))
        for evidence_class in EvidenceClass
    )
    return R24ForecastTrustMetrics(
        total_forecast_n=len(stream.forecasts),
        resolved_forecast_n=len(stream.resolutions),
        unresolved_forecast_n=len(stream.forecasts) - len(stream.resolutions),
        cohorts=cohorts,
    )


def _forecast_cohort(
    evidence_class: EvidenceClass,
    states: tuple[ForecastResolutionState, ...],
) -> R24ForecastCohortMetrics:
    hits = states.count(ForecastResolutionState.HIT_TARGET)
    invalidated = states.count(ForecastResolutionState.INVALIDATED)
    decisive = hits + invalidated
    return R24ForecastCohortMetrics(
        evidence_class=evidence_class,
        resolved_n=len(states),
        hit_target_n=hits,
        invalidated_n=invalidated,
        expired_n=states.count(ForecastResolutionState.EXPIRED),
        ambiguous_n=states.count(ForecastResolutionState.AMBIGUOUS),
        not_evaluable_n=states.count(ForecastResolutionState.NOT_EVALUABLE),
        cancelled_n=states.count(ForecastResolutionState.CANCELLED),
        decisive_n=decisive,
        decisive_accuracy_fraction=(
            None if decisive == 0 else Decimal(hits) / Decimal(decisive)
        ),
    )


def _calibration_metrics(
    stream: ForecastStreamSnapshot,
) -> R24CalibrationTrustMetrics:
    by_forecast = {item.forecast_identity: item for item in stream.forecasts}
    observations: list[tuple[Decimal, int]] = []
    for resolution in stream.resolutions:
        if resolution.evidence_class is not EvidenceClass.LIVE_UNTOUCHED_FORWARD:
            continue
        if resolution.state not in {
            ForecastResolutionState.HIT_TARGET,
            ForecastResolutionState.INVALIDATED,
        }:
            continue
        forecast = by_forecast[resolution.forecast_identity]
        probability = forecast.calibrated_probability_0_1
        if probability is None:
            continue
        observations.append(
            (
                probability,
                1 if resolution.state is ForecastResolutionState.HIT_TARGET else 0,
            )
        )
    if not observations:
        return R24CalibrationTrustMetrics(
            status=R24MetricStatus.NOT_YET_MEASURED,
            evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
            sample_count=0,
            brier_score=None,
            mean_absolute_calibration_gap=None,
            reliability_points=(),
        )

    brier = sum(
        ((probability - Decimal(outcome)) ** 2 for probability, outcome in observations),
        start=Decimal(0),
    ) / Decimal(len(observations))
    groups: dict[Decimal, list[int]] = defaultdict(list)
    for probability, outcome in observations:
        groups[probability].append(outcome)
    points = tuple(
        R24ReliabilityPoint(
            predicted_probability_0_1=probability,
            sample_count=len(groups[probability]),
            hit_target_count=sum(groups[probability]),
            observed_hit_fraction=(
                Decimal(sum(groups[probability]))
                / Decimal(len(groups[probability]))
            ),
            absolute_calibration_gap=abs(
                probability
                - (
                    Decimal(sum(groups[probability]))
                    / Decimal(len(groups[probability]))
                )
            ),
        )
        for probability in sorted(groups)
    )
    mean_gap = sum(
        (
            point.absolute_calibration_gap * Decimal(point.sample_count)
            for point in points
        ),
        start=Decimal(0),
    ) / Decimal(len(observations))
    return R24CalibrationTrustMetrics(
        status=R24MetricStatus.AVAILABLE,
        evidence_class=EvidenceClass.LIVE_UNTOUCHED_FORWARD,
        sample_count=len(observations),
        brier_score=brier,
        mean_absolute_calibration_gap=mean_gap,
        reliability_points=points,
    )


def _decision_metrics(
    decisions: tuple[SignalDecision, ...],
) -> R24DecisionBehaviorMetrics:
    identities = tuple(item.freeze_identity for item in decisions)
    if len(set(identities)) != len(identities):
        raise ValueError("R24 decision population contains duplicate freeze identities")
    abstain = sum(
        item.state in {SignalState.NO_SIGNAL, SignalState.NEUTRAL}
        for item in decisions
    )
    conflict = sum(
        item.agreement.opposing_method_count > 0
        or any(
            relation.relation is PairRelation.CONTRADICT
            for relation in item.agreement.pairwise_relations
        )
        for item in decisions
    )
    ambiguous = sum(
        any(
            relation.relation is PairRelation.INTERNAL_AMBIGUITY
            for relation in item.agreement.pairwise_relations
        )
        for item in decisions
    )
    total = len(decisions)
    denominator = None if total == 0 else Decimal(total)
    return R24DecisionBehaviorMetrics(
        total_decision_n=total,
        abstain_n=abstain,
        conflict_n=conflict,
        ambiguous_n=ambiguous,
        abstain_rate_fraction=(
            None if denominator is None else Decimal(abstain) / denominator
        ),
        conflict_rate_fraction=(
            None if denominator is None else Decimal(conflict) / denominator
        ),
        ambiguous_rate_fraction=(
            None if denominator is None else Decimal(ambiguous) / denominator
        ),
    )


def _version_key(forecast: ImmutableForecast) -> tuple[str, ...]:
    refs = tuple(
        sorted(
            f"{item.component}={item.version}"
            for item in forecast.version_refs
        )
    )
    return refs or (f"forecast_engine={forecast.engine_version}",)


def _version_metrics(
    stream: ForecastStreamSnapshot,
) -> tuple[R24VersionOutcomeMetrics, ...]:
    by_forecast = {item.forecast_identity: item for item in stream.forecasts}
    grouped: dict[
        tuple[EvidenceClass, tuple[str, ...]],
        list[ForecastResolutionState],
    ] = defaultdict(list)
    for resolution in stream.resolutions:
        forecast = by_forecast[resolution.forecast_identity]
        grouped[(resolution.evidence_class, _version_key(forecast))].append(
            resolution.state
        )
    rows: list[R24VersionOutcomeMetrics] = []
    for evidence_class, version_key in sorted(
        grouped,
        key=lambda item: (item[0].value, item[1]),
    ):
        states = tuple(grouped[(evidence_class, version_key)])
        rows.append(
            R24VersionOutcomeMetrics(
                evidence_class=evidence_class,
                version_key=version_key,
                resolved_n=len(states),
                hit_target_n=states.count(ForecastResolutionState.HIT_TARGET),
                invalidated_n=states.count(ForecastResolutionState.INVALIDATED),
                expired_n=states.count(ForecastResolutionState.EXPIRED),
                ambiguous_n=states.count(ForecastResolutionState.AMBIGUOUS),
                not_evaluable_n=states.count(
                    ForecastResolutionState.NOT_EVALUABLE
                ),
                cancelled_n=states.count(ForecastResolutionState.CANCELLED),
            )
        )
    return tuple(rows)


def _event_block_metrics(
    analyses: tuple[CircuitBreakerAnalysis, ...],
) -> R24EventBlockMetrics:
    identities = tuple(item.evidence_identity for item in analyses)
    if len(set(identities)) != len(identities):
        raise ValueError("R24 event analyses contain duplicate identities")
    total = len(analyses)
    block = sum(item.state is CircuitBreakerState.EVENT_BLOCK for item in analyses)
    return R24EventBlockMetrics(
        analysis_n=total,
        event_block_n=block,
        caution_n=sum(item.state is CircuitBreakerState.CAUTION for item in analyses),
        degraded_data_n=sum(
            item.state is CircuitBreakerState.DEGRADED_DATA for item in analyses
        ),
        abstain_n=sum(item.state is CircuitBreakerState.ABSTAIN for item in analyses),
        event_block_rate_fraction=(
            None if total == 0 else Decimal(block) / Decimal(total)
        ),
        effectiveness_status=R24MetricStatus.NOT_YET_MEASURED,
        effectiveness_fraction=None,
        effectiveness_reason=_EVENT_EFFECTIVENESS_REASON,
    )


def _paper_metrics(
    state: Epoch2LedgerState,
    history: tuple[Epoch2ConsolidatedAccountingSnapshot, ...],
    fills: tuple[PaperTapeFill, ...],
) -> R24PaperCapitalMetrics:
    latest = state.consolidated_snapshot
    max_drawdown = max(item.drawdown_fraction for item in history)
    ordered_fills = tuple(sorted(fills, key=lambda item: (item.snapshot_at_ms, item.fill_identity)))
    closed = tuple(
        item
        for item in ordered_fills
        if item.financial_outcome
        in {
            R22FinancialOutcome.CLOSED_WIN,
            R22FinancialOutcome.CLOSED_LOSS,
            R22FinancialOutcome.CLOSED_BREAKEVEN,
        }
    )
    if len(closed) != latest.closed_trade_count:
        raise ValueError("R24 R22 closed-fill count does not match canonical R21 accounting")
    realized_sum = sum(
        (item.realized_pnl_delta_usdt for item in closed),
        start=Decimal(0),
    )
    if realized_sum != latest.realized_pnl_usdt:
        raise ValueError("R24 R22 realized PnL does not match canonical R21 accounting")

    if not closed:
        profit_status = R24MetricStatus.NOT_YET_MEASURED
        gross_profit: Decimal | None = None
        gross_loss: Decimal | None = None
        profit_factor: Decimal | None = None
    else:
        gross_profit = sum(
            (
                item.realized_pnl_delta_usdt
                for item in closed
                if item.realized_pnl_delta_usdt > 0
            ),
            start=Decimal(0),
        )
        gross_loss = sum(
            (
                -item.realized_pnl_delta_usdt
                for item in closed
                if item.realized_pnl_delta_usdt < 0
            ),
            start=Decimal(0),
        )
        if gross_loss == 0:
            profit_status = R24MetricStatus.UNDEFINED
            profit_factor = None
        else:
            profit_status = R24MetricStatus.AVAILABLE
            profit_factor = gross_profit / gross_loss

    by_vault = {item.vault_id: item for item in state.vault_snapshots}
    vaults = tuple(
        R24VaultPerformance(
            vault_id=vault_id,
            snapshot_identity=by_vault[vault_id].snapshot_identity,
            nav_usdt=by_vault[vault_id].nav_usdt,
            realized_pnl_usdt=by_vault[vault_id].realized_pnl_usdt,
            unrealized_pnl_usdt=by_vault[vault_id].unrealized_pnl_usdt,
            current_drawdown_fraction=by_vault[vault_id].drawdown_fraction,
            fee_usdt=by_vault[vault_id].fee_usdt,
            spread_usdt=by_vault[vault_id].spread_usdt,
            slippage_usdt=by_vault[vault_id].slippage_usdt,
            turnover_fraction=by_vault[vault_id].turnover_fraction,
            closed_trade_count=by_vault[vault_id].closed_trade_count,
            win_count=by_vault[vault_id].win_count,
            loss_count=by_vault[vault_id].loss_count,
            breakeven_count=by_vault[vault_id].breakeven_count,
            expectancy_usdt_per_closed_trade=(
                by_vault[vault_id].expectancy_usdt_per_closed_trade
            ),
            metrics_status=by_vault[vault_id].metrics_status,
        )
        for vault_id in PaperVaultId
    )
    return R24PaperCapitalMetrics(
        activation_identity=state.activation.activation_identity,
        consolidated_snapshot_identity=latest.snapshot_identity,
        nav_usdt=latest.nav_usdt,
        realized_pnl_usdt=latest.realized_pnl_usdt,
        unrealized_pnl_usdt=latest.unrealized_pnl_usdt,
        max_drawdown_fraction=max_drawdown,
        fee_usdt=latest.fee_usdt,
        spread_usdt=latest.spread_usdt,
        slippage_usdt=latest.slippage_usdt,
        turnover_fraction=latest.turnover_fraction,
        closed_trade_count=latest.closed_trade_count,
        win_count=latest.win_count,
        loss_count=latest.loss_count,
        breakeven_count=latest.breakeven_count,
        expectancy_usdt_per_closed_trade=latest.expectancy_usdt_per_closed_trade,
        profit_factor_status=profit_status,
        gross_profit_usdt=gross_profit,
        gross_loss_usdt=gross_loss,
        profit_factor=profit_factor,
        vaults=vaults,
    )


def _validate_consolidated_history(
    state: Epoch2LedgerState,
    history: tuple[Epoch2ConsolidatedAccountingSnapshot, ...],
) -> None:
    if not history:
        raise ValueError("R24 requires canonical Epoch2 consolidated history")
    if history[-1] != state.consolidated_snapshot:
        raise ValueError("R24 history must end at exact canonical Epoch2 state")
    keys = tuple((item.snapshot_at_ms, item.snapshot_identity) for item in history)
    if keys != tuple(sorted(keys)):
        raise ValueError("R24 consolidated history must be chronological")
    seen: set[str] = set()
    previous: Epoch2ConsolidatedAccountingSnapshot | None = None
    for item in history:
        if item.snapshot_identity in seen:
            raise ValueError("R24 consolidated history contains duplicate snapshots")
        seen.add(item.snapshot_identity)
        if item.activation_identity != state.activation.activation_identity:
            raise ValueError("R24 consolidated history activation mismatch")
        if previous is None:
            if item.previous_snapshot_identity is not None:
                raise ValueError("R24 first consolidated history item must be the root")
        elif item.previous_snapshot_identity != previous.snapshot_identity:
            raise ValueError("R24 consolidated history predecessor mismatch")
        previous = item


def _validate_transaction_fills(
    state: Epoch2LedgerState,
    fills: tuple[PaperTapeFill, ...],
) -> None:
    identities = tuple(item.fill_identity for item in fills)
    if len(set(identities)) != len(identities):
        raise ValueError("R24 transaction fills contain duplicate identities")
    for item in fills:
        if item.activation_identity != state.activation.activation_identity:
            raise ValueError("R24 transaction fill activation mismatch")


def _validate_source_times(
    observed_at_ms: int,
    stream: ForecastStreamSnapshot,
    decisions: tuple[SignalDecision, ...],
    history: tuple[Epoch2ConsolidatedAccountingSnapshot, ...],
    fills: tuple[PaperTapeFill, ...],
    analyses: tuple[CircuitBreakerAnalysis, ...],
) -> None:
    timestamps = [
        *(item.issued_at_ms for item in stream.forecasts),
        *(item.evaluated_at_ms for item in stream.resolutions),
        *(item.as_of_ms for item in decisions),
        *(item.snapshot_at_ms for item in history),
        *(item.snapshot_at_ms for item in fills),
        *(item.as_of_ms for item in analyses),
    ]
    if timestamps and max(timestamps) > observed_at_ms:
        raise ValueError("R24 cannot consume evidence from the future")


def _center_payload(center: R24PerformanceTrustCenter) -> dict[str, object]:
    return {
        field.name: getattr(center, field.name)
        for field in fields(center)
        if field.name != "center_identity"
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be an exact SHA256 identity")


def _require_unit_interval(value: Decimal, label: str) -> None:
    if not value.is_finite() or value < Decimal(0) or value > Decimal(1):
        raise ValueError(f"{label} must be inside [0,1]")
