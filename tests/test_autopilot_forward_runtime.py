from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_immutable_forecast_stream import _event_context
from test_intelligence_stream_capital_forward_runtime import _stream
from test_transaction_tape_atomic import _initial_state
from test_unified_decision_runtime import _issue

from crypto_signal.paper.autopilot_forward_runtime import (
    FP3_AUTOPILOT_STORE_SUFFIX,
    CanonicalPaperAutopilotForwardRuntime,
    FP3AutopilotProcessDisposition,
    FP3AutopilotStore,
)
from crypto_signal.paper.canonical_vault_decisions import CanonicalVaultDecisionLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.intelligence_stream_capital_forward_runtime import (
    IntelligenceStreamCapitalForwardRuntime,
)


def _paths(tmp_path: Path):
    epoch2_path, _ = _initial_state(tmp_path)
    stream_path = _stream(tmp_path)
    autopilot_path = tmp_path / f"runtime{FP3_AUTOPILOT_STORE_SUFFIX}"
    _, issuance = _issue(tmp_path)
    return epoch2_path, stream_path, autopilot_path, issuance


def test_fp3_a_processes_front_half_once_and_replays_from_receipt(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance = _paths(tmp_path)
    assessed_at_ms = issuance.forecast.issued_at_ms + 1
    runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    activation = runtime.ensure_activated(
        activated_at_ms=issuance.forecast.issued_at_ms,
    )

    first = runtime.process_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
        processed_at_ms=assessed_at_ms + 10,
    )
    epoch_after_first = epoch2_path.read_bytes()
    stream_after_first = stream_path.read_bytes()

    second = runtime.process_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
        processed_at_ms=assessed_at_ms + 100,
    )

    assert first.disposition is FP3AutopilotProcessDisposition.INSERTED
    assert first.activation_identity == activation
    assert first.receipt is not None
    assert first.receipt.hold_or_block_count == 2
    assert first.receipt.decision_states == (
        ("CORE", "eligible"),
        ("OPPORTUNITY_RESERVE", "hold"),
        ("TACTICAL", "hold"),
    )
    assert len(first.receipt.decision_identities) == 3
    assert first.receipt.real_capital == 0
    assert first.receipt.production_authority is False

    assert second.disposition is FP3AutopilotProcessDisposition.REPLAYED
    assert second.receipt == first.receipt
    assert epoch2_path.read_bytes() == epoch_after_first
    assert stream_path.read_bytes() == stream_after_first

    decisions = CanonicalVaultDecisionLedger(epoch2_path).read_assessment_decisions(
        first.receipt.allocator_assessment_identity
    )
    assert len(decisions) == 3
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == (2, 0, 0)


def test_fp3_a_recovers_missing_receipt_after_front_half_commit(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance = _paths(tmp_path)
    assessed_at_ms = issuance.forecast.issued_at_ms + 1
    runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    runtime.ensure_activated(activated_at_ms=issuance.forecast.issued_at_ms)

    front = IntelligenceStreamCapitalForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
    ).project_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
    )
    assert front.inserted_decision_count == 3
    assert FP3AutopilotStore(autopilot_path).read_receipt_for_forecast(
        issuance.forecast.forecast_identity
    ) is None

    recovered = runtime.process_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
        processed_at_ms=assessed_at_ms + 20,
    )

    assert recovered.disposition is FP3AutopilotProcessDisposition.RECOVERED
    assert recovered.receipt is not None
    assert recovered.receipt.allocator_assessment_identity == (
        front.allocator_assessment_identity
    )
    assert R22Epoch2AtomicTape(epoch2_path).audit_all_read_only() == (2, 0, 0)


def test_fp3_a_before_activation_is_skipped_without_receipt(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance = _paths(tmp_path)
    runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    runtime.ensure_activated(
        activated_at_ms=issuance.forecast.issued_at_ms + 10,
    )

    result = runtime.process_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=issuance.forecast.issued_at_ms + 20,
        processed_at_ms=issuance.forecast.issued_at_ms + 30,
    )

    assert (
        result.disposition
        is FP3AutopilotProcessDisposition.SKIPPED_BEFORE_ACTIVATION
    )
    assert result.receipt is None
    assert FP3AutopilotStore(autopilot_path).read_receipt_for_forecast(
        issuance.forecast.forecast_identity
    ) is None
    assert CanonicalVaultDecisionLedger(epoch2_path).read_assessment_decisions(
        "0" * 64
    ) == ()


def test_fp3_a_activation_is_future_bound_and_immutable(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance = _paths(tmp_path)
    runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    activated_at_ms = issuance.forecast.issued_at_ms
    identity = runtime.ensure_activated(activated_at_ms=activated_at_ms)
    assert runtime.ensure_activated(activated_at_ms=activated_at_ms) == identity

    with pytest.raises(ValueError, match="differs from existing front runtime"):
        runtime.ensure_activated(activated_at_ms=activated_at_ms + 1)

    activation = FP3AutopilotStore(autopilot_path).read_activation()
    assert activation is not None
    assert activation.activation_identity == identity
    assert activation.historical_backfill_authority is False
    assert activation.production_authority is False
    assert activation.real_capital == 0


def test_fp3_a_receipt_store_is_append_only(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, autopilot_path, issuance = _paths(tmp_path)
    assessed_at_ms = issuance.forecast.issued_at_ms + 1
    runtime = CanonicalPaperAutopilotForwardRuntime(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )
    runtime.ensure_activated(activated_at_ms=issuance.forecast.issued_at_ms)
    result = runtime.process_issuance(
        issuance,
        event_context=_event_context(),
        base_asset="BTC",
        assessed_at_ms=assessed_at_ms,
        processed_at_ms=assessed_at_ms + 5,
    )
    assert result.receipt is not None

    with sqlite3.connect(autopilot_path) as connection, pytest.raises(
        sqlite3.IntegrityError,
        match="immutable FP3 paper autopilot truth",
    ):
        connection.execute(
            """
            UPDATE fp3_paper_autopilot_receipts
            SET assessed_at_ms = assessed_at_ms + 1
            WHERE receipt_identity = ?
            """,
            (result.receipt.receipt_identity,),
        )

    with sqlite3.connect(autopilot_path) as connection, pytest.raises(
        sqlite3.IntegrityError,
        match="immutable FP3 paper autopilot truth",
    ):
        connection.execute("DELETE FROM fp3_paper_autopilot_activation")


def test_fp3_a_missing_store_reads_do_not_create_file(tmp_path: Path) -> None:
    path = tmp_path / f"missing{FP3_AUTOPILOT_STORE_SUFFIX}"
    store = FP3AutopilotStore(path)

    assert store.read_activation() is None
    assert store.read_receipt_for_forecast("0" * 64) is None
    assert not path.exists()


def test_fp3_a_rejects_store_alias_with_canonical_databases(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, _, _ = _paths(tmp_path)

    with pytest.raises(ValueError, match="must be separate"):
        CanonicalPaperAutopilotForwardRuntime(
            epoch2_path=epoch2_path,
            stream_path=stream_path,
            autopilot_path=epoch2_path,
        )
