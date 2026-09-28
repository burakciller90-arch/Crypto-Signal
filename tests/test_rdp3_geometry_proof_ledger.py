from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_immutable_ledger import build_bundle, candles
from test_live_freeze_clock import market_candles

from crypto_signal.ledger.bundle import bundle_json
from crypto_signal.ledger.geometry_proof import (
    build_frozen_geometry_proof,
    geometry_proof_json,
)
from crypto_signal.ledger.live_clock import freeze_live_candles
from crypto_signal.ledger.store import (
    ImmutableSignalLedger,
    LedgerWriteDisposition,
)


def test_fresh_freeze_persists_exact_geometry_proof_atomically(
    tmp_path: Path,
) -> None:
    bundle = build_bundle(candles())
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    persisted_at = bundle.signal_decision.as_of_ms + 1_000
    expected = build_frozen_geometry_proof(bundle)

    disposition = ledger.freeze(
        bundle,
        frozen_at_ms=persisted_at,
    )

    assert disposition is LedgerWriteDisposition.INSERTED
    assert ledger.count_freezes() == 1
    assert ledger.count_geometry_proofs() == 1

    record = ledger.read_geometry_proof_by_signal(
        bundle.signal_decision.freeze_identity
    )
    assert record is not None
    assert record.proof_identity == expected.proof_identity
    assert record.bundle_identity == bundle.bundle_identity
    assert record.signal_freeze_identity == (
        bundle.signal_decision.freeze_identity
    )
    assert record.as_of_ms == bundle.signal_decision.as_of_ms
    assert record.source_cutoff_open_time_ms == (
        bundle.source_cutoff_open_time_ms
    )
    assert record.persisted_at_ms == persisted_at
    assert record.proof_json == geometry_proof_json(expected)

    by_bundle = ledger.read_geometry_proof_by_bundle(
        bundle.bundle_identity
    )
    assert by_bundle == record


def test_geometry_proof_freeze_replay_is_idempotent(tmp_path: Path) -> None:
    bundle = build_bundle(candles())
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")

    first = ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 1_000,
    )
    original = ledger.read_geometry_proof_by_signal(
        bundle.signal_decision.freeze_identity
    )
    second = ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 9_000,
    )

    assert first is LedgerWriteDisposition.INSERTED
    assert second is LedgerWriteDisposition.UNCHANGED
    assert ledger.count_freezes() == 1
    assert ledger.count_geometry_proofs() == 1
    assert ledger.read_geometry_proof_by_signal(
        bundle.signal_decision.freeze_identity
    ) == original


def test_geometry_proof_table_is_sql_immutable(tmp_path: Path) -> None:
    bundle = build_bundle(candles())
    path = tmp_path / "ledger.sqlite3"
    ledger = ImmutableSignalLedger(path)
    ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 1_000,
    )

    with sqlite3.connect(path) as connection:
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable ledger",
        ):
            connection.execute(
                "UPDATE geometry_proofs SET as_of_ms = as_of_ms + 1"
            )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable ledger",
        ):
            connection.execute("DELETE FROM geometry_proofs")


def test_geometry_proof_read_only_lookup_never_initializes_missing_db(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.sqlite3"
    ledger = ImmutableSignalLedger(path)

    assert ledger.read_geometry_proof_by_signal("a" * 64) is None
    assert ledger.read_geometry_proof_by_bundle("b" * 64) is None
    assert not path.exists()


def test_historical_freeze_is_not_retroactively_backfilled(
    tmp_path: Path,
) -> None:
    bundle = build_bundle(candles())
    path = tmp_path / "historical.sqlite3"
    frozen_at = bundle.signal_decision.as_of_ms + 1_000
    decision = bundle.signal_decision

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
                frozen_at_ms INTEGER NOT NULL,
                UNIQUE (
                    exchange,
                    market_type,
                    symbol,
                    timeframe,
                    source_cutoff_open_time_ms
                )
            )
            """
        )
        connection.execute(
            """
            INSERT INTO signal_freezes(
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
                bundle.bundle_identity,
                decision.freeze_identity,
                decision.exchange.value,
                decision.market_type.value,
                decision.symbol,
                decision.timeframe,
                decision.as_of_ms,
                bundle.source_cutoff_open_time_ms,
                decision.state.value,
                decision.direction.value,
                bundle_json(bundle),
                frozen_at,
            ),
        )

    ledger = ImmutableSignalLedger(path)
    assert ledger.read_geometry_proof_by_signal(
        decision.freeze_identity
    ) is None

    ledger.initialize()
    assert ledger.count_geometry_proofs() == 0

    disposition = ledger.freeze(
        bundle,
        frozen_at_ms=frozen_at + 5_000,
    )
    assert disposition is LedgerWriteDisposition.UNCHANGED
    assert ledger.count_geometry_proofs() == 0
    assert ledger.read_geometry_proof_by_signal(
        decision.freeze_identity
    ) is None


def test_live_forward_freeze_has_read_only_replayable_geometry_proof(
    tmp_path: Path,
) -> None:
    source = market_candles()
    path = tmp_path / "live.sqlite3"
    ledger = ImmutableSignalLedger(path)
    now_ms = max(item.ingested_at_ms for item in source) + 1_000

    result = freeze_live_candles(
        candles=source,
        ledger=ledger,
        minimum_closed_candles=100,
        now_ms=lambda: now_ms,
    )
    assert result.signal_freeze_identity is not None
    assert result.bundle_identity is not None

    record = ledger.read_geometry_proof_by_signal(
        result.signal_freeze_identity
    )
    assert record is not None
    assert record.bundle_identity == result.bundle_identity
    assert record.signal_freeze_identity == result.signal_freeze_identity
    assert len(record.proof_identity) == 64
    assert '"annotations":' in record.proof_json
    assert '"consumed_candle_identities":' in record.proof_json


def test_geometry_proof_listing_is_parent_complete(tmp_path: Path) -> None:
    bundle = build_bundle(candles())
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 1_000,
    )

    records = ledger.list_geometry_proofs()
    assert len(records) == 1
    assert records[0].bundle_identity == bundle.bundle_identity
    assert records[0].signal_freeze_identity == (
        bundle.signal_decision.freeze_identity
    )
