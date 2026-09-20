"""Tests for paper_activation_dry_run.v1."""

from __future__ import annotations

import hashlib
import inspect
import sqlite3
from decimal import Decimal

from crypto_signal.confluence.models import (
    InvalidationTrigger,
    MethodologyKind,
    PriceZone,
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import dry_run as paper_dry_run
from crypto_signal.paper.activation import (
    activate_paper_policy,
    compute_processed_event_identity,
)
from crypto_signal.paper.dry_run import (
    PAPER_ACTIVATION_DRY_RUN_VERSION,
    PaperActivationDryRunStatus,
    evaluate_paper_activation_dry_run,
    read_paper_activation_read_only,
)
from crypto_signal.paper.event_scanner import (
    PAPER_SIGNAL_EVENT_SCANNER_VERSION,
    PaperSignalEventCandidate,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperSymbol,
    build_fund_creation,
)
from crypto_signal.paper.state import reconstruct_paper_fund_state
from crypto_signal.paper.venue_rules import (
    PaperVenueRuleStore,
    parse_binance_spot_venue_rules,
)
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

ACTIVATED_AT = 900
SIGNAL_AS_OF = 1_000
EVALUATED_AT = 2_000


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _paper(tmp_path):
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


def _signal(exchange: Exchange, *, state: SignalState = SignalState.ACTIVE):
    identity = _sha(f"{exchange.value}:{state.value}")
    geometry = (
        SignalGeometry(
            source_evidence_id=f"{exchange.value}-g",
            source_methodology=MethodologyKind.HARMONIC,
            entry_zone=PriceZone(Decimal(95), Decimal(105)),
            entry_reference_price=Decimal(100),
            entry_reference_model=(
                EntryReferenceModel.ZONE_MIDPOINT_REFERENCE_NOT_EXECUTION
            ),
            invalidation_price=Decimal(90),
            invalidation_trigger=InvalidationTrigger.TOUCH_OR_CROSS,
            targets=(RiskRewardTarget("t1", Decimal(110), Decimal(1)),),
        )
        if state is SignalState.ACTIVE
        else None
    )
    return SignalDecision(
        freeze_identity=identity,
        signal_version="signal.test.v1",
        state=state,
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="4h",
        as_of_ms=SIGNAL_AS_OF,
        direction=SignalDirection.BULLISH,
        setup_type="dry-run-test",
        geometry=geometry,
        agreement=SignalAgreementSummary(
            confluence_score=Decimal("66.67"),
            score_semantic=ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY,
            support_method_count=2 if state is SignalState.ACTIVE else 1,
            opposing_method_count=0,
            resolved_method_count=2 if state is SignalState.ACTIVE else 1,
            total_methodology_slots=3,
            pairwise_relations=(),
        ),
        selected_evidence_ids=(f"{exchange.value}-a", f"{exchange.value}-b"),
        methodology_versions=(
            MethodologyVersionRef(MethodologyKind.PRICE_ACTION, "pa.v1"),
            MethodologyVersionRef(MethodologyKind.HARMONIC, "h.v1"),
        ),
        probability_status=ProbabilityStatus.NOT_CALIBRATED,
        historical_stats_status=HistoricalStatsStatus.NOT_EVALUATED,
        uncertainty_flags=("partial_methodology_coverage",),
        evidence_summary=(),
    )


def _event(activation, *, state: SignalState = SignalState.ACTIVE):
    signals = (
        _signal(Exchange.BINANCE, state=state),
        _signal(Exchange.BYBIT, state=state),
    )
    source_ids = (signals[0].freeze_identity, signals[1].freeze_identity)
    identity = compute_processed_event_identity(
        activation_identity=activation.activation_identity,
        source_freeze_identities=source_ids,
        symbol=PaperSymbol.BTCUSDT,
        timeframe="4h",
        signal_as_of_ms=SIGNAL_AS_OF,
    )
    return PaperSignalEventCandidate(
        event_identity=identity,
        scanner_version=PAPER_SIGNAL_EVENT_SCANNER_VERSION,
        activation_identity=activation.activation_identity,
        symbol=PaperSymbol.BTCUSDT,
        timeframe="4h",
        signal_as_of_ms=SIGNAL_AS_OF,
        source_freeze_identities=source_ids,
        source_frozen_at_ms=(1_010, 1_011),
        signals=signals,
        real_capital=REAL_CAPITAL,
    )


def _candle_cache(path, *, include_future: bool = True):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE candles (
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time_ms INTEGER NOT NULL,
                close_time_ms INTEGER NOT NULL,
                open TEXT NOT NULL,
                high TEXT NOT NULL,
                low TEXT NOT NULL,
                close TEXT NOT NULL,
                volume TEXT NOT NULL,
                quote_volume TEXT,
                trade_count INTEGER,
                is_closed INTEGER NOT NULL,
                source TEXT NOT NULL,
                source_timestamp_ms INTEGER NOT NULL,
                ingested_at_ms INTEGER NOT NULL,
                adapter_version TEXT NOT NULL,
                PRIMARY KEY (
                    exchange,
                    market_type,
                    symbol,
                    timeframe,
                    open_time_ms
                )
            )
            """
        )
        if include_future:
            connection.execute(
                """
                INSERT INTO candles VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    Exchange.BINANCE.value,
                    MarketType.SPOT.value,
                    "BTCUSDT",
                    "15m",
                    1_100,
                    1_300,
                    "100",
                    "101",
                    "99",
                    "100",
                    "1",
                    None,
                    1,
                    1,
                    "rest",
                    1_300,
                    1_301,
                    "adapter.test.v1",
                ),
            )
    return path


def _rules_payload():
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "isSpotTradingAllowed": True,
                "orderTypes": ["LIMIT", "MARKET"],
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.01",
                        "maxPrice": "1000000",
                        "tickSize": "0.01",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.00001",
                        "maxQty": "9000",
                        "stepSize": "0.00001",
                    },
                    {
                        "filterType": "NOTIONAL",
                        "minNotional": "5",
                        "applyMinToMarket": True,
                        "maxNotional": "100000000",
                    },
                ],
            }
        ]
    }


def _append_rules(ledger: PaperFundLedger, *, observed_at_ms: int = 1_500):
    snapshot = parse_binance_spot_venue_rules(
        _rules_payload(),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=observed_at_ms,
    )
    PaperVenueRuleStore(ledger.path).append(snapshot)
    return snapshot


def test_read_only_activation_loader_returns_exact_persistent_state(tmp_path) -> None:
    ledger, _, activation = _paper(tmp_path)
    before = tuple(
        (entry.record_identity, entry.payload_json)
        for entry in ledger.replay()
    )

    loaded = read_paper_activation_read_only(ledger.path)

    after = tuple(
        (entry.record_identity, entry.payload_json)
        for entry in ledger.replay()
    )
    assert loaded == activation
    assert before == after


def test_read_only_activation_loader_rejects_missing_singleton(tmp_path) -> None:
    ledger = PaperFundLedger(tmp_path / "paper.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))

    try:
        read_paper_activation_read_only(ledger.path)
    except paper_dry_run.PaperActivationDryRunError as exc:
        assert "not initialized" in str(exc)
    else:
        raise AssertionError("missing activation must fail closed")


def test_dry_run_reaches_pretrade_ready_without_mutating_paper_ledger(tmp_path) -> None:
    ledger, _, activation = _paper(tmp_path)
    rules = _append_rules(ledger)
    candle_cache = _candle_cache(tmp_path / "candles.sqlite3")
    event = _event(activation)
    before = tuple(
        (entry.record_identity, entry.payload_json)
        for entry in ledger.replay()
    )

    result = evaluate_paper_activation_dry_run(
        event=event,
        activation=activation,
        paper_ledger_path=ledger.path,
        candle_cache_path=candle_cache,
        evaluated_at_ms=EVALUATED_AT,
    )

    after = tuple(
        (entry.record_identity, entry.payload_json)
        for entry in ledger.replay()
    )
    assert result.version == PAPER_ACTIVATION_DRY_RUN_VERSION
    assert result.status is PaperActivationDryRunStatus.PRETRADE_READY
    assert result.execution_input is not None
    assert result.venue_rule_snapshot_identity == rules.snapshot_identity
    assert result.sizing is not None
    assert result.venue_bound_pretrade is not None
    assert result.venue_bound_pretrade.pretrade.plan is not None
    assert before == after
    assert result.real_capital == REAL_CAPITAL == 0


def test_dry_run_hold_stops_before_execution_input(tmp_path) -> None:
    ledger, _, activation = _paper(tmp_path)
    _append_rules(ledger)
    candle_cache = _candle_cache(tmp_path / "candles.sqlite3")
    result = evaluate_paper_activation_dry_run(
        event=_event(activation, state=SignalState.WATCH),
        activation=activation,
        paper_ledger_path=ledger.path,
        candle_cache_path=candle_cache,
        evaluated_at_ms=EVALUATED_AT,
    )
    assert result.status is PaperActivationDryRunStatus.HOLD_CASH
    assert result.execution_input is None
    assert result.sizing is None
    assert result.venue_bound_pretrade is None


def test_dry_run_waits_for_first_closed_post_signal_candle(tmp_path) -> None:
    ledger, _, activation = _paper(tmp_path)
    _append_rules(ledger)
    candle_cache = _candle_cache(
        tmp_path / "candles.sqlite3",
        include_future=False,
    )
    result = evaluate_paper_activation_dry_run(
        event=_event(activation),
        activation=activation,
        paper_ledger_path=ledger.path,
        candle_cache_path=candle_cache,
        evaluated_at_ms=EVALUATED_AT,
    )
    assert result.status is PaperActivationDryRunStatus.WAITING_EXECUTION_INPUT


def test_dry_run_waits_when_no_asof_venue_rule_snapshot_exists(tmp_path) -> None:
    ledger, _, activation = _paper(tmp_path)
    candle_cache = _candle_cache(tmp_path / "candles.sqlite3")
    result = evaluate_paper_activation_dry_run(
        event=_event(activation),
        activation=activation,
        paper_ledger_path=ledger.path,
        candle_cache_path=candle_cache,
        evaluated_at_ms=EVALUATED_AT,
    )
    assert result.status is PaperActivationDryRunStatus.WAITING_VENUE_RULES
    assert result.execution_input is not None
    assert result.venue_rule_snapshot_identity is None


def test_future_venue_rule_snapshot_is_not_backdated_into_dry_run(tmp_path) -> None:
    ledger, _, activation = _paper(tmp_path)
    _append_rules(ledger, observed_at_ms=2_001)
    candle_cache = _candle_cache(tmp_path / "candles.sqlite3")
    result = evaluate_paper_activation_dry_run(
        event=_event(activation),
        activation=activation,
        paper_ledger_path=ledger.path,
        candle_cache_path=candle_cache,
        evaluated_at_ms=EVALUATED_AT,
    )
    assert result.status is PaperActivationDryRunStatus.WAITING_VENUE_RULES


def test_dry_run_surface_contains_no_write_or_commit_authority() -> None:
    source = inspect.getsource(paper_dry_run).lower()
    forbidden = (
        "insert into",
        "update ",
        "delete from",
        "create table",
        "append_",
        "commit_planned_pretrade",
        "commit_orchestration_bundle",
        "record_terminal_no_action",
        "commit_planned_pretrade_event",
        "fetch_binance_spot_venue_rules",
        "httpx",
        "requests",
        "place_order",
        "submit_order",
        "cancel_order",
        "launchctl",
        "subprocess",
    )
    assert all(token not in source for token in forbidden)
    assert paper_dry_run.REAL_CAPITAL == REAL_CAPITAL == 0
