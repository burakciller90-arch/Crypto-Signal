from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
from crypto_signal.product.education import (
    EducationLesson,
    EducationLookupMissing,
    all_education_lessons,
    lookup_education_lesson,
)
from crypto_signal.product.intelligence_center import build_intelligence_center_payload
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
DEFAULT_CANDLE_CACHE_PATH = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "data"
    / "live_base_15m_cache.sqlite3"
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


def create_app(
    ledger_path: Path | None = None,
    alert_outbox_path: Path | None = None,
    paper_ledger_path: Path | None = None,
    candle_cache_path: Path | None = None,
    learning_memory_path: Path | None = None,
    epoch2_ledger_path: Path | None = None,
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
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/galactech", include_in_schema=False)
    def galactech_preview() -> FileResponse:
        return FileResponse(GALACTECH_DIR / "index.html")

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
