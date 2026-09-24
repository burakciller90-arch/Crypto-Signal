from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _block(name: str, next_name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index(f"      - name: {name}")
    end = text.index(f"      - name: {next_name}", start)
    return text[start:end]


def test_protocol_registration_is_allowlisted_and_exact_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "wc2protocolregister" in text

    checkout = _block(
        "CHECKOUT EXACT WC2 POLICY COMMAND SOURCE",
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
    )
    verify = _block(
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
        "STATUS",
    )
    assert "steps.parse.outputs.command == 'wc2protocolregister'" in checkout
    assert "steps.parse.outputs.command == 'wc2protocolregister'" in verify
    assert "ref: ${{ github.sha }}" in checkout
    assert 'test "$WORKSPACE_HEAD" = "$GITHUB_SHA"' in verify


def test_protocol_registration_mutates_only_protocol_db() -> None:
    block = _block(
        "WC2 COLLECTION PROTOCOL REGISTER",
        "WC2 STATE",
    )
    assert 'POLICY_DB="$DEV/runtime/wc2/wc2_forward_policy.sqlite3"' in block
    assert 'EPOCH2_DB="$DEV/runtime/paper/paper_fund_epoch2.sqlite3"' in block
    assert (
        'PROTOCOL_DB="$DEV/runtime/wc2/'
        'wc2_collection_protocol.wc2-collection-protocol.sqlite3"'
        in block
    )
    assert (
        'REGISTER="$GITHUB_WORKSPACE/ops/'
        'register_wc2_collection_protocol.py"'
        in block
    )
    assert '--policy-db "$POLICY_DB"' in block
    assert '--epoch2-db "$EPOCH2_DB"' in block
    assert '--protocol-db "$PROTOCOL_DB"' in block
    assert 'test "$policy_before" = "$policy_after"' in block
    assert 'test "$epoch2_before" = "$epoch2_after"' in block
    assert "WC2_PROTOCOL_REGISTER_BOUNDED_PASS=YES" in block
    assert "WC2_PROTOCOL_HISTORICAL_BACKFILL=NO" in block
    assert 'echo "REAL_CAPITAL=0"' in block

    for forbidden in (
        "launchctl",
        "curl ",
        'git -C "$DEV" checkout',
        'git -C "$DEV" merge',
        "productdeploy",
        "place_order",
        "api_key",
        "credential",
        "leverage",
        "martingale",
    ):
        assert forbidden not in block


def test_wc2_state_exposes_protocol_and_uses_its_collection_boundary() -> None:
    block = _block("WC2 STATE", "BLS SOURCE PROBE")

    assert "wc2_collection_protocol.wc2-collection-protocol.sqlite3" in block
    assert "WC2_PROTOCOL_STATUS=NOT_REGISTERED" in block
    assert "WC2_PROTOCOL_STATUS=REGISTERED" in block
    assert "WC2_PROTOCOL_POLICY_BINDING_MISMATCH" in block
    assert "collection_start_ms = int(row[4])" in block
