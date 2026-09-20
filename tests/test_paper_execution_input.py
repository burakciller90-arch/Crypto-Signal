"""Focused tests for paper_execution_input_policy.v1."""

from __future__ import annotations

import inspect
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.data.models import Exchange, MarketType
from crypto_signal.paper import execution_input as paper_execution_input
from crypto_signal.paper.autonomy import (
    PAPER_AUTONOMY_POLICY_VERSION,
    PaperAutonomyDecision,
    PaperAutonomyReason,
)
from crypto_signal.paper.execution_input import (
    PAPER_EXECUTION_INPUT_POLICY_VERSION,
    PaperExecutionInputError,
    PaperExecutionInputStatus,
    freeze_execution_input_from_cache,
)
from crypto_signal.paper.models import REAL_CAPITAL, PaperAction, PaperSymbol

SIGNAL_AS_OF = 1_000
EVALUATED_AT = 1_050


def _candidate(
    *,
    action: PaperAction = PaperAction.BUY,
    source_as_of_ms: int = SIGNAL_AS_OF,
) -> PaperAutonomyDecision:
    return PaperAutonomyDecision(
        policy_version=PAPER_AUTONOMY_POLICY_VERSION,
        evaluated_at_ms=EVALUATED_AT,
        activation_cutoff_ms=900,
        candidate_action=action,
        symbol=PaperSymbol.BTCUSDT,
        source_freeze_identities=("a" * 64, "b" * 64),
        source_as_of_ms=source_as_of_ms,
        reason_code=(
            PaperAutonomyReason.BUY_ELIGIBLE
            if action is PaperAction.BUY
            else PaperAutonomyReason.EXIT_ELIGIBLE
        ),
        reason="test candidate",
        max_position_risk_usdt=(
            Decimal("1.00") if action is PaperAction.BUY else Decimal(0)
        ),
        execution_input_required=True,
        real_capital=REAL_CAPITAL,
    )


def _create_cache(path: Path) -> Path:
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
    return path


def _insert(
    path: Path,
    *,
    exchange: Exchange = Exchange.BINANCE,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    open_time_ms: int,
    close_time_ms: int,
    open_price: str,
    is_closed: bool = True,
    ingested_at_ms: int | None = None,
    source_timestamp_ms: int | None = None,
) -> None:
    ingested = close_time_ms + 1 if ingested_at_ms is None else ingested_at_ms
    source_timestamp = (
        close_time_ms if source_timestamp_ms is None else source_timestamp_ms
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO candles VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                exchange.value,
                MarketType.SPOT.value,
                symbol,
                timeframe,
                open_time_ms,
                close_time_ms,
                open_price,
                open_price,
                open_price,
                open_price,
                "1",
                None,
                None,
                int(is_closed),
                "rest",
                source_timestamp,
                ingested,
                "adapter.test.v1",
            ),
        )


def test_freezes_first_closed_binance_15m_candle_strictly_after_signal(
    tmp_path: Path,
) -> None:
    path = _create_cache(tmp_path / "candles.sqlite3")
    _insert(path, open_time_ms=900, close_time_ms=1_000, open_price="99")
    _insert(
        path,
        exchange=Exchange.BYBIT,
        open_time_ms=1_001,
        close_time_ms=1_200,
        open_price="50",
    )
    _insert(path, open_time_ms=1_100, close_time_ms=1_300, open_price="101.25")
    _insert(path, open_time_ms=1_400, close_time_ms=1_600, open_price="102")

    result = freeze_execution_input_from_cache(
        candle_cache_path=path,
        autonomy_decision=_candidate(),
        observed_at_ms=2_000,
    )

    assert result.status is PaperExecutionInputStatus.FROZEN
    frozen = result.frozen_input
    assert frozen is not None
    assert frozen.policy_version == PAPER_EXECUTION_INPUT_POLICY_VERSION
    assert frozen.source_exchange is Exchange.BINANCE
    assert frozen.source_market_type is MarketType.SPOT
    assert frozen.source_timeframe == "15m"
    assert frozen.source_candle_open_time_ms == 1_100
    assert frozen.reference_price == Decimal("101.25")
    assert frozen.price_field == "open"
    assert frozen.real_capital == REAL_CAPITAL == 0


def test_same_timestamp_candle_is_rejected_for_later_candle(tmp_path: Path) -> None:
    path = _create_cache(tmp_path / "candles.sqlite3")
    _insert(
        path,
        open_time_ms=SIGNAL_AS_OF,
        close_time_ms=1_200,
        open_price="100",
    )
    _insert(path, open_time_ms=1_300, close_time_ms=1_500, open_price="103")

    result = freeze_execution_input_from_cache(
        candle_cache_path=path,
        autonomy_decision=_candidate(),
        observed_at_ms=2_000,
    )

    assert result.frozen_input is not None
    assert result.frozen_input.source_candle_open_time_ms == 1_300
    assert result.frozen_input.reference_price == Decimal(103)


def test_waits_until_next_source_candle_is_closed_and_observed(tmp_path: Path) -> None:
    path = _create_cache(tmp_path / "candles.sqlite3")
    _insert(
        path,
        open_time_ms=1_100,
        close_time_ms=2_000,
        open_price="101",
        is_closed=False,
        ingested_at_ms=1_200,
        source_timestamp_ms=1_200,
    )

    result = freeze_execution_input_from_cache(
        candle_cache_path=path,
        autonomy_decision=_candidate(),
        observed_at_ms=1_500,
    )

    assert result.status is PaperExecutionInputStatus.WAITING_FOR_NEXT_CLOSED_CANDLE
    assert result.frozen_input is None


def test_read_only_cache_bytes_do_not_change(tmp_path: Path) -> None:
    path = _create_cache(tmp_path / "candles.sqlite3")
    _insert(path, open_time_ms=1_100, close_time_ms=1_300, open_price="101")
    before = path.read_bytes()

    result = freeze_execution_input_from_cache(
        candle_cache_path=path,
        autonomy_decision=_candidate(),
        observed_at_ms=2_000,
    )

    assert result.status is PaperExecutionInputStatus.FROZEN
    assert path.read_bytes() == before


def test_missing_cache_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PaperExecutionInputError, match="does not exist"):
        freeze_execution_input_from_cache(
            candle_cache_path=tmp_path / "missing.sqlite3",
            autonomy_decision=_candidate(),
            observed_at_ms=2_000,
        )


def test_hold_cash_candidate_cannot_request_execution_input(tmp_path: Path) -> None:
    hold = PaperAutonomyDecision(
        policy_version=PAPER_AUTONOMY_POLICY_VERSION,
        evaluated_at_ms=EVALUATED_AT,
        activation_cutoff_ms=900,
        candidate_action=PaperAction.HOLD_CASH,
        symbol=PaperSymbol.BTCUSDT,
        source_freeze_identities=("a" * 64, "b" * 64),
        source_as_of_ms=SIGNAL_AS_OF,
        reason_code=PaperAutonomyReason.SIGNAL_NOT_ACTIVE,
        reason="not active",
        max_position_risk_usdt=Decimal(0),
        execution_input_required=False,
        real_capital=REAL_CAPITAL,
    )
    path = _create_cache(tmp_path / "candles.sqlite3")

    with pytest.raises(PaperExecutionInputError, match="BUY or EXIT"):
        freeze_execution_input_from_cache(
            candle_cache_path=path,
            autonomy_decision=hold,
            observed_at_ms=2_000,
        )


def test_exit_candidate_uses_same_frozen_reference_rule(tmp_path: Path) -> None:
    path = _create_cache(tmp_path / "candles.sqlite3")
    _insert(path, open_time_ms=1_100, close_time_ms=1_300, open_price="98.50")

    result = freeze_execution_input_from_cache(
        candle_cache_path=path,
        autonomy_decision=_candidate(action=PaperAction.EXIT),
        observed_at_ms=2_000,
    )

    assert result.frozen_input is not None
    assert result.frozen_input.candidate_action is PaperAction.EXIT
    assert result.frozen_input.reference_price == Decimal("98.50")


def test_frozen_input_identity_is_deterministic_and_auditable(tmp_path: Path) -> None:
    path = _create_cache(tmp_path / "candles.sqlite3")
    _insert(path, open_time_ms=1_100, close_time_ms=1_300, open_price="101")

    first = freeze_execution_input_from_cache(
        candle_cache_path=path,
        autonomy_decision=_candidate(),
        observed_at_ms=2_000,
    )
    second = freeze_execution_input_from_cache(
        candle_cache_path=path,
        autonomy_decision=_candidate(),
        observed_at_ms=2_000,
    )

    assert first == second
    assert first.frozen_input is not None
    assert len(first.frozen_input.input_identity) == 64
    assert first.frozen_input.input_identity in first.frozen_input.venue_reference


def test_execution_input_surface_has_no_network_or_order_authority() -> None:
    source = inspect.getsource(paper_execution_input).lower()
    forbidden = (
        "import requests",
        "import httpx",
        "import urllib",
        "import socket",
        "place_order",
        "submit_order",
        "cancel_order",
        "api_key",
        "api_secret",
        "ccxt",
        "subprocess",
        "launchctl",
    )
    assert all(token not in source for token in forbidden)
    assert paper_execution_input.REAL_CAPITAL == REAL_CAPITAL == 0
