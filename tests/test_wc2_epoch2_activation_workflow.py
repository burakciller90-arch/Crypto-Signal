from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _block(name: str, next_name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index(f"      - name: {name}")
    end = text.index(f"      - name: {next_name}", start)
    return text[start:end]


def test_epoch2_activation_command_is_allowlisted_and_exact_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "wc2epoch2activate" in text
    checkout = _block(
        "CHECKOUT EXACT WC2 POLICY COMMAND SOURCE",
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
    )
    verify = _block(
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
        "STATUS",
    )
    assert "steps.parse.outputs.command == 'wc2epoch2activate'" in checkout
    assert "steps.parse.outputs.command == 'wc2epoch2activate'" in verify
    assert "uses: actions/checkout@v4" in checkout
    assert "ref: ${{ github.sha }}" in checkout
    assert 'test "$WORKSPACE_HEAD" = "$GITHUB_SHA"' in verify


def test_epoch2_activation_command_is_bounded_and_epoch1_byte_stable() -> None:
    block = _block("WC2 EPOCH2 ACTIVATE", "WC2 STATE")

    assert 'EPOCH1="$DEV/runtime/paper/paper_fund.sqlite3"' in block
    assert 'EPOCH2="$DEV/runtime/paper/paper_fund_epoch2.sqlite3"' in block
    assert 'ACTIVATE="$GITHUB_WORKSPACE/ops/activate_wc2_epoch2.py"' in block
    assert 'test -f "$EPOCH1"' in block
    assert 'test "$epoch1_before" = "$epoch1_after"' in block
    assert "WC2_EPOCH2_ACTIVATION_BOUNDED_PASS=YES" in block
    assert "WC2_EPOCH1_BYTE_STABLE_PASS=YES" in block
    assert "WC2_EPOCH2_READONLY_REPLAY_PASS=YES" in block
    assert "REAL_CAPITAL=0" in block

    forbidden = (
        "launchctl",
        "curl ",
        "git checkout",
        "git merge",
        "git fetch",
        "productdeploy",
        "place_order",
        "api_key",
        "credential",
        "leverage=",
        "martingale=",
    )
    for token in forbidden:
        assert token not in block
