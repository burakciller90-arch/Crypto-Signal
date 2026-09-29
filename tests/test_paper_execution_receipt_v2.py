from __future__ import annotations

from decimal import Decimal

import pytest

from crypto_signal.data.microstructure import (
    AggressorSide,
    OrderBookLevel,
    build_orderbook_snapshot,
    build_public_trade_observation,
)
from crypto_signal.data.models import DataSource, Exchange, MarketType
from crypto_signal.paper.execution_depth_v2 import (
    DepthExecutionStatus,
    simulate_depth_execution,
)
from crypto_signal.paper.execution_input import (
    PAPER_EXECUTION_INPUT_POLICY_VERSION,
    FrozenPaperExecutionInput,
    compute_execution_input_identity,
)
from crypto_signal.paper.execution_limit_v2 import (
    PassiveLimitExecutionStatus,
    simulate_passive_limit_execution,
)
from crypto_signal.paper.execution_receipt_v2 import (
    ExecutionReceiptMode,
    ExecutionReceiptRejectedError,
    ExecutionReceiptStatus,
    build_execution_receipt_v2,
)
from crypto_signal.paper.instrument_fees_v2 import (
    InstrumentFeeRole,
    normalize_binance_spot_commission_snapshot,
    project_instrument_fee,
)
from crypto_signal.paper.ledger import PaperFundLedger
from crypto_signal.paper.models import (
    REAL_CAPITAL,
    PaperAction,
    PaperSymbol,
    build_fund_creation,
)
from crypto_signal.paper.pretrade import PaperPretradeStatus
from crypto_signal.paper.sizing import (
    PAPER_POSITION_SIZING_POLICY_VERSION,
    PaperPositionSizingDecision,
    PaperPositionSizingReason,
    PaperPositionSizingStatus,
    compute_position_sizing_identity,
)
from crypto_signal.paper.state import reconstruct_paper_fund_state
from crypto_signal.paper.venue_rules import (
    parse_binance_spot_venue_rules,
    prepare_authoritative_paper_trade_plan,
)

SOURCE_IDS = ("a" * 64, "b" * 64)


def _venue_payload():
    return {
        "timezone": "UTC",
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
        ],
    }


def _execution_input() -> FrozenPaperExecutionInput:
    kwargs = {
        "policy_version": PAPER_EXECUTION_INPUT_POLICY_VERSION,
        "candidate_action": PaperAction.BUY,
        "symbol": PaperSymbol.BTCUSDT,
        "source_freeze_identities": SOURCE_IDS,
        "signal_as_of_ms": 10_000,
        "source_exchange": Exchange.BINANCE,
        "source_market_type": MarketType.SPOT,
        "source_timeframe": "15m",
        "source_candle_open_time_ms": 11_000,
        "source_candle_close_time_ms": 19_000,
        "source_candle_ingested_at_ms": 19_100,
        "source_adapter_version": "binance-spot/1",
        "reference_price": Decimal(100),
        "price_field": "open",
    }
    return FrozenPaperExecutionInput(
        input_identity=compute_execution_input_identity(**kwargs),
        observed_at_ms=20_000,
        real_capital=REAL_CAPITAL,
        **kwargs,
    )


def _sizing(
    execution_input: FrozenPaperExecutionInput,
) -> PaperPositionSizingDecision:
    raw_quantity = Decimal("0.10")
    kwargs = {
        "policy_version": PAPER_POSITION_SIZING_POLICY_VERSION,
        "status": PaperPositionSizingStatus.SIZED,
        "reason_code": PaperPositionSizingReason.BUY_RISK_SIZED,
        "action": PaperAction.BUY,
        "symbol": PaperSymbol.BTCUSDT,
        "execution_input_identity": execution_input.input_identity,
        "source_freeze_identities": SOURCE_IDS,
        "reference_price": execution_input.reference_price,
        "conservative_invalidation_price": Decimal(90),
        "risk_per_unit_usdt": Decimal(10),
        "max_position_risk_usdt": raw_quantity * Decimal(10),
        "raw_quantity": raw_quantity,
        "venue_rule_check_required": True,
        "cost_adjustment_required": True,
    }
    return PaperPositionSizingDecision(
        sizing_identity=compute_position_sizing_identity(**kwargs),
        real_capital=REAL_CAPITAL,
        **kwargs,
    )


def _bound_pretrade(tmp_path):
    ledger = PaperFundLedger(tmp_path / "receipt.sqlite3")
    ledger.append_fund_creation(build_fund_creation(created_at_ms=1))
    state = reconstruct_paper_fund_state(ledger)
    execution_input = _execution_input()
    rules = parse_binance_spot_venue_rules(
        _venue_payload(),
        symbol=PaperSymbol.BTCUSDT,
        observed_at_ms=19_500,
    )
    bound = prepare_authoritative_paper_trade_plan(
        state=state,
        sizing=_sizing(execution_input),
        execution_input=execution_input,
        venue_rules=rules,
        planned_at_ms=20_100,
    )
    assert bound.pretrade.status is PaperPretradeStatus.PLANNED
    assert bound.pretrade.plan is not None
    assert bound.pretrade.planned_quantity == Decimal("0.10")
    return bound


def _orderbook(
    *,
    ask_size: str = "0.10",
    bid_price: str = "99",
    bid_size: str = "1",
    ask_price: str = "101",
):
    return build_orderbook_snapshot(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=20_110,
        source_timestamp_ms=20_110,
        response_time_ms=20_110,
        ingested_at_ms=20_110,
        update_id=10,
        sequence=20,
        bids=(OrderBookLevel(Decimal(bid_price), Decimal(bid_size)),),
        asks=(OrderBookLevel(Decimal(ask_price), Decimal(ask_size)),),
        source=DataSource.REST,
        adapter_version="fp4e-test/1",
    )


def _public_trade(*, size: str = "0.15"):
    return build_public_trade_observation(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        exec_id="receipt-fill",
        sequence=1,
        aggressor_side=AggressorSide.SELL,
        price=Decimal(99),
        size=Decimal(size),
        event_at_ms=20_120,
        source_timestamp_ms=20_120,
        ingested_at_ms=20_120,
        is_block_trade=False,
        is_rpi_trade=False,
        source=DataSource.REST,
        adapter_version="fp4e-test/1",
    )


def _fee_snapshot(*, ingested_at_ms: int = 20_050):
    payload = {
        "symbol": "BTCUSDT",
        "standardCommission": {
            "maker": "0.0005",
            "taker": "0.0010",
            "buyer": "0",
            "seller": "0",
        },
        "specialCommission": {
            "maker": "0",
            "taker": "0",
            "buyer": "0",
            "seller": "0",
        },
        "taxCommission": {
            "maker": "0",
            "taker": "0",
            "buyer": "0",
            "seller": "0",
        },
        "discount": {
            "enabledForAccount": False,
            "enabledForSymbol": False,
            "discountAsset": "BNB",
            "discount": "0.25",
        },
    }
    return normalize_binance_spot_commission_snapshot(
        payload=payload,
        observed_at_ms=20_000,
        ingested_at_ms=ingested_at_ms,
    )


def _fee(*, role: InstrumentFeeRole, notional: Decimal):
    return project_instrument_fee(
        snapshot=_fee_snapshot(),
        symbol=PaperSymbol.BTCUSDT,
        action=PaperAction.BUY,
        role=role,
        fill_notional_usdt=notional,
        evaluation_cutoff_ms=20_200,
    )


def test_depth_full_receipt_binds_taker_fee_and_real_price_impact(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook()
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        orderbook=book,
        execution_cutoff_ms=20_200,
        partial_fills_enabled=True,
    )
    fee = _fee(role=InstrumentFeeRole.TAKER, notional=outcome.fill_notional)

    receipt = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=fee,
        fee_snapshot=_fee_snapshot(),
        orderbook=book,
    )

    assert outcome.status is DepthExecutionStatus.FULL
    assert receipt.mode is ExecutionReceiptMode.DEPTH
    assert receipt.status is ExecutionReceiptStatus.FULL
    assert receipt.filled_quantity == Decimal("0.10")
    assert receipt.average_fill_price == Decimal(101)
    assert receipt.fill_notional_usdt == Decimal("10.10")
    assert receipt.adverse_price_impact_usdt == Decimal("0.10")
    assert receipt.fee_usdt == Decimal("0.01010")
    assert receipt.immediate_execution_cost_usdt == Decimal("0.11010")
    assert receipt.fee_role is InstrumentFeeRole.TAKER
    assert receipt.funding_accounted_separately is True


def test_depth_partial_receipt_reconciles_partial_notional_exactly(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook(ask_size="0.05")
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        orderbook=book,
        execution_cutoff_ms=20_200,
        partial_fills_enabled=True,
    )
    fee = _fee(role=InstrumentFeeRole.TAKER, notional=outcome.fill_notional)

    receipt = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=fee,
        fee_snapshot=_fee_snapshot(),
        orderbook=book,
    )

    assert outcome.status is DepthExecutionStatus.PARTIAL
    assert receipt.status is ExecutionReceiptStatus.PARTIAL
    assert receipt.filled_quantity == Decimal("0.05")
    assert receipt.unfilled_quantity == Decimal("0.05")
    assert receipt.fill_notional_usdt == Decimal("5.05")
    assert receipt.fee_usdt == Decimal("0.00505")


def test_passive_full_receipt_requires_maker_fee_and_no_optimistic_cost_credit(
    tmp_path,
) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook(
        bid_price="99",
        bid_size="0.05",
        ask_price="101",
        ask_size="1",
    )
    trades = (_public_trade(),)
    outcome = simulate_passive_limit_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        limit_price=Decimal(99),
        arrival_book=book,
        public_trades=trades,
        submitted_at_ms=20_100,
        latency_ms=10,
        timeout_ms=100,
        max_book_age_ms=0,
        partial_fills_enabled=True,
        queue_position_proven=True,
    )
    fee = _fee(role=InstrumentFeeRole.MAKER, notional=outcome.fill_notional)

    receipt = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=fee,
        fee_snapshot=_fee_snapshot(),
        orderbook=book,
        public_trades=trades,
    )

    assert outcome.status is PassiveLimitExecutionStatus.FULL
    assert receipt.mode is ExecutionReceiptMode.PASSIVE_LIMIT
    assert receipt.average_fill_price == Decimal(99)
    assert receipt.adverse_price_impact_usdt == Decimal(0)
    assert receipt.immediate_execution_cost_usdt == receipt.fee_usdt
    assert receipt.fee_role is InstrumentFeeRole.MAKER
    assert receipt.market_evidence_identities[0] == outcome.orderbook_snapshot_identity
    assert set(outcome.evidence_trade_identities).issubset(
        set(receipt.market_evidence_identities)
    )


def test_not_filled_receipt_has_zero_cost_and_no_fee_evidence(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook(
        bid_price="99",
        bid_size="0.05",
        ask_price="101",
        ask_size="1",
    )
    outcome = simulate_passive_limit_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        limit_price=Decimal(99),
        arrival_book=book,
        public_trades=(),
        submitted_at_ms=20_100,
        latency_ms=10,
        timeout_ms=100,
        max_book_age_ms=0,
        partial_fills_enabled=True,
        queue_position_proven=True,
    )

    receipt = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=None,
        fee_snapshot=None,
        orderbook=book,
    )

    assert outcome.status is PassiveLimitExecutionStatus.NOT_FILLED
    assert receipt.status is ExecutionReceiptStatus.NOT_FILLED
    assert receipt.fill_notional_usdt == Decimal(0)
    assert receipt.fee_usdt == Decimal(0)
    assert receipt.adverse_price_impact_usdt == Decimal(0)
    assert receipt.immediate_execution_cost_usdt == Decimal(0)
    assert receipt.fee_projection_identity is None


def test_fill_not_proven_receipt_cannot_invent_fee_or_cost(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook(
        bid_price="99",
        bid_size="0.05",
        ask_price="101",
        ask_size="1",
    )
    trades = (_public_trade(),)
    outcome = simulate_passive_limit_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        limit_price=Decimal(99),
        arrival_book=book,
        public_trades=trades,
        submitted_at_ms=20_100,
        latency_ms=10,
        timeout_ms=100,
        max_book_age_ms=0,
        partial_fills_enabled=True,
        queue_position_proven=False,
    )

    receipt = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=None,
        fee_snapshot=None,
        orderbook=book,
        public_trades=trades,
    )

    assert outcome.status is PassiveLimitExecutionStatus.FILL_NOT_PROVEN
    assert receipt.status is ExecutionReceiptStatus.FILL_NOT_PROVEN
    assert receipt.filled_quantity == Decimal(0)
    assert receipt.fee_usdt == Decimal(0)


def test_filled_receipt_rejects_wrong_fee_role(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook()
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        orderbook=book,
        execution_cutoff_ms=20_200,
        partial_fills_enabled=True,
    )
    wrong_fee = _fee(
        role=InstrumentFeeRole.MAKER,
        notional=outcome.fill_notional,
    )

    with pytest.raises(ExecutionReceiptRejectedError, match="fee role"):
        build_execution_receipt_v2(
            bound_pretrade=bound,
            outcome=outcome,
            fee_projection=wrong_fee,
            fee_snapshot=_fee_snapshot(),
            orderbook=book,
        )


def test_filled_receipt_rejects_fee_notional_mismatch(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook()
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        orderbook=book,
        execution_cutoff_ms=20_200,
        partial_fills_enabled=True,
    )
    wrong_fee = _fee(
        role=InstrumentFeeRole.TAKER,
        notional=outcome.fill_notional + Decimal(1),
    )

    with pytest.raises(ExecutionReceiptRejectedError, match="notional mismatch"):
        build_execution_receipt_v2(
            bound_pretrade=bound,
            outcome=outcome,
            fee_projection=wrong_fee,
            fee_snapshot=_fee_snapshot(),
            orderbook=book,
        )


def test_nonfilled_receipt_rejects_fee_projection(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook(
        bid_price="99",
        bid_size="0.05",
        ask_price="101",
        ask_size="1",
    )
    outcome = simulate_passive_limit_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        limit_price=Decimal(99),
        arrival_book=book,
        public_trades=(),
        submitted_at_ms=20_100,
        latency_ms=10,
        timeout_ms=100,
        max_book_age_ms=0,
        partial_fills_enabled=True,
        queue_position_proven=True,
    )
    unrelated_fee = _fee(
        role=InstrumentFeeRole.MAKER,
        notional=Decimal(1),
    )

    with pytest.raises(ExecutionReceiptRejectedError, match="must not carry fee"):
        build_execution_receipt_v2(
            bound_pretrade=bound,
            outcome=outcome,
            fee_projection=unrelated_fee,
            fee_snapshot=_fee_snapshot(),
            orderbook=book,
        )


def test_exact_receipt_replay_is_identity_stable(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook()
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        orderbook=book,
        execution_cutoff_ms=20_200,
        partial_fills_enabled=True,
    )
    fee = _fee(role=InstrumentFeeRole.TAKER, notional=outcome.fill_notional)

    first = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=fee,
        fee_snapshot=_fee_snapshot(),
        orderbook=book,
    )
    replay = build_execution_receipt_v2(
        bound_pretrade=bound,
        outcome=outcome,
        fee_projection=fee,
        fee_snapshot=_fee_snapshot(),
        orderbook=book,
    )

    assert replay == first
    assert replay.receipt_identity == first.receipt_identity


def test_cross_venue_market_evidence_is_rejected(tmp_path) -> None:
    bound = _bound_pretrade(tmp_path)
    bybit_book = build_orderbook_snapshot(
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_at_ms=20_110,
        source_timestamp_ms=20_110,
        response_time_ms=20_110,
        ingested_at_ms=20_110,
        update_id=99,
        sequence=99,
        bids=(OrderBookLevel(Decimal(99), Decimal(1)),),
        asks=(OrderBookLevel(Decimal(101), Decimal("0.10")),),
        source=DataSource.REST,
        adapter_version="fp4e-test/1",
    )
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        orderbook=bybit_book,
        execution_cutoff_ms=20_200,
        partial_fills_enabled=True,
    )
    fee = _fee(role=InstrumentFeeRole.TAKER, notional=outcome.fill_notional)

    with pytest.raises(ExecutionReceiptRejectedError, match="Binance Spot"):
        build_execution_receipt_v2(
            bound_pretrade=bound,
            outcome=outcome,
            fee_projection=fee,
            fee_snapshot=_fee_snapshot(),
            orderbook=bybit_book,
        )


def test_receipt_rejects_fee_schedule_learned_after_execution_cutoff(
    tmp_path,
) -> None:
    bound = _bound_pretrade(tmp_path)
    book = _orderbook()
    outcome = simulate_depth_execution(
        action=PaperAction.BUY,
        requested_quantity=Decimal("0.10"),
        orderbook=book,
        execution_cutoff_ms=20_200,
        partial_fills_enabled=True,
    )
    future_snapshot = _fee_snapshot(ingested_at_ms=20_300)
    fee = project_instrument_fee(
        snapshot=future_snapshot,
        symbol=PaperSymbol.BTCUSDT,
        action=PaperAction.BUY,
        role=InstrumentFeeRole.TAKER,
        fill_notional_usdt=outcome.fill_notional,
        evaluation_cutoff_ms=20_400,
    )

    with pytest.raises(ExecutionReceiptRejectedError, match="future fee schedule"):
        build_execution_receipt_v2(
            bound_pretrade=bound,
            outcome=outcome,
            fee_projection=fee,
            fee_snapshot=future_snapshot,
            orderbook=book,
        )
