from __future__ import annotations

from pathlib import Path

from support_stream_s15 import append_capital, append_resolution, seed

from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamMessageQuery,
)
from crypto_signal.product.intelligence_stream_visual_proof import (
    IntelligenceStreamVisualProofReadModel,
)


def test_s15_end_to_end_persists_story_proof_change_and_capital(tmp_path: Path) -> None:
    manifest = seed(tmp_path)
    stream_path = Path(str(manifest["stream_path"]))
    reader = IntelligenceStreamReadModel(stream_path)

    initial = reader.read_messages(StreamMessageQuery(limit=20))
    assert len(initial.items) == 1
    root = initial.items[0]
    assert root["narrative_identity"] == manifest["root_narrative_identity"]
    assert root["text"]["collapsed_text"] == manifest["root_collapsed_text"]
    root_before = reader.read_message(str(manifest["root_narrative_identity"]))
    assert root_before is not None

    proof = IntelligenceStreamVisualProofReadModel(
        stream_ledger_path=stream_path,
        signal_ledger_path=Path(str(manifest["signal_path"])),
        decision_evidence_path=Path(str(manifest["decision_path"])),
    ).read_for_narrative(str(manifest["root_narrative_identity"]))
    assert proof is not None
    assert proof["status"] == "ready"
    assert proof["provenance"]["current_data_substitution"] is False
    assert len(proof["candles"]) == 28
    assert {item["kind"] for item in proof["annotations"]} == {
        "entry_zone",
        "invalidation",
        "target",
    }

    after_resolution = append_resolution(tmp_path)
    page_after_resolution = reader.read_messages(StreamMessageQuery(limit=20))
    assert len(page_after_resolution.items) == 2
    root_after = reader.read_message(str(manifest["root_narrative_identity"]))
    assert root_after == root_before

    resolution_id = str(after_resolution["resolution_narrative_identity"])
    resolution = reader.read_message(resolution_id)
    assert resolution is not None
    assert resolution["story_identity"] == manifest["story_identity"]
    assert resolution["narrative_identity"] != manifest["root_narrative_identity"]

    after_capital = append_capital(tmp_path)
    final_page = reader.read_messages(StreamMessageQuery(limit=20))
    assert len(final_page.items) == 3
    capital_id = str(after_capital["capital_narrative_identity"])
    capital = reader.read_message(capital_id)
    assert capital is not None
    assert capital["category"] == "capital"
    assert capital["forecast_identity"] == manifest["forecast_identity"]
    assert capital["proof_identity"] == manifest["proof_identity"]
    assert capital["bundle_identity"] == after_capital["capital_bundle_identity"]
    assert capital["intent_identity"] == after_capital["capital_intent_identity"]
    assert capital["fill_identity"] == after_capital["capital_fill_identity"]
    assert capital["real_capital"] == 0
    assert capital["production_authority"] is False

    searched = reader.read_messages(
        StreamMessageQuery(limit=20, symbol="BTCUSDT")
    )
    assert str(manifest["root_narrative_identity"]) in {
        item["narrative_identity"] for item in searched.items
    }
    capital_only = reader.read_messages(
        StreamMessageQuery(limit=20, category="capital")
    )
    assert [item["narrative_identity"] for item in capital_only.items] == [
        capital_id
    ]

    reopened = IntelligenceStreamReadModel(stream_path)
    assert reopened.read_message(str(manifest["root_narrative_identity"])) == root_before
    assert reopened.read_message(resolution_id) == resolution
    assert reopened.read_message(capital_id) == capital
