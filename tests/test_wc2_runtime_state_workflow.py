from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _block(name: str, next_name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index(f"      - name: {name}")
    end = text.index(f"      - name: {next_name}", start)
    return text[start:end]


def test_wc2_state_is_allowlisted_and_uses_exact_workflow_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "wc2policyregister|wc2protocolregister|wc2executionprotocolregister|wc2collectonce|wc2state|services|" in text

    checkout = _block(
        "CHECKOUT EXACT WC2 POLICY COMMAND SOURCE",
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
    )
    verify = _block(
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
        "STATUS",
    )
    for command in ("wc2policyregister", "wc2protocolregister", "wc2executionprotocolregister", "wc2state"):
        assert f"steps.parse.outputs.command == '{command}'" in checkout
        assert f"steps.parse.outputs.command == '{command}'" in verify

    assert "uses: actions/checkout@v4" in checkout
    assert "ref: ${{ github.sha }}" in checkout
    assert "clean: true" in checkout
    assert "fetch-depth: 1" in checkout
    assert 'test "$WORKSPACE_HEAD" = "$GITHUB_SHA"' in verify
    assert "WC2_POLICY_EXACT_WORKFLOW_SOURCE_PASS=YES" in verify


def test_wc2_state_reads_only_ephemeral_stable_copies() -> None:
    block = _block("WC2 STATE", "BLS SOURCE PROBE")

    for path in (
        'runtime / "wc2" / "wc2_forward_policy.sqlite3"',
        '"wc2_collection_protocol.wc2-collection-protocol.sqlite3"',
        '"wc2_paper_execution.wc2-paper-execution-protocol.sqlite3"',
        'runtime / "decision" / "decision_evidence.sqlite3"',
        'runtime / "r25" / "r25.shadow-cycle.sqlite3"',
        'runtime / "paper" / "paper_fund_epoch2.sqlite3"',
        'runtime / "wc2" / "wc2_untouched_forward.sqlite3"',
    ):
        assert path in block

    assert "tempfile.mkdtemp" in block
    assert "shutil.copy2" in block
    assert "source_snapshot(source)" in block
    assert "SELECT regime, COUNT(*)" in block
    assert "GROUP BY regime" in block
    assert "ORDER BY regime" in block
    assert "SELECT forecast_identity, regime, issued_at_ms" in block
    assert "WC2_STATE_SOURCE_BYTE_STABLE_PASS=YES" in block
    assert "WC2_STATE_READONLY_PASS=YES" in block
    assert 'print("REAL_CAPITAL=0")' in block

    forbidden = (
        "WC2PolicyStore(",
        "WC2CohortJournal(",
        ".initialize()",
        'git -C "$DEV" checkout',
        'git -C "$PRODUCT" checkout',
        "git fetch",
        "launchctl",
        "kickstart",
        "bootstrap",
        "kill ",
        "productdeploy",
        "place_order",
        "api_key",
        "credential",
        "leverage",
        "martingale",
    )
    for token in forbidden:
        assert token not in block


def test_wc2_state_reports_all_lineage_layers_without_performance_claims() -> None:
    block = _block("WC2 STATE", "BLS SOURCE PROBE")

    for marker in (
        "WC2_POLICY_STATUS=",
        "WC2_PROTOCOL_STATUS=",
        "WC2_EXECUTION_PROTOCOL_STATUS=",
        "WC2_DECISION_EVIDENCE",
        "WC2_SHADOW_CYCLE",
        "WC2_EPOCH2_R22",
        "WC2_COHORT_STATUS=",
        "WC2_COHORT_REGIMES",
        "WC2_COHORT_LATEST_FORECAST",
        "post_execution_start_executions",
    ):
        assert marker in block

    for forbidden in (
        "win_rate",
        "profit_factor",
        "sharpe",
        "sortino",
        "expectancy",
        "edge_supported",
        "calibrated_probability",
    ):
        assert forbidden not in block.lower()
