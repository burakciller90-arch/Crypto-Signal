from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ops.audit_fp3_genuine_forward_liveness import (
    candidate_signal_identities,
    snapshot_sqlite_read_only,
    verify_live_signal_source,
)


def _create_db(path: Path, schema: str, rows: tuple[tuple[object, ...], ...]) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
        if "wc2_prepared_cycle_receipts" in schema:
            connection.executemany(
                """
                INSERT INTO wc2_prepared_cycle_receipts(
                    sequence_id,
                    signal_freeze_identity,
                    issued_at_ms
                ) VALUES (?, ?, ?)
                """,
                rows,
            )
        else:
            connection.executemany(
                """
                INSERT INTO signal_freezes(
                    signal_freeze_identity,
                    bundle_identity,
                    frozen_at_ms
                ) VALUES (?, ?, ?)
                """,
                rows,
            )


def test_snapshot_sqlite_read_only_isolates_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "copy.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE facts(identity TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO facts(identity) VALUES ('source')")

    snapshot_sqlite_read_only(source, destination)

    with sqlite3.connect(destination) as connection:
        connection.execute("INSERT INTO facts(identity) VALUES ('copy-only')")
    with sqlite3.connect(source) as connection:
        source_rows = connection.execute(
            "SELECT identity FROM facts ORDER BY identity"
        ).fetchall()
    with sqlite3.connect(destination) as connection:
        copied_rows = connection.execute(
            "SELECT identity FROM facts ORDER BY identity"
        ).fetchall()

    assert source_rows == [("source",)]
    assert copied_rows == [("copy-only",), ("source",)]


def test_candidate_signal_identities_are_post_activation_newest_first(
    tmp_path: Path,
) -> None:
    prepared = tmp_path / "prepared.sqlite3"
    _create_db(
        prepared,
        """
        CREATE TABLE wc2_prepared_cycle_receipts(
            sequence_id INTEGER PRIMARY KEY,
            signal_freeze_identity TEXT NOT NULL,
            issued_at_ms INTEGER NOT NULL
        );
        """,
        (
            (1, "a" * 64, 99),
            (2, "b" * 64, 100),
            (3, "c" * 64, 101),
            (4, "d" * 64, 101),
        ),
    )

    assert candidate_signal_identities(
        prepared,
        activated_at_ms=100,
    ) == ("d" * 64, "c" * 64, "b" * 64)


def test_verify_live_signal_source_requires_exact_immutable_lineage(
    tmp_path: Path,
) -> None:
    signal = tmp_path / "signal.sqlite3"
    signal_identity = "1" * 64
    bundle_identity = "2" * 64
    _create_db(
        signal,
        """
        CREATE TABLE signal_freezes(
            signal_freeze_identity TEXT PRIMARY KEY,
            bundle_identity TEXT NOT NULL,
            frozen_at_ms INTEGER NOT NULL
        );
        """,
        ((signal_identity, bundle_identity, 1234),),
    )

    verify_live_signal_source(
        signal,
        signal_freeze_identity=signal_identity,
        bundle_identity=bundle_identity,
        frozen_at_ms=1234,
    )

    with pytest.raises(ValueError, match="bundle identity mismatch"):
        verify_live_signal_source(
            signal,
            signal_freeze_identity=signal_identity,
            bundle_identity="3" * 64,
            frozen_at_ms=1234,
        )
    with pytest.raises(ValueError, match="frozen-at mismatch"):
        verify_live_signal_source(
            signal,
            signal_freeze_identity=signal_identity,
            bundle_identity=bundle_identity,
            frozen_at_ms=1235,
        )
