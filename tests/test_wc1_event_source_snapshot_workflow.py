from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _event_source_snapshot_block() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: EVENT SOURCE SNAPSHOT")
    end = text.index("      - name: ROLLING WAKE STATE", start)
    return text[start:end]


def test_event_source_snapshot_is_explicitly_allowlisted() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert (
        "status|eventsourcestate|eventsourcesnapshot|services|"
        in text
    )
    block = _event_source_snapshot_block()
    assert (
        "steps.parse.outputs.command == 'eventsourcesnapshot'"
        in block
    )


def test_event_source_snapshot_is_bounded_to_exact_evidence_db() -> None:
    block = _event_source_snapshot_block()

    assert "/Volumes/Crypto-504/Crypto-Signal" in block
    assert 'EVENT_DB="$DEV/runtime/events/event_source.sqlite3"' in block
    assert 'SNAPSHOT="$GITHUB_WORKSPACE/ops/run_event_source_snapshot.py"' in block
    assert 'PYTHONPATH="$GITHUB_WORKSPACE/src"' in block
    assert '--db "$EVENT_DB"' in block
    assert "--timeout-seconds 20" in block
    assert "read_event_source_runtime_truth" in block
    assert "EVENT_SOURCE_SNAPSHOT_BOUNDED_PASS=YES" in block
    assert "EVENT_SOURCE_SNAPSHOT_APPEND_ONLY_EVIDENCE=YES" in block
    assert "EVENT_SOURCE_ONLINE_NOT_ASSERTED_PASS=YES" in block
    assert '"NOT_ASSERTED"' in block
    assert 'echo "REAL_CAPITAL=0"' in block


def test_event_source_snapshot_has_no_service_or_repo_mutation_surface() -> None:
    block = _event_source_snapshot_block()
    forbidden = (
        'git -C "$DEV" merge',
        'git -C "$DEV" checkout',
        'git -C "$PRODUCT" checkout',
        "git fetch",
        "launchctl",
        "kickstart",
        "bootstrap",
        "kill ",
        "rm -",
        "cp ",
        "mv ",
        "touch ",
        "productdeploy",
        "place_order",
        "api_key",
        "secret",
        "credential",
        "leverage",
        "martingale",
    )

    for token in forbidden:
        assert token not in block
