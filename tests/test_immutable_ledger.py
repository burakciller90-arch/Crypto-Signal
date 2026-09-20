import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_signal.confluence.adapters import (
    elliott_result_evidence,
    harmonic_result_evidence,
    price_action_structure_evidence,
)
from crypto_signal.confluence.agreement import analyze_confluence
from crypto_signal.data.models import Candle, DataSource, Exchange, MarketType
from crypto_signal.ledger.bundle import (
    DecisionFreezeBundle,
    build_decision_freeze_bundle,
    bundle_json,
    verify_bundle_identity,
)
from crypto_signal.ledger.serialization import canonical_json, sha256_text
from crypto_signal.ledger.store import (
    ImmutableSignalLedger,
    LedgerConflictError,
    LedgerWriteDisposition,
)
from crypto_signal.methodologies.elliott.analysis import analyze_elliott
from crypto_signal.methodologies.harmonic.analysis import analyze_harmonics
from crypto_signal.methodologies.price_action.analysis import analyze_price_action
from crypto_signal.signals.lifecycle import evaluate_signal_lifecycle
from crypto_signal.signals.models import (
    LifecycleEvaluationStatus,
    SignalLifecycleEvaluation,
    SignalState,
)
from crypto_signal.signals.semantics import build_signal_decision

BASE_MS = 900_000
START_MS = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000)


def candles() -> tuple[Candle, ...]:
    output: list[Candle] = []
    for index in range(96):
        block = index % 16
        base = Decimal(1000 + (index // 16) * 3)
        if block in {3, 4, 5}:
            base += Decimal(24)
        elif block in {10, 11, 12}:
            base -= Decimal(22)
        close = base + (Decimal(4) if index % 2 == 0 else Decimal(-4))
        open_time_ms = START_MS + index * BASE_MS
        close_time_ms = open_time_ms + BASE_MS - 1
        output.append(
            Candle(
                exchange=Exchange.BYBIT,
                market_type=MarketType.SPOT,
                symbol="BTCUSDT",
                timeframe="15m",
                open_time_ms=open_time_ms,
                close_time_ms=close_time_ms,
                open=base,
                high=max(base, close) + Decimal(3),
                low=min(base, close) - Decimal(3),
                close=close,
                volume=Decimal(1),
                quote_volume=Decimal(1000),
                trade_count=None,
                is_closed=True,
                source=DataSource.REST,
                source_timestamp_ms=close_time_ms + 1,
                ingested_at_ms=close_time_ms + 2,
                adapter_version="test/1",
            )
        )
    return tuple(output)


def build_bundle(
    source: tuple[Candle, ...],
) -> DecisionFreezeBundle:
    as_of_ms = max(candle.ingested_at_ms for candle in source)
    pa = analyze_price_action(source, as_of_ms=as_of_ms)
    harmonic = analyze_harmonics(source, as_of_ms=as_of_ms)
    elliott = analyze_elliott(source, as_of_ms=as_of_ms)

    evidence = []
    pa_item = price_action_structure_evidence(pa)
    if pa_item is not None:
        evidence.append(pa_item)
    evidence.extend(harmonic_result_evidence(harmonic))
    evidence.extend(elliott_result_evidence(elliott))

    confluence = analyze_confluence(
        evidence,
        exchange=Exchange.BYBIT,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        as_of_ms=as_of_ms,
    )
    decision = build_signal_decision(confluence)
    return build_decision_freeze_bundle(
        decision=decision,
        confluence=confluence,
        price_action=pa,
        harmonic=harmonic,
        elliott=elliott,
        candles=source,
    )


def test_canonical_serialization_preserves_decimal_text() -> None:
    payload = {
        "z": Decimal("1.2300"),
        "a": ("x", Decimal("2.00")),
    }

    encoded = canonical_json(payload)

    assert encoded == '{"a":["x","2.00"],"z":"1.2300"}'
    assert sha256_text(encoded) == sha256_text(encoded)


def test_bundle_is_deterministic_and_input_order_independent() -> None:
    source = candles()

    first = build_bundle(source)
    second = build_decision_freeze_bundle(
        decision=first.signal_decision,
        confluence=first.confluence,
        price_action=first.price_action,
        harmonic=first.harmonic,
        elliott=first.elliott,
        candles=tuple(reversed(source)),
    )

    assert first == second
    assert first.bundle_identity == second.bundle_identity
    assert first.source_cutoff_open_time_ms == source[-1].open_time_ms
    assert len(first.candles) == len(source)
    assert first.signal_decision.selected_evidence_ids == tuple(
        item.evidence_id for item in first.selected_evidence
    )
    verify_bundle_identity(first)
    assert sha256_text(bundle_json(first)) == first.bundle_identity


def test_bundle_rejects_gap_in_consumed_candles() -> None:
    source = candles()
    full = build_bundle(source)
    gapped = (*source[:20], *source[21:])

    with pytest.raises(ValueError, match="refuses candle gaps"):
        build_decision_freeze_bundle(
            decision=full.signal_decision,
            confluence=full.confluence,
            price_action=full.price_action,
            harmonic=full.harmonic,
            elliott=full.elliott,
            candles=gapped,
        )


def test_ledger_freeze_is_insert_once_and_idempotent(tmp_path: Path) -> None:
    bundle = build_bundle(candles())
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    frozen_at_ms = bundle.signal_decision.as_of_ms + 1_000

    first = ledger.freeze(bundle, frozen_at_ms=frozen_at_ms)
    second = ledger.freeze(bundle, frozen_at_ms=frozen_at_ms + 1_000)

    assert first is LedgerWriteDisposition.INSERTED
    assert second is LedgerWriteDisposition.UNCHANGED
    assert ledger.count_freezes() == 1

    record = ledger.get_freeze_by_signal(
        bundle.signal_decision.freeze_identity
    )
    assert record is not None
    assert record.bundle_identity == bundle.bundle_identity
    assert record.bundle_json == bundle_json(bundle)
    assert record.frozen_at_ms == frozen_at_ms


def test_same_source_cutoff_with_different_bundle_is_conflict(
    tmp_path: Path,
) -> None:
    source = candles()
    first = build_bundle(source)
    changed = list(source)
    changed[0] = replace(changed[0], volume=Decimal(2))
    second = build_bundle(tuple(changed))

    assert first.source_cutoff_open_time_ms == second.source_cutoff_open_time_ms
    assert first.bundle_identity != second.bundle_identity

    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    ledger.freeze(
        first,
        frozen_at_ms=first.signal_decision.as_of_ms + 1_000,
    )

    with pytest.raises(LedgerConflictError, match="immutable freeze conflict"):
        ledger.freeze(
            second,
            frozen_at_ms=second.signal_decision.as_of_ms + 1_000,
        )


def test_sql_update_and_delete_are_rejected(tmp_path: Path) -> None:
    bundle = build_bundle(candles())
    path = tmp_path / "ledger.sqlite3"
    ledger = ImmutableSignalLedger(path)
    ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 1_000,
    )

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable ledger"):
            connection.execute(
                "UPDATE signal_freezes SET signal_state = 'active'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable ledger"):
            connection.execute("DELETE FROM signal_freezes")


def test_lifecycle_evaluation_append_is_idempotent(tmp_path: Path) -> None:
    bundle = build_bundle(candles())
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 1_000,
    )
    evaluation = evaluate_signal_lifecycle(
        bundle.signal_decision,
        bundle.candles,
        as_of_ms=bundle.signal_decision.as_of_ms,
    )
    assert evaluation.status is LifecycleEvaluationStatus.NO_NEW_EVIDENCE

    first = ledger.append_lifecycle_evaluation(
        evaluation,
        appended_at_ms=evaluation.evaluated_as_of_ms + 1_000,
    )
    second = ledger.append_lifecycle_evaluation(
        evaluation,
        appended_at_ms=evaluation.evaluated_as_of_ms + 2_000,
    )

    assert first is LedgerWriteDisposition.INSERTED
    assert second is LedgerWriteDisposition.UNCHANGED
    assert ledger.count_lifecycle_evaluations() == 1
    records = ledger.list_lifecycle_evaluations(
        bundle.signal_decision.freeze_identity
    )
    assert len(records) == 1
    assert records[0].signal_freeze_identity == (
        bundle.signal_decision.freeze_identity
    )


def test_lifecycle_requires_known_parent_and_one_payload_per_as_of(
    tmp_path: Path,
) -> None:
    bundle = build_bundle(candles())
    ledger = ImmutableSignalLedger(tmp_path / "ledger.sqlite3")
    evaluation = evaluate_signal_lifecycle(
        bundle.signal_decision,
        bundle.candles,
        as_of_ms=bundle.signal_decision.as_of_ms,
    )
    unknown = replace(
        evaluation,
        signal_freeze_identity="f" * 64,
    )

    with pytest.raises(LedgerConflictError, match="unknown signal freeze"):
        ledger.append_lifecycle_evaluation(
            unknown,
            appended_at_ms=unknown.evaluated_as_of_ms + 1_000,
        )

    ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 1_000,
    )
    ledger.append_lifecycle_evaluation(
        evaluation,
        appended_at_ms=evaluation.evaluated_as_of_ms + 1_000,
    )
    conflicting = SignalLifecycleEvaluation(
        signal_freeze_identity=evaluation.signal_freeze_identity,
        evaluated_as_of_ms=evaluation.evaluated_as_of_ms,
        current_state=SignalState.INVALIDATED,
        status=evaluation.status,
        missing_open_times_ms=evaluation.missing_open_times_ms,
        skipped_partial_decision_bucket=(
            evaluation.skipped_partial_decision_bucket
        ),
        transition=None,
    )

    with pytest.raises(
        LedgerConflictError,
        match="immutable lifecycle evaluation conflict",
    ):
        ledger.append_lifecycle_evaluation(
            conflicting,
            appended_at_ms=conflicting.evaluated_as_of_ms + 2_000,
        )


def test_lifecycle_table_is_sql_immutable(tmp_path: Path) -> None:
    bundle = build_bundle(candles())
    path = tmp_path / "ledger.sqlite3"
    ledger = ImmutableSignalLedger(path)
    ledger.freeze(
        bundle,
        frozen_at_ms=bundle.signal_decision.as_of_ms + 1_000,
    )
    evaluation = evaluate_signal_lifecycle(
        bundle.signal_decision,
        bundle.candles,
        as_of_ms=bundle.signal_decision.as_of_ms,
    )
    ledger.append_lifecycle_evaluation(
        evaluation,
        appended_at_ms=evaluation.evaluated_as_of_ms + 1_000,
    )

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable ledger"):
            connection.execute(
                "UPDATE lifecycle_evaluations SET status = 'complete'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable ledger"):
            connection.execute("DELETE FROM lifecycle_evaluations")
