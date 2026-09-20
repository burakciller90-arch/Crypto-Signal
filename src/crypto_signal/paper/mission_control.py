"""Read-only paper mission-control composition.

This module composes already accepted production truth into one deterministic
snapshot for product surfaces. It never mutates paper or signal ledgers and
never grants trade authority. Candidate explanations come only from the
accepted dry-run decision trace; no free-form trader thoughts are invented.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_sha256
from crypto_signal.paper.activation import PaperActivationState
from crypto_signal.paper.dry_run import (
    PaperActivationDryRunStatus,
    PaperDecisionTrace,
    evaluate_paper_activation_dry_run,
    explain_paper_activation_dry_run,
    read_paper_activation_read_only,
)
from crypto_signal.paper.event_scanner import (
    PaperSignalEventScanResult,
    scan_post_activation_signal_events,
)
from crypto_signal.paper.execution import simulate_paper_fill
from crypto_signal.paper.execution_input import FrozenPaperExecutionInput
from crypto_signal.paper.models import (
    PERMITTED_SYMBOLS,
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
)
from crypto_signal.paper.performance import (
    PaperTradePerformanceSnapshot,
    read_paper_trade_performance,
)
from crypto_signal.paper.portfolio import (
    PaperPortfolioAvailability,
    PaperPortfolioSnapshot,
    read_paper_portfolio_snapshot,
)
from crypto_signal.paper.sizing import PaperPositionSizingDecision
from crypto_signal.paper.venue_rules import PaperVenueBoundPretrade

__all__ = [
    "PAPER_MISSION_CONTROL_VERSION",
    "PaperDecisionCadenceProviderEvidence",
    "PaperDecisionCadenceReadiness",
    "PaperDecisionCadenceStatus",
    "PaperMissionControlCandidate",
    "PaperMissionControlError",
    "PaperMissionControlSnapshot",
    "PaperPlanCostPreview",
    "PaperPortfolioExposurePosition",
    "PaperPortfolioExposureView",
    "PaperSignalStreamOverview",
    "read_paper_decision_cadence_readiness",
    "read_paper_mission_control_snapshot",
    "read_paper_signal_stream_overview",
]

PAPER_MISSION_CONTROL_VERSION = "paper_mission_control.v3"


class PaperMissionControlError(RuntimeError):
    """Raised when composed production truth cannot be reconciled safely."""


@dataclass(frozen=True, slots=True)
class PaperSignalStreamOverview:
    total_freeze_count: int
    latest_signal_freeze_identity: str | None
    latest_frozen_at_ms: int | None
    latest_signal_as_of_ms: int | None
    latest_exchange: str | None
    latest_symbol: str | None
    latest_timeframe: str | None
    latest_signal_state: str | None
    latest_direction: str | None
    latest_freeze_age_ms: int | None

    def __post_init__(self) -> None:
        if self.total_freeze_count < 0:
            raise ValueError("signal freeze count cannot be negative")
        detail = (
            self.latest_signal_freeze_identity,
            self.latest_frozen_at_ms,
            self.latest_signal_as_of_ms,
            self.latest_exchange,
            self.latest_symbol,
            self.latest_timeframe,
            self.latest_signal_state,
            self.latest_direction,
            self.latest_freeze_age_ms,
        )
        if self.total_freeze_count == 0:
            if any(value is not None for value in detail):
                raise ValueError("empty signal stream cannot carry latest-freeze detail")
            return
        if any(value is None for value in detail):
            raise ValueError("non-empty signal stream requires latest-freeze detail")
        assert self.latest_signal_freeze_identity is not None
        assert self.latest_frozen_at_ms is not None
        assert self.latest_signal_as_of_ms is not None
        assert self.latest_freeze_age_ms is not None
        _require_sha256(self.latest_signal_freeze_identity, "latest signal freeze")
        if min(
            self.latest_frozen_at_ms,
            self.latest_signal_as_of_ms,
            self.latest_freeze_age_ms,
        ) < 0:
            raise ValueError("signal stream timestamps/age must be non-negative")


class PaperDecisionCadenceStatus(StrEnum):
    NO_4H_EVIDENCE = "no_4h_evidence"
    WAITING_PROVIDER_PAIR = "waiting_provider_pair"
    PROVIDER_CUTOFF_MISMATCH = "provider_cutoff_mismatch"
    PRE_ACTIVATION_PAIR = "pre_activation_pair"
    POST_ACTIVATION_PAIR = "post_activation_pair"


@dataclass(frozen=True, slots=True)
class PaperDecisionCadenceProviderEvidence:
    exchange: Exchange
    freeze_identity: str
    signal_as_of_ms: int
    source_cutoff_open_time_ms: int
    frozen_at_ms: int
    signal_state: str
    direction: str

    def __post_init__(self) -> None:
        if self.exchange not in {Exchange.BINANCE, Exchange.BYBIT}:
            raise ValueError("decision-cadence provider must be Binance or Bybit")
        _require_sha256(self.freeze_identity, "decision-cadence freeze identity")
        if min(
            self.signal_as_of_ms,
            self.source_cutoff_open_time_ms,
            self.frozen_at_ms,
        ) < 0:
            raise ValueError("decision-cadence timestamps must be non-negative")
        if self.frozen_at_ms < self.signal_as_of_ms:
            raise ValueError("decision-cadence freeze cannot predate signal as-of")
        if not self.signal_state.strip() or not self.direction.strip():
            raise ValueError("decision-cadence state/direction must be non-empty")


@dataclass(frozen=True, slots=True)
class PaperDecisionCadenceReadiness:
    symbol: PaperSymbol
    status: PaperDecisionCadenceStatus
    binance: PaperDecisionCadenceProviderEvidence | None
    bybit: PaperDecisionCadenceProviderEvidence | None
    paired_as_of_ms: int | None
    paired_source_cutoff_open_time_ms: int | None
    candidate_available: bool

    def __post_init__(self) -> None:
        if self.binance is not None and self.binance.exchange is not Exchange.BINANCE:
            raise ValueError("binance cadence evidence exchange mismatch")
        if self.bybit is not None and self.bybit.exchange is not Exchange.BYBIT:
            raise ValueError("bybit cadence evidence exchange mismatch")
        if self.status is PaperDecisionCadenceStatus.NO_4H_EVIDENCE:
            if self.binance is not None or self.bybit is not None:
                raise ValueError("no-evidence cadence cannot carry provider evidence")
            if (
                self.paired_as_of_ms is not None
                or self.paired_source_cutoff_open_time_ms is not None
                or self.candidate_available
            ):
                raise ValueError("no-evidence cadence cannot carry pair/candidate")
        elif self.status is PaperDecisionCadenceStatus.WAITING_PROVIDER_PAIR:
            if (self.binance is None) == (self.bybit is None):
                raise ValueError("waiting-provider cadence requires exactly one provider")
            if (
                self.paired_as_of_ms is not None
                or self.paired_source_cutoff_open_time_ms is not None
                or self.candidate_available
            ):
                raise ValueError("waiting-provider cadence cannot carry pair/candidate")
        elif self.status is PaperDecisionCadenceStatus.PROVIDER_CUTOFF_MISMATCH:
            if self.binance is None or self.bybit is None:
                raise ValueError("cutoff mismatch requires both providers")
            if (
                self.binance.source_cutoff_open_time_ms
                == self.bybit.source_cutoff_open_time_ms
            ):
                raise ValueError(
                    "cutoff mismatch requires different provider market cutoffs"
                )
            if (
                self.paired_as_of_ms is not None
                or self.paired_source_cutoff_open_time_ms is not None
                or self.candidate_available
            ):
                raise ValueError("cutoff mismatch cannot carry exact pair/candidate")
        else:
            if self.binance is None or self.bybit is None:
                raise ValueError("paired cadence requires both providers")
            if (
                self.binance.source_cutoff_open_time_ms
                != self.bybit.source_cutoff_open_time_ms
            ):
                raise ValueError("paired cadence requires identical market cutoff")
            if self.paired_as_of_ms != max(
                self.binance.signal_as_of_ms,
                self.bybit.signal_as_of_ms,
            ):
                raise ValueError("paired cadence availability as-of mismatch")
            if (
                self.paired_source_cutoff_open_time_ms
                != self.binance.source_cutoff_open_time_ms
            ):
                raise ValueError("paired cadence market cutoff mismatch")
            if (
                self.status is PaperDecisionCadenceStatus.PRE_ACTIVATION_PAIR
                and self.candidate_available
            ):
                raise ValueError("pre-activation pair cannot be a paper candidate")


@dataclass(frozen=True, slots=True)
class PaperPlanCostPreview:
    """Read-only exact cost decomposition for an accepted virtual plan."""

    execution_snapshot_identity: str
    fee_usdt: Decimal
    spread_usdt: Decimal
    slippage_usdt: Decimal
    total_cost_usdt: Decimal
    reference_notional_usdt: Decimal
    fill_notional_usdt: Decimal
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("plan cost preview must remain REAL_CAPITAL=0")
        _require_sha256(
            self.execution_snapshot_identity,
            "plan cost preview execution snapshot",
        )
        for label, value in (
            ("fee_usdt", self.fee_usdt),
            ("spread_usdt", self.spread_usdt),
            ("slippage_usdt", self.slippage_usdt),
            ("total_cost_usdt", self.total_cost_usdt),
            ("reference_notional_usdt", self.reference_notional_usdt),
            ("fill_notional_usdt", self.fill_notional_usdt),
        ):
            if not isinstance(value, Decimal):
                raise TypeError(f"{label} must be Decimal")
            if value < Decimal(0):
                raise ValueError(f"{label} cannot be negative")
        if self.total_cost_usdt != (
            self.fee_usdt + self.spread_usdt + self.slippage_usdt
        ):
            raise ValueError("plan cost preview total must equal explicit costs")


@dataclass(frozen=True, slots=True)
class PaperMissionControlCandidate:
    event_identity: str
    symbol: PaperSymbol
    signal_as_of_ms: int
    terminal_status: PaperActivationDryRunStatus
    candidate_action: PaperAction
    reason_code: str
    trace: PaperDecisionTrace
    execution_input: FrozenPaperExecutionInput | None = None
    venue_rule_snapshot_identity: str | None = None
    sizing: PaperPositionSizingDecision | None = None
    venue_bound_pretrade: PaperVenueBoundPretrade | None = None
    cost_preview: PaperPlanCostPreview | None = None

    def __post_init__(self) -> None:
        _require_sha256(self.event_identity, "mission-control event identity")
        if self.signal_as_of_ms < 0:
            raise ValueError("candidate signal as-of must be non-negative")
        if not self.reason_code.strip():
            raise ValueError("candidate reason code must be non-empty")
        if self.trace.event_identity != self.event_identity:
            raise ValueError("candidate/trace event identity mismatch")
        if self.trace.terminal_status is not self.terminal_status:
            raise ValueError("candidate/trace terminal status mismatch")
        if self.trace.candidate_action is not self.candidate_action:
            raise ValueError("candidate/trace action mismatch")
        if self.execution_input is not None:
            if self.execution_input.real_capital != REAL_CAPITAL:
                raise ValueError("candidate execution input must remain REAL_CAPITAL=0")
            if self.execution_input.candidate_action is not self.candidate_action:
                raise ValueError("candidate/execution-input action mismatch")
            if self.execution_input.symbol is not self.symbol:
                raise ValueError("candidate/execution-input symbol mismatch")
        if self.venue_rule_snapshot_identity is not None:
            _require_sha256(
                self.venue_rule_snapshot_identity,
                "candidate venue-rule snapshot identity",
            )
        if self.sizing is not None:
            if self.sizing.real_capital != REAL_CAPITAL:
                raise ValueError("candidate sizing must remain REAL_CAPITAL=0")
            if self.sizing.action is not self.candidate_action:
                raise ValueError("candidate/sizing action mismatch")
            if self.sizing.symbol is not self.symbol:
                raise ValueError("candidate/sizing symbol mismatch")
        if self.venue_bound_pretrade is not None:
            if self.venue_bound_pretrade.real_capital != REAL_CAPITAL:
                raise ValueError("candidate pretrade must remain REAL_CAPITAL=0")
            if (
                self.venue_rule_snapshot_identity
                != self.venue_bound_pretrade.venue_rule_snapshot_identity
            ):
                raise ValueError("candidate/pretrade venue-rule identity mismatch")
            if self.venue_bound_pretrade.pretrade.action is not self.candidate_action:
                raise ValueError("candidate/pretrade action mismatch")
            if self.venue_bound_pretrade.pretrade.symbol is not self.symbol:
                raise ValueError("candidate/pretrade symbol mismatch")

        downstream = (
            self.execution_input,
            self.venue_rule_snapshot_identity,
            self.sizing,
            self.venue_bound_pretrade,
        )
        if self.terminal_status is PaperActivationDryRunStatus.HOLD_CASH:
            if any(item is not None for item in downstream):
                raise ValueError(
                    "HOLD_CASH candidate cannot carry downstream plan truth"
                )
        elif (
            self.terminal_status
            is PaperActivationDryRunStatus.WAITING_EXECUTION_INPUT
        ):
            if any(item is not None for item in downstream):
                raise ValueError(
                    "waiting-execution-input candidate cannot carry downstream truth"
                )
        elif self.terminal_status is PaperActivationDryRunStatus.WAITING_VENUE_RULES:
            if (
                self.execution_input is None
                or any(item is not None for item in downstream[1:])
            ):
                raise ValueError("waiting-venue-rules candidate has invalid lineage")
        elif self.terminal_status is PaperActivationDryRunStatus.SIZING_REJECTED:
            if (
                self.execution_input is None
                or self.venue_rule_snapshot_identity is None
                or self.sizing is None
                or self.venue_bound_pretrade is not None
            ):
                raise ValueError("sizing-rejected candidate has invalid lineage")
        elif self.terminal_status in {
            PaperActivationDryRunStatus.PRETRADE_REJECTED,
            PaperActivationDryRunStatus.PRETRADE_READY,
        }:
            if any(item is None for item in downstream):
                raise ValueError("pretrade candidate requires complete plan lineage")
            assert self.venue_bound_pretrade is not None
            plan = self.venue_bound_pretrade.pretrade.plan
            if (
                self.terminal_status is PaperActivationDryRunStatus.PRETRADE_READY
                and plan is None
            ):
                raise ValueError("PRETRADE_READY candidate requires a virtual plan")
            if (
                self.terminal_status is PaperActivationDryRunStatus.PRETRADE_REJECTED
                and plan is not None
            ):
                raise ValueError("PRETRADE_REJECTED candidate cannot carry a plan")

        if self.terminal_status is PaperActivationDryRunStatus.PRETRADE_READY:
            if self.cost_preview is None:
                raise ValueError("PRETRADE_READY candidate requires exact cost preview")
            assert self.venue_bound_pretrade is not None
            plan = self.venue_bound_pretrade.pretrade.plan
            assert plan is not None
            if (
                self.cost_preview.execution_snapshot_identity
                != self.venue_bound_pretrade.execution_snapshot.snapshot_identity
            ):
                raise ValueError("candidate/cost-preview execution snapshot mismatch")
            if self.cost_preview.total_cost_usdt != plan.cost_budget_usdt:
                raise ValueError("candidate/cost-preview budget mismatch")
        elif self.cost_preview is not None:
            raise ValueError("only PRETRADE_READY may carry a plan cost preview")


@dataclass(frozen=True, slots=True)
class PaperPortfolioExposurePosition:
    """Deterministic marked exposure for one virtual paper position."""

    symbol: PaperSymbol
    quantity: Decimal
    marked_value_usdt: Decimal | None
    nav_fraction: Decimal | None

    def __post_init__(self) -> None:
        if self.quantity <= Decimal(0):
            raise ValueError("portfolio exposure quantity must be positive")
        if (self.marked_value_usdt is None) != (self.nav_fraction is None):
            raise ValueError("marked value and NAV fraction must appear together")
        if self.marked_value_usdt is not None and self.marked_value_usdt < Decimal(0):
            raise ValueError("marked position value cannot be negative")
        if self.nav_fraction is not None and not (
            Decimal(0) <= self.nav_fraction <= Decimal(1)
        ):
            raise ValueError("position NAV fraction must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class PaperPortfolioExposureView:
    """Read-only allocation view derived only from accepted portfolio truth."""

    availability: PaperPortfolioAvailability
    cash_usdt: Decimal
    marked_positions_value_usdt: Decimal | None
    nav_usdt: Decimal | None
    cash_fraction: Decimal | None
    invested_fraction: Decimal | None
    positions: tuple[PaperPortfolioExposurePosition, ...]
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("portfolio exposure must remain REAL_CAPITAL=0")
        if self.cash_usdt < Decimal(0):
            raise ValueError("portfolio exposure cash cannot be negative")
        if self.availability is PaperPortfolioAvailability.AVAILABLE:
            if (
                self.marked_positions_value_usdt is None
                or self.nav_usdt is None
            ):
                raise ValueError("available exposure requires marked NAV truth")
            if self.nav_usdt > Decimal(0):
                if self.cash_fraction is None or self.invested_fraction is None:
                    raise ValueError("positive NAV requires exposure fractions")
                if self.cash_fraction + self.invested_fraction != Decimal(1):
                    raise ValueError("cash and invested fractions must sum to one")
                position_total = sum(
                    (
                        item.nav_fraction
                        for item in self.positions
                        if item.nav_fraction is not None
                    ),
                    start=Decimal(0),
                )
                if position_total != self.invested_fraction:
                    raise ValueError("position exposure must reconcile to invested share")
            elif self.cash_fraction is not None or self.invested_fraction is not None:
                raise ValueError("non-positive NAV cannot carry exposure fractions")
        elif any(
            value is not None
            for value in (
                self.marked_positions_value_usdt,
                self.nav_usdt,
                self.cash_fraction,
                self.invested_fraction,
            )
        ):
            raise ValueError("missing-mark exposure cannot fabricate portfolio metrics")


@dataclass(frozen=True, slots=True)
class PaperMissionControlSnapshot:
    snapshot_identity: str
    version: str
    observed_at_ms: int
    activation_identity: str
    activation_cutoff_ms: int
    baseline_signal_freeze_count: int
    signal_stream: PaperSignalStreamOverview
    decision_cadence: tuple[PaperDecisionCadenceReadiness, ...]
    eligible_post_activation_freezes: int
    incomplete_provider_pairs: int
    processed_event_skips: int
    candidates: tuple[PaperMissionControlCandidate, ...]
    ready_candidate_count: int
    attention_required: bool
    portfolio: PaperPortfolioSnapshot
    portfolio_exposure: PaperPortfolioExposureView
    performance: PaperTradePerformanceSnapshot
    trade_policy: str = "NOT_ACTIVATED"
    real_capital: int = REAL_CAPITAL

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_identity, "mission-control snapshot identity")
        _require_sha256(self.activation_identity, "activation identity")
        if self.version != PAPER_MISSION_CONTROL_VERSION:
            raise ValueError("unsupported paper mission-control version")
        if self.real_capital != REAL_CAPITAL:
            raise ValueError("REAL_CAPITAL must remain 0")
        if self.trade_policy != "NOT_ACTIVATED":
            raise ValueError("paper mission control cannot grant trade authority")
        if self.observed_at_ms < 0 or self.activation_cutoff_ms < 0:
            raise ValueError("mission-control timestamps must be non-negative")
        if self.baseline_signal_freeze_count < 0:
            raise ValueError("activation baseline count cannot be negative")
        expected_symbols = tuple(
            sorted(PERMITTED_SYMBOLS, key=lambda item: item.value)
        )
        if tuple(item.symbol for item in self.decision_cadence) != expected_symbols:
            raise ValueError(
                "decision cadence must contain every permitted symbol in order"
            )
        if min(
            self.eligible_post_activation_freezes,
            self.incomplete_provider_pairs,
            self.processed_event_skips,
            self.ready_candidate_count,
        ) < 0:
            raise ValueError("mission-control counts cannot be negative")
        ordered = tuple(
            sorted(
                self.candidates,
                key=lambda item: (
                    item.signal_as_of_ms,
                    item.symbol.value,
                    item.event_identity,
                ),
            )
        )
        if self.candidates != ordered:
            raise ValueError("mission-control candidates must be ordered")
        expected_ready = sum(
            1
            for item in self.candidates
            if item.terminal_status is PaperActivationDryRunStatus.PRETRADE_READY
        )
        if self.ready_candidate_count != expected_ready:
            raise ValueError("ready candidate count mismatch")
        if self.attention_required != (expected_ready > 0):
            raise ValueError("attention flag must match ready candidates")
        if self.portfolio.observed_at_ms != self.observed_at_ms:
            raise ValueError("portfolio observation time mismatch")
        expected_exposure = _build_portfolio_exposure(self.portfolio)
        if self.portfolio_exposure != expected_exposure:
            raise ValueError("portfolio exposure must derive exactly from portfolio truth")
        if self.performance.observed_at_ms != self.observed_at_ms:
            raise ValueError("performance observation time mismatch")
        if self.portfolio.fund_identity != self.performance.fund_identity:
            raise ValueError("portfolio/performance fund mismatch")
        if self.snapshot_identity != canonical_sha256(_snapshot_payload(self)):
            raise ValueError("mission-control snapshot identity mismatch")


def read_paper_mission_control_snapshot(
    *,
    paper_ledger_path: Path,
    signal_ledger_path: Path,
    candle_cache_path: Path,
    observed_at_ms: int,
    max_candidates: int = 100,
) -> PaperMissionControlSnapshot:
    """Compose current paper truth using read-only accepted readers."""
    if observed_at_ms < 0:
        raise ValueError("observed_at_ms must be non-negative")
    if max_candidates <= 0:
        raise ValueError("max_candidates must be positive")
    if REAL_CAPITAL != 0:
        raise PaperMissionControlError("REAL_CAPITAL must remain 0")

    activation = read_paper_activation_read_only(paper_ledger_path)
    signal_stream = read_paper_signal_stream_overview(
        signal_ledger_path=signal_ledger_path,
        observed_at_ms=observed_at_ms,
    )
    scan = scan_post_activation_signal_events(
        signal_ledger_path=signal_ledger_path,
        paper_ledger_path=paper_ledger_path,
        activation=activation,
        observed_at_ms=observed_at_ms,
    )
    decision_cadence = read_paper_decision_cadence_readiness(
        signal_ledger_path=signal_ledger_path,
        activation=activation,
        scan=scan,
        observed_at_ms=observed_at_ms,
    )
    if len(scan.candidates) > max_candidates:
        raise PaperMissionControlError(
            "mission-control candidate count exceeds bounded max_candidates"
        )
    _validate_scan_point_in_time(scan=scan, observed_at_ms=observed_at_ms)

    candidates: list[PaperMissionControlCandidate] = []
    for event in scan.candidates:
        result = evaluate_paper_activation_dry_run(
            event=event,
            activation=activation,
            paper_ledger_path=paper_ledger_path,
            candle_cache_path=candle_cache_path,
            evaluated_at_ms=observed_at_ms,
        )
        trace = explain_paper_activation_dry_run(result)
        candidates.append(
            PaperMissionControlCandidate(
                event_identity=event.event_identity,
                symbol=event.symbol,
                signal_as_of_ms=event.signal_as_of_ms,
                terminal_status=result.status,
                candidate_action=result.autonomy.candidate_action,
                reason_code=result.autonomy.reason_code.value,
                trace=trace,
                execution_input=result.execution_input,
                venue_rule_snapshot_identity=result.venue_rule_snapshot_identity,
                sizing=result.sizing,
                venue_bound_pretrade=result.venue_bound_pretrade,
                cost_preview=_build_plan_cost_preview(
                    event_identity=event.event_identity,
                    bound=result.venue_bound_pretrade,
                ),
            )
        )

    portfolio = read_paper_portfolio_snapshot(
        paper_ledger_path=paper_ledger_path,
        candle_cache_path=candle_cache_path,
        observed_at_ms=observed_at_ms,
    )
    performance = read_paper_trade_performance(
        paper_ledger_path=paper_ledger_path,
        observed_at_ms=observed_at_ms,
    )
    portfolio_exposure = _build_portfolio_exposure(portfolio)
    return _build_snapshot(
        activation=activation,
        signal_stream=signal_stream,
        decision_cadence=decision_cadence,
        scan=scan,
        candidates=tuple(candidates),
        portfolio=portfolio,
        portfolio_exposure=portfolio_exposure,
        performance=performance,
        observed_at_ms=observed_at_ms,
    )



def _build_portfolio_exposure(
    portfolio: PaperPortfolioSnapshot,
) -> PaperPortfolioExposureView:
    if portfolio.availability is not PaperPortfolioAvailability.AVAILABLE:
        return PaperPortfolioExposureView(
            availability=portfolio.availability,
            cash_usdt=portfolio.cash_usdt,
            marked_positions_value_usdt=None,
            nav_usdt=None,
            cash_fraction=None,
            invested_fraction=None,
            positions=tuple(
                PaperPortfolioExposurePosition(
                    symbol=item.symbol,
                    quantity=item.quantity,
                    marked_value_usdt=None,
                    nav_fraction=None,
                )
                for item in portfolio.positions
            ),
            real_capital=REAL_CAPITAL,
        )

    assert portfolio.marked_positions_value_usdt is not None
    assert portfolio.nav_usdt is not None
    nav = portfolio.nav_usdt
    can_fraction = nav > Decimal(0)
    positions = tuple(
        PaperPortfolioExposurePosition(
            symbol=item.symbol,
            quantity=item.quantity,
            marked_value_usdt=item.marked_value_usdt,
            nav_fraction=(
                item.marked_value_usdt / nav
                if can_fraction and item.marked_value_usdt is not None
                else None
            ),
        )
        for item in portfolio.positions
    )
    return PaperPortfolioExposureView(
        availability=portfolio.availability,
        cash_usdt=portfolio.cash_usdt,
        marked_positions_value_usdt=portfolio.marked_positions_value_usdt,
        nav_usdt=nav,
        cash_fraction=portfolio.cash_usdt / nav if can_fraction else None,
        invested_fraction=(
            portfolio.marked_positions_value_usdt / nav if can_fraction else None
        ),
        positions=positions,
        real_capital=REAL_CAPITAL,
    )


def _build_plan_cost_preview(
    *,
    event_identity: str,
    bound: PaperVenueBoundPretrade | None,
) -> PaperPlanCostPreview | None:
    if bound is None or bound.pretrade.plan is None:
        return None
    plan = bound.pretrade.plan
    preview = simulate_paper_fill(
        plan=plan,
        snapshot=bound.execution_snapshot,
        decision_identity=event_identity,
        filled_at_ms=plan.planned_at_ms,
    )
    if preview.costs is None:
        raise PaperMissionControlError(
            "trade plan cost preview requires explicit simulator costs"
        )
    if preview.total_cost_usdt != plan.cost_budget_usdt:
        raise PaperMissionControlError(
            "trade plan cost preview must match accepted cost budget exactly"
        )
    return PaperPlanCostPreview(
        execution_snapshot_identity=bound.execution_snapshot.snapshot_identity,
        fee_usdt=preview.costs.fee_usdt,
        spread_usdt=preview.costs.spread_usdt,
        slippage_usdt=preview.costs.slippage_usdt,
        total_cost_usdt=preview.total_cost_usdt,
        reference_notional_usdt=preview.reference_notional_usdt,
        fill_notional_usdt=preview.fill_notional_usdt,
        real_capital=REAL_CAPITAL,
    )

def _build_snapshot(
    *,
    activation: PaperActivationState,
    signal_stream: PaperSignalStreamOverview,
    decision_cadence: tuple[PaperDecisionCadenceReadiness, ...],
    scan: PaperSignalEventScanResult,
    candidates: tuple[PaperMissionControlCandidate, ...],
    portfolio: PaperPortfolioSnapshot,
    portfolio_exposure: PaperPortfolioExposureView,
    performance: PaperTradePerformanceSnapshot,
    observed_at_ms: int,
) -> PaperMissionControlSnapshot:
    ready_count = sum(
        1
        for item in candidates
        if item.terminal_status is PaperActivationDryRunStatus.PRETRADE_READY
    )
    payload = {
        "activation_cutoff_ms": activation.activation_cutoff_ms,
        "activation_identity": activation.activation_identity,
        "attention_required": ready_count > 0,
        "baseline_signal_freeze_count": activation.baseline_signal_freeze_count,
        "candidates": [_candidate_payload(item) for item in candidates],
        "decision_cadence": [
            _decision_cadence_payload(item) for item in decision_cadence
        ],
        "eligible_post_activation_freezes": scan.eligible_freeze_count,
        "incomplete_provider_pairs": scan.incomplete_pair_count,
        "observed_at_ms": observed_at_ms,
        "performance_snapshot_identity": performance.snapshot_identity,
        "portfolio_exposure": _portfolio_exposure_payload(portfolio_exposure),
        "portfolio_snapshot_identity": portfolio.snapshot_identity,
        "processed_event_skips": scan.processed_skip_count,
        "ready_candidate_count": ready_count,
        "signal_stream": _signal_stream_payload(signal_stream),
        "trade_policy": "NOT_ACTIVATED",
        "version": PAPER_MISSION_CONTROL_VERSION,
    }
    return PaperMissionControlSnapshot(
        snapshot_identity=canonical_sha256(payload),
        version=PAPER_MISSION_CONTROL_VERSION,
        observed_at_ms=observed_at_ms,
        activation_identity=activation.activation_identity,
        activation_cutoff_ms=activation.activation_cutoff_ms,
        baseline_signal_freeze_count=activation.baseline_signal_freeze_count,
        signal_stream=signal_stream,
        decision_cadence=decision_cadence,
        eligible_post_activation_freezes=scan.eligible_freeze_count,
        incomplete_provider_pairs=scan.incomplete_pair_count,
        processed_event_skips=scan.processed_skip_count,
        candidates=candidates,
        ready_candidate_count=ready_count,
        attention_required=ready_count > 0,
        portfolio=portfolio,
        portfolio_exposure=portfolio_exposure,
        performance=performance,
        trade_policy="NOT_ACTIVATED",
        real_capital=REAL_CAPITAL,
    )


def read_paper_decision_cadence_readiness(
    *,
    signal_ledger_path: Path,
    activation: PaperActivationState,
    scan: PaperSignalEventScanResult,
    observed_at_ms: int,
) -> tuple[PaperDecisionCadenceReadiness, ...]:
    """Explain 4h provider-pair readiness without inventing a candidate."""
    if observed_at_ms < 0:
        raise ValueError("observed_at_ms must be non-negative")
    if scan.activation_identity != activation.activation_identity:
        raise PaperMissionControlError("cadence scan/activation identity mismatch")
    if not signal_ledger_path.exists():
        raise PaperMissionControlError("signal ledger does not exist")

    uri = f"file:{signal_ledger_path.resolve()}?mode=ro"
    latest: dict[
        tuple[PaperSymbol, Exchange],
        PaperDecisionCadenceProviderEvidence,
    ] = {}
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            if connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'signal_freezes'
                """
            ).fetchone() is None:
                raise PaperMissionControlError(
                    "signal ledger missing required table: signal_freezes"
                )
            placeholders = ",".join("?" for _ in PERMITTED_SYMBOLS)
            rows = connection.execute(
                f"""
                SELECT
                    signal_freeze_identity,
                    exchange,
                    symbol,
                    as_of_ms,
                    source_cutoff_open_time_ms,
                    frozen_at_ms,
                    signal_state,
                    direction
                FROM signal_freezes
                WHERE market_type = ?
                  AND timeframe = ?
                  AND exchange IN (?, ?)
                  AND symbol IN ({placeholders})
                  AND as_of_ms <= ?
                  AND frozen_at_ms <= ?
                ORDER BY
                    symbol ASC,
                    exchange ASC,
                    as_of_ms DESC,
                    frozen_at_ms DESC,
                    signal_freeze_identity DESC
                """,
                (
                    MarketType.SPOT.value,
                    "4h",
                    Exchange.BINANCE.value,
                    Exchange.BYBIT.value,
                    *(symbol.value for symbol in sorted(
                        PERMITTED_SYMBOLS,
                        key=lambda item: item.value,
                    )),
                    observed_at_ms,
                    observed_at_ms,
                ),
            ).fetchall()
    except sqlite3.Error as exc:
        raise PaperMissionControlError(
            f"failed to read 4h decision-cadence readiness: {exc}"
        ) from exc

    for row in rows:
        try:
            symbol = PaperSymbol(str(row["symbol"]))
            exchange = Exchange(str(row["exchange"]))
        except ValueError as exc:
            raise PaperMissionControlError(
                "decision-cadence index contains unsupported symbol/exchange"
            ) from exc
        key = (symbol, exchange)
        if key in latest:
            continue
        latest[key] = PaperDecisionCadenceProviderEvidence(
            exchange=exchange,
            freeze_identity=str(row["signal_freeze_identity"]),
            signal_as_of_ms=int(row["as_of_ms"]),
            source_cutoff_open_time_ms=int(row["source_cutoff_open_time_ms"]),
            frozen_at_ms=int(row["frozen_at_ms"]),
            signal_state=str(row["signal_state"]),
            direction=str(row["direction"]),
        )

    candidate_keys = {
        (candidate.symbol, candidate.source_cutoff_open_time_ms)
        for candidate in scan.candidates
    }
    result: list[PaperDecisionCadenceReadiness] = []
    for symbol in sorted(PERMITTED_SYMBOLS, key=lambda item: item.value):
        binance = latest.get((symbol, Exchange.BINANCE))
        bybit = latest.get((symbol, Exchange.BYBIT))
        paired_as_of_ms: int | None = None
        paired_source_cutoff_open_time_ms: int | None = None
        candidate_available = False
        if binance is None and bybit is None:
            status = PaperDecisionCadenceStatus.NO_4H_EVIDENCE
        elif binance is None or bybit is None:
            status = PaperDecisionCadenceStatus.WAITING_PROVIDER_PAIR
        elif (
            binance.source_cutoff_open_time_ms
            != bybit.source_cutoff_open_time_ms
        ):
            status = PaperDecisionCadenceStatus.PROVIDER_CUTOFF_MISMATCH
        else:
            paired_as_of_ms = max(
                binance.signal_as_of_ms,
                bybit.signal_as_of_ms,
            )
            paired_source_cutoff_open_time_ms = (
                binance.source_cutoff_open_time_ms
            )
            if (
                binance.signal_as_of_ms < activation.activation_cutoff_ms
                or bybit.signal_as_of_ms < activation.activation_cutoff_ms
                or binance.frozen_at_ms < activation.activated_at_ms
                or bybit.frozen_at_ms < activation.activated_at_ms
            ):
                status = PaperDecisionCadenceStatus.PRE_ACTIVATION_PAIR
            else:
                status = PaperDecisionCadenceStatus.POST_ACTIVATION_PAIR
                candidate_available = (
                    symbol,
                    paired_source_cutoff_open_time_ms,
                ) in candidate_keys
        result.append(
            PaperDecisionCadenceReadiness(
                symbol=symbol,
                status=status,
                binance=binance,
                bybit=bybit,
                paired_as_of_ms=paired_as_of_ms,
                paired_source_cutoff_open_time_ms=(
                    paired_source_cutoff_open_time_ms
                ),
                candidate_available=candidate_available,
            )
        )
    return tuple(result)


def read_paper_signal_stream_overview(
    *,
    signal_ledger_path: Path,
    observed_at_ms: int,
) -> PaperSignalStreamOverview:
    if not signal_ledger_path.exists():
        raise PaperMissionControlError("signal ledger does not exist")
    uri = f"file:{signal_ledger_path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            if connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'signal_freezes'
                """
            ).fetchone() is None:
                raise PaperMissionControlError(
                    "signal ledger missing required table: signal_freezes"
                )
            count_row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM signal_freezes
                WHERE frozen_at_ms <= ? AND as_of_ms <= ?
                """,
                (observed_at_ms, observed_at_ms),
            ).fetchone()
            total = 0 if count_row is None else int(count_row["count"])
            row = connection.execute(
                """
                SELECT
                    signal_freeze_identity,
                    exchange,
                    symbol,
                    timeframe,
                    as_of_ms,
                    signal_state,
                    direction,
                    frozen_at_ms
                FROM signal_freezes
                WHERE frozen_at_ms <= ? AND as_of_ms <= ?
                ORDER BY frozen_at_ms DESC, signal_freeze_identity DESC
                LIMIT 1
                """,
                (observed_at_ms, observed_at_ms),
            ).fetchone()
    except sqlite3.Error as exc:
        raise PaperMissionControlError(
            f"failed to read signal stream overview: {exc}"
        ) from exc
    if row is None:
        return PaperSignalStreamOverview(
            total_freeze_count=0,
            latest_signal_freeze_identity=None,
            latest_frozen_at_ms=None,
            latest_signal_as_of_ms=None,
            latest_exchange=None,
            latest_symbol=None,
            latest_timeframe=None,
            latest_signal_state=None,
            latest_direction=None,
            latest_freeze_age_ms=None,
        )
    frozen_at_ms = int(row["frozen_at_ms"])
    return PaperSignalStreamOverview(
        total_freeze_count=total,
        latest_signal_freeze_identity=str(row["signal_freeze_identity"]),
        latest_frozen_at_ms=frozen_at_ms,
        latest_signal_as_of_ms=int(row["as_of_ms"]),
        latest_exchange=str(row["exchange"]),
        latest_symbol=str(row["symbol"]),
        latest_timeframe=str(row["timeframe"]),
        latest_signal_state=str(row["signal_state"]),
        latest_direction=str(row["direction"]),
        latest_freeze_age_ms=observed_at_ms - frozen_at_ms,
    )


def _validate_scan_point_in_time(
    *,
    scan: PaperSignalEventScanResult,
    observed_at_ms: int,
) -> None:
    for event in scan.candidates:
        if event.signal_as_of_ms > observed_at_ms:
            raise PaperMissionControlError(
                "scanner candidate signal as-of is after mission-control observation"
            )
        if any(value > observed_at_ms for value in event.source_frozen_at_ms):
            raise PaperMissionControlError(
                "scanner candidate freeze is after mission-control observation"
            )


def _decision_cadence_payload(
    item: PaperDecisionCadenceReadiness,
) -> dict[str, object]:
    def provider_payload(
        provider: PaperDecisionCadenceProviderEvidence | None,
    ) -> dict[str, object] | None:
        if provider is None:
            return None
        return {
            "direction": provider.direction,
            "exchange": provider.exchange.value,
            "freeze_identity": provider.freeze_identity,
            "frozen_at_ms": provider.frozen_at_ms,
            "signal_as_of_ms": provider.signal_as_of_ms,
            "source_cutoff_open_time_ms": provider.source_cutoff_open_time_ms,
            "signal_state": provider.signal_state,
        }

    return {
        "binance": provider_payload(item.binance),
        "bybit": provider_payload(item.bybit),
        "candidate_available": item.candidate_available,
        "paired_as_of_ms": item.paired_as_of_ms,
        "paired_source_cutoff_open_time_ms": (
            item.paired_source_cutoff_open_time_ms
        ),
        "status": item.status.value,
        "symbol": item.symbol.value,
    }


def _portfolio_exposure_payload(
    exposure: PaperPortfolioExposureView,
) -> dict[str, object]:
    return {
        "availability": exposure.availability.value,
        "cash_fraction": exposure.cash_fraction,
        "cash_usdt": exposure.cash_usdt,
        "invested_fraction": exposure.invested_fraction,
        "marked_positions_value_usdt": exposure.marked_positions_value_usdt,
        "nav_usdt": exposure.nav_usdt,
        "positions": [
            {
                "marked_value_usdt": item.marked_value_usdt,
                "nav_fraction": item.nav_fraction,
                "quantity": item.quantity,
                "symbol": item.symbol.value,
            }
            for item in exposure.positions
        ],
    }


def _candidate_payload(item: PaperMissionControlCandidate) -> dict[str, object]:
    return {
        "candidate_action": item.candidate_action.value,
        "cost_preview": (
            {
                "execution_snapshot_identity": (
                    item.cost_preview.execution_snapshot_identity
                ),
                "fee_usdt": item.cost_preview.fee_usdt,
                "fill_notional_usdt": item.cost_preview.fill_notional_usdt,
                "reference_notional_usdt": (
                    item.cost_preview.reference_notional_usdt
                ),
                "slippage_usdt": item.cost_preview.slippage_usdt,
                "spread_usdt": item.cost_preview.spread_usdt,
                "total_cost_usdt": item.cost_preview.total_cost_usdt,
            }
            if item.cost_preview is not None
            else None
        ),
        "event_identity": item.event_identity,
        "execution_input_identity": (
            item.execution_input.input_identity
            if item.execution_input is not None
            else None
        ),
        "plan_identity": (
            item.venue_bound_pretrade.pretrade.plan.plan_identity
            if (
                item.venue_bound_pretrade is not None
                and item.venue_bound_pretrade.pretrade.plan is not None
            )
            else None
        ),
        "pretrade_identity": (
            item.venue_bound_pretrade.pretrade.pretrade_identity
            if item.venue_bound_pretrade is not None
            else None
        ),
        "reason_code": item.reason_code,
        "signal_as_of_ms": item.signal_as_of_ms,
        "sizing_identity": (
            item.sizing.sizing_identity if item.sizing is not None else None
        ),
        "symbol": item.symbol.value,
        "terminal_status": item.terminal_status.value,
        "trace_identity": item.trace.trace_identity,
        "venue_rule_snapshot_identity": item.venue_rule_snapshot_identity,
    }


def _signal_stream_payload(
    overview: PaperSignalStreamOverview,
) -> dict[str, object]:
    return {
        "latest_direction": overview.latest_direction,
        "latest_exchange": overview.latest_exchange,
        "latest_freeze_age_ms": overview.latest_freeze_age_ms,
        "latest_frozen_at_ms": overview.latest_frozen_at_ms,
        "latest_signal_as_of_ms": overview.latest_signal_as_of_ms,
        "latest_signal_freeze_identity": overview.latest_signal_freeze_identity,
        "latest_signal_state": overview.latest_signal_state,
        "latest_symbol": overview.latest_symbol,
        "latest_timeframe": overview.latest_timeframe,
        "total_freeze_count": overview.total_freeze_count,
    }


def _snapshot_payload(
    snapshot: PaperMissionControlSnapshot,
) -> dict[str, object]:
    return {
        "activation_cutoff_ms": snapshot.activation_cutoff_ms,
        "activation_identity": snapshot.activation_identity,
        "attention_required": snapshot.attention_required,
        "baseline_signal_freeze_count": snapshot.baseline_signal_freeze_count,
        "candidates": [_candidate_payload(item) for item in snapshot.candidates],
        "decision_cadence": [
            _decision_cadence_payload(item) for item in snapshot.decision_cadence
        ],
        "eligible_post_activation_freezes": snapshot.eligible_post_activation_freezes,
        "incomplete_provider_pairs": snapshot.incomplete_provider_pairs,
        "observed_at_ms": snapshot.observed_at_ms,
        "performance_snapshot_identity": snapshot.performance.snapshot_identity,
        "portfolio_snapshot_identity": snapshot.portfolio.snapshot_identity,
        "processed_event_skips": snapshot.processed_event_skips,
        "ready_candidate_count": snapshot.ready_candidate_count,
        "signal_stream": _signal_stream_payload(snapshot.signal_stream),
        "trade_policy": snapshot.trade_policy,
        "version": snapshot.version,
    }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be SHA256")
