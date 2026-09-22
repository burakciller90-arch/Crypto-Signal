from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_r13_integrated_acceptance_is_ssd_canonical_and_read_only() -> None:
    workflow = (
        ROOT / ".github/workflows/crypto-r13-integrated-acceptance-v2.yml"
    ).read_text()

    assert "[R13] FULL VERSION INTEGRATED ACCEPTANCE V2" in workflow
    assert 'ROOT="/Volumes/Crypto-504/Crypto-Signal"' in workflow
    assert 'DEV="$ROOT/Development"' in workflow
    assert "/Users/crypto-signal-agent/Crypto-Signal/" not in workflow
    assert "r11_runtime_acceptance.py" in workflow
    assert "verify_stage10_integrated.py" in workflow
    assert "r13_integrated_acceptance.py" in workflow
    assert "R13_CANONICAL_RUNTIME_VERIFIER_PASS=YES" in workflow
    assert "R13_PRODUCT_CODE_PARITY_PASS=YES" in workflow
    assert "tests/js/test_product_freshness.js" in workflow
    assert "tests/test_paper_state.py" in workflow
    assert "tests/test_paper_execution.py" in workflow
    assert "tests/test_paper_benchmarks.py" in workflow
    assert "tests/test_alpha_factory_foundation.py" in workflow
    assert "tests/test_alpha_factory_ml_walk_forward.py" in workflow
    assert "tests/test_alpha_factory_ml_family_untouched_forward.py" in workflow
    assert "tests/test_dashboard_web.py" in workflow
    assert "tests/test_intelligence_center.py" in workflow
    assert "tests/test_meta_intelligence.py" in workflow


def test_r13_integrated_acceptance_preserves_authority_boundaries() -> None:
    workflow = (
        ROOT / ".github/workflows/crypto-r13-integrated-acceptance-v2.yml"
    ).read_text()

    assert 'health.get("real_capital") == 0' in workflow
    assert 'health.get("read_only") is True' in workflow
    assert 'intel.get("production_active_engine_count") == 0' in workflow
    assert 'intel.get("probability_status") == "not_calibrated"' in workflow
    assert "R13_REAL_CAPITAL_ZERO_PASS=YES" in workflow
    assert "R13_NO_EXCHANGE_ORDER_CREDENTIAL_AUTHORITY_PASS=YES" in workflow
    assert "R13_FULL_VERSION_INTEGRATED_ACCEPTANCE_V2=PASS" in workflow
    assert "productdeploy" not in workflow
    assert "wake_resume" not in workflow
    assert "wakeresume" not in workflow


def test_r13_integrated_acceptance_does_not_fake_human_impact_recovery() -> None:
    workflow = (
        ROOT / ".github/workflows/crypto-r13-integrated-acceptance-v2.yml"
    ).read_text()

    assert "R13_HUMAN_IMPACT_REBOOT_LOGOUT_SSD_DETACH_NOT_EXECUTED=YES" in workflow
    lowered = workflow.lower()
    assert "sudo reboot" not in lowered
    assert "shutdown -r" not in lowered
    assert "diskutil unmount" not in lowered
    assert "diskutil eject" not in lowered


def test_r13_requires_live_gift_research_and_paused_continuity() -> None:
    workflow = (
        ROOT / ".github/workflows/crypto-r13-integrated-acceptance-v2.yml"
    ).read_text()

    assert "GIFT EDITION · SADE BAŞLANGIÇ" in workflow
    assert "İSTİHBARAT LABORATUVARI" in workflow
    assert "R13_LIVE_PRODUCT_GIFT_RESEARCH_TRUTH_PASS=YES" in workflow
    assert "PAUSED=YES" in workflow
    assert "ACTIVE_LEASES=0" in workflow
    assert "WAKE_QUEUE=0" in workflow
    assert "RELAY_SHARED_PAUSED=YES" in workflow
    assert "RELAY_QUEUE=0" in workflow


def test_r13_has_exactly_one_issue_triggered_canonical_acceptance() -> None:
    workflows = tuple((ROOT / ".github/workflows").glob("*.yml"))
    marker = "[R13] FULL VERSION INTEGRATED ACCEPTANCE V2"
    owners = [
        path.name
        for path in workflows
        if marker in path.read_text()
    ]

    assert owners == ["crypto-r13-integrated-acceptance-v2.yml"]
