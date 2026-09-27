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
    assert (
        'BYBIT_REST_BASE_URL="${CRYPTO_SIGNAL_BYBIT_REST_BASE_URL:-'
        'https://api.bybit.tr}"'
    ) in text
    assert '--bybit-base-url "$BYBIT_REST_BASE_URL"' in text
    assert "--stream-enabled" in text
    assert '--stream-ledger "$stream"' in text
    assert '--stream-market-tape "$market_tape"' in text
    assert "--stream-family-symbols BTCUSDT ETHUSDT SOLUSDT" in text
    assert 'local stream="$runtime/stream/intelligence_stream.sqlite3"' in text
    assert 'local market_tape="$runtime/market_tape/market_tape.sqlite3"' in text
    assert "run_market_tape_snapshot_clock" in text
    assert '"$DEV/ops/run_market_tape_snapshot.py"' in text
    assert "--wc2-enabled" in text
    assert '--wc2-policy "$policy"' in text
    assert '--wc2-epoch2 "$epoch2"' in text
    assert '--wc2-collection-protocol "$protocol"' in text
    assert '--wc2-prepared "$prepared"' in text
    assert '--wc2-decision-evidence "$decision"' in text
    assert '--wc2-cohort "$cohort"' in text
    assert '--wc2-shadow-intent "$shadow_intent"' in text
    assert '--wc2-shadow-cycle "$shadow_cycle"' in text
    assert text.count("--wc2-execution-enabled") == 1
    assert '--wc2-execution-protocol "$execution_protocol"' in text
    assert '--wc2-execution-runtime "$execution_runtime"' in text
    assert '--wc2-execution-journal "$execution_journal"' in text
    assert '--wc2-venue-rules "$venue_rules"' in text
    assert "run_wc2_paper_execution_cycle.py" not in text
    assert "FAIL_CLOSED=YES REAL_CAPITAL=0" in text
