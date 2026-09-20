# POST-V1 CANONICAL FREEZE PATH — ACCEPTANCE

Status: ACCEPTED
Date: 2026-09-20
REAL_CAPITAL=0

## Scope
The live freeze pipeline no longer depends on adapter acquisition.
freeze_live_candles() is the canonical immutable decision/freeze/lifecycle path,
while freeze_live_provider() only acquires provider candles and delegates.

## Accepted behavior
- Existing 15m provider-path semantics are preserved exactly.
- Direct canonical-candle freeze and provider freeze produce equal result, freeze rows and lifecycle rows.
- Repeated source cutoff remains idempotent.
- Non-positive minimum history is rejected explicitly.
- Canonical aggregated higher-timeframe candles can enter the same immutable freeze path.
- Higher-timeframe production coverage remains disabled; this acceptance does not activate it.

## Scientific boundary discovered and resolved
PA previous-period/session levels remain defined from canonical 15m source truth.
When an aggregated higher-timeframe candle series is analyzed without its underlying 15m level source,
the PA result deliberately carries no previous-period/session range evidence rather than fabricating
coarser identities from aggregated candles. Explicit sessions on a non-15m-only call fail closed.

Before higher-timeframe production activation, product/coverage behavior must continue to make this
boundary explicit. Any future use of an additional 15m reference source must also preserve immutable
input provenance.

## Acceptance evidence
- focused live freeze tests: 7 PASS
- full repository pytest: 271 PASS
- Ruff: PASS
- mypy: PASS across 119 source files
- uv lock check: PASS
- git diff check: PASS
- direct/provider 15m equivalence: PASS
- source-cutoff idempotence: PASS
- canonical 1h aggregated freeze path: PASS

## Next frontier
V2+ Birthday Edition Stage 1: multi-timeframe production truth.
Start with a bounded implementation that integrates already-accepted higher-timeframe preparation
into the live runner while keeping activation fail-closed until exact tests and runtime evidence pass.
