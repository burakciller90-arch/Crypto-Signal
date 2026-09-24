from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _event_source_state_block() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: EVENT SOURCE STATE")
    end = text.index("      - name: ROLLING WAKE STATE", start)
    return text[start:end]


def test_event_source_state_is_explicitly_allowlisted() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "eventsourcestate" in text
    assert "eventsourcesnapshot" in text
    block = _event_source_state_block()
    assert "steps.parse.outputs.command == 'eventsourcestate'" in block


def test_event_source_state_reads_exact_runtime_truth_without_mutation() -> None:
    block = _event_source_state_block()

    assert "/Volumes/Crypto-504/Crypto-Signal" in block
    assert 'EVENT_DB="$DEV/runtime/events/event_source.sqlite3"' in block
    assert 'WRAPPER="$ROOT/ssd-clock-wrapper.py"' in block
    assert "SSD_SUPERVISOR_COUNT=" in block
    assert "ps -axo pid=,comm=,args=" in block
    assert '($2 == "bash" || $2 == "/bin/bash")' in block
    assert "SSD_CLOCK_WRAPPER_SHA256=" in block
    assert "SSD_CLOCK_WRAPPER_CONTENT_BEGIN" in block
    assert "read_event_source_runtime_truth" in block
    assert "EVENT_SOURCE_RUNTIME_STATUS=" in block
    assert "EVENT_SOURCE_ONLINE_STATUS=" in block
    assert "EVENT_SOURCE_PROCESS_STATUS=" in block
    assert "EVENT_SOURCE_COVERAGE_CLAIM=" in block
    assert "EVENT_SOURCE_REAL_CAPITAL=" in block
    assert "EVENT_SOURCE_STATE_BYTE_STABLE_PASS=YES" in block
    assert "EVENT_SOURCE_STATE_READONLY_PASS=YES" in block


def test_event_source_state_has_no_runtime_mutation_surface() -> None:
    block = _event_source_state_block()
    forbidden = (
        "run_event_source_snapshot.py",
        'git -C "$DEV" merge',
        'git -C "$DEV" checkout',
        'git -C "$PRODUCT" checkout',
        "launchctl kickstart",
        "launchctl bootstrap",
        "kill ",
        "rm -",
        "cp ",
        "mv ",
        "touch ",
        "mkdir ",
        "sqlite3 ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
    )

    for token in forbidden:
        assert token not in block



def test_event_source_commands_checkout_and_verify_exact_workflow_sha() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    checkout_start = text.index(
        "      - name: CHECKOUT EXACT EVENT SOURCE COMMAND SOURCE"
    )
    verify_start = text.index(
        "      - name: VERIFY EXACT EVENT SOURCE COMMAND SOURCE",
        checkout_start,
    )
    status_start = text.index("      - name: STATUS", verify_start)
    checkout = text[checkout_start:verify_start]
    verify = text[verify_start:status_start]

    assert "uses: actions/checkout@v4" in checkout
    for command in (
        "eventsourcestate",
        "eventsourcesnapshot",
        "blsprobe",
        "fredprobe",
    ):
        assert f"steps.parse.outputs.command == '{command}'" in checkout
        assert f"steps.parse.outputs.command == '{command}'" in verify

    assert "ref: ${{ github.sha }}" in checkout
    assert "clean: true" in checkout
    assert "fetch-depth: 1" in checkout
    assert 'git -C "$GITHUB_WORKSPACE" rev-parse HEAD' in verify
    assert 'test "$WORKSPACE_HEAD" = "$GITHUB_SHA"' in verify
    assert "EVENT_SOURCE_EXACT_WORKFLOW_SOURCE_PASS=YES" in verify
    assert "/Volumes/Crypto-504/Crypto-Signal/Development" not in checkout
    assert "/Volumes/Crypto-504/Crypto-Signal/Product" not in checkout
    assert "/Volumes/Crypto-504/Crypto-Signal/Development" not in verify
    assert "/Volumes/Crypto-504/Crypto-Signal/Product" not in verify
