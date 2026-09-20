from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from crypto_signal.ledger.serialization import canonicalize
from crypto_signal.product.reader import DashboardReader, DashboardReadError

DEFAULT_LEDGER_PATH = (
    Path("/Users/crypto-signal-agent/Crypto-Signal")
    / "runtime"
    / "ledger"
    / "live_signal_ledger.sqlite3"
)
STATIC_DIR = Path(__file__).with_name("static")
PRODUCT_VERSION = "dashboard-v1-slice2/1"


def _json(value: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=canonicalize(value), status_code=status_code)


def create_app(ledger_path: Path | None = None) -> FastAPI:
    selected_path = ledger_path or Path(
        os.environ.get("CRYPTO_SIGNAL_LEDGER_PATH", str(DEFAULT_LEDGER_PATH))
    )
    reader = DashboardReader(selected_path)

    app = FastAPI(
        title="Crypto Signal Mission Control",
        version=PRODUCT_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.ledger_path = selected_path
    app.state.reader = reader

    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "product_version": PRODUCT_VERSION,
            "real_capital": 0,
            "ledger_present": selected_path.exists(),
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

    @app.get("/api/signals/{signal_freeze_identity}")
    def signal_detail(signal_freeze_identity: str) -> JSONResponse:
        try:
            return _json(reader.signal_detail(signal_freeze_identity))
        except DashboardReadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
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
