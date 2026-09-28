from __future__ import annotations

import argparse
import asyncio
import base64
import fcntl
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx

import ops.run_cross_market_snapshot as cross_runner
from crypto_signal.data.adapters.cboe_vix import CboeVixDailyAdapter
from crypto_signal.data.cross_market import (
    CrossMarketSeries,
    CrossMarketUnit,
    build_cross_market_daily_record,
    build_cross_market_window_observation,
)
from crypto_signal.data.cross_market_runtime_store import CrossMarketRuntimeStore
from crypto_signal.data.cross_market_source_contract import (
    CBOE_VIX_CHANNEL,
    CBOE_VIX_PROVIDER,
    CBOE_VIX_SOURCE,
    CBOE_VIX_SYMBOL,
    CrossMarketSourceSnapshot,
    persist_cross_market_source_snapshot,
    persist_cross_market_unavailable,
)
from crypto_signal.data.models import DataSource
from crypto_signal.data.source_contract import (
    SourceContractStore,
    SourceCoverageState,
)

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "ops" / "ssd_runtime_supervisor.sh"
_DAY_MS = 24 * 60 * 60 * 1000


def _day_ms(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp() * 1000)


def _vix_observation(*, observed_at_ms: int):
    records = tuple(
        build_cross_market_daily_record(
            series=CrossMarketSeries.CBOE_VIX_CLOSE,
            unit=CrossMarketUnit.INDEX_POINTS,
            day_start_ms=_day_ms(2026, 9, day),
            value=value,
        )
        for day, value in (
            (16, Decimal("17.5")),
            (17, Decimal("18.5")),
            (18, Decimal("19.5")),
        )
    )
    return build_cross_market_window_observation(
        series=CrossMarketSeries.CBOE_VIX_CLOSE,
        unit=CrossMarketUnit.INDEX_POINTS,
        observed_at_ms=observed_at_ms,
        records=records,
        source=DataSource.REST,
        adapter_version="cboe-vix-daily/test",
    )


def test_cboe_vix_adapter_follows_official_redirect() -> None:
    csv_text = """DATE,CLOSE
09/16/2026,17.5
09/17/2026,18.5
09/18/2026,19.5
"""
    original = CboeVixDailyAdapter.URL
    redirected = (
        "https://cdn-api.cboe.com/api/global/us_indices/"
        "daily_prices/VIX_History.csv"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == original:
            return httpx.Response(
                307,
                headers={"location": redirected},
                request=request,
            )
        assert str(request.url) == redirected
        return httpx.Response(
            200,
            text=csv_text,
            headers={"content-type": "text/csv"},
            request=request,
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await CboeVixDailyAdapter(client).fetch_source_snapshot(
                sessions=3
            )

    snapshot = asyncio.run(run())
    assert snapshot.response_url == redirected
    assert snapshot.observation.records[-1].value == Decimal("19.5")
    assert snapshot.payload_bytes == csv_text.encode()


def test_cross_market_source_lineage_and_pit_store_are_exact(
    tmp_path: Path,
) -> None:
    observed_at_ms = _day_ms(2026, 9, 20)
    observation = _vix_observation(observed_at_ms=observed_at_ms)
    payload_bytes = b"DATE,CLOSE\n09/18/2026,19.5\n"
    snapshot = CrossMarketSourceSnapshot(
        provider=CBOE_VIX_PROVIDER,
        source=CBOE_VIX_SOURCE,
        channel=CBOE_VIX_CHANNEL,
        symbol=CBOE_VIX_SYMBOL,
        requested_url=CboeVixDailyAdapter.URL,
        response_url=(
            "https://cdn-api.cboe.com/api/global/us_indices/"
            "daily_prices/VIX_History.csv"
        ),
        http_status=200,
        content_type="text/csv",
        payload_bytes=payload_bytes,
        observation=observation,
    )
    runtime = CrossMarketRuntimeStore(tmp_path / "cross-market.sqlite3")
    source = SourceContractStore(tmp_path / "source-contract.sqlite3")

    persisted = persist_cross_market_source_snapshot(
        snapshot=snapshot,
        runtime_store=runtime,
        source_store=source,
    )

    assert persisted.inserted_observation
    assert runtime.quick_check()
    latest = runtime.latest_observation_as_of(
        series=CrossMarketSeries.CBOE_VIX_CLOSE,
        as_of_ms=observed_at_ms,
    )
    assert latest == observation
    assert (
        runtime.latest_observation_as_of(
            series=CrossMarketSeries.CBOE_VIX_CLOSE,
            as_of_ms=observed_at_ms - 1,
        )
        is None
    )

    envelope = source.latest_envelope_at(
        provider=CBOE_VIX_PROVIDER,
        source=CBOE_VIX_SOURCE,
        channel=CBOE_VIX_CHANNEL,
        symbol=CBOE_VIX_SYMBOL,
        as_of_ms=observed_at_ms,
    )
    assert envelope is not None
    assert envelope.envelope_identity == persisted.envelope_identity
    assert envelope.raw_identity == persisted.raw_identity
    assert envelope.normalized_identity == observation.observation_identity

    raw = source.raw_payload(persisted.raw_identity)
    assert raw is not None
    decoded = __import__("json").loads(raw.payload_json)
    assert base64.b64decode(decoded["payload_base64"]) == payload_bytes

    coverage = source.coverage_at(
        provider=CBOE_VIX_PROVIDER,
        source=CBOE_VIX_SOURCE,
        channel=CBOE_VIX_CHANNEL,
        symbol=CBOE_VIX_SYMBOL,
        as_of_ms=observed_at_ms,
    )
    assert coverage is not None
    assert coverage.state is SourceCoverageState.OBSERVED
    assert coverage.source_envelope_identity == envelope.envelope_identity


def test_cross_market_unavailable_is_explicit_not_zero(
    tmp_path: Path,
) -> None:
    source = SourceContractStore(tmp_path / "source-contract.sqlite3")
    coverage = persist_cross_market_unavailable(
        series=CrossMarketSeries.CBOE_VIX_CLOSE,
        observed_at_ms=123_000,
        reason_code="network_error",
        source_store=source,
    )

    assert coverage.state is SourceCoverageState.UNAVAILABLE
    assert coverage.source_envelope_identity is None
    assert coverage.reason_codes == ("network_error",)


def test_cross_market_runner_skips_when_single_writer_lock_is_held(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    lock_path = tmp_path / "cross-market.lock"
    monkeypatch.setattr(
        cross_runner,
        "_require_canonical_path",
        lambda path, *, label: None,
    )
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(
            lock_file.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )
        args = argparse.Namespace(
            cross_market_db=tmp_path / "cross-market.sqlite3",
            source_contract_db=tmp_path / "source-contract.sqlite3",
            lock_path=lock_path,
            sessions=10,
        )
        assert asyncio.run(cross_runner.run(args)) == 0

    captured = capsys.readouterr()
    assert "RDP8_CROSS_MARKET_SNAPSHOT_SKIPPED=LOCK_HELD" in captured.out
    assert "REAL_CAPITAL=0" in captured.out


def test_supervisor_schedules_cross_market_hourly() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "run_cross_market_snapshot_clock() {" in text
    assert 'local runner="$DEV/ops/run_cross_market_snapshot.py"' in text
    assert 'local db="$runtime/cross_market.sqlite3"' in text
    assert 'local source_contract="$runtime/source_contract.sqlite3"' in text
    assert 'local lock="$runtime/cross_market_snapshot.lock"' in text
    assert "last_cross_market_clock=0" in text
    assert "if [ $((now-last_cross_market_clock)) -ge 3600 ]; then" in text
    assert "run_cross_market_snapshot_clock" in text
    assert 'last_cross_market_clock="$now"' in text
    assert "REAL_CAPITAL=0" in text
