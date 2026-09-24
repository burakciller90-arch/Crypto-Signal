from __future__ import annotations

import pytest

from crypto_signal.data.market_data_gap_ledger import (
    GapEventKind,
    IngestionSilenceGapMonitor,
    MarketDataGapLedger,
    build_gap_observed,
    build_gap_recovered,
    build_gap_recovery_attempt,
)


def test_gap_ledger_preserves_append_only_transition_chain(tmp_path) -> None:
    ledger = MarketDataGapLedger(tmp_path / "gaps.sqlite3")
    observed = build_gap_observed(
        provider="bybit",
        source="market_tape_stream",
        channel="orderbook.50",
        symbol="BTCUSDT",
        expectation_value=300,
        last_successful_ingestion_ms=1_000,
        observed_at_ms=1_400,
        source_evidence_identities=("a" * 64,),
    )
    attempt = build_gap_recovery_attempt(
        observed,
        attempted_at_ms=1_450,
        recovery_action="operator_restart_requested",
        source_evidence_identities=("b" * 64,),
    )
    recovered = build_gap_recovered(
        attempt,
        recovered_at_ms=1_500,
        source_evidence_identities=("c" * 64,),
    )

    ledger.append(observed)
    ledger.append(observed)
    ledger.append(attempt)
    ledger.append(recovered)

    events = ledger.events()
    assert tuple(event.event_kind for event in events) == (
        GapEventKind.OBSERVED,
        GapEventKind.RECOVERY_ATTEMPTED,
        GapEventKind.RECOVERED,
    )
    assert events[0].gap_started_at_ms == 1_300
    assert events[1].previous_event_identity == events[0].event_identity
    assert events[2].previous_event_identity == events[1].event_identity
    assert ledger.latest_for_gap(observed.gap_identity) == recovered
    assert ledger.quick_check() is True

    with pytest.raises(ValueError, match="terminal"):
        ledger.append(
            build_gap_recovery_attempt(
                recovered,
                attempted_at_ms=1_600,
                recovery_action="invalid_after_terminal",
                source_evidence_identities=("d" * 64,),
            )
        )


def test_gap_monitor_observes_open_silence_and_later_recovery(tmp_path) -> None:
    ledger = MarketDataGapLedger(tmp_path / "gaps.sqlite3")
    monitor = IngestionSilenceGapMonitor(
        ledger=ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=300,
    )

    monitor.observe_persisted_event(
        channel="publicTrade",
        symbol="BTCUSDT",
        ingested_at_ms=1_000,
        source_evidence_identities=("a" * 64,),
    )
    monitor.check_silence(
        observed_at_ms=1_250,
        source_evidence_identities=("b" * 64,),
    )
    assert ledger.events() == ()

    monitor.check_silence(
        observed_at_ms=1_400,
        source_evidence_identities=("c" * 64,),
    )
    events = ledger.events()
    assert len(events) == 1
    assert events[0].event_kind is GapEventKind.OBSERVED

    monitor.observe_persisted_event(
        channel="publicTrade",
        symbol="BTCUSDT",
        ingested_at_ms=1_500,
        source_evidence_identities=("d" * 64,),
    )
    events = ledger.events()
    assert len(events) == 2
    assert events[1].event_kind is GapEventKind.RECOVERED
    assert events[1].gap_identity == events[0].gap_identity


def test_gap_monitor_records_post_hoc_silence_without_sequence_assumption(
    tmp_path,
) -> None:
    ledger = MarketDataGapLedger(tmp_path / "gaps.sqlite3")
    monitor = IngestionSilenceGapMonitor(
        ledger=ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=300,
    )

    monitor.observe_persisted_event(
        channel="orderbook.50",
        symbol="ETHUSDT",
        ingested_at_ms=1_000,
        source_evidence_identities=("a" * 64,),
    )
    monitor.observe_persisted_event(
        channel="orderbook.50",
        symbol="ETHUSDT",
        ingested_at_ms=1_500,
        source_evidence_identities=("b" * 64,),
    )

    events = ledger.events()
    assert len(events) == 2
    assert events[0].event_kind is GapEventKind.OBSERVED
    assert events[1].event_kind is GapEventKind.RECOVERED
    assert events[0].expectation_value == 300
    assert events[0].reason_codes == ("ingestion_silence_exceeded_policy",)
    assert events[1].reason_codes == ("ingestion_resumed_after_gap",)


def test_gap_monitor_rejects_time_regression(tmp_path) -> None:
    ledger = MarketDataGapLedger(tmp_path / "gaps.sqlite3")
    monitor = IngestionSilenceGapMonitor(
        ledger=ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=300,
    )
    monitor.observe_persisted_event(
        channel="publicTrade",
        symbol="SOLUSDT",
        ingested_at_ms=1_000,
        source_evidence_identities=("a" * 64,),
    )

    with pytest.raises(ValueError, match="regressed"):
        monitor.check_silence(
            observed_at_ms=999,
            source_evidence_identities=("b" * 64,),
        )


def test_gap_monitor_restores_open_gap_without_duplicate_root(tmp_path) -> None:
    ledger = MarketDataGapLedger(tmp_path / "gaps.sqlite3")
    first_monitor = IngestionSilenceGapMonitor(
        ledger=ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=300,
    )
    first_monitor.observe_persisted_event(
        channel="publicTrade",
        symbol="BTCUSDT",
        ingested_at_ms=1_000,
        source_evidence_identities=("a" * 64,),
    )
    first_monitor.check_silence(
        observed_at_ms=1_400,
        source_evidence_identities=("b" * 64,),
    )

    restored = IngestionSilenceGapMonitor(
        ledger=ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=300,
    )
    restored.seed_persisted_event(
        channel="publicTrade",
        symbol="BTCUSDT",
        ingested_at_ms=1_000,
        source_evidence_identities=("a" * 64,),
    )
    restored.check_silence(
        observed_at_ms=1_500,
        source_evidence_identities=("c" * 64,),
    )

    events = ledger.events()
    assert len(events) == 1
    assert events[0].event_kind is GapEventKind.OBSERVED

    restored.observe_persisted_event(
        channel="publicTrade",
        symbol="BTCUSDT",
        ingested_at_ms=1_600,
        source_evidence_identities=("d" * 64,),
    )
    events = ledger.events()
    assert len(events) == 2
    assert events[1].event_kind is GapEventKind.RECOVERED
    assert events[1].previous_event_identity == events[0].event_identity


def test_gap_monitor_fails_closed_on_restored_policy_mismatch(tmp_path) -> None:
    ledger = MarketDataGapLedger(tmp_path / "gaps.sqlite3")
    monitor = IngestionSilenceGapMonitor(
        ledger=ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=300,
    )
    monitor.observe_persisted_event(
        channel="orderbook.50",
        symbol="ETHUSDT",
        ingested_at_ms=1_000,
        source_evidence_identities=("a" * 64,),
    )
    monitor.check_silence(
        observed_at_ms=1_400,
        source_evidence_identities=("b" * 64,),
    )

    with pytest.raises(ValueError, match="expectation conflicts"):
        IngestionSilenceGapMonitor(
            ledger=ledger,
            provider="bybit",
            source="market_tape_stream",
            max_ingestion_silence_ms=600,
        )


def test_gap_monitor_rejects_ambiguous_restart_seed(tmp_path) -> None:
    ledger = MarketDataGapLedger(tmp_path / "gaps.sqlite3")
    monitor = IngestionSilenceGapMonitor(
        ledger=ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=300,
    )
    monitor.observe_persisted_event(
        channel="publicTrade",
        symbol="SOLUSDT",
        ingested_at_ms=1_000,
        source_evidence_identities=("a" * 64,),
    )
    monitor.check_silence(
        observed_at_ms=1_400,
        source_evidence_identities=("b" * 64,),
    )

    restored = IngestionSilenceGapMonitor(
        ledger=ledger,
        provider="bybit",
        source="market_tape_stream",
        max_ingestion_silence_ms=300,
    )
    with pytest.raises(ValueError, match="conflicts with restored open gap"):
        restored.seed_persisted_event(
            channel="publicTrade",
            symbol="SOLUSDT",
            ingested_at_ms=1_350,
            source_evidence_identities=("c" * 64,),
        )
