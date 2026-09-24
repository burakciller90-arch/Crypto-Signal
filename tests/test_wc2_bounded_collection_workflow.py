from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _block(name: str, next_name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index(f"      - name: {name}")
    end = text.index(f"      - name: {next_name}", start)
    return text[start:end]


def test_wc2_collect_once_is_explicitly_allowlisted_and_exact_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "wc2protocolregister|wc2collectonce|wc2state|" in text

    checkout = _block(
        "CHECKOUT EXACT WC2 POLICY COMMAND SOURCE",
        "VERIFY EXACT WC2 POLICY COMMAND SOURCE",
    )
    assert "steps.parse.outputs.command == 'wc2collectonce'" in checkout
    assert "ref: ${{ github.sha }}" in checkout
    assert "clean: true" in checkout

    collect = _block("WC2 COLLECTION ONCE", "WC2 STATE")
    assert 'test "$DEV_HEAD" = "$GITHUB_SHA"' in collect


def test_wc2_collect_once_uses_only_canonical_ssd_runtime_paths() -> None:
    block = _block("WC2 COLLECTION ONCE", "WC2 STATE")

    for token in (
        'ROOT="/Volumes/Crypto-504/Crypto-Signal"',
        'DEV="$ROOT/Development"',
        'LEDGER="$RUNTIME/ledger/live_signal_ledger.sqlite3"',
        'CANDLE="$RUNTIME/data/live_base_15m_cache.sqlite3"',
        'POLICY="$RUNTIME/wc2/wc2_forward_policy.sqlite3"',
        'EPOCH2="$RUNTIME/paper/paper_fund_epoch2.sqlite3"',
        'PROTOCOL="$RUNTIME/wc2/wc2_collection_protocol.wc2-collection-protocol.sqlite3"',
        'PREPARED="$RUNTIME/wc2/wc2.wc2-prepared.sqlite3"',
        'DECISION="$RUNTIME/decision/decision_evidence.sqlite3"',
        'COHORT="$RUNTIME/wc2/wc2_untouched_forward.sqlite3"',
        'SHADOW_INTENT="$RUNTIME/wc2/wc2.shadow-intent.sqlite3"',
        'SHADOW_CYCLE="$RUNTIME/wc2/wc2.shadow-cycle.sqlite3"',
    ):
        assert token in block

    assert "/Users/crypto-signal-agent/Crypto-Signal" not in block
    assert 'test "$DEV_HEAD" = "$GITHUB_SHA"' in block


def test_wc2_collect_once_is_bounded_and_non_service_mutating() -> None:
    block = _block("WC2 COLLECTION ONCE", "WC2 STATE")

    for token in (
        "--wc2-enabled",
        '--wc2-policy "$POLICY"',
        '--wc2-epoch2 "$EPOCH2"',
        '--wc2-collection-protocol "$PROTOCOL"',
        '--wc2-prepared "$PREPARED"',
        '--wc2-decision-evidence "$DECISION"',
        '--wc2-cohort "$COHORT"',
        '--wc2-shadow-intent "$SHADOW_INTENT"',
        '--wc2-shadow-cycle "$SHADOW_CYCLE"',
        "WC2_COLLECTION_BOUNDED_ONE_SHOT_PASS=YES",
        "WC2_COLLECTION_NO_SERVICE_MUTATION_PASS=YES",
        "WC2_COLLECTION_HISTORICAL_BACKFILL=NO",
        "REAL_CAPITAL=0",
    ):
        assert token in block

    for forbidden in (
        "launchctl ",
        "bootstrap ",
        "kickstart ",
        "bootout ",
        "rsync ",
        'git -C "$DEV" checkout',
        'git -C "$PRODUCT"',
        "productdeploy",
        "place_order",
        "api_key",
        "credential",
        "leverage",
        "martingale",
    ):
        assert forbidden not in block


def test_wc2_collect_once_freezes_preregistered_inputs_byte_stably() -> None:
    block = _block("WC2 COLLECTION ONCE", "WC2 STATE")

    for token in (
        "policy_before=",
        "epoch2_before=",
        "protocol_before=",
        'test "$policy_before" = "$policy_after"',
        'test "$epoch2_before" = "$epoch2_after"',
        'test "$protocol_before" = "$protocol_after"',
        "PRAGMA quick_check",
        "HISTORICAL_FORECAST_BACKFILL=NO REAL_CAPITAL=0",
    ):
        assert token in block
