from pathlib import Path

import ops.run_live_evidence_clock as clock


def test_live_clock_lock_follows_selected_ledger_path(
    tmp_path: Path,
) -> None:
    ledger = (
        tmp_path
        / "runtime"
        / "ledger"
        / "live_signal_ledger.sqlite3"
    )

    assert clock.live_clock_lock_path(ledger) == (
        tmp_path / "runtime" / "ledger" / "live_clock.lock"
    )
