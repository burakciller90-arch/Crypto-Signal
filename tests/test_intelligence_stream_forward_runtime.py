from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from test_wc2_live_source_adapter import _bundle

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.evaluation.live_untouched_forward_operational import (
    issue_same_cycle_untouched_forward_forecast,
)
from crypto_signal.product.intelligence_stream_forward_runtime import (
    IntelligenceStreamForwardRuntime,
    StreamForwardProjectionDisposition,
)
from crypto_signal.product.intelligence_stream_ledger import IntelligenceStreamLedger
from crypto_signal.product.intelligence_stream_narrative import (
    StreamNarrativeRewriteRequest,
    StreamNarrativeText,
)
from crypto_signal.product.intelligence_stream_narrative_ledger import (
    IntelligenceStreamNarrativeLedger,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamMessageQuery,
)


class _PassthroughLocalRewriter:
    rewriter_identity = "f" * 64
    rewriter_version = "stream-f7-test-rewriter/1"

    def rewrite(
        self,
        request: StreamNarrativeRewriteRequest,
    ) -> StreamNarrativeText:
        return request.deterministic_text


def _issuance(tmp_path: Path, *, issued_at_ms: int):
    bundle = _bundle()
    signal = bundle.signal_decision
    return issue_same_cycle_untouched_forward_forecast(
        bundle,
        frozen_at_ms=signal.as_of_ms + 10,
        issued_at_ms=issued_at_ms,
        maximum_issuance_delay_ms=10_000,
        horizon_bars=4,
        base_asset="BTC",
        ledger=ImmutableDecisionEvidenceLedger(tmp_path / "decision.sqlite3"),
    )


def test_forward_runtime_initializes_full_schema_and_publishes_same_cycle(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime" / "stream" / "intelligence_stream.sqlite3"
    runtime = IntelligenceStreamForwardRuntime(path)
    issuance = _issuance(tmp_path, issued_at_ms=_bundle().signal_decision.as_of_ms + 100)

    activation = runtime.ensure_activated(
        activated_at_ms=issuance.forecast.issued_at_ms - 1
    )
    result = runtime.project_issuance(issuance)

    assert result.disposition is StreamForwardProjectionDisposition.INSERTED
    assert result.forecast_identity == issuance.forecast.forecast_identity
    assert result.narrative_identity is not None
    assert result.activation_identity == activation.activation_identity
    assert result.historical_backfill_performed is False
    assert result.production_authority is False
    assert result.real_capital == 0

    status = IntelligenceStreamLedger(path).read_status()
    assert status.source_event_count == 1
    assert status.decision_context_count == 1
    narrative_status = IntelligenceStreamNarrativeLedger(path).read_status()
    assert narrative_status.narrative_count == 1

    page = IntelligenceStreamReadModel(path).read_messages(StreamMessageQuery())
    assert len(page.items) == 1
    assert page.items[0]["symbol"] == issuance.forecast.symbol
    assert page.items[0]["narrative_identity"] == result.narrative_identity
    assert page.real_capital == 0


def test_forward_runtime_persists_guarded_local_rewrite_provenance(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream-local-rewrite.sqlite3"
    rewriter = _PassthroughLocalRewriter()
    runtime = IntelligenceStreamForwardRuntime(path, rewriter=rewriter)
    issuance = _issuance(
        tmp_path,
        issued_at_ms=_bundle().signal_decision.as_of_ms + 100,
    )
    runtime.ensure_activated(activated_at_ms=issuance.forecast.issued_at_ms - 1)

    result = runtime.project_issuance(issuance)

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


def test_forward_runtime_replay_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "stream.sqlite3"
    runtime = IntelligenceStreamForwardRuntime(path)
    issuance = _issuance(tmp_path, issued_at_ms=_bundle().signal_decision.as_of_ms + 100)
    runtime.ensure_activated(activated_at_ms=issuance.forecast.issued_at_ms - 1)

    first = runtime.project_issuance(issuance)
    second = runtime.project_issuance(issuance)

    assert first.disposition is StreamForwardProjectionDisposition.INSERTED
    assert second.disposition is StreamForwardProjectionDisposition.UNCHANGED
    assert second.narrative_identity == first.narrative_identity
    assert IntelligenceStreamNarrativeLedger(path).read_status().narrative_count == 1


def test_forward_runtime_never_backfills_pre_activation_issuance(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    runtime = IntelligenceStreamForwardRuntime(path)
    issuance = _issuance(tmp_path, issued_at_ms=_bundle().signal_decision.as_of_ms + 100)
    activation = runtime.ensure_activated(
        activated_at_ms=issuance.forecast.issued_at_ms + 1
    )

    result = runtime.project_issuance(issuance)

    assert (
        result.disposition
        is StreamForwardProjectionDisposition.SKIPPED_BEFORE_ACTIVATION
    )
    assert result.activation_identity == activation.activation_identity
    assert IntelligenceStreamLedger(path).read_status().source_event_count == 0
    assert IntelligenceStreamNarrativeLedger(path).read_status().narrative_count == 0
    page = IntelligenceStreamReadModel(path).read_messages(StreamMessageQuery())
    assert page.items == ()


def test_forward_runtime_preserves_first_activation_across_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    first = IntelligenceStreamForwardRuntime(path).ensure_activated(
        activated_at_ms=10_000
    )
    second = IntelligenceStreamForwardRuntime(path).ensure_activated(
        activated_at_ms=99_000
    )

    assert second == first
    assert IntelligenceStreamLedger(path).read_status().activated_at_ms == 10_000
