# PAPER ATOMIC PROCESSED TRADE RECEIPT V1

Status: candidate Stage 6C crash-safety gate. It does not activate PAPER/STABLE.

A committed trade event now uses one SQLite transaction for:
1. DecisionIntent;
2. SimulatedFill;
3. PositionCashMutation;
4. immutable `paper_processed_events` receipt.

The receipt binds activation identity, exact two source signal freeze identities, symbol, 4h signal as-of, pretrade identity and the exact ordered decision/fill/mutation record identities.

`processed_at_ms` is derived from the deterministic pretrade plan timestamp, not wall-clock time, so exact crash/restart retries reconstruct the same receipt payload.

Properties:
- first exact commit -> INSERTED;
- exact retry from the original precommit inputs -> UNCHANGED;
- receipt already terminal as no-action -> trade attempt conflicts before any trade write;
- injected failure on processed-event INSERT rolls back decision/fill/mutation too;
- event and fund mutation can no longer diverge because of a crash between two databases/transactions.

PAPER/STABLE remains observation-only. The remaining activation blockers are an authoritative frozen Binance venue-rule snapshot source and production event-selection/runtime wiring. REAL_CAPITAL remains 0.
