from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from test_final_product_read_model import _seed_trade_passport_bundle
from test_intelligence_stream_read_model import _sha
from test_intelligence_stream_visual_proof import _create_visual_truth

from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.product.final_product_read_model import FinalProductReadModel
from crypto_signal.product.intelligence_stream_read_model import IntelligenceStreamReadModel
from crypto_signal.product.trade_passport_frozen_proof import (
    TradePassportFrozenProofError,
    TradePassportFrozenProofReadModel,
)


def _truth_paths(tmp_path: Path) -> tuple[Path, Path, Path, str, str, str, str]:
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
        narrative_identity,
        str(fact["forecast_identity"]),
        str(fact["proof_identity"]),
        _sha("s10-signal-freeze"),
    )


def _append_stream_rewrite(
    stream_path: Path,
    *,
    source_narrative_identity: str,
    event_at_ms: int,
    label: str,
) -> str:
    with sqlite3.connect(stream_path) as connection:
        row = connection.execute(
            """
            SELECT
                n.plan_identity,
                p.fact_bundle_identity,
                n.payload_json
            FROM stream_narrative_messages AS n
            JOIN stream_narrative_plans AS p
              ON p.plan_identity = n.plan_identity
            WHERE n.narrative_identity = ?
            """,
            (source_narrative_identity,),
        ).fetchone()
        assert row is not None
        fact_bundle_identity = str(row[1])
        payload = json.loads(str(row[2]))
        assert isinstance(payload, dict)

        new_plan_identity = _sha(f"{label}-plan")
        connection.execute(
            """
            INSERT INTO stream_narrative_plans (
                plan_identity,
                fact_bundle_identity
            ) VALUES (?, ?)
            """,
            (new_plan_identity, fact_bundle_identity),
        )

        payload_without_identity = dict(payload)
        payload_without_identity.pop("narrative_identity", None)
        payload_without_identity["plan_identity"] = new_plan_identity
        payload_without_identity["event_at_ms"] = event_at_ms
        payload_without_identity["source_kind"] = "local_rewrite"
        text = dict(payload_without_identity["text"])
        text["collapsed_text"] = f"{text['collapsed_text']} [{label}]"
        text["simple_text"] = f"{text['simple_text']} [{label}]"
        payload_without_identity["text"] = text

        narrative_identity = canonical_sha256(payload_without_identity)
        rewritten = {
            "narrative_identity": narrative_identity,
            **payload_without_identity,
        }
        payload_json = canonical_json(rewritten)
        connection.execute(
            """
            INSERT INTO stream_narrative_messages (
                narrative_identity,
                plan_identity,
                analytical_view_identity,
                story_identity,
                source_event_identity,
                stream_event_identity,
                event_at_ms,
                source_kind,
                payload_json,
                payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                narrative_identity,
                new_plan_identity,
                rewritten["analytical_view_identity"],
                rewritten["story_identity"],
                rewritten["source_event_identity"],
                rewritten["stream_event_identity"],
                event_at_ms,
                "local_rewrite",
                payload_json,
                sha256_text(payload_json),
            ),
        )
        connection.commit()
    return narrative_identity


def test_fp6b_exact_lineage_opens_existing_frozen_proof_read_only(
    tmp_path: Path,
) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        narrative_identity,
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
    assert view.audit.narrative_identity == narrative_identity
    assert view.audit.narrative_event_at_ms == 1_000
    assert view.audit.forecast_identity == forecast_identity
    assert view.audit.proof_identity == proof_identity
    assert view.audit.signal_freeze_identity == signal_freeze_identity
    assert view.audit.decision_freeze_bundle_identity is not None
    assert view.audit.event_as_of_ms is None
    assert view.audit.proof_frozen_at_ms == 1_000

    assert stream_path.read_bytes() == before[stream_path]
    assert signal_path.read_bytes() == before[signal_path]
    assert decision_path.read_bytes() == before[decision_path]


def test_fp6b_stream_rewrite_is_selected_point_in_time_without_rewriting_history(
    tmp_path: Path,
) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        original_narrative,
        forecast_identity,
        proof_identity,
        signal_freeze_identity,
    ) = _truth_paths(tmp_path)
    rewrite_narrative = _append_stream_rewrite(
        stream_path,
        source_narrative_identity=original_narrative,
        event_at_ms=2_000,
        label="fp6b-later-story",
    )
    before = {
        stream_path: stream_path.read_bytes(),
        signal_path: signal_path.read_bytes(),
        decision_path: decision_path.read_bytes(),
    }
    model = TradePassportFrozenProofReadModel(
        stream_ledger_path=stream_path,
        epoch2_path=tmp_path / "unused-epoch2.sqlite3",
        decision_evidence_path=decision_path,
        signal_ledger_path=signal_path,
    )

    early = model.read_for_lineage(
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        signal_freeze_identity=signal_freeze_identity,
        as_of_ms=1_500,
        include_audit=True,
    )
    late = model.read_for_lineage(
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        signal_freeze_identity=signal_freeze_identity,
        as_of_ms=2_500,
        include_audit=True,
    )

    assert early.audit is not None
    assert late.audit is not None
    assert early.audit.narrative_identity == original_narrative
    assert early.audit.narrative_event_at_ms == 1_000
    assert early.audit.event_as_of_ms == 1_500
    assert late.audit.narrative_identity == rewrite_narrative
    assert late.audit.narrative_event_at_ms == 2_000
    assert late.audit.event_as_of_ms == 2_500
    assert early.audit.proof_identity == late.audit.proof_identity == proof_identity
    assert early.current_data_substitution is False
    assert late.current_data_substitution is False
    assert stream_path.read_bytes() == before[stream_path]
    assert signal_path.read_bytes() == before[signal_path]
    assert decision_path.read_bytes() == before[decision_path]


def test_fp6b_passport_fill_time_binds_each_lifecycle_event_to_then_current_story(
    tmp_path: Path,
) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        original_narrative,
        forecast_identity,
        proof_identity,
        signal_freeze_identity,
    ) = _truth_paths(tmp_path)
    rewrite_narrative = _append_stream_rewrite(
        stream_path,
        source_narrative_identity=original_narrative,
        event_at_ms=2_000,
        label="fp6b-lifecycle-rewrite",
    )
    passport_dir = tmp_path / "passport"
    passport_dir.mkdir()
    epoch2_path, _, _, bundle = _seed_trade_passport_bundle(passport_dir)
    passport = FinalProductReadModel(
        stream_ledger_path=stream_path,
        epoch2_path=epoch2_path,
    ).trade_passport(
        bundle_identity=bundle.bundle_identity,
        include_audit=True,
    )
    assert passport.audit is not None
    exact_audit = replace(
        passport.audit,
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        signal_freeze_identity=signal_freeze_identity,
    )
    lifecycle_passports = (
        replace(passport, filled_at_ms=1_500, audit=exact_audit),
        replace(passport, filled_at_ms=2_500, audit=exact_audit),
    )
    before = {
        stream_path: stream_path.read_bytes(),
        signal_path: signal_path.read_bytes(),
        decision_path: decision_path.read_bytes(),
        epoch2_path: epoch2_path.read_bytes(),
    }
    model = TradePassportFrozenProofReadModel(
        stream_ledger_path=stream_path,
        epoch2_path=epoch2_path,
        decision_evidence_path=decision_path,
        signal_ledger_path=signal_path,
    )

    proofs = tuple(
        model.read_for_passport(item, include_audit=True)
        for item in lifecycle_passports
    )

    assert all(item.audit is not None for item in proofs)
    assert tuple(
        item.audit.narrative_identity
        for item in proofs
        if item.audit is not None
    ) == (original_narrative, rewrite_narrative)
    assert tuple(
        item.audit.event_as_of_ms
        for item in proofs
        if item.audit is not None
    ) == (1_500, 2_500)
    assert all(item.current_data_substitution is False for item in proofs)
    assert stream_path.read_bytes() == before[stream_path]
    assert signal_path.read_bytes() == before[signal_path]
    assert decision_path.read_bytes() == before[decision_path]
    assert epoch2_path.read_bytes() == before[epoch2_path]


def test_fp6b_proof_that_did_not_exist_yet_is_not_opened(tmp_path: Path) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        _,
        forecast_identity,
        proof_identity,
        signal_freeze_identity,
    ) = _truth_paths(tmp_path)

    view = TradePassportFrozenProofReadModel(
        stream_ledger_path=stream_path,
        epoch2_path=tmp_path / "unused-epoch2.sqlite3",
        decision_evidence_path=decision_path,
        signal_ledger_path=signal_path,
    ).read_for_lineage(
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        signal_freeze_identity=signal_freeze_identity,
        as_of_ms=999,
        include_audit=True,
    )

    assert view.availability_label == "Bu işlem için exact tarihsel Stream kanıtı bulunamadı"
    assert view.audit is None
    assert view.current_data_substitution is False


def test_fp6b_same_timestamp_competing_exact_stories_fail_closed(
    tmp_path: Path,
) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        original_narrative,
        forecast_identity,
        proof_identity,
        signal_freeze_identity,
    ) = _truth_paths(tmp_path)
    _append_stream_rewrite(
        stream_path,
        source_narrative_identity=original_narrative,
        event_at_ms=2_000,
        label="fp6b-competing-a",
    )
    _append_stream_rewrite(
        stream_path,
        source_narrative_identity=original_narrative,
        event_at_ms=2_000,
        label="fp6b-competing-b",
    )

    with pytest.raises(
        TradePassportFrozenProofError,
        match="competing narratives at the same event time",
    ):
        TradePassportFrozenProofReadModel(
            stream_ledger_path=stream_path,
            epoch2_path=tmp_path / "unused-epoch2.sqlite3",
            decision_evidence_path=decision_path,
            signal_ledger_path=signal_path,
        ).read_for_lineage(
            forecast_identity=forecast_identity,
            proof_identity=proof_identity,
            signal_freeze_identity=signal_freeze_identity,
            as_of_ms=2_500,
        )


def test_fp6b_missing_stream_lineage_is_explicit_and_does_not_backfill(
    tmp_path: Path,
) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        _,
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


def test_fp6b_wrong_signal_lineage_fails_closed_without_substitution(tmp_path: Path) -> None:
    (
        stream_path,
        signal_path,
        decision_path,
        _,
        forecast_identity,
        proof_identity,
        _,
    ) = _truth_paths(tmp_path)

    view = TradePassportFrozenProofReadModel(
        stream_ledger_path=stream_path,
        epoch2_path=tmp_path / "unused-epoch2.sqlite3",
        decision_evidence_path=decision_path,
        signal_ledger_path=signal_path,
    ).read_for_lineage(
        forecast_identity=forecast_identity,
        proof_identity=proof_identity,
        signal_freeze_identity=_sha("fp6b-wrong-signal-freeze"),
        include_audit=True,
    )

    assert view.availability_label == "Bu işlem için exact tarihsel Stream kanıtı bulunamadı"
    assert view.audit is None
    assert view.current_data_substitution is False


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
