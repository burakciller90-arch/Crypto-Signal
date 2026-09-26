from __future__ import annotations

import argparse
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from test_intelligence_stream_ledger import (
    _full_bundle,
    _persist_narrative_fixture,
    _resolution,
)
from test_position_sizing_intelligence import _policy as sizing_policy
from test_smart_capital_allocator import _candidate
from test_transaction_tape_atomic import _initial_state

from crypto_signal.decision_ledger import ImmutableDecisionEvidenceLedger
from crypto_signal.ledger.serialization import canonical_json, canonical_sha256, sha256_text
from crypto_signal.ledger.store import ImmutableSignalLedger
from crypto_signal.paper.canonical_capital_runtime import commit_canonical_paper_buy
from crypto_signal.paper.canonical_sizing import promote_fixed_fractional_sizing
from crypto_signal.paper.canonical_vault_eligibility import promote_vault_eligibility
from crypto_signal.paper.epoch2_accounting import Epoch2CanonicalLedger
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.execution import build_frozen_execution_snapshot
from crypto_signal.paper.models import PaperSymbol
from crypto_signal.paper.position_sizing_intelligence import (
    build_position_sizing_risk_context,
    evaluate_position_sizing_intelligence,
)
from crypto_signal.paper.smart_capital_allocator import assess_smart_capital_candidate
from crypto_signal.product.decision_proof import build_live_intelligence_feed_event
from crypto_signal.product.intelligence_stream_analytical import (
    build_stream_analytical_policy,
    compose_stream_analytical_view,
)
from crypto_signal.product.intelligence_stream_analytical_ledger import (
    IntelligenceStreamAnalyticalLedger,
)
from crypto_signal.product.intelligence_stream_capital import (
    project_capital_bundle_to_stream,
)
from crypto_signal.product.intelligence_stream_ledger import IntelligenceStreamLedger
from crypto_signal.product.intelligence_stream_message_ledger import (
    IntelligenceStreamMessageLedger,
)
from crypto_signal.product.intelligence_stream_narrative import (
    build_stream_narrative_plan,
    render_stream_narrative,
)
from crypto_signal.product.intelligence_stream_narrative_ledger import (
    IntelligenceStreamNarrativeLedger,
)
from crypto_signal.product.intelligence_stream_projectors import (
    project_forecast_resolution,
)
from crypto_signal.product.intelligence_stream_story import (
    build_change_set,
    build_story_observation,
    build_story_state,
)
from crypto_signal.product.intelligence_stream_story_ledger import (
    IntelligenceStreamStoryLedger,
)

SEED = "s15-e2e"
AS_OF_MS = 1_790_000_000_000
ISSUED_AT_MS = AS_OF_MS + 1_000
RESOLUTION_AT_MS = ISSUED_AT_MS + 14_400_000
CAPITAL_AT_MS = RESOLUTION_AT_MS + 100_000
MANIFEST_NAME = "s15-manifest.json"
REAL_CAPITAL = 0


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _manifest_path(root: Path) -> Path:
    return root / MANIFEST_NAME


def _read_manifest(root: Path) -> dict[str, object]:
    path = _manifest_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"S15 manifest missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("S15 manifest must decode to object")
    return raw


def _write_manifest(root: Path, payload: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _manifest_path(root).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _seed_signal_freeze(
    *,
    signal_path: Path,
    forecast: object,
) -> str:
    ledger = ImmutableSignalLedger(signal_path)
    ledger.initialize()

    interval_ms = 14_400_000
    candles: list[dict[str, object]] = []
    close = Decimal("99.40")
    for index in range(28):
        open_price = close
        delta = (
            Decimal("0.35")
            if index % 3 == 0
            else Decimal("-0.18")
            if index % 3 == 1
            else Decimal("0.24")
        )
        close = open_price + delta
        high = max(open_price, close) + Decimal("0.28")
        low = min(open_price, close) - Decimal("0.24")
        open_time_ms = AS_OF_MS - (28 - index) * interval_ms
        close_time_ms = open_time_ms + interval_ms - 1
        candles.append(
            {
                "exchange": "binance",
                "market_type": "spot",
                "symbol": "BTCUSDT",
                "timeframe": "4h",
                "open_time_ms": open_time_ms,
                "close_time_ms": close_time_ms,
                "open": str(open_price),
                "high": str(high),
                "low": str(low),
                "close": str(close),
                "volume": str(Decimal(10) + index),
                "quote_volume": str((Decimal(10) + index) * close),
                "trade_count": 100 + index,
                "is_closed": True,
                "source": "s15_acceptance",
                "source_timestamp_ms": close_time_ms - 2,
                "ingested_at_ms": close_time_ms - 1,
                "adapter_version": "s15-acceptance-v1",
            }
        )

    signal_identity = str(getattr(forecast, "signal_freeze_identity"))
    geometry_identity = _sha("s15-geometry")
    bundle = {
        "schema_version": "decision-freeze-v1/1",
        "source_cutoff_open_time_ms": candles[-1]["open_time_ms"],
        "signal_decision": {
            "freeze_identity": signal_identity,
            "signal_version": "s15-acceptance-v1",
            "state": "active",
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "as_of_ms": AS_OF_MS,
            "direction": "bullish",
            "setup_type": "s15_end_to_end",
            "geometry": {
                "source_evidence_id": geometry_identity,
                "source_methodology": "price_action",
                "entry_zone": {"low": "100", "high": "102"},
                "entry_reference_price": "101",
                "entry_reference_model": "zone_midpoint_reference_not_execution",
                "invalidation_price": "95",
                "invalidation_trigger": "touch_or_cross",
                "targets": [
                    {
                        "label": "target_1",
                        "target_price": "108",
                        "reference_rr": "2.33",
                    }
                ],
            },
            "agreement": {},
            "selected_evidence_ids": [],
            "methodology_versions": [],
            "probability_status": "not_calibrated",
            "historical_stats_status": "not_evaluated",
            "uncertainty_flags": [],
            "evidence_summary": [],
        },
        "confluence": {},
        "selected_evidence": [],
        "price_action": {},
        "harmonic": {},
        "elliott": {},
        "candles": candles,
    }
    bundle_json = canonical_json(bundle)
    bundle_identity = sha256_text(bundle_json)
    with sqlite3.connect(signal_path) as connection:
        connection.execute(
            """
            INSERT INTO signal_freezes (
                bundle_identity,
                signal_freeze_identity,
                exchange,
                market_type,
                symbol,
                timeframe,
                as_of_ms,
                source_cutoff_open_time_ms,
                signal_state,
                direction,
                bundle_json,
                frozen_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bundle_identity,
                signal_identity,
                "binance",
                "spot",
                "BTCUSDT",
                "4h",
                AS_OF_MS,
                int(candles[-1]["open_time_ms"]),
                "active",
                "bullish",
                bundle_json,
                ISSUED_AT_MS,
            ),
        )
        connection.commit()
    return bundle_identity


def seed(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    (
        stream_path,
        activation,
        forecast,
        proof,
        _context,
        _issuance,
        _state,
        _view,
        plan,
        narrative,
    ) = _persist_narrative_fixture(
        root,
        seed=SEED,
        as_of_ms=AS_OF_MS,
        issued_at_ms=ISSUED_AT_MS,
    )
    IntelligenceStreamNarrativeLedger(stream_path).append_narrative(plan, narrative)

    decision_path = root / "decision_evidence.sqlite3"
    decision_event = build_live_intelligence_feed_event(proof, forecast)
    ImmutableDecisionEvidenceLedger(decision_path).append_issuance_bundle(
        forecast,
        proof,
        decision_event,
    )

    signal_path = root / "signal_ledger.sqlite3"
    freeze_bundle_identity = _seed_signal_freeze(
        signal_path=signal_path,
        forecast=forecast,
    )
    epoch2_path, epoch2_state = _initial_state(root)

    payload: dict[str, object] = {
        "schema_version": "stream-s15-acceptance-manifest-v1/1",
        "stream_path": str(stream_path),
        "decision_path": str(decision_path),
        "signal_path": str(signal_path),
        "epoch2_path": str(epoch2_path),
        "root_narrative_identity": narrative.narrative_identity,
        "root_collapsed_text": narrative.text.collapsed_text,
        "story_identity": plan.story_identity,
        "forecast_identity": forecast.forecast_identity,
        "proof_identity": proof.proof_identity,
        "signal_freeze_identity": forecast.signal_freeze_identity,
        "freeze_bundle_identity": freeze_bundle_identity,
        "activation_identity": activation.activation_identity,
        "epoch2_activation_identity": epoch2_state.activation.activation_identity,
        "resolution_narrative_identity": None,
        "capital_narrative_identity": None,
        "real_capital": REAL_CAPITAL,
    }
    _write_manifest(root, payload)
    return payload


def append_resolution(root: Path) -> dict[str, object]:
    manifest = _read_manifest(root)
    (
        stream_path,
        activation,
        forecast,
        proof,
        context,
        issuance,
        root_state,
        _,
        _,
        _,
    ) = _persist_narrative_fixture(
        root,
        seed=SEED,
        as_of_ms=AS_OF_MS,
        issued_at_ms=ISSUED_AT_MS,
    )
    resolution = _resolution(
        forecast,
        evaluated_at_ms=RESOLUTION_AT_MS,
        seed=SEED,
    )
    feed_event = build_live_intelligence_feed_event(
        proof,
        forecast,
        resolution=resolution,
    )
    resolved = project_forecast_resolution(
        activation,
        context,
        forecast,
        proof,
        feed_event,
        resolution,
        issuance_message=issuance.message_input,
    )
    IntelligenceStreamLedger(stream_path).append_source_event(resolved.source_event)
    IntelligenceStreamMessageLedger(stream_path).append_message_bundle(
        resolved.fact_bundle,
        resolved.message_input,
    )
    observation = build_story_observation(
        resolved.message_input,
        resolved.fact_bundle,
        previous_state_identity=root_state.state_identity,
    )
    state = build_story_state(observation, previous_state=root_state)
    change = build_change_set(state, previous_state=root_state)
    IntelligenceStreamStoryLedger(stream_path).append_transition(
        observation,
        state,
        change,
    )
    view = compose_stream_analytical_view(
        build_stream_analytical_policy(),
        resolved.fact_bundle,
        state,
        change,
        message=resolved.message_input,
    )
    IntelligenceStreamAnalyticalLedger(stream_path).append_view(view)
    plan = build_stream_narrative_plan(
        view,
        resolved.fact_bundle,
        change,
    )
    narrative = render_stream_narrative(
        plan,
        view,
        resolved.fact_bundle,
        change,
    )
    IntelligenceStreamNarrativeLedger(stream_path).append_narrative(
        plan,
        narrative,
    )

    decision_ledger = ImmutableDecisionEvidenceLedger(
        Path(str(manifest["decision_path"]))
    )
    decision_ledger.append_resolution(resolution)
    decision_ledger.append_feed_event(feed_event)

    manifest["resolution_identity"] = resolution.resolution_identity
    manifest["resolution_narrative_identity"] = narrative.narrative_identity
    manifest["resolution_collapsed_text"] = narrative.text.collapsed_text
    _write_manifest(root, manifest)
    return manifest


def _capital_execution_snapshot():
    return build_frozen_execution_snapshot(
        venue_reference="s15:acceptance-paper-only",
        symbol=PaperSymbol.BTCUSDT,
        quantity_step=Decimal("0.0001"),
        min_quantity=Decimal("0.0001"),
        min_notional_usdt=Decimal(1),
        fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
    )


def append_capital(root: Path) -> dict[str, object]:
    manifest = _read_manifest(root)
    _, forecast, proof, _context, _event = _full_bundle(
        as_of_ms=AS_OF_MS,
        issued_at_ms=ISSUED_AT_MS,
        seed=SEED,
    )
    epoch2_path = Path(str(manifest["epoch2_path"]))
    stream_path = Path(str(manifest["stream_path"]))
    state = Epoch2CanonicalLedger(epoch2_path).read_state()
    core = next(
        item
        for item in state.vault_snapshots
        if item.vault_id is PaperVaultId.CORE
    )

    candidate = _candidate()
    allocator = assess_smart_capital_candidate(
        candidate,
        assessed_at_ms=candidate.as_of_ms + 1,
    )
    envelope = next(
        item for item in allocator.vaults if item.vault_id is PaperVaultId.CORE
    )
    sizing_context = build_position_sizing_risk_context(
        vault_id=PaperVaultId.CORE,
        asset="BTCUSDT",
        as_of_ms=CAPITAL_AT_MS - 300,
        allocator_assessment_identity=allocator.assessment_identity,
        allocator_candidate_identity=candidate.candidate_identity,
        expected_win_r=Decimal(2),
        expected_loss_r=Decimal(1),
        transaction_cost_r=Decimal("0.10"),
        absolute_correlation_0_1=Decimal("0.20"),
        current_drawdown_fraction=Decimal("0.05"),
        volatility_fraction=Decimal("0.10"),
        liquidity_score_0_1=Decimal("0.90"),
        source_evidence_identities=tuple(
            sorted(
                (
                    _sha("s15-correlation"),
                    _sha("s15-drawdown"),
                    _sha("s15-liquidity"),
                    _sha("s15-payoff"),
                    _sha("s15-volatility"),
                )
            )
        ),
    )
    assessment = evaluate_position_sizing_intelligence(
        policy=sizing_policy(),
        vault=envelope,
        context=sizing_context,
    )
    eligibility = promote_vault_eligibility(
        candidate,
        allocator,
        vault_id=PaperVaultId.CORE,
    )
    selection = promote_fixed_fractional_sizing(
        assessment,
        current_vault=core,
        selected_at_ms=CAPITAL_AT_MS - 200,
    )
    committed = commit_canonical_paper_buy(
        epoch2_path=epoch2_path,
        forecast=forecast,
        proof=proof,
        sizing_assessment=assessment,
        sizing_selection=selection,
        eligibility_proof=eligibility,
        symbol=PaperSymbol.BTCUSDT,
        reference_price=Decimal(101),
        reference_price_evidence_identity=_sha("s15-reference-price"),
        mark_prices={PaperSymbol.BTCUSDT: Decimal(101)},
        mark_evidence_identity=_sha("s15-mark"),
        execution_snapshot=_capital_execution_snapshot(),
        decided_at_ms=CAPITAL_AT_MS - 150,
        filled_at_ms=CAPITAL_AT_MS - 100,
        mutated_at_ms=CAPITAL_AT_MS - 50,
        snapshot_at_ms=CAPITAL_AT_MS,
    )
    projected = project_capital_bundle_to_stream(
        epoch2_path=epoch2_path,
        stream_path=stream_path,
        bundle_identity=committed.accounting_bundle_identity,
    )
    manifest["capital_narrative_identity"] = projected.narrative_identity
    manifest["capital_bundle_identity"] = committed.accounting_bundle_identity
    manifest["capital_intent_identity"] = committed.intent_identity
    manifest["capital_fill_identity"] = committed.fill_identity
    _write_manifest(root, manifest)
    return manifest


def snapshot(root: Path) -> dict[str, object]:
    return _read_manifest(root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("seed", "append-resolution", "append-capital", "snapshot"),
    )
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    if args.action == "seed":
        result = seed(args.root)
    elif args.action == "append-resolution":
        result = append_resolution(args.root)
    elif args.action == "append-capital":
        result = append_capital(args.root)
    else:
        result = snapshot(args.root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
