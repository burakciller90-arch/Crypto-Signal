from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _block(name: str, next_name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index(f"      - name: {name}")
    end = text.index(f"      - name: {next_name}", start)
    return text[start:end]


def test_execution_protocol_registration_is_allowlisted_and_exact_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "wc2executionprotocolregister" in text

    checkout = _block(
        "CHECKOUT EXACT WC2 POLICY COMMAND SOURCE",
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
    )
    verify = _block(
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
        "CHECKOUT EXACT GALACTECH PREVIEW SOURCE",
    )
    assert (
        "steps.parse.outputs.command == 'wc2executionprotocolregister'"
        in checkout
    )
    assert (
        "steps.parse.outputs.command == 'wc2executionprotocolregister'"
        in verify
    )
    assert "ref: ${{ github.sha }}" in checkout
    assert 'test "$WORKSPACE_HEAD" = "$GITHUB_SHA"' in verify


def test_execution_protocol_registration_mutates_only_new_protocol_db() -> None:
    block = _block(
        "WC2 PAPER EXECUTION PROTOCOL REGISTER",
        "WC2 STATE",
    )
    assert 'POLICY_DB="$DEV/runtime/wc2/wc2_forward_policy.sqlite3"' in block
    assert (
        'COLLECTION_PROTOCOL_DB="$DEV/runtime/wc2/'
        'wc2_collection_protocol.wc2-collection-protocol.sqlite3"'
        in block
    )
    assert 'EPOCH2_DB="$DEV/runtime/paper/paper_fund_epoch2.sqlite3"' in block
    assert (
        'EXECUTION_PROTOCOL_DB="$DEV/runtime/wc2/'
        'wc2_paper_execution.wc2-paper-execution-protocol.sqlite3"'
        in block
    )
    assert (
        'REGISTER="$GITHUB_WORKSPACE/ops/'
        'register_wc2_paper_execution_protocol.py"'
        in block
    )
    assert '--policy-db "$POLICY_DB"' in block
    assert '--collection-protocol-db "$COLLECTION_PROTOCOL_DB"' in block
    assert '--epoch2-db "$EPOCH2_DB"' in block
    assert '--execution-protocol-db "$EXECUTION_PROTOCOL_DB"' in block
    assert 'test "$policy_before" = "$policy_after"' in block
    assert 'test "$collection_before" = "$collection_after"' in block
    assert 'test "$epoch2_before" = "$epoch2_after"' in block
    assert "WC2_EXECUTION_PROTOCOL_PREREGISTERED_PASS=YES" in block
    assert "WC2_EXECUTION_PROTOCOL_HISTORICAL_BACKFILL=NO" in block
    assert "WC2_EXECUTION_PROTOCOL_REAL_ORDER_AUTHORITY=NO" in block
    assert "WC2_EXECUTION_PROTOCOL_ZERO_TRADE_ECONOMIC_CLAIM=NO" in block
    assert "WC2_EXECUTION_PROTOCOL_REGISTER_BOUNDED_PASS=YES" in block
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


def test_wc2_state_exposes_execution_protocol_lineage_and_boundary() -> None:
    block = _block("WC2 STATE", "BLS SOURCE PROBE")

    assert "wc2_paper_execution.wc2-paper-execution-protocol.sqlite3" in block
    assert "WC2_EXECUTION_PROTOCOL_STATUS=NOT_REGISTERED" in block
    assert "WC2_EXECUTION_PROTOCOL_STATUS=REGISTERED" in block
    assert "WC2_EXECUTION_PROTOCOL_POLICY_BINDING_MISMATCH" in block
    assert "WC2_EXECUTION_PROTOCOL_COLLECTION_BINDING_MISMATCH" in block
    assert "WC2_EXECUTION_PROTOCOL_EPOCH2_BINDING_MISMATCH" in block
    assert "execution_start_ms = int(row[5])" in block
    assert "simulated_cost_policy_version" in block
    assert "economic_claim_rule" in block
    assert "real_order_authority" in block
    assert "post_execution_start_executions" in block
