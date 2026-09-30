from __future__ import annotations

from pathlib import Path

import pytest
from test_intelligence_stream_read_model import _sha
from test_intelligence_stream_visual_proof import _create_visual_truth

from crypto_signal.product.intelligence_stream_read_model import IntelligenceStreamReadModel
from crypto_signal.product.trade_passport_frozen_proof import (
    TradePassportFrozenProofError,
    TradePassportFrozenProofReadModel,
)


def _truth_paths(tmp_path: Path) -> tuple[Path, Path, Path, str, str, str]:
    stream_path = tmp_path / "fp6b-stream.sqlite3"
    signal_path = tmp_path / "fp6b-signal.sqlite3"
    decision_path = tmp_path / "fp6b-decision.sqlite3"
    narrative_identity = _create_visual_truth(
        stream_path=stream_path,
        signal_path=signal_path,
        decision_path=decision_path,
    )
    detail = IntelligenceStreamReadModel(stream_path).read_message_detail(
        narrative_identity
    )
    assert detail is not None
    fact = detail["fact_bundle"]
    return (
        stream_path,
        signal_path,
        decision_path,
        str(fact["forecast_identity"]),
        str(fact["proof_identity"]),
        _sha("s10-signal-freeze"),
    )


def test_fp6b_exact_lineage_opens_existing_frozen_proof_read_only(
    tmp_path: Path,
) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        forecast_identity,
        proof_identity,
        signal_freeze_identity,
    ) = _truth_paths(tmp_path)
    before = {
        stream_path: stream_path.read_bytes(),
        signal_path: signal_path.read_bytes(),
        decision_path: decision_path.read_bytes(),
    }

    view = TradePassportFrozenProofReadModel(
        stream_ledger_path=stream_path,
        epoch2_path=tmp_path / "unused-epoch2.sqlite3",
        decision_evidence_path=decision_path,
        signal_ledger_path=signal_path,
    ).read_for_lineage(
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        signal_freeze_identity=signal_freeze_identity,
        include_audit=True,
    )

    assert view.availability_label == "Doğrulanmış tarihsel kanıt"
    assert view.frozen_market_story_label == "Dondurulmuş Market Story doğrulandı"
    assert view.exact_evidence_label == "Exact aile/source kanıtı doğrulandı"
    assert view.source_as_of_ms == 1_000
    assert view.issued_at_ms == 1_000
    assert view.chart_candle_count == 2
    assert view.annotation_count >= 3
    assert view.family_proof_count == 5
    assert view.evidence_domain_count >= 1
    assert view.current_data_substitution is False
    assert view.read_only is True
    assert view.real_capital == 0
    assert view.audit is not None
    assert view.audit.forecast_identity == forecast_identity
    assert view.audit.proof_identity == proof_identity
    assert view.audit.signal_freeze_identity == signal_freeze_identity
    assert len(view.audit.narrative_identity) == 64
    assert view.audit.decision_freeze_bundle_identity is not None

    assert stream_path.read_bytes() == before[stream_path]
    assert signal_path.read_bytes() == before[signal_path]
    assert decision_path.read_bytes() == before[decision_path]


def test_fp6b_missing_stream_lineage_is_explicit_and_does_not_backfill(
    tmp_path: Path,
) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        _,
        _,
        signal_freeze_identity,
    ) = _truth_paths(tmp_path)
    before = {
        stream_path: stream_path.read_bytes(),
        signal_path: signal_path.read_bytes(),
        decision_path: decision_path.read_bytes(),
    }

    view = TradePassportFrozenProofReadModel(
        stream_ledger_path=stream_path,
        epoch2_path=tmp_path / "unused-epoch2.sqlite3",
        decision_evidence_path=decision_path,
        signal_ledger_path=signal_path,
    ).read_for_lineage(
        forecast_identity=_sha("fp6b-unknown-forecast"),
        proof_identity=_sha("fp6b-unknown-proof"),
        signal_freeze_identity=signal_freeze_identity,
        include_audit=True,
    )

    assert view.availability_label == "Bu işlem için exact tarihsel Stream kanıtı bulunamadı"
    assert view.chart_candle_count == 0
    assert view.family_proof_count == 0
    assert view.current_data_substitution is False
    assert view.audit is None
    assert stream_path.read_bytes() == before[stream_path]
    assert signal_path.read_bytes() == before[signal_path]
    assert decision_path.read_bytes() == before[decision_path]


def test_fp6b_signal_lineage_mismatch_fails_closed(tmp_path: Path) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        forecast_identity,
        proof_identity,
        _,
    ) = _truth_paths(tmp_path)

    with pytest.raises(
        TradePassportFrozenProofError,
        match="signal freeze / frozen proof lineage mismatch",
    ):
        TradePassportFrozenProofReadModel(
            stream_ledger_path=stream_path,
            epoch2_path=tmp_path / "unused-epoch2.sqlite3",
            decision_evidence_path=decision_path,
            signal_ledger_path=signal_path,
        ).read_for_lineage(
            forecast_identity=forecast_identity,
            proof_identity=proof_identity,
            signal_freeze_identity=_sha("fp6b-wrong-signal-freeze"),
        )


def test_fp6b_invalid_hash_is_rejected_before_any_lookup(tmp_path: Path) -> None:
    model = TradePassportFrozenProofReadModel(
        stream_ledger_path=tmp_path / "missing-stream.sqlite3",
        epoch2_path=tmp_path / "missing-epoch2.sqlite3",
        decision_evidence_path=tmp_path / "missing-decision.sqlite3",
        signal_ledger_path=tmp_path / "missing-signal.sqlite3",
    )

    with pytest.raises(TradePassportFrozenProofError, match="must be SHA256"):
        model.read_for_lineage(
            forecast_identity="not-a-sha",
            proof_identity=_sha("fp6b-proof"),
            signal_freeze_identity=_sha("fp6b-signal"),
        )

    assert not (tmp_path / "missing-stream.sqlite3").exists()
    assert not (tmp_path / "missing-epoch2.sqlite3").exists()
    assert not (tmp_path / "missing-decision.sqlite3").exists()
    assert not (tmp_path / "missing-signal.sqlite3").exists()
