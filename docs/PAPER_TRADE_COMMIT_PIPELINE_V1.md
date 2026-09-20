# PAPER TRADE COMMIT PIPELINE V1

Status: candidate Stage 6C bounded integration gate. It is not a runtime activation mechanism.

## Purpose

Take one already accepted `PLANNED` pre-trade decision and its exact frozen execution snapshot, materialize the deterministic simulated execution bundle, and persist that bundle through the already-accepted atomic/idempotent paper ledger boundary.

This layer does **not**:
- select signals;
- evaluate autonomy;
- fetch candles;
- fetch or create venue rules;
- activate PAPER/STABLE trading;
- contact an exchange or broker.

## Required lineage

Before orchestration:
- pre-trade status must be `PLANNED`;
- embedded paper plan fund identity must equal reconstructed state;
- execution snapshot identity must equal the one bound into pre-trade;
- snapshot symbol/policy must match the plan/fund;
- snapshot venue reference must end in the exact frozen execution-input identity carried by pre-trade.

After orchestration:
- decision action/symbol/quantity/reference must equal the accepted pre-trade plan;
- fill must bind the exact frozen execution snapshot;
- a trade must produce decision + simulated fill + position/cash mutation.

## Persistence semantics

Persistence delegates to the accepted atomic paper bundle boundary:
- first exact commit -> INSERTED;
- exact retry from the original accepted pre-commit state -> UNCHANGED;
- stale current state -> fail closed;
- partial existing bundle -> fail closed;
- SQLite mid-bundle failure -> rollback.

This pipeline adds no new ledger mutation primitive; it composes already accepted boundaries.

## Remaining blockers before PAPER/STABLE trade activation

1. persistent activation watermark / processed-event truth;
2. deterministic production grouping of exact Binance+Bybit 4h consensus events;
3. authoritative frozen Binance venue-rule/cost snapshot sourcing;
4. runtime retry/restart/lock semantics for candidate processing;
5. operational acceptance showing no historical backfill and no duplicate virtual trades.

REAL_CAPITAL remains 0.
