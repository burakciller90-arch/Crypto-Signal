from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "ops" / "ssd_runtime_supervisor.sh"


def test_ssd_supervisor_has_single_wc2_live_owner() -> None:
    text = SUPERVISOR.read_text()

    assert "run_wc2_live_clock" in text
    assert 'run_clock live "$LIVE/.venv/bin/python" "$LIVE/src"' not in text
    assert 'export PYTHONPATH="$DEV:$DEV/src"' in text
    assert '"$DEV/ops/run_live_evidence_clock.py"' in text
    assert "--wc2-enabled" in text
    assert '--wc2-policy "$policy"' in text
    assert '--wc2-epoch2 "$epoch2"' in text
    assert '--wc2-collection-protocol "$protocol"' in text
    assert '--wc2-prepared "$prepared"' in text
    assert '--wc2-decision-evidence "$decision"' in text
    assert '--wc2-cohort "$cohort"' in text
    assert '--wc2-shadow-intent "$shadow_intent"' in text
    assert '--wc2-shadow-cycle "$shadow_cycle"' in text
    assert "FAIL_CLOSED=YES REAL_CAPITAL=0" in text
