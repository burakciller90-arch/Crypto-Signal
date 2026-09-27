from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ops import audit_stream_f8_production_e2e as audit

IDENTITY = "a" * 64


def _proof_payload(
    *,
    state: str = "READY_EXACT",
    current_data_substitution: bool = False,
    production_authority: bool = False,
    top_status: str = "ready",
) -> dict[str, object]:
    return {
        "status": top_status,
        "narrative_identity": IDENTITY,
        "evidence": {
            "status": "ready",
            "narrative_identity": IDENTITY,
            "resolutions": [
                {
                    "domain": "geometry",
                    "resolution_state": state,
                    "reason": "test_exact_resolution",
                    "current_data_substitution": current_data_substitution,
                }
            ],
            "reference_resolutions": [],
            "current_data_substitution": current_data_substitution,
            "read_only": True,
            "production_authority": production_authority,
            "real_capital": 0,
        },
        "read_only": True,
        "real_capital": 0,
    }


def test_require_read_only_accepts_exact_safety_boundary() -> None:
    payload = {
        "read_only": True,
        "real_capital": 0,
    }
    assert audit._require_read_only(payload, "test") is payload


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"read_only": False, "real_capital": 0}, "not read-only"),
        ({"read_only": True, "real_capital": 1}, "REAL_CAPITAL"),
    ],
)
def test_require_read_only_rejects_authority_crossing(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(audit.AuditError, match=message):
        audit._require_read_only(payload, "test")


def test_require_sha256_is_strict_lowercase() -> None:
    assert audit._require_sha256(IDENTITY, "identity") == IDENTITY
    with pytest.raises(audit.AuditError, match="lowercase SHA256"):
        audit._require_sha256("A" * 64, "identity")
    with pytest.raises(audit.AuditError, match="lowercase SHA256"):
        audit._require_sha256("a" * 63, "identity")


@pytest.mark.parametrize(
    "state",
    [
        "READY_EXACT",
        "IDENTITY_ONLY_EXACT",
        "UNAVAILABLE_EXPLICIT",
    ],
)
def test_proof_result_accepts_f6_exact_resolution_states(state: str) -> None:
    result = audit._proof_result(_proof_payload(state=state))
    assert result["status"] == "ready"
    assert result["accepted_fail_closed"] is True
    assert result["resolution_states"] == [state.lower()]


def test_proof_result_rejects_non_ready_top_level_response() -> None:
    result = audit._proof_result(_proof_payload(top_status="unavailable"))
    assert result["accepted_fail_closed"] is False


def test_proof_result_rejects_unknown_resolution_state() -> None:
    result = audit._proof_result(_proof_payload(state="SYNTHETIC_READY"))
    assert result["accepted_fail_closed"] is False
    assert "unsupported_resolution_state" in str(result["reason"])


def test_proof_result_rejects_current_data_substitution() -> None:
    with pytest.raises(audit.AuditError, match="substituted current data"):
        audit._proof_result(_proof_payload(current_data_substitution=True))


def test_proof_result_rejects_production_authority() -> None:
    with pytest.raises(audit.AuditError, match="production authority"):
        audit._proof_result(_proof_payload(production_authority=True))

def test_walk_values_collects_nested_lineage() -> None:
    payload = {
        "narrative_identity": IDENTITY,
        "nested": {
            "narrative_identity": "b" * 64,
            "items": [
                {"narrative_identity": "c" * 64},
                {"other": "ignored"},
            ],
        },
    }
    assert audit._walk_values(payload, "narrative_identity") == [
        IDENTITY,
        "b" * 64,
        "c" * 64,
    ]


def test_parse_sse_identities_preserves_replay_order() -> None:
    raw = (
        "retry: 1500\n\n"
        "id: first\n"
        "event: message\n"
        "data: {}\n\n"
        "id: second\n"
        "event: message\n"
        "data: {}\n\n"
        "id: second\n"
        "event: message\n"
        "data: {}\n\n"
    )
    assert audit._parse_sse_identities(raw) == ["first", "second", "second"]



def _seed_stream_ledger(path: Path, *, duplicate_source_narrative: bool = False) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE stream_activation (
                activation_identity TEXT PRIMARY KEY,
                activated_at_ms INTEGER NOT NULL
            );
            CREATE TABLE stream_source_events (
                source_event_identity TEXT PRIMARY KEY,
                event_at_ms INTEGER NOT NULL
            );
            CREATE TABLE stream_narrative_messages (
                narrative_identity TEXT PRIMARY KEY,
                source_event_identity TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO stream_activation (activation_identity, activated_at_ms) VALUES (?, ?)",
            ("d" * 64, 1000),
        )
        connection.execute(
            "INSERT INTO stream_source_events (source_event_identity, event_at_ms) VALUES (?, ?)",
            ("e" * 64, 1100),
        )
        connection.execute(
            "INSERT INTO stream_narrative_messages "
            "(narrative_identity, source_event_identity) VALUES (?, ?)",
            ("f" * 64, "e" * 64),
        )
        if duplicate_source_narrative:
            connection.execute(
                "INSERT INTO stream_narrative_messages "
                "(narrative_identity, source_event_identity) VALUES (?, ?)",
                ("1" * 64, "e" * 64),
            )
        connection.commit()


def test_stream_ledger_negative_acceptance_passes_unique_forward_truth(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    _seed_stream_ledger(path)
    result = audit._audit_stream_ledger(path)
    assert result["status"] == "PASS"
    assert result["historical_source_rows_before_activation"] == 0
    assert result["multi_narrative_rows_for_one_source"] == 0
    assert result["read_only"] is True
    assert result["real_capital"] == 0


def test_stream_ledger_negative_acceptance_catches_one_source_spam(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stream.sqlite3"
    _seed_stream_ledger(path, duplicate_source_narrative=True)
    result = audit._audit_stream_ledger(path)
    assert result["status"] == "FAIL"
    assert result["multi_narrative_rows_for_one_source"] == 1
