from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from pathlib import Path

ROOT = Path("/Volumes/Crypto-504/Crypto-Signal/Development/runtime/market_tape")
REAL_CAPITAL = 0


def ro(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=5.0)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def main() -> int:
    now_ms = time.time_ns() // 1_000_000
    print(f"RDP1_PROD_ROOT={ROOT}")
    print(f"RDP1_PROD_NOW_MS={now_ms}")

    ps = subprocess.run(
        ["/bin/ps", "-axo", "pid=,ppid=,etime=,command="],
        check=False,
        capture_output=True,
        text=True,
    )
    for line in ps.stdout.splitlines():
        if "run_market_tape_stream.py" in line:
            print(f"RDP1_PROD_PROCESS {line.strip()}")

    lock = ROOT / "market_tape_stream.lock"
    lsof = subprocess.run(
        ["/usr/sbin/lsof", "-t", str(lock)],
        check=False,
        capture_output=True,
        text=True,
    )
    print(f"RDP1_PROD_LOCK_HOLDERS={lsof.stdout.strip()!r}")

    for name in (
        "collector_runtime.sqlite3",
        "market_data_gaps.sqlite3",
        "raw_market_tape.sqlite3",
        "market_tape.sqlite3",
    ):
        path = ROOT / name
        owners = subprocess.run(
            ["/usr/sbin/lsof", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        rows = [line for line in owners.stdout.splitlines() if line.strip()]
        print(f"RDP1_PROD_LSOF {name} rows={len(rows)}")
        for line in rows[:20]:
            print(f"RDP1_PROD_LSOF_ROW {name} {line}")

    runtime = ROOT / "collector_runtime.sqlite3"
    with ro(runtime) as db:
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        print(f"RDP1_PROD_RUNTIME_JOURNAL={mode}")
        instances = db.execute(
            """
            SELECT instance_identity, process_id, started_at_ms, payload_json
            FROM collector_instances
            ORDER BY started_at_ms DESC, instance_identity DESC
            LIMIT 12
            """
        ).fetchall()
        for row in instances:
            payload = json.loads(str(row["payload_json"]))
            hb = db.execute(
                """
                SELECT sequence_no, observed_at_ms,
                       last_successful_ingestion_ms, payload_json
                FROM collector_heartbeats
                WHERE instance_identity=?
                ORDER BY sequence_no DESC LIMIT 1
                """,
                (str(row["instance_identity"]),),
            ).fetchone()
            print(
                "RDP1_PROD_INSTANCE "
                f"id={str(row['instance_identity'])[:12]} "
                f"pid={row['process_id']} "
                f"start_ms={row['started_at_ms']} "
                f"start_kind={payload.get('start_kind')} "
                f"previous={str(payload.get('previous_instance_identity'))[:12]} "
                f"hb_seq={None if hb is None else hb['sequence_no']} "
                f"hb_ms={None if hb is None else hb['observed_at_ms']} "
                f"ingest_ms={None if hb is None else hb['last_successful_ingestion_ms']}"
            )

    gaps = ROOT / "market_data_gaps.sqlite3"
    with ro(gaps) as db:
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        total = db.execute(
            "SELECT COUNT(*) FROM market_data_gap_events"
        ).fetchone()[0]
        print(f"RDP1_PROD_GAP_JOURNAL={mode}")
        print(f"RDP1_PROD_GAP_EVENTS={total}")
        rows = db.execute(
            """
            SELECT sequence_id, event_kind, channel, symbol,
                   observed_at_ms, payload_json
            FROM market_data_gap_events
            ORDER BY sequence_id DESC
            LIMIT 30
            """
        ).fetchall()
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            print(
                "RDP1_PROD_GAP "
                f"seq={row['sequence_id']} "
                f"kind={row['event_kind']} "
                f"channel={row['channel']} "
                f"symbol={row['symbol']} "
                f"observed_ms={row['observed_at_ms']} "
                f"last_ingest={payload.get('last_successful_ingestion_ms')} "
                f"gap={str(payload.get('gap_identity'))[:12]} "
                f"prev={str(payload.get('previous_event_identity'))[:12]}"
            )

    raw = ROOT / "raw_market_tape.sqlite3"
    with ro(raw) as db:
        rows = db.execute(
            """
            SELECT channel, symbol, MAX(ingested_at_ms) AS ingest_ms,
                   COUNT(*) AS n
            FROM raw_market_events
            GROUP BY channel, symbol
            ORDER BY channel, symbol
            """
        ).fetchall()
        for row in rows:
            print(
                "RDP1_PROD_RAW "
                f"channel={row['channel']} symbol={row['symbol']} "
                f"ingest_ms={row['ingest_ms']} count={row['n']}"
            )

    print("RDP1_PRODUCTION_STATE_READONLY_PASS=YES")
    print("REAL_CAPITAL=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
