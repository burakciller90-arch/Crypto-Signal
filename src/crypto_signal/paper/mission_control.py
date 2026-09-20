"""Read-only paper mission-control composition.

This module composes already accepted production truth into one deterministic
snapshot for product surfaces. It never mutates paper or signal ledgers and
never grants trade authority. Candidate explanations come only from the
accepted dry-run decision trace; no free-form trader thoughts are invented.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

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
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol
from crypto_signal.paper.performance import (
    PaperTradePerformanceSnapshot,
    read_paper_trade_performance,
)
from crypto_signal.paper.portfolio import (
    PaperPortfolioSnapshot,
    read_paper_portfolio_snapshot,
)

__all__ = [
    "PAPER_MISSION_CONTROL_VERSION",
    "PaperMissionControlCandidate",
    "PaperMissionControlError",
    "PaperMissionControlSnapshot",
    "PaperSignalStreamOverview",
    "read_paper_mission_control_snapshot",
    "read_paper_signal_stream_overview",
]

PAPER_MISSION_CONTROL_VERSION = "paper_mission_control.v1"


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


@dataclass(frozen=True, slots=True)
class PaperMissionControlCandidate:
    event_identity: str
    symbol: PaperSymbol
    signal_as_of_ms: int
    terminal_status: PaperActivationDryRunStatus
    candidate_action: PaperAction
    reason_code: str
    trace: PaperDecisionTrace

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


@dataclass(frozen=True, slots=True)
class PaperMissionControlSnapshot:
    snapshot_identity: str
    version: str
    observed_at_ms: int
    activation_identity: str
    activation_cutoff_ms: int
    baseline_signal_freeze_count: int
    signal_stream: PaperSignalStreamOverview
    eligible_post_activation_freezes: int
    incomplete_provider_pairs: int
    processed_event_skips: int
    candidates: tuple[PaperMissionControlCandidate, ...]
    ready_candidate_count: int
    attention_required: bool
    portfolio: PaperPortfolioSnapshot
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
    return _build_snapshot(
        activation=activation,
        signal_stream=signal_stream,
        scan=scan,
        candidates=tuple(candidates),
        portfolio=portfolio,
        performance=performance,
        observed_at_ms=observed_at_ms,
    )


def _build_snapshot(
    *,
    activation: PaperActivationState,
    signal_stream: PaperSignalStreamOverview,
    scan: PaperSignalEventScanResult,
    candidates: tuple[PaperMissionControlCandidate, ...],
    portfolio: PaperPortfolioSnapshot,
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
        "eligible_post_activation_freezes": scan.eligible_freeze_count,
        "incomplete_provider_pairs": scan.incomplete_pair_count,
        "observed_at_ms": observed_at_ms,
        "performance_snapshot_identity": performance.snapshot_identity,
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
        eligible_post_activation_freezes=scan.eligible_freeze_count,
        incomplete_provider_pairs=scan.incomplete_pair_count,
        processed_event_skips=scan.processed_skip_count,
        candidates=candidates,
        ready_candidate_count=ready_count,
        attention_required=ready_count > 0,
        portfolio=portfolio,
        performance=performance,
        trade_policy="NOT_ACTIVATED",
        real_capital=REAL_CAPITAL,
    )


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


def _candidate_payload(item: PaperMissionControlCandidate) -> dict[str, object]:
    return {
        "candidate_action": item.candidate_action.value,
        "event_identity": item.event_identity,
        "reason_code": item.reason_code,
        "signal_as_of_ms": item.signal_as_of_ms,
        "symbol": item.symbol.value,
        "terminal_status": item.terminal_status.value,
        "trace_identity": item.trace.trace_identity,
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
