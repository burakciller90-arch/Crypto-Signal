"""Tests for paper_signal_event_scanner.v1."""

from __future__ import annotations

import hashlib
import inspect
import sqlite3
from decimal import Decimal

import pytest

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.ledger.serialization import canonical_json
from crypto_signal.paper import event_scanner as paper_event_scanner
from crypto_signal.paper.activation import (
    PAPER_ACTIVATION_SCHEMA_VERSION,
    PaperActivationState,
    PaperProcessedEventOutcome,
    activate_paper_policy,
    build_processed_event_receipt,
    compute_activation_identity,
    record_terminal_no_action,
)
from crypto_signal.paper.event_scanner import (
    PAPER_SIGNAL_EVENT_SCANNER_VERSION,
    PaperSignalEventScanError,
    scan_post_activation_signal_events,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperSymbol,
    build_fund_creation,
)
from crypto_signal.paper.state import reconstruct_paper_fund_state
from crypto_signal.signals.models import (
    EntryReferenceModel,
    HistoricalStatsStatus,
    MethodologyVersionRef,
    ProbabilityStatus,
    RiskRewardTarget,
    SignalAgreementSummary,
    SignalDecision,
    SignalDirection,
    SignalGeometry,
    SignalState,
)

ACTIVATED_AT = 1_000


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _paper_activation(tmp_path):
    ledger = PaperFundLedger(tmp_path / "paper.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    state = reconstruct_paper_fund_state(ledger)
    _, activation = activate_paper_policy(
        ledger=ledger,
        state=state,
        activated_at_ms=ACTIVATED_AT,
        baseline_signal_freeze_count=0,
        baseline_latest_signal_freeze_identity=None,
        baseline_latest_frozen_at_ms=None,
    )
    return ledger, state, activation


def _decision(
    *,
    exchange: Exchange,
    symbol: PaperSymbol,
    as_of_ms: int,
    suffix: str = "",
) -> SignalDecision:
    identity = _sha(f"{exchange.value}:{symbol.value}:{as_of_ms}:{suffix}")
    return SignalDecision(
        freeze_identity=identity,
        signal_version="signal.test.v1",
        state=SignalState.ACTIVE,
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol=symbol.value,
        timeframe="4h",
        as_of_ms=as_of_ms,
        direction=SignalDirection.BULLISH,
        setup_type="scanner-test",
        geometry=SignalGeometry(
            source_evidence_id=f"{exchange.value}-geometry",
            source_methodology=MethodologyKind.HARMONIC,
            entry_zone=PriceZone(Decimal(95), Decimal(105)),
            entry_reference_price=Decimal(100),
            entry_reference_model=(
                EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
            ),
            invalidation_price=Decimal(90),
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=(
                RiskRewardTarget("t1", Decimal(110), Decimal(1)),
            ),
        ),
        agreement=SignalAgreementSummary(
            confluence_score=Decimal("66.67"),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2,
            opposing_method_count=0,
            resolved_method_count=2,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(
            f"{exchange.value}-a",
            f"{exchange.value}-b",
        ),
        methodology_versions=(
            MethodologyVersionRef(MethodologyKind.PRICE_ACTION, "pa.test.v1"),
            MethodologyVersionRef(MethodologyKind.HARMONIC, "h.test.v1"),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=("partial_methodology_coverage",),
        evidence_summary=(),
    )


def _init_signal_db(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE signal_freezes (
                bundle_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL UNIQUE,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                as_of_ms INTEGER NOT NULL,
                source_cutoff_open_time_ms INTEGER NOT NULL,
                signal_state TEXT NOT NULL,
                direction TEXT NOT NULL,
                bundle_json TEXT NOT NULL,
                frozen_at_ms INTEGER NOT NULL
            )
            """
        )


def _insert_signal(
    path,
    decision: SignalDecision,
    *,
    frozen_at_ms: int | None = None,
    indexed_state: str | None = None,
) -> None:
    frozen = decision.as_of_ms + 10 if frozen_at_ms is None else frozen_at_ms
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO signal_freezes (
                bundle_identity,
                signal_freeze_identity,
                exchange,
                market_type,
                symbol,
                timeframe,
                as_of_ms,
                source_cutoff_open_time_ms,
                signal_state,
                direction,
                bundle_json,
                frozen_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _sha(f"bundle:{decision.freeze_identity}"),
                decision.freeze_identity,
                decision.exchange.value,
                decision.market_type.value,
                decision.symbol,
                decision.timeframe,
                decision.as_of_ms,
                decision.as_of_ms - 1,
                decision.state.value if indexed_state is None else indexed_state,
                decision.direction.value,
                canonical_json({"signal_decision": decision}),
                frozen,
            ),
        )


def test_exact_post_activation_provider_pair_becomes_candidate(tmp_path) -> None:
    ledger, _, activation = _paper_activation(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    binance = _decision(
        exchange=Exchange.BINANCE,
        symbol=PaperSymbol.BTCUSDT,
        as_of_ms=1_100,
    )
    bybit = _decision(
        exchange=Exchange.BYBIT,
        symbol=PaperSymbol.BTCUSDT,
        as_of_ms=1_100,
    )
    _insert_signal(signal_db, bybit)
    _insert_signal(signal_db, binance)

    result = scan_post_activation_signal_events(
        signal_ledger_path=signal_db,
        paper_ledger_path=ledger.path,
        activation=activation,
    )

    assert result.scanner_version == PAPER_SIGNAL_EVENT_SCANNER_VERSION
    assert result.eligible_freeze_count == 2
    assert result.incomplete_pair_count == 0
    assert result.processed_skip_count == 0
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.signals == (binance, bybit)
    assert candidate.source_freeze_identities == (
        binance.freeze_identity,
        bybit.freeze_identity,
    )
    assert candidate.real_capital == REAL_CAPITAL == 0


def test_pre_activation_and_incomplete_events_do_not_emit_candidates(tmp_path) -> None:
    ledger, _, activation = _paper_activation(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    for exchange in (Exchange.BINANCE, Exchange.BYBIT):
        _insert_signal(
            signal_db,
            _decision(
                exchange=exchange,
                symbol=PaperSymbol.BTCUSDT,
                as_of_ms=900,
            ),
            frozen_at_ms=950,
        )
    _insert_signal(
        signal_db,
        _decision(
            exchange=Exchange.BINANCE,
            symbol=PaperSymbol.ETHUSDT,
            as_of_ms=1_100,
        ),
    )

    result = scan_post_activation_signal_events(
        signal_ledger_path=signal_db,
        paper_ledger_path=ledger.path,
        activation=activation,
    )

    assert result.eligible_freeze_count == 1
    assert result.incomplete_pair_count == 1
    assert result.candidates == ()


def test_processed_event_is_skipped_deterministically(tmp_path) -> None:
    ledger, state, activation = _paper_activation(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    binance = _decision(
        exchange=Exchange.BINANCE,
        symbol=PaperSymbol.SOLUSDT,
        as_of_ms=1_100,
    )
    bybit = _decision(
        exchange=Exchange.BYBIT,
        symbol=PaperSymbol.SOLUSDT,
        as_of_ms=1_100,
    )
    _insert_signal(signal_db, binance)
    _insert_signal(signal_db, bybit)
    receipt = build_processed_event_receipt(
        activation=activation,
        source_freeze_identities=(
            binance.freeze_identity,
            bybit.freeze_identity,
        ),
        symbol=PaperSymbol.SOLUSDT,
        timeframe="4h",
        signal_as_of_ms=1_100,
        outcome=PaperProcessedEventOutcome.TERMINAL_NO_ACTION,
        processed_at_ms=1_200,
        terminal_reason="scanner processed-event test",
    )
    record_terminal_no_action(
        ledger=ledger,
        state=state,
        activation=activation,
        receipt=receipt,
    )

    result = scan_post_activation_signal_events(
        signal_ledger_path=signal_db,
        paper_ledger_path=ledger.path,
        activation=activation,
    )
    assert result.processed_skip_count == 1
    assert result.candidates == ()


def test_duplicate_provider_context_fails_closed(tmp_path) -> None:
    ledger, _, activation = _paper_activation(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    _insert_signal(
        signal_db,
        _decision(
            exchange=Exchange.BINANCE,
            symbol=PaperSymbol.BTCUSDT,
            as_of_ms=1_100,
            suffix="one",
        ),
    )
    _insert_signal(
        signal_db,
        _decision(
            exchange=Exchange.BINANCE,
            symbol=PaperSymbol.BTCUSDT,
            as_of_ms=1_100,
            suffix="two",
        ),
    )
    _insert_signal(
        signal_db,
        _decision(
            exchange=Exchange.BYBIT,
            symbol=PaperSymbol.BTCUSDT,
            as_of_ms=1_100,
        ),
    )

    with pytest.raises(PaperSignalEventScanError, match="duplicate provider"):
        scan_post_activation_signal_events(
            signal_ledger_path=signal_db,
            paper_ledger_path=ledger.path,
            activation=activation,
        )


def test_index_bundle_lineage_mismatch_fails_closed(tmp_path) -> None:
    ledger, _, activation = _paper_activation(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    _insert_signal(
        signal_db,
        _decision(
            exchange=Exchange.BINANCE,
            symbol=PaperSymbol.BTCUSDT,
            as_of_ms=1_100,
        ),
        indexed_state=SignalState.WATCH.value,
    )

    with pytest.raises(PaperSignalEventScanError, match="index/bundle"):
        scan_post_activation_signal_events(
            signal_ledger_path=signal_db,
            paper_ledger_path=ledger.path,
            activation=activation,
        )


def test_candidates_are_ordered_by_asof_then_symbol(tmp_path) -> None:
    ledger, _, activation = _paper_activation(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    contexts = (
        (PaperSymbol.SOLUSDT, 1_200),
        (PaperSymbol.ETHUSDT, 1_100),
        (PaperSymbol.BTCUSDT, 1_100),
    )
    for symbol, as_of_ms in contexts:
        for exchange in (Exchange.BYBIT, Exchange.BINANCE):
            _insert_signal(
                signal_db,
                _decision(
                    exchange=exchange,
                    symbol=symbol,
                    as_of_ms=as_of_ms,
                ),
            )

    result = scan_post_activation_signal_events(
        signal_ledger_path=signal_db,
        paper_ledger_path=ledger.path,
        activation=activation,
    )
    assert tuple(
        (item.signal_as_of_ms, item.symbol)
        for item in result.candidates
    ) == (
        (1_100, PaperSymbol.BTCUSDT),
        (1_100, PaperSymbol.ETHUSDT),
        (1_200, PaperSymbol.SOLUSDT),
    )


def test_scanner_requires_matching_persistent_activation(tmp_path) -> None:
    ledger, _, activation = _paper_activation(tmp_path)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    mismatched_activated_at = activation.activated_at_ms + 1
    mismatched_identity = compute_activation_identity(
        schema_version=PAPER_ACTIVATION_SCHEMA_VERSION,
        fund_identity=activation.fund_identity,
        activated_at_ms=mismatched_activated_at,
        activation_cutoff_ms=mismatched_activated_at,
        baseline_signal_freeze_count=0,
        baseline_latest_signal_freeze_identity=None,
        baseline_latest_frozen_at_ms=None,
    )
    mismatched = PaperActivationState(
        activation_identity=mismatched_identity,
        schema_version=PAPER_ACTIVATION_SCHEMA_VERSION,
        fund_identity=activation.fund_identity,
        activated_at_ms=mismatched_activated_at,
        activation_cutoff_ms=mismatched_activated_at,
        baseline_signal_freeze_count=0,
        baseline_latest_signal_freeze_identity=None,
        baseline_latest_frozen_at_ms=None,
        real_capital=REAL_CAPITAL,
    )
    with pytest.raises(
        PaperSignalEventScanError,
        match="persistent activation identity mismatch",
    ):
        scan_post_activation_signal_events(
            signal_ledger_path=signal_db,
            paper_ledger_path=ledger.path,
            activation=mismatched,
        )


def test_scanner_surface_is_strictly_read_only() -> None:
    source = inspect.getsource(paper_event_scanner).lower()
    forbidden = (
        "insert into",
        "update ",
        "delete from",
        "create table",
        "requests",
        "httpx",
        "place_order",
        "submit_order",
        "cancel_order",
        "simulate_paper_fill",
        "commit_planned_pretrade",
        "run_paper_runtime_tick",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert paper_event_scanner.REAL_CAPITAL == REAL_CAPITAL == 0
