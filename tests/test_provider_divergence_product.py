from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crypto_signal.data.models import (
    Candle,
    DataSource,
    Exchange,
    MarketType,
)
from crypto_signal.data.provider_divergence import (
    ProviderDivergenceStore,
    build_provider_divergence_snapshot,
)
from crypto_signal.product.provider_divergence_runtime import (
    read_provider_divergence_runtime_truth,
)
from crypto_signal.product.web import create_app


def _candle(exchange: Exchange, open_time_ms: int, close: str) -> Candle:
    value = Decimal(close)
    close_time_ms = open_time_ms + 899_999
    return Candle(
        exchange=exchange,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=value,
        high=value + Decimal(1),
        low=value - Decimal(1),
        close=value,
        volume=Decimal(1),
        quote_volume=Decimal(100),
        trade_count=1 if exchange is Exchange.BINANCE else None,
        is_closed=True,
        source=DataSource.REST,
        source_timestamp_ms=close_time_ms + 10,
        ingested_at_ms=close_time_ms + 20,
        adapter_version=f"{exchange.value}-test/1",
    )


def _seed(path: Path, *, observed_at_ms: int = 1_000_000) -> None:
    snapshot = build_provider_divergence_snapshot(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        timeframe="15m",
        observed_at_ms=observed_at_ms,
        left_exchange=Exchange.BINANCE,
        right_exchange=Exchange.BYBIT,
        left_candles=(_candle(Exchange.BINANCE, 0, "100"),),
        right_candles=(_candle(Exchange.BYBIT, 0, "100.1"),),
        lookback_limit=96,
    )
    ProviderDivergenceStore(path).append(snapshot)


def test_provider_divergence_product_reader_is_read_only_and_hash_verified(
    tmp_path: Path,
) -> None:
    path = tmp_path / "provider_divergence.sqlite3"
    _seed(path)
    before = path.read_bytes()

    snapshots = read_provider_divergence_runtime_truth(
        path,
        observed_at_ms=1_100_000,
    )

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.market_type == "spot"
    assert snapshot.timeframe == "15m"
    assert snapshot.observation_age_ms == 100_000
    assert snapshot.left_exchange == "binance"
    assert snapshot.right_exchange == "bybit"
    assert snapshot.overlap_count == 1
    assert snapshot.grid_state == "full_overlap"
    assert snapshot.consensus_status == "NOT_INFERRED"
    assert snapshot.read_only_verified is True
    assert snapshot.production_authority is False
    assert snapshot.real_capital == 0
    assert path.read_bytes() == before


def test_provider_divergence_product_reader_is_point_in_time(tmp_path: Path) -> None:
    path = tmp_path / "provider_divergence.sqlite3"
    _seed(path, observed_at_ms=1_000_000)
    _seed(path, observed_at_ms=2_000_000)

    historical = read_provider_divergence_runtime_truth(
        path,
        observed_at_ms=1_500_000,
    )
    latest = read_provider_divergence_runtime_truth(
        path,
        observed_at_ms=2_100_000,
    )

    assert historical[0].observed_at_ms == 1_000_000
    assert latest[0].observed_at_ms == 2_000_000


def test_provider_divergence_product_reader_fails_on_payload_tamper(
    tmp_path: Path,
) -> None:
    path = tmp_path / "provider_divergence.sqlite3"
    _seed(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER provider_divergence_no_update")
        db.execute(
            "UPDATE provider_divergence_snapshots "
            "SET payload_json='{}'"
        )

    with pytest.raises(ValueError, match="payload identity mismatch"):
        read_provider_divergence_runtime_truth(
            path,
            observed_at_ms=1_100_000,
        )


def test_provider_divergence_missing_runtime_creates_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.sqlite3"

    with pytest.raises(ValueError, match="missing"):
        read_provider_divergence_runtime_truth(
            path,
            observed_at_ms=1_100_000,
        )

    assert not path.exists()


def test_provider_divergence_endpoint_exposes_persisted_truth_without_consensus(
    tmp_path: Path,
) -> None:
    path = tmp_path / "provider_divergence.sqlite3"
    _seed(path)
    before = path.read_bytes()
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            provider_divergence_path=path,
        )
    )

    response = client.get(
        "/api/provider-divergence/status?observed_at_ms=1100000"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database_filename"] == "provider_divergence.sqlite3"
    assert body["consensus_status"] == "NOT_INFERRED"
    assert body["runtime_status"] == "PERSISTED_EVIDENCE_ONLY"
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert len(body["snapshots"]) == 1
    snapshot = body["snapshots"][0]
    assert snapshot["symbol"] == "BTCUSDT"
    assert snapshot["grid_state"] == "full_overlap"
    assert snapshot["left_quality"]["exchange"] == "binance"
    assert snapshot["right_quality"]["exchange"] == "bybit"
    assert snapshot["consensus_status"] == "NOT_INFERRED"
    assert path.read_bytes() == before
    assert client.post("/api/provider-divergence/status").status_code == 405


def test_provider_divergence_endpoint_missing_runtime_creates_nothing(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "provider-divergence-missing.sqlite3"
    client = TestClient(
        create_app(
            tmp_path / "missing-signals.sqlite3",
            provider_divergence_path=missing,
        )
    )

    body = client.get("/api/provider-divergence/status").json()

    assert body["status"] == "unavailable"
    assert body["reason"] == "provider_divergence_runtime_evidence_missing"
    assert body["snapshots"] == []
    assert body["consensus_status"] == "NOT_INFERRED"
    assert body["read_only"] is True
    assert body["real_capital"] == 0
    assert not missing.exists()


def test_galactech_system_exposes_provider_divergence_without_consensus(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path / "missing-signals.sqlite3"))

    html = client.get("/galactech").text
    js = client.get("/galactech-static/app.js").text

    assert 'id="systemProviderDivergence"' in html
    assert 'id="systemProviderDivergenceNote"' in html
    assert "VERİ SAĞLAYICI AYRIŞMASI" in html
    assert "consensus not inferred" in html.lower()
    assert (
        'providerDivergenceStatus: "/api/provider-divergence/status"'
        in js
    )
    assert '"providerDivergenceStatus"' in js
    assert '"systemProviderDivergence"' in js
    assert "CONSENSUS NOT INFERRED" in js
