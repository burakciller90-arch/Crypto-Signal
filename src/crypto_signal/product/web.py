from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from crypto_signal.decision_ledger import (
    DecisionLedgerConflictError,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.ledger.serialization import canonicalize
from crypto_signal.paper.epoch2_accounting import read_epoch2_state_read_only
from crypto_signal.paper.epochs import (
    EPOCH_1_SPEC,
    EPOCH_2_LEDGER_FILENAME,
    PaperFundEpochSpec,
    current_paper_epoch_spec,
)
from crypto_signal.paper.mission_control import (
    PaperMissionControlError,
    read_paper_mission_control_snapshot,
)
from crypto_signal.paper.runtime_replay_observation import (
    R25RuntimeReplayObservationLedger,
    RuntimeReplayObservation,
)
from crypto_signal.paper.shadow_cycle_manifest import (
    R25ShadowCycleManifest,
    ShadowCycleManifestRecord,
)
from crypto_signal.paper.shadow_intent_journal import R25ShadowIntentJournal
from crypto_signal.product.education import (
    EducationLesson,
    EducationLookupMissing,
    all_education_lessons,
    lookup_education_lesson,
)
from crypto_signal.product.event_source_runtime import (
    read_event_source_runtime_truth,
)
from crypto_signal.product.intelligence_center import build_intelligence_center_payload
from crypto_signal.product.market_tape_runtime import (
    read_cold_archive_runtime_truth,
    read_market_tape_collector_runtime_truth,
    read_market_tape_runtime_truth,
)
from crypto_signal.product.provider_divergence_runtime import (
    read_provider_divergence_runtime_truth,
)
from crypto_signal.product.reader import DashboardReader, DashboardReadError

DEFAULT_LEDGER_PATH = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "ledger"
    / "live_signal_ledger.sqlite3"
)
DEFAULT_ALERT_OUTBOX_PATH = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "alerts"
    / "alert_outbox.sqlite3"
)
DEFAULT_PAPER_LEDGER_PATH = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "paper"
    / "paper_fund.sqlite3"
)
DEFAULT_EPOCH2_LEDGER_PATH = DEFAULT_PAPER_LEDGER_PATH.with_name(
    EPOCH_2_LEDGER_FILENAME
)
DEFAULT_DECISION_EVIDENCE_LEDGER_PATH = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "decision"
    / "decision_evidence.sqlite3"
)
DEFAULT_CANDLE_CACHE_PATH = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "data"
    / "live_base_15m_cache.sqlite3"
)
DEFAULT_PROVIDER_DIVERGENCE_PATH = DEFAULT_CANDLE_CACHE_PATH.with_name(
    "provider_divergence.sqlite3"
)
DEFAULT_EVENT_SOURCE_RUNTIME_PATH = (
    DEFAULT_LEDGER_PATH.parent.parent
    / "events"
    / "event_source.sqlite3"
)
STATIC_DIR = Path(__file__).with_name("static")
GALACTECH_DIR = Path(__file__).with_name("galactech")
PRODUCT_VERSION = "full-version-contextual-evidence/1"


def _json(value: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=canonicalize(value), status_code=status_code)


def _education_payload(lesson: EducationLesson) -> dict[str, object]:
    return {
        "concept_id": lesson.concept_id.value,
        "title_tr": lesson.title_tr,
        "beginner_tr": lesson.beginner_tr,
        "why_it_matters_tr": lesson.why_it_matters_tr,
        "advanced_tr": lesson.advanced_tr,
    }


def _paper_epoch_payload(epoch: PaperFundEpochSpec) -> dict[str, object]:
    return {
        "epoch_id": epoch.epoch_id,
        "epoch_identity": epoch.epoch_identity,
        "status": epoch.status.value,
        "starting_cash_usdt": epoch.starting_cash_usdt,
        "ledger_filename": epoch.ledger_filename,
        "predecessor_epoch_id": epoch.predecessor_epoch_id,
        "canonical_for_new_activity": epoch.canonical_for_new_activity,
        "vault_allocations": [
            {
                "vault_id": item.vault_id.value,
                "starting_cash_usdt": item.starting_cash_usdt,
            }
            for item in epoch.vault_allocations
        ],
        "real_capital": epoch.real_capital,
        "leverage_allowed": epoch.leverage_allowed,
        "borrowing_allowed": epoch.borrowing_allowed,
        "martingale_allowed": epoch.martingale_allowed,
        "schema_version": epoch.schema_version,
    }


def _is_lower_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _replay_matches_cycle(
    replay: RuntimeReplayObservation,
    cycle: ShadowCycleManifestRecord,
) -> bool:
    return (
        replay.cycle_identity == cycle.cycle_identity
        and replay.forecast_identity == cycle.forecast_identity
        and replay.proof_identity == cycle.proof_identity
        and replay.capital_bridge_identity == cycle.capital_bridge_identity
        and replay.sizing_bridge_identity == cycle.sizing_bridge_identity
        and replay.review_selection_identity == cycle.review_selection_identity
        and replay.preview_identity == cycle.preview_identity
        and replay.journal_record_identity == cycle.journal_record_identity
        and replay.manifest_identity == cycle.manifest_identity
    )


def _operational_component_ready(value: object) -> bool:
    return isinstance(value, dict) and value.get("status") == "ready"


def create_app(
    ledger_path: Path | None = None,
    alert_outbox_path: Path | None = None,
    paper_ledger_path: Path | None = None,
    candle_cache_path: Path | None = None,
    learning_memory_path: Path | None = None,
    epoch2_ledger_path: Path | None = None,
    decision_evidence_path: Path | None = None,
    shadow_intent_journal_path: Path | None = None,
    shadow_cycle_manifest_path: Path | None = None,
    runtime_replay_observation_path: Path | None = None,
    market_tape_path: Path | None = None,
    market_tape_collector_runtime_path: Path | None = None,
    cold_archive_path: Path | None = None,
    provider_divergence_path: Path | None = None,
    event_source_runtime_path: Path | None = None,
) -> FastAPI:
    selected_path = ledger_path or Path(
        os.environ.get("CRYPTO_SIGNAL_LEDGER_PATH", str(DEFAULT_LEDGER_PATH))
    )
    if alert_outbox_path is not None:
        selected_alert_path: Path | None = alert_outbox_path
    elif ledger_path is None:
        selected_alert_path = Path(
            os.environ.get(
                "CRYPTO_SIGNAL_ALERT_OUTBOX_PATH",
                str(DEFAULT_ALERT_OUTBOX_PATH),
            )
        )
    else:
        selected_alert_path = None

    if paper_ledger_path is not None:
        selected_paper_path: Path | None = paper_ledger_path
    elif ledger_path is None:
        selected_paper_path = Path(
            os.environ.get(
                "CRYPTO_SIGNAL_PAPER_LEDGER_PATH",
                str(DEFAULT_PAPER_LEDGER_PATH),
            )
        )
    else:
        selected_paper_path = None

    if epoch2_ledger_path is not None:
        selected_epoch2_path: Path | None = epoch2_ledger_path
    elif ledger_path is None:
        selected_epoch2_path = Path(
            os.environ.get(
                "CRYPTO_SIGNAL_EPOCH2_LEDGER_PATH",
                str(DEFAULT_EPOCH2_LEDGER_PATH),
            )
        )
    else:
        selected_epoch2_path = None

    if candle_cache_path is not None:
        selected_candle_path: Path | None = candle_cache_path
    elif ledger_path is None:
        selected_candle_path = Path(
            os.environ.get(
                "CRYPTO_SIGNAL_CANDLE_CACHE_PATH",
                str(DEFAULT_CANDLE_CACHE_PATH),
            )
        )
    else:
        selected_candle_path = None

    if decision_evidence_path is not None:
        selected_decision_path: Path | None = decision_evidence_path
    elif ledger_path is None:
        selected_decision_path = Path(
            os.environ.get(
                "CRYPTO_SIGNAL_DECISION_EVIDENCE_PATH",
                str(DEFAULT_DECISION_EVIDENCE_LEDGER_PATH),
            )
        )
    else:
        selected_decision_path = None

    if shadow_intent_journal_path is not None:
        selected_shadow_intent_path: Path | None = shadow_intent_journal_path
    elif ledger_path is None:
        shadow_intent_env = os.environ.get(
            "CRYPTO_SIGNAL_SHADOW_INTENT_JOURNAL_PATH"
        )
        selected_shadow_intent_path = (
            None if not shadow_intent_env else Path(shadow_intent_env)
        )
    else:
        selected_shadow_intent_path = None

    if shadow_cycle_manifest_path is not None:
        selected_shadow_cycle_path: Path | None = shadow_cycle_manifest_path
    elif ledger_path is None:
        shadow_cycle_env = os.environ.get(
            "CRYPTO_SIGNAL_SHADOW_CYCLE_MANIFEST_PATH"
        )
        selected_shadow_cycle_path = (
            None if not shadow_cycle_env else Path(shadow_cycle_env)
        )
    else:
        selected_shadow_cycle_path = None

    if runtime_replay_observation_path is not None:
        selected_runtime_replay_path: Path | None = runtime_replay_observation_path
    elif ledger_path is None:
        runtime_replay_env = os.environ.get(
            "CRYPTO_SIGNAL_RUNTIME_REPLAY_OBSERVATION_PATH"
        )
        selected_runtime_replay_path = (
            None if not runtime_replay_env else Path(runtime_replay_env)
        )
    else:
        selected_runtime_replay_path = None

    if market_tape_path is not None:
        selected_market_tape_path: Path | None = market_tape_path
    elif ledger_path is None:
        market_tape_env = os.environ.get("CRYPTO_SIGNAL_MARKET_TAPE_PATH")
        selected_market_tape_path = (
            None if not market_tape_env else Path(market_tape_env)
        )
    else:
        selected_market_tape_path = None

    if market_tape_collector_runtime_path is not None:
        selected_market_tape_collector_runtime_path: Path | None = (
            market_tape_collector_runtime_path
        )
    elif ledger_path is None:
        collector_runtime_env = os.environ.get(
            "CRYPTO_SIGNAL_MARKET_TAPE_COLLECTOR_RUNTIME_PATH"
        )
        selected_market_tape_collector_runtime_path = (
            None if not collector_runtime_env else Path(collector_runtime_env)
        )
    else:
        selected_market_tape_collector_runtime_path = None

    if cold_archive_path is not None:
        selected_cold_archive_path: Path | None = cold_archive_path
    elif ledger_path is None:
        cold_archive_env = os.environ.get("CRYPTO_SIGNAL_COLD_ARCHIVE_PATH")
        selected_cold_archive_path = (
            None if not cold_archive_env else Path(cold_archive_env)
        )
    else:
        selected_cold_archive_path = None

    if provider_divergence_path is not None:
        selected_provider_divergence_path: Path | None = (
            provider_divergence_path
        )
    elif ledger_path is None:
        provider_divergence_env = os.environ.get(
            "CRYPTO_SIGNAL_PROVIDER_DIVERGENCE_PATH"
        )
        selected_provider_divergence_path = (
            Path(provider_divergence_env)
            if provider_divergence_env
            else DEFAULT_PROVIDER_DIVERGENCE_PATH
        )
    else:
        selected_provider_divergence_path = None

    if event_source_runtime_path is not None:
        selected_event_source_runtime_path: Path | None = (
            event_source_runtime_path
        )
    elif ledger_path is None:
        event_source_env = os.environ.get(
            "CRYPTO_SIGNAL_EVENT_SOURCE_RUNTIME_PATH"
        )
        selected_event_source_runtime_path = (
            Path(event_source_env)
            if event_source_env
            else DEFAULT_EVENT_SOURCE_RUNTIME_PATH
        )
    else:
        selected_event_source_runtime_path = None

    selected_learning_memory_path = learning_memory_path
    if selected_learning_memory_path is None:
        learning_memory_env = os.environ.get("CRYPTO_SIGNAL_LEARNING_MEMORY_PATH")
        if learning_memory_env:
            selected_learning_memory_path = Path(learning_memory_env)

    reader = DashboardReader(
        selected_path,
        alert_outbox_path=selected_alert_path,
    )

    app = FastAPI(
        title="Crypto Signal Piyasa Istihbarat Merkezi",
        version=PRODUCT_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.ledger_path = selected_path
    app.state.alert_outbox_path = selected_alert_path
    app.state.paper_ledger_path = selected_paper_path
    app.state.epoch2_ledger_path = selected_epoch2_path
    app.state.candle_cache_path = selected_candle_path
    app.state.learning_memory_path = selected_learning_memory_path
    app.state.decision_evidence_path = selected_decision_path
    app.state.shadow_intent_journal_path = selected_shadow_intent_path
    app.state.shadow_cycle_manifest_path = selected_shadow_cycle_path
    app.state.runtime_replay_observation_path = selected_runtime_replay_path
    app.state.market_tape_path = selected_market_tape_path
    app.state.market_tape_collector_runtime_path = (
        selected_market_tape_collector_runtime_path
    )
    app.state.cold_archive_path = selected_cold_archive_path
    app.state.provider_divergence_path = selected_provider_divergence_path
    app.state.event_source_runtime_path = selected_event_source_runtime_path
    app.state.reader = reader

    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )
    app.mount(
        "/galactech-static",
        StaticFiles(directory=str(GALACTECH_DIR)),
        name="galactech-static",
    )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(GALACTECH_DIR / "index.html")

    @app.get("/galactech", include_in_schema=False)
    def galactech_preview() -> FileResponse:
        return FileResponse(GALACTECH_DIR / "index.html")

    @app.get("/legacy", include_in_schema=False)
    def legacy_product() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "product_version": PRODUCT_VERSION,
            "real_capital": 0,
            "ledger_present": selected_path.exists(),
            "alert_outbox_present": (
                selected_alert_path is not None
                and selected_alert_path.exists()
            ),
            "decision_evidence_present": (
                selected_decision_path is not None
                and selected_decision_path.exists()
            ),
            "read_only": True,
        }

    @app.get("/api/command-center")
    def command_center(
        recent_limit: int = Query(default=8, ge=1, le=100),
    ) -> JSONResponse:
        try:
            return _json(reader.command_center(recent_limit=recent_limit))
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/market-radar")
    def market_radar() -> JSONResponse:
        try:
            return _json(reader.market_radar())
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/navigation")
    def navigation() -> JSONResponse:
        try:
            return _json(reader.navigation())
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/assets/{symbol}/{timeframe}")
    def asset_cockpit(
        symbol: str,
        timeframe: str,
        recent_limit: int = Query(default=20, ge=1, le=200),
    ) -> JSONResponse:
        try:
            return _json(
                reader.asset_cockpit(
                    symbol=symbol.upper(),
                    timeframe=timeframe,
                    recent_limit=recent_limit,
                )
            )
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/signals")
    def signal_archive(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> JSONResponse:
        try:
            return _json(reader.signal_archive(limit=limit, offset=offset))
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/archive/proof-wall")
    def archive_proof_wall(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> JSONResponse:
        try:
            return _json(reader.proof_wall(limit=limit, offset=offset))
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/signals/{signal_freeze_identity}")
    def signal_detail(signal_freeze_identity: str) -> JSONResponse:
        try:
            return _json(reader.signal_detail(signal_freeze_identity))
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/decision-proof/{signal_freeze_identity}")
    def decision_proof(signal_freeze_identity: str) -> JSONResponse:
        if selected_decision_path is None or not selected_decision_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "decision_evidence_runtime_not_configured",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            proof = ImmutableDecisionEvidenceLedger(
                selected_decision_path
            ).read_proof_for_signal(signal_freeze_identity)
        except DecisionLedgerConflictError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if proof is None:
            return _json(
                {
                    "status": "empty",
                    "reason": "no_persisted_decision_proof_for_signal",
                    "signal_freeze_identity": signal_freeze_identity,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        return _json(
            {
                "status": "ready",
                "proof": proof,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/intelligence-feed")
    def live_intelligence_feed(
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> JSONResponse:
        if selected_decision_path is None or not selected_decision_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "decision_evidence_runtime_not_configured",
                    "events": [],
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            events = ImmutableDecisionEvidenceLedger(
                selected_decision_path
            ).read_feed(limit=limit)
        except DecisionLedgerConflictError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready" if events else "empty",
                "events": events,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/decision-evidence/status")
    def decision_evidence_status() -> JSONResponse:
        if selected_decision_path is None or not selected_decision_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "decision_evidence_runtime_not_configured",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            snapshot = ImmutableDecisionEvidenceLedger(
                selected_decision_path
            ).read_status()
        except DecisionLedgerConflictError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready",
                "snapshot": snapshot,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/shadow-decision-rail/status")
    def shadow_decision_rail_status() -> JSONResponse:
        if selected_shadow_intent_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "shadow_intent_journal_runtime_not_configured",
                    "semantic": "SHADOW_RESEARCH_ONLY",
                    "canonical_epoch2_mutation": False,
                    "production_authority": False,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        if not selected_shadow_intent_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "shadow_intent_journal_evidence_missing",
                    "journal_filename": selected_shadow_intent_path.name,
                    "semantic": "SHADOW_RESEARCH_ONLY",
                    "canonical_epoch2_mutation": False,
                    "production_authority": False,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            snapshot = R25ShadowIntentJournal(
                selected_shadow_intent_path
            ).verify_read_only()
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready",
                "snapshot": snapshot,
                "journal_filename": selected_shadow_intent_path.name,
                "semantic": "SHADOW_RESEARCH_ONLY",
                "canonical_epoch2_mutation": False,
                "production_authority": False,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/shadow-decision-rail/forecast/{forecast_identity}")
    def shadow_cycle_for_forecast(forecast_identity: str) -> JSONResponse:
        if not _is_lower_sha256(forecast_identity):
            raise HTTPException(
                status_code=400,
                detail="forecast_identity must be lowercase SHA256",
            )
        if selected_shadow_cycle_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "shadow_cycle_manifest_runtime_not_configured",
                    "forecast_identity": forecast_identity,
                    "semantic": "EXACT_PERSISTED_CYCLE_IDENTITY_ONLY",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        if not selected_shadow_cycle_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "shadow_cycle_manifest_evidence_missing",
                    "forecast_identity": forecast_identity,
                    "manifest_filename": selected_shadow_cycle_path.name,
                    "semantic": "EXACT_PERSISTED_CYCLE_IDENTITY_ONLY",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            record = R25ShadowCycleManifest(
                selected_shadow_cycle_path
            ).read_latest_for_forecast(forecast_identity)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if record is None:
            return _json(
                {
                    "status": "empty",
                    "reason": "no_exact_persisted_shadow_cycle_for_forecast",
                    "forecast_identity": forecast_identity,
                    "semantic": "EXACT_PERSISTED_CYCLE_IDENTITY_ONLY",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        replay_observation = None
        replay_status = "NOT_MEASURED"
        replay_reason = "runtime_replay_observation_not_configured"
        if selected_runtime_replay_path is not None:
            if not selected_runtime_replay_path.exists():
                replay_reason = "runtime_replay_observation_evidence_missing"
            else:
                try:
                    replay_observation = R25RuntimeReplayObservationLedger(
                        selected_runtime_replay_path
                    ).read_latest_for_forecast(forecast_identity)
                except ValueError as exc:
                    raise HTTPException(status_code=500, detail=str(exc)) from exc
                if replay_observation is None:
                    replay_reason = "no_exact_runtime_replay_observation_for_forecast"
                elif not _replay_matches_cycle(replay_observation, record):
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "runtime replay observation does not match exact "
                            "persisted shadow cycle lineage"
                        ),
                    )
                else:
                    replay_status = "VERIFIED"
                    replay_reason = "exact_runtime_restart_replay_observed"

        return _json(
            {
                "status": "ready",
                "forecast_identity": forecast_identity,
                "cycle": record,
                "explicit_review_present": (
                    record.review_selection_identity is not None
                ),
                "journal_record_referenced": True,
                "journal_runtime_verified_here": False,
                "restart_replay_runtime_status": replay_status,
                "restart_replay_runtime_reason": replay_reason,
                "runtime_replay_observation": replay_observation,
                "semantic": "EXACT_PERSISTED_CYCLE_IDENTITY_ONLY",
                "canonical_epoch2_mutation": False,
                "production_authority": False,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/r25/operational-truth")
    def r25_operational_truth() -> JSONResponse:
        components: dict[str, object] = {}

        if selected_decision_path is None:
            components["decision_evidence"] = {
                "status": "unavailable",
                "reason": "decision_evidence_runtime_not_configured",
            }
        elif not selected_decision_path.exists():
            components["decision_evidence"] = {
                "status": "unavailable",
                "reason": "decision_evidence_runtime_evidence_missing",
            }
        else:
            try:
                decision_status = ImmutableDecisionEvidenceLedger(
                    selected_decision_path
                ).read_status()
            except DecisionLedgerConflictError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            components["decision_evidence"] = {
                "status": "ready",
                "snapshot": decision_status,
            }

        if selected_shadow_intent_path is None:
            components["shadow_intent_journal"] = {
                "status": "unavailable",
                "reason": "shadow_intent_journal_runtime_not_configured",
            }
        elif not selected_shadow_intent_path.exists():
            components["shadow_intent_journal"] = {
                "status": "unavailable",
                "reason": "shadow_intent_journal_evidence_missing",
            }
        else:
            try:
                shadow_status = R25ShadowIntentJournal(
                    selected_shadow_intent_path
                ).verify_read_only()
            except ValueError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            components["shadow_intent_journal"] = {
                "status": "ready",
                "snapshot": shadow_status,
            }

        if selected_shadow_cycle_path is None:
            components["shadow_cycle_manifest"] = {
                "status": "unavailable",
                "reason": "shadow_cycle_manifest_runtime_not_configured",
            }
        elif not selected_shadow_cycle_path.exists():
            components["shadow_cycle_manifest"] = {
                "status": "unavailable",
                "reason": "shadow_cycle_manifest_evidence_missing",
            }
        else:
            try:
                cycle_status = R25ShadowCycleManifest(
                    selected_shadow_cycle_path
                ).verify_read_only()
            except ValueError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            components["shadow_cycle_manifest"] = {
                "status": "ready",
                "snapshot": cycle_status,
            }

        if selected_runtime_replay_path is None:
            components["runtime_replay_observation"] = {
                "status": "unavailable",
                "reason": "runtime_replay_observation_not_configured",
            }
        elif not selected_runtime_replay_path.exists():
            components["runtime_replay_observation"] = {
                "status": "unavailable",
                "reason": "runtime_replay_observation_evidence_missing",
            }
        else:
            try:
                replay_status = R25RuntimeReplayObservationLedger(
                    selected_runtime_replay_path
                ).verify_read_only()
            except ValueError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            components["runtime_replay_observation"] = {
                "status": "ready",
                "snapshot": replay_status,
            }

        if selected_epoch2_path is None:
            components["canonical_epoch2"] = {
                "status": "unavailable",
                "reason": "epoch2_runtime_not_configured",
            }
        elif not selected_epoch2_path.exists():
            components["canonical_epoch2"] = {
                "status": "unavailable",
                "reason": "epoch2_runtime_evidence_missing",
            }
        else:
            try:
                epoch2_state = read_epoch2_state_read_only(selected_epoch2_path)
            except ValueError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            if epoch2_state is None:
                components["canonical_epoch2"] = {
                    "status": "unavailable",
                    "reason": "epoch2_not_activated",
                }
            else:
                components["canonical_epoch2"] = {
                    "status": "ready",
                    "activation_identity": (
                        epoch2_state.activation.activation_identity
                    ),
                    "consolidated_snapshot_identity": (
                        epoch2_state.consolidated_snapshot.snapshot_identity
                    ),
                    "nav_usdt": epoch2_state.consolidated_snapshot.nav_usdt,
                    "metrics_status": (
                        epoch2_state.consolidated_snapshot.metrics_status
                    ),
                }

        if selected_market_tape_path is None:
            components["market_tape_runtime"] = {
                "status": "unavailable",
                "reason": "market_tape_runtime_not_configured",
            }
        elif not selected_market_tape_path.exists():
            components["market_tape_runtime"] = {
                "status": "unavailable",
                "reason": "market_tape_runtime_evidence_missing",
            }
        else:
            try:
                market_tape_status = read_market_tape_runtime_truth(
                    selected_market_tape_path,
                    observed_at_ms=time.time_ns() // 1_000_000,
                )
            except (OSError, sqlite3.DatabaseError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            components["market_tape_runtime"] = {
                "status": "ready",
                "snapshot": market_tape_status,
                "online_status": "NOT_ASSERTED",
            }

        if selected_provider_divergence_path is None:
            components["provider_divergence"] = {
                "status": "unavailable",
                "reason": "provider_divergence_runtime_not_configured",
            }
        elif not selected_provider_divergence_path.exists():
            components["provider_divergence"] = {
                "status": "unavailable",
                "reason": "provider_divergence_runtime_evidence_missing",
            }
        else:
            try:
                provider_snapshots = read_provider_divergence_runtime_truth(
                    selected_provider_divergence_path,
                    observed_at_ms=time.time_ns() // 1_000_000,
                )
            except (
                OSError,
                sqlite3.DatabaseError,
                TypeError,
                ValueError,
            ) as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            components["provider_divergence"] = {
                "status": "ready" if provider_snapshots else "empty",
                "snapshot_count": len(provider_snapshots),
                "consensus_status": "NOT_INFERRED",
            }

        if selected_cold_archive_path is None:
            components["cold_archive"] = {
                "status": "unavailable",
                "reason": "cold_archive_runtime_not_configured",
            }
        elif not selected_cold_archive_path.exists():
            components["cold_archive"] = {
                "status": "unavailable",
                "reason": "cold_archive_runtime_evidence_missing",
            }
        else:
            try:
                cold_archive_status = read_cold_archive_runtime_truth(
                    selected_cold_archive_path,
                    verify_limit=1,
                )
            except (OSError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            components["cold_archive"] = {
                "status": (
                    "ready"
                    if cold_archive_status.partition_count > 0
                    else "empty"
                ),
                "snapshot": cold_archive_status,
                "archive_process_status": "NOT_MEASURED",
            }

        components["galactech_product"] = {
            "status": "exposed",
            "route": "/galactech",
            "read_only_product_api": True,
        }
        required = (
            "decision_evidence",
            "shadow_intent_journal",
            "shadow_cycle_manifest",
            "runtime_replay_observation",
            "canonical_epoch2",
        )
        all_present = all(
            _operational_component_ready(components.get(name))
            for name in required
        )

        return _json(
            {
                "status": "ready",
                "components": components,
                "all_required_runtime_evidence_present": all_present,
                "canonical_epoch2_mutation_authorized": False,
                "production_authority": False,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/market-tape-runtime/status")
    def market_tape_runtime_status(
        observed_at_ms: int | None = Query(default=None, ge=0),
    ) -> JSONResponse:
        observation = (
            time.time_ns() // 1_000_000
            if observed_at_ms is None
            else observed_at_ms
        )
        collector_runtime = None
        collector_reason: str | None = None
        collection_process_status = "NOT_MEASURED"
        if selected_market_tape_collector_runtime_path is None:
            collector_reason = "collector_runtime_not_configured"
        elif not selected_market_tape_collector_runtime_path.exists():
            collector_reason = "collector_runtime_evidence_missing"
            collection_process_status = "RUNTIME_EVIDENCE_MISSING"
        else:
            try:
                collector_runtime = read_market_tape_collector_runtime_truth(
                    selected_market_tape_collector_runtime_path,
                    observed_at_ms=observation,
                )
            except (
                OSError,
                sqlite3.DatabaseError,
                TypeError,
                ValueError,
            ) as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            if collector_runtime is None:
                collector_reason = "collector_runtime_instance_missing"
                collection_process_status = "NO_INSTANCE"
            else:
                collection_process_status = (
                    collector_runtime.process_evidence_status
                )
        if selected_market_tape_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "market_tape_runtime_not_configured",
                    "collection_process_status": collection_process_status,
                    "collector_runtime": collector_runtime,
                    "collector_runtime_reason": collector_reason,
                    "online_status": "NOT_ASSERTED",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        if not selected_market_tape_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "market_tape_runtime_evidence_missing",
                    "database_filename": selected_market_tape_path.name,
                    "collection_process_status": collection_process_status,
                    "collector_runtime": collector_runtime,
                    "collector_runtime_reason": collector_reason,
                    "online_status": "NOT_ASSERTED",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            snapshot = read_market_tape_runtime_truth(
                selected_market_tape_path,
                observed_at_ms=observation,
            )
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready",
                "snapshot": snapshot,
                "database_filename": selected_market_tape_path.name,
                "collection_process_status": collection_process_status,
                "collector_runtime": collector_runtime,
                "collector_runtime_reason": collector_reason,
                "online_status": "NOT_ASSERTED",
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/provider-divergence/status")
    def provider_divergence_status(
        observed_at_ms: int | None = Query(default=None, ge=0),
    ) -> JSONResponse:
        observation = (
            time.time_ns() // 1_000_000
            if observed_at_ms is None
            else observed_at_ms
        )
        if selected_provider_divergence_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "provider_divergence_runtime_not_configured",
                    "snapshots": [],
                    "consensus_status": "NOT_INFERRED",
                    "runtime_status": "PERSISTED_EVIDENCE_ONLY",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        if not selected_provider_divergence_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "provider_divergence_runtime_evidence_missing",
                    "database_filename": (
                        selected_provider_divergence_path.name
                    ),
                    "snapshots": [],
                    "consensus_status": "NOT_INFERRED",
                    "runtime_status": "PERSISTED_EVIDENCE_ONLY",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            snapshots = read_provider_divergence_runtime_truth(
                selected_provider_divergence_path,
                observed_at_ms=observation,
            )
        except (
            OSError,
            sqlite3.DatabaseError,
            TypeError,
            ValueError,
        ) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready" if snapshots else "empty",
                "database_filename": selected_provider_divergence_path.name,
                "observed_at_ms": observation,
                "snapshots": snapshots,
                "consensus_status": "NOT_INFERRED",
                "runtime_status": "PERSISTED_EVIDENCE_ONLY",
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/event-source-runtime/status")
    def event_source_runtime_status(
        observed_at_ms: int | None = Query(default=None, ge=0),
    ) -> JSONResponse:
        observation = (
            time.time_ns() // 1_000_000
            if observed_at_ms is None
            else observed_at_ms
        )
        if selected_event_source_runtime_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "event_source_runtime_not_configured",
                    "runtime_status": "NOT_EXPOSED",
                    "online_status": "NOT_ASSERTED",
                    "process_status": "NOT_MEASURED",
                    "coverage_claim": "SOURCE_SCOPED_ONLY",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        if not selected_event_source_runtime_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "event_source_runtime_evidence_missing",
                    "database_filename": selected_event_source_runtime_path.name,
                    "runtime_status": "NOT_EXPOSED",
                    "online_status": "NOT_ASSERTED",
                    "process_status": "NOT_MEASURED",
                    "coverage_claim": "SOURCE_SCOPED_ONLY",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            snapshot = read_event_source_runtime_truth(
                selected_event_source_runtime_path,
                observed_at_ms=observation,
            )
        except (
            OSError,
            sqlite3.DatabaseError,
            TypeError,
            ValueError,
        ) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready",
                "database_filename": selected_event_source_runtime_path.name,
                "observed_at_ms": observation,
                "snapshot": snapshot,
                "runtime_status": snapshot.runtime_status,
                "online_status": snapshot.online_status,
                "process_status": snapshot.process_status,
                "coverage_claim": snapshot.coverage_claim,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/cold-archive/status")
    def cold_archive_status(
        verify_limit: int = Query(default=24, ge=1, le=500),
        canonical_replay_limit: int = Query(default=3, ge=1, le=500),
    ) -> JSONResponse:
        if selected_cold_archive_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "cold_archive_runtime_not_configured",
                    "archive_process_status": "NOT_MEASURED",
                    "canonical_row_digest_replay": "NOT_MEASURED",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        if not selected_cold_archive_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "cold_archive_runtime_evidence_missing",
                    "archive_directory": selected_cold_archive_path.name,
                    "archive_process_status": "NOT_MEASURED",
                    "canonical_row_digest_replay": "NOT_MEASURED",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            snapshot = read_cold_archive_runtime_truth(
                selected_cold_archive_path,
                verify_limit=verify_limit,
                canonical_replay_limit=canonical_replay_limit,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": (
                    "ready" if snapshot.partition_count > 0 else "empty"
                ),
                "snapshot": snapshot,
                "archive_directory": selected_cold_archive_path.name,
                "archive_process_status": "NOT_MEASURED",
                "canonical_row_digest_replay": (
                    snapshot.canonical_row_digest_replay
                ),
                "canonical_replay_verified_partition_count": (
                    snapshot.canonical_replay_verified_partition_count
                ),
                "canonical_replay_scope": snapshot.canonical_replay_scope,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/alerts")
    def alerts(
        limit: int = Query(default=100, ge=1, le=500),
    ) -> JSONResponse:
        try:
            return _json(reader.alert_center(limit=limit))
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/education")
    def education_catalog() -> JSONResponse:
        return _json(
            {
                "status": "ready",
                "real_capital": 0,
                "lessons": [
                    _education_payload(lesson)
                    for lesson in all_education_lessons()
                ],
            }
        )

    @app.get("/api/education/{concept_id}")
    def education_lesson(concept_id: str) -> JSONResponse:
        result = lookup_education_lesson(concept_id)
        if isinstance(result, EducationLookupMissing):
            raise HTTPException(
                status_code=404,
                detail=f"unknown education concept id: {result.requested_id}",
            )
        return _json(
            {
                "status": "found",
                "real_capital": 0,
                "lesson": _education_payload(result.lesson),
            }
        )

    @app.get("/api/paper/epoch-contract")
    def paper_epoch_contract() -> JSONResponse:
        current_epoch = current_paper_epoch_spec()
        configured_name = (
            None if selected_paper_path is None else selected_paper_path.name
        )
        epoch2_name_matches = configured_name == EPOCH_2_LEDGER_FILENAME
        return _json(
            {
                "status": "ready",
                "legacy_epoch": _paper_epoch_payload(EPOCH_1_SPEC),
                "current_program": _paper_epoch_payload(current_epoch),
                "runtime_binding": {
                    "configured": selected_paper_path is not None,
                    "ledger_filename": configured_name,
                    "ledger_present": (
                        selected_paper_path is not None
                        and selected_paper_path.exists()
                    ),
                    "matches_current_epoch_ledger_filename": epoch2_name_matches,
                    "activation_status": (
                        "EPOCH2_PATH_CONFIGURED_UNVERIFIED"
                        if epoch2_name_matches
                        else "EPOCH2_NOT_ACTIVE_ON_THIS_RUNTIME"
                    ),
                },
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/paper/epoch2-state")
    def paper_epoch2_state() -> JSONResponse:
        if selected_epoch2_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "epoch2_runtime_not_configured",
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        if not selected_epoch2_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "epoch2_runtime_evidence_missing",
                    "ledger_filename": selected_epoch2_path.name,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            state = read_epoch2_state_read_only(selected_epoch2_path)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if state is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "epoch2_not_activated",
                    "ledger_filename": selected_epoch2_path.name,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        return _json(
            {
                "status": "ready",
                "activation": state.activation,
                "vaults": state.vault_snapshots,
                "consolidated": state.consolidated_snapshot,
                "ledger_filename": selected_epoch2_path.name,
                "read_only": True,
                "real_capital": state.activation.real_capital,
            }
        )

    @app.get("/api/paper/mission-control")
    def paper_mission_control(
        observed_at_ms: int | None = Query(default=None, ge=0),
    ) -> JSONResponse:
        if selected_paper_path is None or selected_candle_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "paper_runtime_not_configured",
                    "trade_policy": "NOT_ACTIVATED",
                    "real_capital": 0,
                    "read_only": True,
                }
            )
        if (
            not selected_path.exists()
            or not selected_paper_path.exists()
            or not selected_candle_path.exists()
        ):
            return _json(
                {
                    "status": "unavailable",
                    "reason": "paper_runtime_evidence_missing",
                    "trade_policy": "NOT_ACTIVATED",
                    "real_capital": 0,
                    "read_only": True,
                }
            )
        observation = (
            time.time_ns() // 1_000_000
            if observed_at_ms is None
            else observed_at_ms
        )
        try:
            snapshot = read_paper_mission_control_snapshot(
                paper_ledger_path=selected_paper_path,
                signal_ledger_path=selected_path,
                candle_cache_path=selected_candle_path,
                observed_at_ms=observation,
                max_candidates=100,
            )
        except (PaperMissionControlError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready",
                "snapshot": snapshot,
                "trade_policy": snapshot.trade_policy,
                "real_capital": snapshot.real_capital,
                "read_only": True,
            }
        )

    @app.get("/api/intelligence-center")
    def intelligence_center(
        observed_at_ms: int | None = Query(default=None, ge=0),
    ) -> JSONResponse:
        observation = (
            time.time_ns() // 1_000_000
            if observed_at_ms is None
            else observed_at_ms
        )
        try:
            return _json(
                build_intelligence_center_payload(
                    selected_learning_memory_path,
                    observed_at_ms=observation,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/performance")
    def performance() -> JSONResponse:
        try:
            return _json(reader.performance_availability())
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()
