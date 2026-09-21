from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from crypto_signal.confluence.models import (
    ScoreSemantic,
)
from crypto_signal.data.models import Exchange
from crypto_signal.product.models import (
    ProductDataStatus,
    SignalEvidenceClassStatus,
)
from crypto_signal.product.reader import DashboardReader, DashboardReadError
from crypto_signal.signals.models import (
    ProbabilityStatus,
    SignalDirection,
    SignalState,
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def create_signal_schema(path: Path) -> None:
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


def bundle_json(
    *,
    state: str,
    direction: str,
    setup_type: str,
    score: str,
    flags: tuple[str, ...] = (),
) -> str:
    evidence_id = "pa:test"
    selected = {
        "ambiguity_flags": [],
        "as_of_ms": 1_000,
        "contradiction_flags": [],
        "direction": direction,
        "entry_zone": None,
        "evidence_id": evidence_id,
        "evidence_summary": ["current_structure=" + direction],
        "exchange": "bybit",
        "invalidation_price": None,
        "invalidation_trigger": None,
        "key_levels": [{"label": "structure", "price": "100"}],
        "market_available_at_ms": 900,
        "market_type": "spot",
        "methodology": "price_action",
        "methodology_version": "price-action-v1/1",
        "metrics": [{"name": "distance", "unit": "bps", "value": "5"}],
        "observed_at_ms": 950,
        "setup_type": "market_structure",
        "symbol": "BTCUSDT",
        "targets": [],
        "timeframe": "15m",
        "validity": "context",
    }
    return json.dumps(
        {
            "schema_version": "decision-freeze-v1/1",
            "source_cutoff_open_time_ms": 900,
            "candles": [
                {
                    "open_time_ms": 0,
                    "close_time_ms": 899,
                    "open": "100",
                    "high": "101",
                    "low": "99",
                    "close": "100",
                },
                {
                    "open_time_ms": 900,
                    "close_time_ms": 1799,
                    "open": "100",
                    "high": "102",
                    "low": "99",
                    "close": "101",
                },
            ],
            "confluence": {
                "selections": [
                    {
                        "methodology": "price_action",
                        "source_count": 1,
                        "selected": [selected],
                        "latest_market_available_at_ms": 900,
                        "resolved_direction": direction,
                        "has_internal_direction_conflict": False,
                    },
                    {
                        "methodology": "harmonic",
                        "source_count": 0,
                        "selected": [],
                        "latest_market_available_at_ms": None,
                        "resolved_direction": "unresolved",
                        "has_internal_direction_conflict": False,
                    },
                    {
                        "methodology": "elliott",
                        "source_count": 0,
                        "selected": [],
                        "latest_market_available_at_ms": None,
                        "resolved_direction": "unresolved",
                        "has_internal_direction_conflict": False,
                    },
                ]
            },
            "signal_decision": {
                "state": state,
                "direction": direction,
                "setup_type": setup_type,
                "geometry": None,
                "agreement": {
                    "confluence_score": score,
                    "score_semantic": (
                        ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY.value
                    ),
                    "support_method_count": 1,
                    "opposing_method_count": 0,
                    "resolved_method_count": 1,
                    "total_methodology_slots": 3,
                    "pairwise_relations": [
                        {
                            "left": "price_action",
                            "right": "harmonic",
                            "relation": "insufficient",
                            "left_direction": direction,
                            "right_direction": "unresolved",
                        }
                    ],
                },
                "probability_status": ProbabilityStatus.NOT_CALIBRATED.value,
                "uncertainty_flags": list(flags),
                "evidence_summary": [
                    f"price_action:market_structure:{direction}:context"
                ],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def insert_signal(
    path: Path,
    *,
    seed: str,
    exchange: str = "bybit",
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    state: str = "watch",
    direction: str = "bearish",
    setup_type: str = "confluence_watch",
    score: str = "33.33",
    as_of_ms: int = 1_000,
    cutoff_ms: int = 900,
    frozen_at_ms: int = 1_100,
    flags: tuple[str, ...] = ("partial_methodology_coverage",),
) -> tuple[str, str]:
    bundle = digest(f"bundle-{seed}")
    signal = digest(f"signal-{seed}")
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
                bundle,
                signal,
                exchange,
                "spot",
                symbol,
                timeframe,
                as_of_ms,
                cutoff_ms,
                state,
                direction,
                bundle_json(
                    state=state,
                    direction=direction,
                    setup_type=setup_type,
                    score=score,
                    flags=flags,
                ),
                frozen_at_ms,
            ),
        )
    return bundle, signal


def test_missing_ledger_returns_explicit_no_ledger(tmp_path: Path) -> None:
    reader = DashboardReader(tmp_path / "missing.sqlite3")

    command = reader.command_center()
    radar = reader.market_radar()
    performance = reader.performance_availability()

    assert command.status is ProductDataStatus.NO_LEDGER
    assert command.freeze_count == 0
    assert radar.status is ProductDataStatus.NO_LEDGER
    assert performance.status is ProductDataStatus.NO_LEDGER
    assert not (tmp_path / "missing.sqlite3").exists()


def test_command_center_reads_real_frozen_semantics(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path)
    insert_signal(path, seed="old", frozen_at_ms=1_100)
    _, latest_signal = insert_signal(
        path,
        seed="new",
        exchange="binance",
        state="active",
        direction="bullish",
        setup_type="gartley",
        score="66.67",
        as_of_ms=2_000,
        cutoff_ms=1_800,
        frozen_at_ms=2_100,
        flags=(),
    )

    view = DashboardReader(path).command_center(recent_limit=1)

    assert view.status is ProductDataStatus.READY
    assert view.freeze_count == 2
    assert view.latest_frozen_at_ms == 2_100
    assert dict(view.state_counts) == {
        SignalState.ACTIVE: 1,
        SignalState.WATCH: 1,
    }
    assert dict(view.direction_counts) == {
        SignalDirection.BEARISH: 1,
        SignalDirection.BULLISH: 1,
    }
    assert len(view.recent_signals) == 1
    card = view.recent_signals[0]
    assert card.signal_freeze_identity == latest_signal
    assert card.exchange is Exchange.BINANCE
    assert card.state is SignalState.ACTIVE
    assert card.direction is SignalDirection.BULLISH
    assert str(card.confluence_score) == "66.67"
    assert (
        card.confluence_score_semantic
        is ScoreSemantic.AGREEMENT_INDEX_NOT_PROBABILITY
    )
    assert card.probability_status is ProbabilityStatus.NOT_CALIBRATED
    assert (
        card.evidence_class_status
        is SignalEvidenceClassStatus.NOT_EXPLICIT_AT_FREEZE_LEVEL
    )


def test_command_center_parses_only_recent_cards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path)
    for index in range(40):
        insert_signal(
            path,
            seed=f"bulk-{index}",
            frozen_at_ms=1_000 + index,
            as_of_ms=900 + index,
            cutoff_ms=800 + index,
        )

    original = DashboardReader._card_from_row
    parsed = 0

    def counting_card(
        self: DashboardReader,
        row: sqlite3.Row,
    ):
        nonlocal parsed
        parsed += 1
        return original(self, row)

    monkeypatch.setattr(DashboardReader, "_card_from_row", counting_card)

    view = DashboardReader(path).command_center(recent_limit=3)

    assert view.status is ProductDataStatus.READY
    assert view.freeze_count == 40
    assert len(view.recent_signals) == 3
    assert parsed == 3


def test_market_radar_returns_latest_per_provider_context(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path)
    insert_signal(path, seed="bybit-old", frozen_at_ms=1_100)
    _, bybit_new = insert_signal(
        path,
        seed="bybit-new",
        frozen_at_ms=2_100,
        as_of_ms=2_000,
        cutoff_ms=1_800,
    )
    _, binance = insert_signal(
        path,
        seed="binance",
        exchange="binance",
        frozen_at_ms=2_000,
        as_of_ms=1_900,
        cutoff_ms=1_800,
    )

    view = DashboardReader(path).market_radar()

    assert view.status is ProductDataStatus.READY
    assert len(view.items) == 2
    ids = {item.latest.signal_freeze_identity for item in view.items}
    assert ids == {bybit_new, binance}


def test_asset_cockpit_and_archive_use_immutable_ordering(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path)
    _, first = insert_signal(path, seed="first", frozen_at_ms=1_100)
    _, second = insert_signal(
        path,
        seed="second",
        frozen_at_ms=2_100,
        as_of_ms=2_000,
        cutoff_ms=1_800,
    )
    insert_signal(
        path,
        seed="eth",
        symbol="ETHUSDT",
        frozen_at_ms=3_100,
        as_of_ms=3_000,
        cutoff_ms=2_700,
    )
    reader = DashboardReader(path)

    cockpit = reader.asset_cockpit(symbol="BTCUSDT", timeframe="15m")
    archive = reader.signal_archive(limit=2)

    assert cockpit.status is ProductDataStatus.READY
    assert [card.signal_freeze_identity for card in cockpit.recent_signals] == [
        second,
        first,
    ]
    assert len(cockpit.latest_by_provider) == 1
    assert archive.total_count == 3
    assert len(archive.signals) == 2
    assert archive.signals[0].symbol == "ETHUSDT"


def test_signal_detail_returns_exact_bundle_without_reconstruction(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path)
    _, signal = insert_signal(path, seed="detail")
    reader = DashboardReader(path)

    detail = reader.signal_detail(signal)

    assert detail.status is ProductDataStatus.READY
    assert detail.signal is not None
    assert detail.signal.signal_freeze_identity == signal
    assert detail.bundle_json is not None
    assert json.loads(detail.bundle_json)["signal_decision"]["state"] == "watch"


def test_performance_reports_schema_unavailable_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path)
    reader = DashboardReader(path)

    view = reader.performance_availability()

    assert view.status is ProductDataStatus.SCHEMA_UNAVAILABLE
    with sqlite3.connect(path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert tables == {"signal_freezes"}


def test_performance_empty_with_full_outcome_schema(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE outcome_evaluations (
                outcome_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT NOT NULL,
                evidence_class TEXT NOT NULL,
                evaluated_as_of_ms INTEGER NOT NULL,
                resolution_status TEXT NOT NULL,
                outcome_state TEXT,
                max_holding_bars INTEGER NOT NULL,
                outcome_json TEXT NOT NULL,
                appended_at_ms INTEGER NOT NULL
            )
            """
        )

    view = DashboardReader(path).performance_availability()

    assert view.status is ProductDataStatus.EMPTY
    assert view.outcome_snapshot_count == 0
    assert view.evidence_class_counts == ()
    assert view.groups == ()


def test_malformed_bundle_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    create_signal_schema(path)
    insert_signal(path, seed="bad")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE signal_freezes SET bundle_json = ?",
            ('{"signal_decision":{"state":"watch"}}',),
        )

    with pytest.raises(DashboardReadError):
        DashboardReader(path).command_center()
