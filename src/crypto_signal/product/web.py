from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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
from crypto_signal.product.intelligence_stream_exact_evidence import (
    IntelligenceStreamExactEvidenceReadModel,
    StreamExactEvidenceError,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamMessageQuery,
    StreamReadModelError,
    decode_stream_cursor,
)
from crypto_signal.product.intelligence_stream_transport import (
    encode_stream_sse_event,
    encode_stream_sse_heartbeat,
    encode_stream_sse_retry,
    read_stream_live_batch,
    resolve_stream_resume_cursor,
)
from crypto_signal.product.intelligence_stream_visual_proof import (
    IntelligenceStreamVisualProofReadModel,
    StreamVisualProofError,
)
from crypto_signal.product.market_tape_runtime import (
    read_cold_archive_runtime_truth,
    read_market_tape_collector_runtime_truth,
    read_market_tape_runtime_truth,
)
from crypto_signal.product.provider_divergence_runtime import (
    read_provider_divergence_runtime_truth,
)
from crypto_signal.product.reader import DashboardReader, DashboardReadError
from crypto_signal.product.wc5_actionability import read_wc5_actionability

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
DEFAULT_STREAM_LEDGER_PATH = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "stream"
    / "intelligence_stream.sqlite3"
)
DEFAULT_FROZEN_PROOF_STORE_PATH = DEFAULT_STREAM_LEDGER_PATH.with_name(
    "frozen_proofs.sqlite3"
)
DEFAULT_OPTIONS_SURFACE_PATH = (
    DEFAULT_STREAM_LEDGER_PATH.parent.parent
    / "market_tape"
    / "options_surface.sqlite3"
)
DEFAULT_ONCHAIN_CAPITAL_FLOW_PATH = (
    DEFAULT_STREAM_LEDGER_PATH.parent.parent
    / "onchain"
    / "onchain_capital_flow.sqlite3"
)
DEFAULT_ONCHAIN_SOURCE_CONTRACT_PATH = (
    DEFAULT_STREAM_LEDGER_PATH.parent.parent
    / "onchain"
    / "source_contract.sqlite3"
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
DEFAULT_WC2_COHORT_PATH = (
    DEFAULT_LEDGER_PATH.parent.parent
    / "wc2"
    / "wc2_untouched_forward.sqlite3"
)
STATIC_DIR = Path(__file__).with_name("static")
GALACTECH_DIR = Path(__file__).with_name("galactech")
STREAM_DIR = Path(__file__).with_name("stream")
PRODUCT_ROOT_GALACTECH = "galactech"
PRODUCT_ROOT_STREAM = "stream"
PRODUCT_ROOT_CHOICES = (PRODUCT_ROOT_GALACTECH, PRODUCT_ROOT_STREAM)
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
    wc2_cohort_path: Path | None = None,
    stream_ledger_path: Path | None = None,
    frozen_proof_store_path: Path | None = None,
    product_root: str | None = None,
    options_surface_path: Path | None = None,
    onchain_capital_flow_path: Path | None = None,
    onchain_source_contract_path: Path | None = None,
) -> FastAPI:
    selected_path = ledger_path or Path(
        os.environ.get("CRYPTO_SIGNAL_LEDGER_PATH", str(DEFAULT_LEDGER_PATH))
    )
    selected_product_root = (
        product_root
        if product_root is not None
        else os.environ.get(
            "CRYPTO_SIGNAL_PRODUCT_ROOT",
            PRODUCT_ROOT_GALACTECH,
        )
    )
    if selected_product_root not in PRODUCT_ROOT_CHOICES:
        raise ValueError(
            "product_root must be one of: "
            + ", ".join(PRODUCT_ROOT_CHOICES)
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

    if stream_ledger_path is not None:
        selected_stream_path: Path | None = stream_ledger_path
    elif ledger_path is None:
        selected_stream_path = Path(
            os.environ.get(
                "CRYPTO_SIGNAL_STREAM_LEDGER_PATH",
                str(DEFAULT_STREAM_LEDGER_PATH),
            )
        )
    else:
        selected_stream_path = None

    if frozen_proof_store_path is not None:
        selected_frozen_proof_store_path: Path | None = (
            frozen_proof_store_path
        )
    elif stream_ledger_path is not None:
        selected_frozen_proof_store_path = stream_ledger_path.with_name(
            "frozen_proofs.sqlite3"
        )
    elif ledger_path is None:
        frozen_proof_env = os.environ.get(
            "CRYPTO_SIGNAL_FROZEN_PROOF_STORE_PATH"
        )
        selected_frozen_proof_store_path = (
            Path(frozen_proof_env)
            if frozen_proof_env
            else DEFAULT_FROZEN_PROOF_STORE_PATH
        )
    else:
        selected_frozen_proof_store_path = None

    if options_surface_path is not None:
        selected_options_surface_path: Path | None = options_surface_path
    elif ledger_path is None:
        options_surface_env = os.environ.get(
            "CRYPTO_SIGNAL_OPTIONS_SURFACE_PATH"
        )
        selected_options_surface_path = (
            Path(options_surface_env)
            if options_surface_env
            else DEFAULT_OPTIONS_SURFACE_PATH
        )
    else:
        selected_options_surface_path = None

    if onchain_capital_flow_path is not None:
        selected_onchain_capital_flow_path: Path | None = (
            onchain_capital_flow_path
        )
    elif ledger_path is None:
        onchain_flow_env = os.environ.get(
            "CRYPTO_SIGNAL_ONCHAIN_CAPITAL_FLOW_PATH"
        )
        selected_onchain_capital_flow_path = (
            Path(onchain_flow_env)
            if onchain_flow_env
            else DEFAULT_ONCHAIN_CAPITAL_FLOW_PATH
        )
    else:
        selected_onchain_capital_flow_path = None

    if onchain_source_contract_path is not None:
        selected_onchain_source_contract_path: Path | None = (
            onchain_source_contract_path
        )
    elif ledger_path is None:
        onchain_source_env = os.environ.get(
            "CRYPTO_SIGNAL_ONCHAIN_SOURCE_CONTRACT_PATH"
        )
        selected_onchain_source_contract_path = (
            Path(onchain_source_env)
            if onchain_source_env
            else DEFAULT_ONCHAIN_SOURCE_CONTRACT_PATH
        )
    else:
        selected_onchain_source_contract_path = None

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

    if wc2_cohort_path is not None:
        selected_wc2_cohort_path: Path | None = wc2_cohort_path
    elif ledger_path is None:
        wc2_cohort_env = os.environ.get("CRYPTO_SIGNAL_WC2_COHORT_PATH")
        selected_wc2_cohort_path = (
            Path(wc2_cohort_env)
            if wc2_cohort_env
            else DEFAULT_WC2_COHORT_PATH
        )
    else:
        selected_wc2_cohort_path = None

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
    app.state.frozen_proof_store_path = selected_frozen_proof_store_path
    app.state.wc2_cohort_path = selected_wc2_cohort_path
    app.state.product_root = selected_product_root
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
    app.mount(
        "/stream-static",
        StaticFiles(directory=str(STREAM_DIR)),
        name="stream-static",
    )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        root_dir = (
            STREAM_DIR
            if selected_product_root == PRODUCT_ROOT_STREAM
            else GALACTECH_DIR
        )
        return FileResponse(root_dir / "index.html")

    @app.get("/galactech", include_in_schema=False)
    def galactech_preview() -> FileResponse:
        return FileResponse(GALACTECH_DIR / "index.html")

    @app.get("/stream-preview", include_in_schema=False)
    def stream_preview() -> FileResponse:
        return FileResponse(STREAM_DIR / "index.html")

    @app.get("/stream-evidence", include_in_schema=False)
    def stream_evidence_window() -> FileResponse:
        return FileResponse(STREAM_DIR / "evidence.html")

    @app.get("/legacy", include_in_schema=False)
    def legacy_product() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "product_version": PRODUCT_VERSION,
            "product_root": selected_product_root,
            "stream_root_active": selected_product_root == PRODUCT_ROOT_STREAM,
            "stream_preview_route": "/stream-preview",
            "galactech_fallback_route": "/galactech",
            "legacy_route": "/legacy",
            "rollback_mode": PRODUCT_ROOT_GALACTECH,
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

    @app.get("/api/decision-proof/forecast/{forecast_identity}")
    def decision_proof_for_forecast(forecast_identity: str) -> JSONResponse:
        if not _is_lower_sha256(forecast_identity):
            raise HTTPException(
                status_code=400,
                detail="forecast_identity must be lowercase SHA256",
            )
        if selected_decision_path is None or not selected_decision_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "decision_evidence_runtime_not_configured",
                    "forecast_identity": forecast_identity,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            proof = ImmutableDecisionEvidenceLedger(
                selected_decision_path
            ).read_proof_for_forecast(forecast_identity)
        except DecisionLedgerConflictError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if proof is None:
            return _json(
                {
                    "status": "empty",
                    "reason": "no_persisted_decision_proof_for_forecast",
                    "forecast_identity": forecast_identity,
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

    @app.get("/api/stream/messages")
    def stream_messages(
        limit: int = Query(default=50, ge=1, le=200),
        before: str | None = Query(default=None, max_length=512),
        after: str | None = Query(default=None, max_length=512),
        symbol: str | None = Query(default=None, min_length=1, max_length=32),
        timeframe: str | None = Query(default=None, min_length=1, max_length=16),
        story_identity: str | None = Query(default=None, min_length=64, max_length=64),
        source_kind: str | None = Query(default=None, min_length=1, max_length=64),
        effective_stance: str | None = Query(default=None, min_length=1, max_length=32),
        category: str | None = Query(default=None, min_length=1, max_length=64),
        importance: str | None = Query(default=None, min_length=1, max_length=64),
        vault: str | None = Query(default=None, min_length=1, max_length=64),
        state: str | None = Query(default=None, min_length=1, max_length=64),
        evidence_domain: str | None = Query(default=None, min_length=1, max_length=64),
        from_ms: int | None = Query(default=None, ge=0),
        to_ms: int | None = Query(default=None, ge=0),
        text: str | None = Query(default=None, min_length=1, max_length=200),
        surface: Literal["all", "primary"] = Query(default="all"),
    ) -> JSONResponse:
        if selected_stream_path is None or not selected_stream_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "intelligence_stream_runtime_not_configured",
                    "page": {
                        "items": [],
                        "order": "newest_to_oldest",
                        "newest_cursor": None,
                        "oldest_cursor": None,
                        "next_after_cursor": None,
                        "next_before_cursor": None,
                        "has_more": False,
                        "read_only": True,
                        "real_capital": 0,
                        "schema_version": "intelligence-stream-read-model-v1/1",
                    },
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            before_cursor = None if before is None else decode_stream_cursor(before)
            after_cursor = None if after is None else decode_stream_cursor(after)
            query = StreamMessageQuery(
                limit=limit,
                before=before_cursor,
                after=after_cursor,
                symbol=symbol,
                timeframe=timeframe,
                story_identity=story_identity,
                source_kind=source_kind,
                effective_stance=effective_stance,
                category=category,
                importance=importance,
                vault=vault,
                state=state,
                evidence_domain=evidence_domain,
                from_ms=from_ms,
                to_ms=to_ms,
                text=text,
                primary_surface=surface == "primary",
            )
        except (StreamReadModelError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            page = IntelligenceStreamReadModel(selected_stream_path).read_messages(query)
        except StreamReadModelError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready" if page.items else "empty",
                "page": page,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/stream/live")
    async def stream_live(
        request: Request,
        after: str | None = Query(default=None, max_length=512),
        last_event_id: str | None = Header(
            default=None,
            alias="Last-Event-ID",
            max_length=512,
        ),
        batch_limit: int = Query(default=200, ge=1, le=200),
        symbol: str | None = Query(default=None, min_length=1, max_length=32),
        timeframe: str | None = Query(default=None, min_length=1, max_length=16),
        story_identity: str | None = Query(default=None, min_length=64, max_length=64),
        source_kind: str | None = Query(default=None, min_length=1, max_length=64),
        effective_stance: str | None = Query(default=None, min_length=1, max_length=32),
        category: str | None = Query(default=None, min_length=1, max_length=64),
        importance: str | None = Query(default=None, min_length=1, max_length=64),
        vault: str | None = Query(default=None, min_length=1, max_length=64),
        state: str | None = Query(default=None, min_length=1, max_length=64),
        evidence_domain: str | None = Query(default=None, min_length=1, max_length=64),
        from_ms: int | None = Query(default=None, ge=0),
        to_ms: int | None = Query(default=None, ge=0),
        text: str | None = Query(default=None, min_length=1, max_length=200),
        surface: Literal["all", "primary"] = Query(default="all"),
        follow: bool = Query(default=True),
    ) -> StreamingResponse:
        if selected_stream_path is None or not selected_stream_path.exists():
            raise HTTPException(
                status_code=503,
                detail="intelligence_stream_runtime_not_configured",
            )
        reader = IntelligenceStreamReadModel(selected_stream_path)
        try:
            query = StreamMessageQuery(
                limit=batch_limit,
                symbol=symbol,
                timeframe=timeframe,
                story_identity=story_identity,
                source_kind=source_kind,
                effective_stance=effective_stance,
                category=category,
                importance=importance,
                vault=vault,
                state=state,
                evidence_domain=evidence_domain,
                from_ms=from_ms,
                to_ms=to_ms,
                text=text,
                primary_surface=surface == "primary",
            )
            initial_cursor = resolve_stream_resume_cursor(
                reader=reader,
                after=after,
                last_event_id=last_event_id,
            )
        except (StreamReadModelError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        async def event_stream() -> AsyncIterator[str]:
            cursor = initial_cursor
            last_heartbeat_at = time.monotonic()
            yield encode_stream_sse_retry()
            while True:
                if await request.is_disconnected():
                    return
                try:
                    batch = read_stream_live_batch(
                        reader,
                        query,
                        after_cursor=cursor,
                    )
                except StreamReadModelError as exc:
                    yield f"event: error\\ndata: {{\"detail\":\"{exc!s}\"}}\\n\\n"
                    return

                if batch.events:
                    for event in batch.events:
                        yield encode_stream_sse_event(event)
                        cursor = event.event_id
                    last_heartbeat_at = time.monotonic()
                    if batch.has_more:
                        continue
                    if not follow:
                        return
                elif not follow:
                    return

                now = time.monotonic()
                if now - last_heartbeat_at >= 15.0:
                    yield encode_stream_sse_heartbeat(
                        now_ms=int(time.time() * 1000)
                    )
                    last_heartbeat_at = now
                await asyncio.sleep(1.0)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/stream/messages/{narrative_identity}/evidence")
    def stream_message_exact_evidence(
        narrative_identity: str,
    ) -> JSONResponse:
        if not _is_lower_sha256(narrative_identity):
            raise HTTPException(
                status_code=400,
                detail="narrative_identity must be lowercase SHA256",
            )
        if selected_stream_path is None or not selected_stream_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "intelligence_stream_runtime_not_configured",
                    "narrative_identity": narrative_identity,
                    "evidence": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            evidence = IntelligenceStreamExactEvidenceReadModel(
                stream_ledger_path=selected_stream_path,
                signal_ledger_path=(
                    selected_path if selected_path.exists() else None
                ),
                decision_evidence_path=(
                    selected_decision_path
                    if selected_decision_path is not None
                    and selected_decision_path.exists()
                    else None
                ),
                market_tape_path=selected_market_tape_path,
                event_source_runtime_path=selected_event_source_runtime_path,
                provider_divergence_path=selected_provider_divergence_path,
                frozen_proof_store_path=selected_frozen_proof_store_path,
                options_surface_path=selected_options_surface_path,
                onchain_capital_flow_path=selected_onchain_capital_flow_path,
                onchain_source_contract_path=(
                    selected_onchain_source_contract_path
                ),
            ).read_for_narrative(narrative_identity)
        except StreamExactEvidenceError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if evidence is None:
            return _json(
                {
                    "status": "empty",
                    "reason": "stream_message_not_found",
                    "narrative_identity": narrative_identity,
                    "evidence": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        return _json(
            {
                "status": "ready",
                "narrative_identity": narrative_identity,
                "evidence": evidence,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get(
        "/api/stream/messages/{narrative_identity}/evidence/{evidence_identity}"
    )
    def stream_message_exact_evidence_reference(
        narrative_identity: str,
        evidence_identity: str,
    ) -> JSONResponse:
        if not _is_lower_sha256(narrative_identity):
            raise HTTPException(
                status_code=400,
                detail="narrative_identity must be lowercase SHA256",
            )
        if not _is_lower_sha256(evidence_identity):
            raise HTTPException(
                status_code=400,
                detail="evidence_identity must be lowercase SHA256",
            )
        if selected_stream_path is None or not selected_stream_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "intelligence_stream_runtime_not_configured",
                    "narrative_identity": narrative_identity,
                    "evidence_identity": evidence_identity,
                    "reference": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            reference = IntelligenceStreamExactEvidenceReadModel(
                stream_ledger_path=selected_stream_path,
                signal_ledger_path=(
                    selected_path if selected_path.exists() else None
                ),
                decision_evidence_path=(
                    selected_decision_path
                    if selected_decision_path is not None
                    and selected_decision_path.exists()
                    else None
                ),
                market_tape_path=selected_market_tape_path,
                event_source_runtime_path=selected_event_source_runtime_path,
                provider_divergence_path=selected_provider_divergence_path,
                frozen_proof_store_path=selected_frozen_proof_store_path,
                options_surface_path=selected_options_surface_path,
                onchain_capital_flow_path=selected_onchain_capital_flow_path,
                onchain_source_contract_path=(
                    selected_onchain_source_contract_path
                ),
            ).read_reference(
                narrative_identity=narrative_identity,
                evidence_identity=evidence_identity,
            )
        except StreamExactEvidenceError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if reference is None:
            return _json(
                {
                    "status": "empty",
                    "reason": "stream_message_not_found",
                    "narrative_identity": narrative_identity,
                    "evidence_identity": evidence_identity,
                    "reference": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        return _json(
            {
                "status": str(reference.get("status", "ready")),
                "narrative_identity": narrative_identity,
                "evidence_identity": evidence_identity,
                "reference": reference,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/stream/messages/{narrative_identity}/visual-proof")
    def stream_message_visual_proof(narrative_identity: str) -> JSONResponse:
        if not _is_lower_sha256(narrative_identity):
            raise HTTPException(
                status_code=400,
                detail="narrative_identity must be lowercase SHA256",
            )
        if selected_stream_path is None or not selected_stream_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "intelligence_stream_runtime_not_configured",
                    "narrative_identity": narrative_identity,
                    "visual_proof": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        if selected_decision_path is None or not selected_decision_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "decision_evidence_runtime_not_configured",
                    "narrative_identity": narrative_identity,
                    "visual_proof": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            visual_proof = IntelligenceStreamVisualProofReadModel(
                stream_ledger_path=selected_stream_path,
                signal_ledger_path=selected_path,
                decision_evidence_path=selected_decision_path,
            ).read_for_narrative(narrative_identity)
        except StreamVisualProofError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if visual_proof is None:
            return _json(
                {
                    "status": "empty",
                    "reason": "stream_message_not_found",
                    "narrative_identity": narrative_identity,
                    "visual_proof": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        status = str(visual_proof.get("status", "unavailable"))
        return _json(
            {
                "status": status,
                "narrative_identity": narrative_identity,
                "visual_proof": visual_proof,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/stream/messages/{narrative_identity}/detail")
    def stream_message_detail(narrative_identity: str) -> JSONResponse:
        if not _is_lower_sha256(narrative_identity):
            raise HTTPException(
                status_code=400,
                detail="narrative_identity must be lowercase SHA256",
            )
        if selected_stream_path is None or not selected_stream_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "intelligence_stream_runtime_not_configured",
                    "narrative_identity": narrative_identity,
                    "detail": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            detail = IntelligenceStreamReadModel(
                selected_stream_path
            ).read_message_detail(narrative_identity)
        except StreamReadModelError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready" if detail is not None else "empty",
                "narrative_identity": narrative_identity,
                "detail": detail,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/stream/messages/{narrative_identity}")
    def stream_message_lookup(narrative_identity: str) -> JSONResponse:
        if not _is_lower_sha256(narrative_identity):
            raise HTTPException(
                status_code=400,
                detail="narrative_identity must be lowercase SHA256",
            )
        if selected_stream_path is None or not selected_stream_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "intelligence_stream_runtime_not_configured",
                    "narrative_identity": narrative_identity,
                    "message": None,
                    "read_only": True,
                    "real_capital": 0,
                }
            )
        try:
            message = IntelligenceStreamReadModel(
                selected_stream_path
            ).read_message(narrative_identity)
        except StreamReadModelError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": "ready" if message is not None else "empty",
                "narrative_identity": narrative_identity,
                "message": message,
                "read_only": True,
                "real_capital": 0,
            }
        )

    @app.get("/api/wc2/action/{forecast_identity}")
    def wc2_actionability(forecast_identity: str) -> JSONResponse:
        if not _is_lower_sha256(forecast_identity):
            raise HTTPException(
                status_code=400,
                detail="forecast_identity must be lowercase SHA256",
            )
        if selected_wc2_cohort_path is None:
            return _json(
                {
                    "status": "unavailable",
                    "reason": "wc2_cohort_runtime_not_configured",
                    "forecast_identity": forecast_identity,
                    "semantic": "EXACT_PERSISTED_WC2_COHORT_ACTION_ONLY",
                    "read_only": True,
                    "production_authority": False,
                    "real_capital": 0,
                }
            )
        if not selected_wc2_cohort_path.exists():
            return _json(
                {
                    "status": "unavailable",
                    "reason": "wc2_cohort_runtime_evidence_missing",
                    "forecast_identity": forecast_identity,
                    "semantic": "EXACT_PERSISTED_WC2_COHORT_ACTION_ONLY",
                    "read_only": True,
                    "production_authority": False,
                    "real_capital": 0,
                }
            )
        try:
            snapshot = read_wc5_actionability(
                selected_wc2_cohort_path,
                forecast_identity=forecast_identity,
            )
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _json(
            {
                "status": (
                    "empty"
                    if snapshot.status.value == "NO_COHORT_FORECAST"
                    else "ready"
                ),
                "snapshot": snapshot,
                "semantic": "EXACT_PERSISTED_WC2_COHORT_ACTION_ONLY",
                "read_only": True,
                "production_authority": False,
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
            components["market_tape_runtime"] = {
                "status": "delegated",
                "reason": (
                    "detailed_market_tape_verification_delegated_to_"
                    "dedicated_endpoint"
                ),
                "verification_endpoint": "/api/market-tape-runtime/status",
                "runtime_evidence_present": True,
                "online_status": "NOT_ASSERTED",
                "read_only": True,
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
        scope: Literal["full", "collector"] = Query(default="full"),
    ) -> JSONResponse:
        requested_observation = observed_at_ms
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
                    observed_at_ms=requested_observation,
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
        if scope == "collector":
            return _json(
                {
                    "status": (
                        "ready"
                        if collector_runtime is not None
                        else "unavailable"
                    ),
                    "scope": "collector",
                    "collection_process_status": collection_process_status,
                    "collector_runtime": collector_runtime,
                    "collector_runtime_reason": collector_reason,
                    "online_status": "NOT_ASSERTED",
                    "read_only": True,
                    "real_capital": 0,
                }
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
                observed_at_ms=requested_observation,
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
