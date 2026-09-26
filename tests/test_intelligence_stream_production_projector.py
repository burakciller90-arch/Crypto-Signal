from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from test_wc2_live_source_adapter import _bundle

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.live_untouched_forward_operational import (
    issue_same_cycle_untouched_forward_forecast,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
)
from crypto_signal.product.intelligence_stream_ledger import (
    IntelligenceStreamLedger,
)
from crypto_signal.product.intelligence_stream_models import (
    build_stream_decision_context,
)
from crypto_signal.product.intelligence_stream_narrative import (
    StreamNarrativeRewriteRequest,
    StreamNarrativeText,
)
from crypto_signal.product.intelligence_stream_policy import (
    build_stream_materiality_policy,
    evaluate_stream_materiality,
)
from crypto_signal.product.intelligence_stream_production_projector import (
    IntelligenceStreamProductionProjector,
    StreamProductionProjectionDisposition,
    build_stream_production_projector_contract,
)
from crypto_signal.product.intelligence_stream_projectors import (
    project_forecast_issuance,
)


class _PassthroughLocalRewriter:
    rewriter_identity = "e" * 64
    rewriter_version = "stream-f7-test-rewriter/1"

    def rewrite(
        self,
        request: StreamNarrativeRewriteRequest,
    ) -> StreamNarrativeText:
        return request.deterministic_text


def _issuance(tmp_path: Path):
    bundle = _bundle()
    signal = bundle.signal_decision
    return issue_same_cycle_untouched_forward_forecast(
        bundle,
        frozen_at_ms=signal.as_of_ms + 10,
        issued_at_ms=signal.as_of_ms + 100,
        maximum_issuance_delay_ms=10_000,
        horizon_bars=4,
        base_asset="BTC",
        ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
    )


def _projected(tmp_path: Path):
    issuance = _issuance(tmp_path)
    path = tmp_path / "stream.sqlite3"
    runtime = IntelligenceStreamForwardRuntime(path)
    activation = runtime.ensure_activated(
        activated_at_ms=issuance.forecast.issued_at_ms - 1
    )
    context = build_stream_decision_context(
        issuance.forecast,
        issuance.proof,
        issuance.confluence,
    )
    projected = project_forecast_issuance(
        activation,
        context,
        issuance.forecast,
        issuance.proof,
        issuance.feed_event,
    )
    return path, context, projected


def test_f2_contract_captures_required_common_projector_truth(
    tmp_path: Path,
) -> None:
    _, _, projected = _projected(tmp_path)

    contract = build_stream_production_projector_contract(
        "r20_5_forecast_issued",
        projected,
    )

    assert contract.source_event_identity == projected.source_event.source_event_identity
    assert contract.stream_event_identity == projected.source_event.stream_event_identity
    assert contract.category is projected.source_event.category
    assert contract.subtype == projected.source_event.subtype
    assert contract.importance is projected.source_event.importance
    assert contract.asset == projected.source_event.asset
    assert contract.symbol == projected.source_event.symbol
    assert contract.market == projected.fact_bundle.market
    assert contract.timeframe == projected.source_event.timeframe
    assert contract.event_at_ms == projected.source_event.event_at_ms
    assert contract.source_as_of_ms == projected.source_event.source_as_of_ms
    assert contract.evidence_identities == projected.source_event.evidence_identities
    assert contract.story_identity == projected.fact_bundle.story_identity
    assert (
        contract.current_fact_reference_identity
        == projected.fact_bundle.fact_bundle_identity
    )
    assert contract.previous_state_reference_identity is None
    materiality = evaluate_stream_materiality(
        build_stream_materiality_policy(),
        projected.source_event,
    )
    assert contract.materiality_reason_codes == materiality.reason_codes
    assert (
        contract.materiality_decision_identity
        == projected.message_input.materiality_decision_identity
    )
    assert contract.production_authority is False
    assert contract.real_capital == 0


def test_f7_rewriter_flows_through_generic_production_backbone(
    tmp_path: Path,
) -> None:
    path, context, projected = _projected(tmp_path)
    rewriter = _PassthroughLocalRewriter()

    source = IntelligenceStreamLedger(path)
    source.append_issuance_bundle(context, projected.source_event)
    result = IntelligenceStreamProductionProjector(
        path,
        rewriter=rewriter,
    ).project("r20_5_forecast_issued", projected)

    assert result.narrative_identity is not None
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT source_kind, payload_json
            FROM stream_narrative_messages
            WHERE narrative_identity = ?
            """,
            (result.narrative_identity,),
        ).fetchone()
    assert row is not None
    assert row[0] == "local_rewrite"
    payload = json.loads(str(row[1]))
    assert payload["rewrite_engine_identity"] == rewriter.rewriter_identity
    assert payload["rewrite_engine_version"] == rewriter.rewriter_version
    assert payload["original_text_preserved"] is True
    assert payload["production_authority"] is False
    assert payload["real_capital"] == 0


def test_f2_backbone_reuses_canonical_s3_s4_s5_chain_and_is_idempotent(
    tmp_path: Path,
) -> None:
    path, context, projected = _projected(tmp_path)

    source = IntelligenceStreamLedger(path)
    source.append_issuance_bundle(context, projected.source_event)

    backbone = IntelligenceStreamProductionProjector(path)
    first = backbone.project("r20_5_forecast_issued", projected)
    second = backbone.project("r20_5_forecast_issued", projected)

    assert first.disposition is StreamProductionProjectionDisposition.INSERTED
    assert second.disposition is StreamProductionProjectionDisposition.UNCHANGED
    assert second.narrative_identity == first.narrative_identity
    assert second.state_identity == first.state_identity
    assert second.contract_identity == first.contract_identity
    assert first.production_authority is False
    assert first.real_capital == 0


def test_f2_backbone_rejects_still_deferred_source_before_implementation(
    tmp_path: Path,
) -> None:
    _, _, projected = _projected(tmp_path)

    with pytest.raises(ValueError, match="not implemented"):
        build_stream_production_projector_contract(
            "bitcoin_network_context",
            projected,
        )
