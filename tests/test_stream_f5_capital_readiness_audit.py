from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "ops"
    / "audit_stream_f5_capital_readiness.py"
)
SPEC = importlib.util.spec_from_file_location(
    "stream_f5_capital_readiness",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _identity(char: str) -> str:
    return char * 64


class StreamF5CapitalReadinessAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.epoch2 = root / "epoch2.sqlite3"
        self.stream = root / "stream.sqlite3"
        self._create_epoch2()
        self._create_stream()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_epoch2(self) -> None:
        with sqlite3.connect(self.epoch2) as db:
            db.execute(
                """CREATE TABLE r21_epoch2_activation (
                singleton INTEGER PRIMARY KEY,
                activation_identity TEXT,
                payload_json TEXT
                )"""
            )
            db.execute(
                """CREATE TABLE r21_vault_snapshots (
                snapshot_identity TEXT PRIMARY KEY,
                vault_id TEXT,
                payload_json TEXT,
                snapshot_at_ms INTEGER
                )"""
            )
            db.execute(
                """CREATE TABLE r21_consolidated_snapshots (
                snapshot_identity TEXT PRIMARY KEY,
                payload_json TEXT,
                snapshot_at_ms INTEGER
                )"""
            )
            db.execute(
                """CREATE TABLE s11_vault_decisions (
                decision_identity TEXT PRIMARY KEY,
                vault_id TEXT,
                disposition TEXT,
                event_at_ms INTEGER,
                payload_json TEXT
                )"""
            )
            db.execute(
                """CREATE TABLE s11_canonical_sizing_events (
                event_identity TEXT PRIMARY KEY,
                vault_id TEXT,
                event_at_ms INTEGER,
                payload_json TEXT
                )"""
            )
            for table, identity in (
                ("r22_epoch2_intents", "intent_identity"),
                ("r22_epoch2_fills", "fill_identity"),
                ("r22_epoch2_bundles", "bundle_identity"),
                ("s11_capital_outcome_evidence", "outcome_identity"),
            ):
                db.execute(
                    f"""CREATE TABLE {table} (
                    {identity} TEXT PRIMARY KEY,
                    vault_id TEXT,
                    event_at_ms INTEGER,
                    payload_json TEXT
                    )"""
                )

            for index, vault in enumerate(
                ("core", "opportunity_reserve", "tactical"),
                start=1,
            ):
                snapshot = {
                    "snapshot_identity": _identity(str(index)),
                    "snapshot_at_ms": 900,
                    "vault_id": vault,
                    "cash_usdt": "100",
                    "marked_exposure_usdt": "0",
                    "nav_usdt": "100",
                    "realized_pnl_usdt": "0",
                    "unrealized_pnl_usdt": "0",
                    "closed_trade_count": 0,
                    "metrics_status": "NOT_YET_MEASURED",
                    "real_capital": 0,
                }
                db.execute(
                    "INSERT INTO r21_vault_snapshots VALUES (?,?,?,?)",
                    (
                        snapshot["snapshot_identity"],
                        vault,
                        json.dumps(snapshot),
                        900,
                    ),
                )
            consolidated = {
                "snapshot_identity": _identity("a"),
                "snapshot_at_ms": 900,
                "cash_usdt": "300",
                "marked_exposure_usdt": "0",
                "nav_usdt": "300",
                "realized_pnl_usdt": "0",
                "unrealized_pnl_usdt": "0",
                "closed_trade_count": 0,
                "metrics_status": "NOT_YET_MEASURED",
                "real_capital": 0,
            }
            db.execute(
                "INSERT INTO r21_consolidated_snapshots VALUES (?,?,?)",
                (
                    consolidated["snapshot_identity"],
                    json.dumps(consolidated),
                    900,
                ),
            )
            db.execute(
                "INSERT INTO r21_epoch2_activation VALUES (1,?,?)",
                (_identity("b"), json.dumps({"activation_identity": _identity("b")})),
            )

    def _create_stream(self) -> None:
        activation = {
            "activation_identity": _identity("c"),
            "activated_at_ms": 1000,
            "historical_rich_backfill_allowed": False,
            "real_capital": 0,
        }
        with sqlite3.connect(self.stream) as db:
            db.execute(
                """CREATE TABLE stream_activation (
                activation_identity TEXT PRIMARY KEY,
                activated_at_ms INTEGER,
                payload_json TEXT
                )"""
            )
            db.execute(
                """CREATE TABLE stream_source_events (
                stream_event_identity TEXT PRIMARY KEY,
                source_event_identity TEXT,
                category TEXT,
                subtype TEXT,
                event_at_ms INTEGER
                )"""
            )
            db.execute(
                "INSERT INTO stream_activation VALUES (?,?,?)",
                (
                    activation["activation_identity"],
                    activation["activated_at_ms"],
                    json.dumps(activation),
                ),
            )

    def _insert_decision(self, *, event_at_ms: int) -> None:
        payload = {
            "decision_identity": _identity("d"),
            "vault_id": "core",
            "disposition": "hold",
            "candidate_as_of_ms": event_at_ms - 20,
            "assessed_at_ms": event_at_ms - 10,
            "decided_at_ms": event_at_ms,
            "real_capital": 0,
        }
        with sqlite3.connect(self.epoch2) as db:
            db.execute(
                "INSERT INTO s11_vault_decisions VALUES (?,?,?,?,?)",
                (
                    payload["decision_identity"],
                    "core",
                    "hold",
                    event_at_ms,
                    json.dumps(payload),
                ),
            )

    def test_preactivation_capital_truth_is_not_forward_candidate(self) -> None:
        self._insert_decision(event_at_ms=950)
        result = MODULE.audit(
            epoch2_path=self.epoch2,
            stream_path=self.stream,
        )
        partition = result["canonical_forward_partition"]["s11_vault_decisions"]
        self.assertEqual(partition["before_stream_activation"], 1)
        self.assertEqual(partition["at_or_after_stream_activation"], 0)
        self.assertEqual(result["canonical_forward_record_count"], 0)
        self.assertEqual(result["f5_current_classification"], "CODE_EXISTS_NOT_LIVE")
        self.assertTrue(result["three_vault_state_present"])
        self.assertTrue(result["real_capital_zero_verified"])

    def test_postactivation_capital_truth_is_forward_candidate(self) -> None:
        self._insert_decision(event_at_ms=1050)
        result = MODULE.audit(
            epoch2_path=self.epoch2,
            stream_path=self.stream,
        )
        partition = result["canonical_forward_partition"]["s11_vault_decisions"]
        self.assertEqual(partition["before_stream_activation"], 0)
        self.assertEqual(partition["at_or_after_stream_activation"], 1)
        self.assertEqual(result["canonical_forward_record_count"], 1)
        self.assertEqual(
            result["f5_safe_next_action"],
            "WIRE_POST_COMMIT_FORWARD_CALLER_ONLY_NO_BACKFILL",
        )


if __name__ == "__main__":
    unittest.main()
