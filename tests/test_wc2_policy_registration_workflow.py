from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _block() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: WC2 POLICY REGISTER")
    end = text.index("      - name: SERVICES", start)
    return text[start:end]


def test_wc2_policy_register_is_explicitly_allowlisted_and_exact_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "wc2policyregister" in text

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

    assert "steps.parse.outputs.command == 'wc2policyregister'" in checkout
    assert "steps.parse.outputs.command == 'wc2policyregister'" in verify
    assert "ref: ${{ github.sha }}" in checkout
    assert 'test "$WORKSPACE_HEAD" = "$GITHUB_SHA"' in verify


def test_wc2_policy_register_is_bounded_to_policy_db_only() -> None:
    block = _block()

    assert 'POLICY_DB="$DEV/runtime/wc2/wc2_forward_policy.sqlite3"' in block
    assert 'REGISTER="$GITHUB_WORKSPACE/ops/register_wc2_forward_policy.py"' in block
    assert 'PYTHONPATH="$GITHUB_WORKSPACE/src"' in block
    assert '--db "$POLICY_DB"' in block
    assert "WC2_POLICY_REGISTER_BOUNDED_PASS=YES" in block
    assert 'echo "REAL_CAPITAL=0"' in block

    forbidden = (
        'git -C "$DEV" checkout',
        'git -C "$DEV" merge',
        'git -C "$PRODUCT" checkout',
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



def test_wc2_policy_register_does_not_run_event_source_probes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    fred_start = text.index("      - name: FRED CALENDAR PROBE")
    register_start = text.index("      - name: WC2 POLICY REGISTER", fred_start)
    fred_block = text[fred_start:register_start]

    bls_start = text.index("      - name: BLS SOURCE PROBE")
    bls_block = text[bls_start:fred_start]

    assert "wc2policyregister" not in fred_block
    assert "wc2policyregister" not in bls_block
