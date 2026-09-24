from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _block(name: str, next_name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index(f"      - name: {name}")
    end = text.index(f"      - name: {next_name}", start)
    return text[start:end]


def test_execution_runtime_commands_are_allowlisted_and_exact_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for command in (
        "wc2executionruntimeregister",
        "wc2executiononce",
        "wc2executionstate",
    ):
        assert command in text

    checkout = _block(
        "CHECKOUT EXACT WC2 POLICY COMMAND SOURCE",
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
    )
    verify = _block(
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
        "CHECKOUT EXACT GALACTECH PREVIEW SOURCE",
    )
    for command in (
        "wc2executionruntimeregister",
        "wc2executiononce",
        "wc2executionstate",
    ):
        assert f"steps.parse.outputs.command == '{command}'" in checkout
        assert f"steps.parse.outputs.command == '{command}'" in verify
    assert "ref: ${{ github.sha }}" in checkout
    assert 'test "$WORKSPACE_HEAD" = "$GITHUB_SHA"' in verify


def test_execution_runtime_registration_is_forward_only_and_bounded() -> None:
    block = _block(
        "WC2 PAPER EXECUTION RUNTIME REGISTER",
        "WC2 PAPER EXECUTION ONCE",
    )
    for token in (
        'EXECUTION_PROTOCOL_DB="$DEV/runtime/wc2/wc2_paper_execution.wc2-paper-execution-protocol.sqlite3"',
        'RUNTIME_DB="$DEV/runtime/wc2/wc2_paper_execution.wc2-paper-execution-runtime.sqlite3"',
        'REGISTER="$GITHUB_WORKSPACE/ops/register_wc2_paper_execution_runtime.py"',
        '--execution-protocol-db "$EXECUTION_PROTOCOL_DB"',
        '--runtime-db "$RUNTIME_DB"',
        'test "$protocol_before" = "$protocol_after"',
        "WC2_EXECUTION_RUNTIME_FORWARD_ONLY_PASS=YES",
        "WC2_EXECUTION_RUNTIME_HISTORICAL_BACKFILL=NO",
        "WC2_EXECUTION_RUNTIME_PRODUCTION_AUTHORITY=NO",
        "WC2_EXECUTION_RUNTIME_REGISTER_BOUNDED_PASS=YES",
        "REAL_CAPITAL=0",
        "PRAGMA quick_check",
    ):
        assert token in block

    for forbidden in (
        "launchctl ",
        "bootstrap ",
        "kickstart ",
        "bootout ",
        "productdeploy",
        "place_order",
        "submit_order",
        "api_key",
        "api_secret",
        "credential",
        "leverage",
        "martingale",
        "curl ",
    ):
        assert forbidden not in block


def test_execution_once_is_exact_main_bounded_and_preserves_canonical_state() -> None:
    block = _block(
        "WC2 PAPER EXECUTION ONCE",
        "WC2 PAPER EXECUTION STATE",
    )
    for token in (
        'DEV_HEAD="$(git -C "$DEV" rev-parse HEAD)"',
        'test "$DEV_HEAD" = "$GITHUB_SHA"',
        'SIGNAL="$RUNTIME/ledger/live_signal_ledger.sqlite3"',
        'DECISION="$RUNTIME/decision/decision_evidence.sqlite3"',
        'COHORT="$RUNTIME/wc2/wc2_untouched_forward.sqlite3"',
        'EPOCH2="$RUNTIME/paper/paper_fund_epoch2.sqlite3"',
        'EXECUTION_PROTOCOL="$RUNTIME/wc2/wc2_paper_execution.wc2-paper-execution-protocol.sqlite3"',
        'EXECUTION_RUNTIME="$RUNTIME/wc2/wc2_paper_execution.wc2-paper-execution-runtime.sqlite3"',
        'EXECUTION_JOURNAL="$RUNTIME/wc2/wc2_paper_execution.wc2-paper-execution.sqlite3"',
        'CANDLE="$RUNTIME/data/live_base_15m_cache.sqlite3"',
        'VENUE="$RUNTIME/paper/paper_fund.sqlite3"',
        'CYCLE="$GITHUB_WORKSPACE/ops/run_wc2_paper_execution_cycle.py"',
        '--execution-protocol "$EXECUTION_PROTOCOL"',
        '--runtime-activation "$EXECUTION_RUNTIME"',
        '--execution-journal "$EXECUTION_JOURNAL"',
        '--venue-rules "$VENUE"',
        'test "$protocol_before" = "$protocol_after"',
        'test "$runtime_before" = "$runtime_after"',
        'test "$epoch2_before" = "$epoch2_after"',
        "WC2_EXECUTION_CYCLE_HISTORICAL_BACKFILL=NO",
        "WC2_EXECUTION_CYCLE_REAL_ORDER_AUTHORITY=NO",
        "WC2_EXECUTION_BOUNDED_ONE_SHOT_PASS=YES",
        "WC2_EXECUTION_NO_SERVICE_MUTATION_PASS=YES",
        "REAL_CAPITAL=0",
    ):
        assert token in block

    for forbidden in (
        "launchctl ",
        "bootstrap ",
        "kickstart ",
        "bootout ",
        "rsync ",
        "productdeploy",
        "place_order",
        "submit_order",
        "api_key",
        "api_secret",
        "credential",
        "leverage",
        "martingale",
        "curl ",
    ):
        assert forbidden not in block


def test_execution_state_is_stable_read_only_and_checks_exact_lineage() -> None:
    block = _block(
        "WC2 PAPER EXECUTION STATE",
        "WC2 STATE",
    )
    for token in (
        "wc2_paper_execution.wc2-paper-execution-protocol.sqlite3",
        "wc2_paper_execution.wc2-paper-execution-runtime.sqlite3",
        "wc2_paper_execution.wc2-paper-execution.sqlite3",
        "paper_fund_epoch2.sqlite3",
        "tempfile.mkdtemp",
        "shutil.copy2",
        "snapshot(source)",
        "PRAGMA quick_check",
        "WC2_EXECUTION_RUNTIME_PROTOCOL_BINDING_MISMATCH",
        "runtime_activation_identity",
        "WC2_EXECUTION_JOURNAL_RUNTIME_BINDING_MISMATCH",
        "WC2_EXECUTION_JOURNAL_PROTOCOL_BINDING_MISMATCH",
        "WC2_EXECUTION_JOURNAL_EXECUTION_ECONOMICS_MISSING",
        "WC2_EXECUTION_STATE_SOURCE_BYTE_STABLE_PASS=YES",
        "WC2_EXECUTION_STATE_READONLY_PASS=YES",
        "REAL_CAPITAL=0",
    ):
        assert token in block

    lowered = block.lower()
    for forbidden in (
        "win_rate",
        "profit_factor",
        "sharpe",
        "sortino",
        "expectancy",
        "edge_supported",
        "calibrated_probability",
        "launchctl",
        "productdeploy",
        "place_order",
    ):
        assert forbidden not in lowered
