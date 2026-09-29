from __future__ import annotations

import argparse
from pathlib import Path

from ops.run_dashboard import resolve_runtime_paths


def _args(ledger: Path, **overrides: Path | None) -> argparse.Namespace:
    values: dict[str, object] = {
        "ledger": ledger,
        "decision_evidence": None,
        "epoch2_ledger": None,
        "shadow_intent_journal": None,
        "shadow_cycle_manifest": None,
        "runtime_replay_observation": None,
        "market_tape": None,
        "market_tape_collector_runtime": None,
        "cold_archive": None,
        "provider_divergence": None,
        "event_source_runtime": None,
        "wc2_cohort": None,
        "stream_ledger": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_dashboard_derives_all_world_class_runtime_paths_from_live_ledger() -> None:
    ledger = Path(
        "/Volumes/Crypto-504/Crypto-Signal/Development/"
        "runtime/ledger/live_signal_ledger.sqlite3"
    )

    paths = resolve_runtime_paths(_args(ledger))

    runtime = ledger.parent.parent
    assert paths == {
        "decision_evidence_path": (
            runtime / "decision" / "decision_evidence.sqlite3"
        ),
        "epoch2_ledger_path": (
            runtime / "paper" / "paper_fund_epoch2.sqlite3"
        ),
        "shadow_intent_journal_path": (
            runtime / "r25" / "r25.shadow-intent.sqlite3"
        ),
        "shadow_cycle_manifest_path": (
            runtime / "r25" / "r25.shadow-cycle.sqlite3"
        ),
        "runtime_replay_observation_path": (
            runtime / "r25" / "r25.shadow-replay.sqlite3"
        ),
        "market_tape_path": (
            runtime / "market_tape" / "market_tape.sqlite3"
        ),
        "market_tape_collector_runtime_path": (
            runtime / "market_tape" / "collector_runtime.sqlite3"
        ),
        "cold_archive_path": runtime / "market_tape" / "cold",
        "provider_divergence_path": (
            runtime / "data" / "provider_divergence.sqlite3"
        ),
        "event_source_runtime_path": (
            runtime / "events" / "event_source.sqlite3"
        ),
        "wc2_cohort_path": (
            runtime / "wc2" / "wc2_untouched_forward.sqlite3"
        ),
        "stream_ledger_path": (
            runtime / "stream" / "intelligence_stream.sqlite3"
        ),
        "options_surface_path": (
            runtime / "market_tape" / "options_surface.sqlite3"
        ),
        "onchain_capital_flow_path": (
            runtime / "onchain" / "onchain_capital_flow.sqlite3"
        ),
        "onchain_source_contract_path": (
            runtime / "onchain" / "source_contract.sqlite3"
        ),
    }


def test_dashboard_runtime_path_overrides_are_exact_and_not_rebased(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "runtime" / "ledger" / "live_signal_ledger.sqlite3"
    explicit = {
        "decision_evidence": tmp_path / "x" / "decision.sqlite3",
        "epoch2_ledger": tmp_path / "x" / "epoch2.sqlite3",
        "shadow_intent_journal": tmp_path / "x" / "a.shadow-intent.sqlite3",
        "shadow_cycle_manifest": tmp_path / "x" / "b.shadow-cycle.sqlite3",
        "runtime_replay_observation": tmp_path / "x" / "c.shadow-replay.sqlite3",
        "market_tape": tmp_path / "x" / "market.sqlite3",
        "market_tape_collector_runtime": (
            tmp_path / "x" / "collector.sqlite3"
        ),
        "cold_archive": tmp_path / "x" / "cold",
        "provider_divergence": tmp_path / "x" / "provider.sqlite3",
        "event_source_runtime": tmp_path / "x" / "event-source.sqlite3",
        "wc2_cohort": tmp_path / "x" / "wc2.sqlite3",
        "stream_ledger": tmp_path / "x" / "stream.sqlite3",
    }

    paths = resolve_runtime_paths(_args(ledger, **explicit))

    assert paths == {
        "decision_evidence_path": explicit["decision_evidence"],
        "epoch2_ledger_path": explicit["epoch2_ledger"],
        "shadow_intent_journal_path": explicit["shadow_intent_journal"],
        "shadow_cycle_manifest_path": explicit["shadow_cycle_manifest"],
        "runtime_replay_observation_path": explicit[
            "runtime_replay_observation"
        ],
        "market_tape_path": explicit["market_tape"],
        "market_tape_collector_runtime_path": explicit[
            "market_tape_collector_runtime"
        ],
        "cold_archive_path": explicit["cold_archive"],
        "provider_divergence_path": explicit["provider_divergence"],
        "event_source_runtime_path": explicit["event_source_runtime"],
        "wc2_cohort_path": explicit["wc2_cohort"],
        "stream_ledger_path": explicit["stream_ledger"],
        "options_surface_path": (
            ledger.parent.parent / "market_tape" / "options_surface.sqlite3"
        ),
        "onchain_capital_flow_path": (
            ledger.parent.parent / "onchain" / "onchain_capital_flow.sqlite3"
        ),
        "onchain_source_contract_path": (
            ledger.parent.parent / "onchain" / "source_contract.sqlite3"
        ),
    }


def test_productdeploy_contract_is_exact_main_and_stream_root_with_fallback() -> None:
    workflow = Path(
        ".github/workflows/crypto-mac-command.yml"
    ).read_text(encoding="utf-8")

    product_block = workflow[
        workflow.index("- name: PRODUCT DEPLOY"):
        workflow.index("- name: PAPER INSPECT")
    ]

    assert 'git -C "$REPO" merge --ff-only "$TARGET"' in product_block
    assert "timeout-minutes: 60" in workflow
    assert 'git -C "$PRODUCT"' in product_block
    assert 'fetch --no-tags origin main' in product_block
    assert 'rev-parse origin/main' in product_block
    assert 'data-ui-version="crypto-signal-stream-v1-s14"' in product_block
    assert 'GALACTECH · INTELLIGENCE STREAM' in product_block
    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in product_block
    assert 'data-ui-version="galactech-command-center-v1"' in product_block
    assert "/stream-preview" in product_block
    assert 'data.get("product_root") == "stream"' in product_block
    assert 'data.get("stream_root_active") is True' in product_block
    assert "/api/r25/operational-truth" in product_block
    assert "STREAM_ROOT_CUTOVER_LIVE_PASS=YES" in product_block
    assert "GALACTECH_FALLBACK_LIVE_PASS=YES" in product_block
    assert "WC0_RUNTIME_TOPOLOGY_SQLITE_PASS=YES" in product_block
    assert "WC0_CONTINUITY_PAUSE_PRESERVED=YES" in product_block
    assert "DASHBOARD_RESTART_MODE=supervisor-managed" in product_block
    assert "DASHBOARD_SUPERVISOR_RESPAWN_PID=" in product_block
    assert "DASHBOARD_SUPERVISOR_RESPAWN_TIMEOUT=YES" in product_block
    assert "DASHBOARD_OLD_PIDS=" in product_block
    assert '/usr/bin/pgrep -f "^$PRODUCT/.venv/bin/python $PRODUCT/ops/run_dashboard.py( |$)"' in product_block
    assert "ps -axo pid=,command=" not in product_block
    assert "DASHBOARD_OLD_PID_FORCE_KILL=" in product_block
    assert 'kill -KILL "$pid"' in product_block
    assert "DASHBOARD_RESTART_MODE=direct-no-supervisor" in product_block
    assert "DASHBOARD_DIRECT_START_PID=" in product_block
    assert "DIRECT_DASHBOARD_RESTART_TIMEOUT=YES" in product_block
    assert "fetch_live_json() {" in product_block
    assert "PRODUCT_LIVE_API_READY" in product_block
    assert "PRODUCT_LIVE_API_TIMEOUT" in product_block
    assert 'curl -fsS --max-time 15 "$url" -o "$tmp"' in product_block
    assert "for i in {1..8}; do" in product_block
    assert 'grep -F "$PRODUCT/ops/run_dashboard.py"' in product_block
    assert "direct-supervisor-contract" not in product_block
    assert "OLD_DASH_EXIT_TIMEOUT=YES" not in product_block
    assert "REAL_CAPITAL" not in product_block or "real_capital" in product_block


def test_visualsnapshot_command_uses_accepted_cdp_and_uploads_artifact() -> None:
    workflow = Path(
        ".github/workflows/crypto-mac-command.yml"
    ).read_text(encoding="utf-8")

    assert "dashboardstart504|visualcleanup|visualsnapshot|galactechpreview" in workflow
    assert "- name: GALACTECH VISUAL SNAPSHOT UID504" in workflow
    assert "steps.parse.outputs.command == 'visualsnapshot'" in workflow
    assert "- name: CHECKOUT EXACT VISUAL SNAPSHOT SOURCE" in workflow
    assert "- name: VERIFY EXACT VISUAL SNAPSHOT SOURCE" in workflow
    assert 'ref: ${{ github.sha }}' in workflow
    assert "VISUAL_SNAPSHOT_EXACT_SOURCE_PASS=YES" in workflow
    assert 'test -f "$GITHUB_WORKSPACE/ops/capture_chromium_viewport.py"' in workflow
    assert "/usr/sbin/screencapture -x -l" in workflow
    assert "BROWSER_CAPTURE_BACKEND=CHROMIUM_CDP" in workflow
    assert "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" in workflow
    assert "/Applications/Chromium.app/Contents/MacOS/Chromium" in workflow
    assert '"$GITHUB_WORKSPACE/ops/capture_chromium_viewport.py"' in workflow
    assert '--output "$OUT/desktop.png"' in workflow
    assert '--metrics-out "$OUT/desktop.metrics.json"' in workflow
    assert "--width 1440" in workflow
    assert "--height 950" in workflow
    assert '--output "$OUT/mobile.png"' in workflow
    assert '--metrics-out "$OUT/mobile.metrics.json"' in workflow
    assert "--width 430" in workflow
    assert "--height 860" in workflow
    assert "--mobile" in workflow
    assert "--require-no-horizontal-overflow" in workflow
    assert 'tell application "Safari"' in workflow
    assert "capture_window desktop 40 50 1480 1000" in workflow
    assert "capture_window mobile 80 60 510 920" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "GALACTECH_VISUAL_SNAPSHOT_PASS=YES" in workflow
    assert "VISUAL_SNAPSHOT_HEALTH_READY" in workflow
    assert 'curl -fsS --max-time 8 "$URL/api/health"' in workflow
    assert "for i in {1..4}; do" in workflow
    assert 'assert data.get("read_only") is True' in workflow
    assert 'assert data.get("real_capital") == 0' in workflow
    assert "VISUAL_SNAPSHOT_HEALTH_UNAVAILABLE=YES" in workflow
    assert "HEALTH_STATUS=UNAVAILABLE_CAPTURE_CONTINUES" in workflow
    assert 'echo "READ_ONLY_CAPTURE=YES"' in workflow


def test_galactech_preview_contract_is_exact_main_read_only() -> None:
    workflow = Path(
        ".github/workflows/crypto-mac-command.yml"
    ).read_text(encoding="utf-8")

    assert "galactechpreview" in workflow
    assert "- name: CHECKOUT EXACT GALACTECH PREVIEW SOURCE" in workflow
    assert 'ref: ${{ github.sha }}' in workflow
    assert "GALACTECH_PREVIEW_EXACT_SOURCE_PASS=YES" in workflow
    assert "- name: GALACTECH EXACT MAIN PREVIEW" in workflow
    assert "PORT=48705" in workflow
    assert 'export PYTHONPATH="$GITHUB_WORKSPACE/src"' in workflow
    assert '"$GITHUB_WORKSPACE/ops/run_dashboard.py"' in workflow
    assert 'data-ui-version="galactech-v2-intelligence-first-tr"' in workflow
    assert "GALACTECH_PREVIEW_READ_ONLY_PASS=YES" in workflow
    assert 'test "$(curl -sS -o /dev/null -w \'%{http_code}\' -X POST --max-time 5 "$URL/")" = "405"' in workflow
    assert "REAL_CAPITAL=0" in workflow
