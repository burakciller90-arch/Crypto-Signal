from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_autopilot_forward_actions import (
    _action_bridge,
    _half_quantity,
    _open_intent,
    _sized_chain,
)
from test_autopilot_forward_sizing import _sha
from test_canonical_capital_runtime import _execution_snapshot
from test_final_product_read_model import _seed_trade_passport_bundle

from crypto_signal.paper.autopilot_forward_actions import (
    FP3ActionProcessDisposition,
    FP3ActionReason,
    build_fp3_action_intent,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.models import PaperAction, PaperSymbol
from crypto_signal.product.final_product_read_model import (
    FinalProductReadModel,
    _trade_lifecycle_kind,
)


def _sqlite_sidecar_bytes(path: Path) -> dict[str, bytes | None]:
    result: dict[str, bytes | None] = {}
    # SQLite -shm contains volatile reader/coordination metadata, not ledger payload.
    for suffix in ("-wal",):
        sidecar = Path(f"{path}{suffix}")
        result[suffix] = sidecar.read_bytes() if sidecar.exists() else None
    return result


def _seed_forward_episode(
    tmp_path: Path,
    *,
    close_reference_price: Decimal = Decimal(108),
    include_partial_take_profit: bool = True,
):
    (
        epoch2_path,
        stream_path,
        autopilot_path,
        issuance,
        front,
        _,
        sizing,
        assessment,
        selection,
        eligibility,
    ) = _sized_chain(tmp_path)
    bridge = _action_bridge(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        autopilot_path=autopilot_path,
    )

    open_at = selection.selected_at_ms + 10
    opened = bridge.process_buy(
        _open_intent(front, sizing, issuance, requested_at_ms=open_at),
        issuance,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("fp6a-open-reference"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("fp6a-open-mark"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=open_at + 10,
        mutated_at_ms=open_at + 11,
        snapshot_at_ms=open_at + 20,
        processed_at_ms=open_at + 30,
    )
    assert opened.disposition is FP3ActionProcessDisposition.INSERTED
    assert opened.receipt.canonical_action is PaperAction.BUY
    assert opened.receipt.r22_bundle_identity is not None

    bundle_identities = [opened.receipt.r22_bundle_identity]
    previous_at = open_at

    if include_partial_take_profit:
        reduce_at = open_at + 40
        reduced = bridge.process_sell(
            build_fp3_action_intent(
                front_receipt_identity=front.receipt_identity,
                sizing_receipt_identity=sizing.receipt_identity,
                forecast_identity=issuance.forecast.forecast_identity,
                proof_identity=issuance.proof.proof_identity,
                vault_id=PaperVaultId.CORE,
                symbol=PaperSymbol.BTCUSDT,
                reason=FP3ActionReason.PARTIAL_TAKE_PROFIT,
                action_evidence_identity=_sha("fp6a-partial-tp-evidence"),
                requested_at_ms=reduce_at,
                quantity=_half_quantity(epoch2_path),
            ),
            issuance,
            sizing_assessment=assessment,
            reference_price=Decimal(110),
            reference_price_evidence_identity=_sha("fp6a-reduce-reference"),
            mark_prices={PaperSymbol.BTCUSDT: Decimal(110)},
            mark_evidence_identity=_sha("fp6a-reduce-mark"),
            execution_snapshot=_execution_snapshot(),
            filled_at_ms=reduce_at + 10,
            mutated_at_ms=reduce_at + 11,
            snapshot_at_ms=reduce_at + 20,
            processed_at_ms=reduce_at + 30,
        )
        assert reduced.disposition is FP3ActionProcessDisposition.INSERTED
        assert reduced.receipt.canonical_action is PaperAction.REDUCE
        assert reduced.receipt.r22_bundle_identity is not None
        bundle_identities.append(reduced.receipt.r22_bundle_identity)
        previous_at = reduce_at

    close_at = previous_at + 40
    closed = bridge.process_sell(
        build_fp3_action_intent(
            front_receipt_identity=front.receipt_identity,
            sizing_receipt_identity=sizing.receipt_identity,
            forecast_identity=issuance.forecast.forecast_identity,
            proof_identity=issuance.proof.proof_identity,
            vault_id=PaperVaultId.CORE,
            symbol=PaperSymbol.BTCUSDT,
            reason=FP3ActionReason.CLOSE,
            action_evidence_identity=_sha("fp6a-close-evidence"),
            requested_at_ms=close_at,
        ),
        issuance,
        sizing_assessment=assessment,
        reference_price=close_reference_price,
        reference_price_evidence_identity=_sha(
            f"fp6a-close-reference-{close_reference_price}"
        ),
        mark_prices={PaperSymbol.BTCUSDT: close_reference_price},
        mark_evidence_identity=_sha(f"fp6a-close-mark-{close_reference_price}"),
        execution_snapshot=_execution_snapshot(),
        filled_at_ms=close_at + 10,
        mutated_at_ms=close_at + 11,
        snapshot_at_ms=close_at + 20,
        processed_at_ms=close_at + 30,
    )
    assert closed.disposition is FP3ActionProcessDisposition.INSERTED
    assert closed.receipt.canonical_action is PaperAction.EXIT
    assert closed.receipt.r22_bundle_identity is not None
    bundle_identities.append(closed.receipt.r22_bundle_identity)

    return epoch2_path, stream_path, tuple(bundle_identities)


def test_fp6a_missing_epoch2_is_explicit_and_noncreating(tmp_path: Path) -> None:
    epoch2_path = tmp_path / "missing-fp6a-epoch2.sqlite3"

    view = FinalProductReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        epoch2_path=epoch2_path,
    ).trade_lifecycle(bundle_identity=_sha("fp6a-missing-lifecycle"))

    assert view.availability_label == "Trade lifecycle verisi kullanılamıyor"
    assert view.event_count == 0
    assert view.events == ()
    assert view.real_capital == 0
    assert not epoch2_path.exists()


def test_fp6a_single_open_bundle_projects_one_open_episode_read_only(
    tmp_path: Path,
) -> None:
    epoch2_path, _, _, bundle = _seed_trade_passport_bundle(tmp_path)
    before = epoch2_path.read_bytes()
    before_sidecars = _sqlite_sidecar_bytes(epoch2_path)

    view = FinalProductReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        epoch2_path=epoch2_path,
    ).trade_lifecycle(
        bundle_identity=bundle.bundle_identity,
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert view.lifecycle_state_label == "Açık işlem"
    assert view.vault_label == "Core"
    assert view.symbol == "BTCUSDT"
    assert view.event_count == 1
    assert view.closed_at_ms is None
    assert view.final_outcome_label is None
    assert view.events[0].sequence == 1
    assert view.events[0].lifecycle_label == "Pozisyon açılışı"
    assert view.events[0].passport.audit is not None
    assert view.events[0].passport.audit.bundle_identity == bundle.bundle_identity
    assert view.events[0].audit is not None
    assert view.events[0].audit.lifecycle_kind == "OPEN"
    assert view.audit is not None
    assert view.audit.lifecycle_root_bundle_identity == bundle.bundle_identity
    assert view.audit.requested_bundle_identity == bundle.bundle_identity
    assert view.audit.bundle_identities == (bundle.bundle_identity,)
    assert epoch2_path.read_bytes() == before
    assert _sqlite_sidecar_bytes(epoch2_path) == before_sidecars


def test_fp6a_partial_take_profit_and_close_reconstruct_exact_episode(
    tmp_path: Path,
) -> None:
    epoch2_path, stream_path, bundles = _seed_forward_episode(tmp_path)
    before_epoch = epoch2_path.read_bytes()
    before_stream = stream_path.read_bytes()
    before_sidecars = _sqlite_sidecar_bytes(epoch2_path)

    model = FinalProductReadModel(
        stream_ledger_path=stream_path,
        epoch2_path=epoch2_path,
    )
    view = model.trade_lifecycle(
        bundle_identity=bundles[1],
        include_audit=True,
    )
    repeat = model.trade_lifecycle(
        bundle_identity=bundles[-1],
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış veri"
    assert view.lifecycle_state_label == "Kapalı işlem"
    assert view.event_count == 3
    assert tuple(item.sequence for item in view.events) == (1, 2, 3)
    assert tuple(item.lifecycle_label for item in view.events) == (
        "Pozisyon açılışı",
        "Kısmi kâr alma",
        "Pozisyon kapanışı",
    )
    assert tuple(
        item.audit.lifecycle_kind if item.audit is not None else None
        for item in view.events
    ) == ("OPEN", "PARTIAL_TAKE_PROFIT", "CLOSE")
    assert all(item.passport.audit is not None for item in view.events)
    assert tuple(
        item.passport.audit.bundle_identity
        for item in view.events
        if item.passport.audit is not None
    ) == bundles
    assert view.audit is not None
    assert view.audit.lifecycle_root_bundle_identity == bundles[0]
    assert view.audit.requested_bundle_identity == bundles[1]
    assert view.audit.bundle_identities == bundles
    assert repeat.audit is not None
    assert repeat.audit.bundle_identities == bundles
    assert repeat.events == view.events
    assert repeat.final_outcome_label == view.final_outcome_label
    assert view.unavailable_capabilities == (
        "STOP_UPDATE · exact trade-root bağı mevcut değil",
        "CORRECTION/SUPERSEDED · canonical kayıt mevcut değil",
    )
    assert epoch2_path.read_bytes() == before_epoch
    assert stream_path.read_bytes() == before_stream
    assert _sqlite_sidecar_bytes(epoch2_path) == before_sidecars


def test_fp6a_event_classification_distinguishes_scale_in_and_reduce() -> None:
    assert _trade_lifecycle_kind(
        raw_action="BUY",
        reason_codes=("fp3_action_scale_in",),
        position_before=Decimal("0.5"),
    ) == "SCALE_IN"
    assert _trade_lifecycle_kind(
        raw_action="REDUCE",
        reason_codes=("risk_reduction",),
        position_before=Decimal("0.5"),
    ) == "REDUCE"
    assert _trade_lifecycle_kind(
        raw_action="REDUCE",
        reason_codes=("partial_take_profit",),
        position_before=Decimal("0.5"),
    ) == "PARTIAL_TAKE_PROFIT"

    with pytest.raises(ValueError, match="contradicts holdings"):
        _trade_lifecycle_kind(
            raw_action="BUY",
            reason_codes=("fp3_action_open",),
            position_before=Decimal("0.5"),
        )


def test_fp6a_winning_and_losing_closed_trades_are_equally_inspectable(
    tmp_path: Path,
) -> None:
    expected = (
        ("winner", Decimal(108), "Kârla kapandı"),
        ("loser", Decimal(90), "Zararla kapandı"),
    )

    for label, close_price, outcome_label in expected:
        case_path = tmp_path / label
        case_path.mkdir()
        epoch2_path, stream_path, bundles = _seed_forward_episode(
            case_path,
            close_reference_price=close_price,
            include_partial_take_profit=False,
        )
        before = epoch2_path.read_bytes()
        before_sidecars = _sqlite_sidecar_bytes(epoch2_path)
        view = FinalProductReadModel(
            stream_ledger_path=stream_path,
            epoch2_path=epoch2_path,
        ).trade_lifecycle(
            bundle_identity=bundles[-1],
            include_audit=True,
        )

        assert view.lifecycle_state_label == "Kapalı işlem"
        assert view.event_count == 2
        assert view.final_outcome_label == outcome_label
        assert tuple(
            item.audit.lifecycle_kind if item.audit is not None else None
            for item in view.events
        ) == ("OPEN", "CLOSE")
        assert view.events[-1].passport.outcome_label == outcome_label
        assert view.events[-1].passport.audit is not None
        assert view.audit is not None
        assert view.audit.bundle_identities == bundles
        assert epoch2_path.read_bytes() == before
        assert _sqlite_sidecar_bytes(epoch2_path) == before_sidecars