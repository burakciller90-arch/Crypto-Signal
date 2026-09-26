from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "ops" / "audit_wc2_forward_liveness.py"
SPEC = importlib.util.spec_from_file_location("wc2_forward_liveness_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WC2ForwardLivenessAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.signal = root / "signal.sqlite3"
        self.decision = root / "decision.sqlite3"
        self.prepared = root / "prepared.sqlite3"
        self.policy = root / "policy.sqlite3"
        self.protocol = root / "protocol.sqlite3"
        self._create_common()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_common(self) -> None:
        with sqlite3.connect(self.policy) as db:
            db.execute(
                """CREATE TABLE wc2_forward_policies(
                sequence_id INTEGER PRIMARY KEY,
                policy_identity TEXT,
                preregistered_at_ms INTEGER,
                collection_start_ms INTEGER,
                payload_json TEXT
                )"""
            )
            payload = {
                "preregistered_at_ms": 10,
                "collection_start_ms": 100,
            }
            db.execute(
                "INSERT INTO wc2_forward_policies VALUES (1,?,?,?,?)",
                ("a" * 64, 10, 100, json.dumps(payload)),
            )

        with sqlite3.connect(self.protocol) as db:
            db.execute(
                """CREATE TABLE wc2_collection_protocols(
                sequence_id INTEGER PRIMARY KEY,
                protocol_identity TEXT,
                review_policy_identity TEXT,
                epoch2_activation_identity TEXT,
                preregistered_at_ms INTEGER,
                collection_start_ms INTEGER,
                payload_json TEXT
                )"""
            )
            payload = {
                "collection_start_ms": 100,
                "epoch2_activated_at_ms": 90,
                "maximum_issuance_delay_ms": 120000,
                "coverage_context_identities": [
                    ["binance", "spot", "BTCUSDT", "4h"]
                ],
            }
            db.execute(
                "INSERT INTO wc2_collection_protocols VALUES (1,?,?,?,?,?,?)",
                ("b" * 64, "a" * 64, "c" * 64, 20, 100, json.dumps(payload)),
            )

        with sqlite3.connect(self.decision) as db:
            db.execute(
                """CREATE TABLE r20_forecasts(
                forecast_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT,
                asset TEXT,
                symbol TEXT,
                timeframe TEXT,
                issued_at_ms INTEGER,
                source_as_of_ms INTEGER
                )"""
            )
            db.execute(
                "INSERT INTO r20_forecasts VALUES (?,?,?,?,?,?,?)",
                ("d" * 64, "e" * 64, "BTC", "BTCUSDT", "4h", 200, 190),
            )

        with sqlite3.connect(self.prepared) as db:
            db.execute(
                """CREATE TABLE wc2_prepared_cycle_receipts(
                receipt_identity TEXT,
                policy_identity TEXT,
                activation_identity TEXT,
                collection_protocol_identity TEXT,
                signal_freeze_identity TEXT,
                bundle_identity TEXT,
                source_cutoff_open_time_ms INTEGER,
                issued_at_ms INTEGER,
                previewed_at_ms INTEGER,
                payload_json TEXT
                )"""
            )

        with sqlite3.connect(self.signal) as db:
            db.execute(
                """CREATE TABLE signal_freezes(
                bundle_identity TEXT PRIMARY KEY,
                signal_freeze_identity TEXT,
                exchange TEXT,
                market_type TEXT,
                symbol TEXT,
                timeframe TEXT,
                as_of_ms INTEGER,
                source_cutoff_open_time_ms INTEGER,
                signal_state TEXT,
                direction TEXT,
                bundle_json TEXT,
                frozen_at_ms INTEGER
                )"""
            )

    def _insert_signal(
        self,
        *,
        identity: str,
        frozen_at_ms: int,
        state: str,
        direction: str,
        geometry: object,
    ) -> None:
        signal = {
            "freeze_identity": identity,
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "as_of_ms": frozen_at_ms - 10,
            "state": state,
            "direction": direction,
            "geometry": geometry,
        }
        bundle = {"signal_decision": signal}
        with sqlite3.connect(self.signal) as db:
            db.execute(
                "INSERT INTO signal_freezes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity[::-1],
                    identity,
                    "binance",
                    "spot",
                    "BTCUSDT",
                    "4h",
                    frozen_at_ms - 10,
                    frozen_at_ms - 100,
                    state,
                    direction,
                    json.dumps(bundle),
                    frozen_at_ms,
                ),
            )

    def _audit(self) -> dict[str, object]:
        return MODULE.audit(
            signal_path=self.signal,
            decision_path=self.decision,
            prepared_path=self.prepared,
            policy_path=self.policy,
            protocol_path=self.protocol,
        )

    def test_correct_silence_when_all_post_forecast_sources_are_no_signal(self) -> None:
        self._insert_signal(
            identity="1" * 64,
            frozen_at_ms=300,
            state="no_signal",
            direction="none",
            geometry=None,
        )
        result = self._audit()
        self.assertTrue(result["correct_silence_pre_receipt_proven"])
        self.assertEqual(result["candidate_defect_count"], 0)
        self.assertEqual(result["prepared_required_count"], 0)
        self.assertEqual(result["reason_counts"], {"source_no_signal": 1})

    def test_directional_geometry_without_receipt_is_correctness_candidate(self) -> None:
        self._insert_signal(
            identity="2" * 64,
            frozen_at_ms=400,
            state="watch",
            direction="bullish",
            geometry={
                "targets": [
                    {
                        "label": "T1",
                        "target_price": "110",
                        "reference_rr": "2",
                    }
                ]
            },
        )
        result = self._audit()
        self.assertFalse(result["correct_silence_pre_receipt_proven"])
        self.assertEqual(result["prepared_required_count"], 1)
        self.assertEqual(result["candidate_defect_count"], 1)
        self.assertEqual(
            result["reason_counts"],
            {"eligible_without_prepared_receipt": 1},
        )


if __name__ == "__main__":
    unittest.main()
