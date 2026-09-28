from __future__ import annotations

import argparse
import fcntl
from pathlib import Path

import ops.run_event_source_snapshot as event_runner

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "ops" / "ssd_runtime_supervisor.sh"


def test_event_source_runner_requires_canonical_lock_path(
    tmp_path: Path,
    capsys,
) -> None:
    args = argparse.Namespace(
        db=Path(
            "/Volumes/Crypto-504/Crypto-Signal/Development/runtime/events/"
            "event_source.sqlite3"
        ),
        lock_path=tmp_path / "event-source.lock",
        timeout_seconds=20.0,
    )

    assert event_runner.run(args) == 2
    captured = capsys.readouterr()
    assert "event source lock must use canonical SSD path" in captured.err


def test_event_source_runner_skips_when_single_writer_lock_is_held(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    lock_path = tmp_path / "event-source.lock"
    monkeypatch.setattr(
        event_runner,
        "_require_canonical_path",
        lambda path, *, label: None,
    )

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(
            lock_file.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )
        args = argparse.Namespace(
            db=tmp_path / "event-source.sqlite3",
            lock_path=lock_path,
            timeout_seconds=20.0,
        )
        assert event_runner.run(args) == 0

    captured = capsys.readouterr()
    assert "RDP8_EVENT_SOURCE_SNAPSHOT_SKIPPED=LOCK_HELD" in captured.out
    assert "REAL_CAPITAL=0" in captured.out
    assert not (tmp_path / "event-source.sqlite3").exists()


def test_supervisor_schedules_event_source_on_15_minute_clock() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "run_event_source_snapshot_clock() {" in text
    assert 'local runner="$DEV/ops/run_event_source_snapshot.py"' in text
    assert 'local db="$runtime/event_source.sqlite3"' in text
    assert 'local lock="$runtime/event_source_snapshot.lock"' in text
    assert '--db "$db"' in text
    assert '--lock-path "$lock"' in text
    assert '--timeout-seconds 20' in text
    assert 'event-source-snapshot.out.log' in text
    assert 'event-source-snapshot.err.log' in text
    assert "last_event_source_clock=0" in text
    assert "if [ $((now-last_event_source_clock)) -ge 900 ]; then" in text
    assert "run_event_source_snapshot_clock" in text
    assert 'last_event_source_clock="$now"' in text


def test_rdp8_event_source_clock_adds_no_trade_authority() -> None:
    combined = (
        (ROOT / "ops" / "run_event_source_snapshot.py").read_text(
            encoding="utf-8"
        )
        + SUPERVISOR.read_text(encoding="utf-8")
    ).lower()

    for forbidden in (
        "real_capital=1",
        "place_order",
        "submit_order",
        "private_key",
    ):
        assert forbidden not in combined
    assert "real_capital=0" in combined
