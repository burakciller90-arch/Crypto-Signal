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
        "cold_archive": None,
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
        "cold_archive_path": runtime / "market_tape" / "cold",
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
        "cold_archive": tmp_path / "x" / "cold",
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
        "cold_archive_path": explicit["cold_archive"],
    }


def test_productdeploy_contract_is_exact_main_and_current_galactech() -> None:
    workflow = Path(
        ".github/workflows/crypto-mac-command.yml"
    ).read_text(encoding="utf-8")

    product_block = workflow[
        workflow.index("- name: PRODUCT DEPLOY"):
        workflow.index("- name: PAPER INSPECT")
    ]

    assert 'git -C "$REPO" merge --ff-only "$TARGET"' in product_block
    assert 'git -C "$PRODUCT"' in product_block
    assert 'fetch --no-tags origin main' in product_block
    assert 'rev-parse origin/main' in product_block
    assert 'data-ui-version="galactech-v1.1-polish"' in product_block
    assert 'data-ui-version="galactech-command-center-v1"' in product_block
    assert "/api/r25/operational-truth" in product_block
    assert "GALACTECH_ROOT_CUTOVER_LIVE_PASS=YES" in product_block
    assert "WC0_RUNTIME_TOPOLOGY_SQLITE_PASS=YES" in product_block
    assert "WC0_CONTINUITY_PAUSE_PRESERVED=YES" in product_block
    assert "OLD_DASH_EXITED=" in product_block
    assert "OLD_DASH_EXIT_TIMEOUT=YES" in product_block
    assert 'grep -F "$PRODUCT/ops/run_dashboard.py"' in product_block
    assert "REAL_CAPITAL" not in product_block or "real_capital" in product_block
