"""Integration tests for the bounded authorized virtual-paper write tick."""

from __future__ import annotations

import hashlib
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
from crypto_signal.paper import write_tick as paper_write_tick
from crypto_signal.paper.activation import activate_paper_policy
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
from crypto_signal.paper.write_authority import (
    PaperWriteAuthorityError,
    append_paper_write_authority_event,
)
from crypto_signal.paper.write_tick import (
    PaperWriteEventDisposition,
    run_paper_write_tick,
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
SHARED_CUTOFF = 999
EVALUATED_AT = 2_000


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _paper(tmp_path, *, authority_enabled: bool):
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
    if authority_enabled:
        append_paper_write_authority_event(
            ledger=ledger,
            activation=activation,
            enabled=True,
            created_at_ms=950,
            reason="write tick integration test",
            reviewed_event_identities=("a" * 64,),
            reviewed_trace_identities=("b" * 64,),
        )
    return ledger, activation


def _signal(
    exchange: Exchange,
    *,
    state: SignalState,
) -> SignalDecision:
    identity = _sha(f"{exchange.value}:{state.value}")
    geometry = (
        SignalGeometry(
            source_evidence_id=f"{exchange.value}-geometry",
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
        symbol=PaperSymbol.BTCUSDT.value,
        timeframe="4h",
        as_of_ms=SIGNAL_AS_OF,
        direction=SignalDirection.BULLISH,
        setup_type="write-tick-test",
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
        selected_evidence_ids=(
            f"{exchange.value}-pa",
            f"{exchange.value}-harmonic",
        ),
        methodology_versions=(
            MethodologyVersionRef(MethodologyKind.PRICE_ACTION, "pa.test.v1"),
            MethodologyVersionRef(MethodologyKind.HARMONIC, "harmonic.test.v1"),
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


def _insert_provider_pair(path, *, state: SignalState) -> None:
    with sqlite3.connect(path) as connection:
        for index, exchange in enumerate((Exchange.BINANCE, Exchange.BYBIT)):
            decision = _signal(exchange, state=state)
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
                    SHARED_CUTOFF,
                    decision.state.value,
                    decision.direction.value,
                    canonical_json({"signal_decision": decision}),
                    SIGNAL_AS_OF + 10 + index,
                ),
            )


def _init_candle_cache(path, *, include_execution_candle: bool) -> None:
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
        if include_execution_candle:
            connection.execute(
                """
                INSERT INTO candles VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    Exchange.BINANCE.value,
                    MarketType.SPOT.value,
                    PaperSymbol.BTCUSDT.value,
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


def _rules_payload() -> dict[str, object]:
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


def _append_rules(ledger: PaperFundLedger) -> None:
    snapshot = parse_binance_spot_venue_rules(
        _rules_payload(),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=1_500,
    )
    PaperVenueRuleStore(ledger.path).append(snapshot)


def _processed_count(path) -> int:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM paper_processed_events"
            ).fetchone()[0]
        )


def test_disabled_write_authority_is_strict_noop(tmp_path) -> None:
    ledger, _ = _paper(tmp_path, authority_enabled=False)

    result = run_paper_write_tick(
        paper_ledger_path=ledger.path,
        signal_ledger_path=tmp_path / "missing-signals.sqlite3",
        candle_cache_path=tmp_path / "missing-candles.sqlite3",
        evaluated_at_ms=EVALUATED_AT,
    )

    assert result.authority_enabled is False
    assert result.scanned_candidate_count == 0
    assert result.event_results == ()
    assert _processed_count(ledger.path) == 0
    assert reconstruct_paper_fund_state(ledger).replayed_record_count == 1


def test_authority_revoked_during_evaluation_blocks_mutation(
    tmp_path,
    monkeypatch,
) -> None:
    ledger, activation = _paper(tmp_path, authority_enabled=True)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    _insert_provider_pair(signal_db, state=SignalState.WATCH)

    original_evaluate = paper_write_tick.evaluate_paper_activation_dry_run

    def revoke_then_evaluate(**kwargs):
        append_paper_write_authority_event(
            ledger=ledger,
            activation=activation,
            enabled=False,
            created_at_ms=1_500,
            reason="operator revoke during evaluation",
        )
        return original_evaluate(**kwargs)

    monkeypatch.setattr(
        paper_write_tick,
        "evaluate_paper_activation_dry_run",
        revoke_then_evaluate,
    )

    with pytest.raises(PaperWriteAuthorityError, match="revoked"):
        paper_write_tick.run_paper_write_tick(
            paper_ledger_path=ledger.path,
            signal_ledger_path=signal_db,
            candle_cache_path=tmp_path / "missing-candles.sqlite3",
            evaluated_at_ms=EVALUATED_AT,
        )

    assert _processed_count(ledger.path) == 0
    assert reconstruct_paper_fund_state(ledger).replayed_record_count == 1


def test_frozen_watch_pair_records_terminal_no_action_once(tmp_path) -> None:
    ledger, _ = _paper(tmp_path, authority_enabled=True)
    signal_db = tmp_path / "signals.sqlite3"
    _init_signal_db(signal_db)
    _insert_provider_pair(signal_db, state=SignalState.WATCH)

    first = run_paper_write_tick(
        paper_ledger_path=ledger.path,
        signal_ledger_path=signal_db,
        candle_cache_path=tmp_path / "missing-candles.sqlite3",
        evaluated_at_ms=EVALUATED_AT,
    )
    second = run_paper_write_tick(
        paper_ledger_path=ledger.path,
        signal_ledger_path=signal_db,
        candle_cache_path=tmp_path / "missing-candles.sqlite3",
        evaluated_at_ms=EVALUATED_AT + 1,
    )

    assert first.terminal_no_action_count == 1
    assert first.committed_trade_count == 0
    assert first.event_results[0].disposition is PaperWriteEventDisposition.TERMINAL_NO_ACTION
    assert first.event_results[0].reason_code == "signal_not_active"
    assert _processed_count(ledger.path) == 1
    assert reconstruct_paper_fund_state(ledger).replayed_record_count == 1
    assert second.scanned_candidate_count == 0
    assert second.processed_skip_count == 1
    assert second.event_results == ()


def test_waiting_execution_input_remains_retryable_and_unprocessed(tmp_path) -> None:
    ledger, _ = _paper(tmp_path, authority_enabled=True)
    signal_db = tmp_path / "signals.sqlite3"
    candle_db = tmp_path / "candles.sqlite3"
    _init_signal_db(signal_db)
    _insert_provider_pair(signal_db, state=SignalState.ACTIVE)
    _init_candle_cache(candle_db, include_execution_candle=False)

    result = run_paper_write_tick(
        paper_ledger_path=ledger.path,
        signal_ledger_path=signal_db,
        candle_cache_path=candle_db,
        evaluated_at_ms=EVALUATED_AT,
    )

    assert result.retryable_count == 1
    assert result.event_results[0].status.value == "waiting_execution_input"
    assert result.event_results[0].disposition is PaperWriteEventDisposition.RETRYABLE
    assert _processed_count(ledger.path) == 0
    assert reconstruct_paper_fund_state(ledger).replayed_record_count == 1


def test_pretrade_ready_commits_only_simulated_paper_trade_atomically(tmp_path) -> None:
    ledger, _ = _paper(tmp_path, authority_enabled=True)
    signal_db = tmp_path / "signals.sqlite3"
    candle_db = tmp_path / "candles.sqlite3"
    _init_signal_db(signal_db)
    _insert_provider_pair(signal_db, state=SignalState.ACTIVE)
    _init_candle_cache(candle_db, include_execution_candle=True)
    _append_rules(ledger)

    result = run_paper_write_tick(
        paper_ledger_path=ledger.path,
        signal_ledger_path=signal_db,
        candle_cache_path=candle_db,
        evaluated_at_ms=EVALUATED_AT,
    )

    state = reconstruct_paper_fund_state(ledger)
    assert result.committed_trade_count == 1
    assert result.terminal_no_action_count == 0
    assert result.event_results[0].disposition is PaperWriteEventDisposition.COMMITTED_TRADE
    assert len(result.event_results[0].record_identities) == 3
    assert _processed_count(ledger.path) == 1
    assert state.replayed_record_count == 4
    assert state.cash_usdt < Decimal(100)
    assert len(state.positions) == 1
    assert state.positions[0].symbol is PaperSymbol.BTCUSDT
    assert state.positions[0].quantity > Decimal(0)
    assert state.real_capital == REAL_CAPITAL == 0
