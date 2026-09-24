from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def test_galactech_preview_is_low_priority_and_time_bounded() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: GALACTECH EXACT MAIN PREVIEW")
    end = text.find("      - name:", start + 10)
    block = text[start:] if end < 0 else text[start:end]

    assert "PORT=48705" in block
    assert "PREVIEW_TTL_SECONDS=900" in block
    assert 'exec /usr/bin/nice -n 15 "$PY"' in block
    assert 'GALACTECH_PREVIEW_TTL_SECONDS=$PREVIEW_TTL_SECONDS' in block
    assert 'sleep "$PREVIEW_TTL_SECONDS"' in block
    assert "grep -F 'ops/run_dashboard.py'" in block
    assert "grep -F -- '--port 48705'" in block
    assert 'kill "$current"' in block
    assert 'kill -KILL "$current"' in block
    assert 'rm -f "$PIDFILE"' in block
    assert "REAL_CAPITAL=0" in block
