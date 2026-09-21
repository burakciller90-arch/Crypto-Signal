# Stage 10 — Full Integrated Acceptance

Status: **RUNTIME_PENDING**  
Project: Crypto Signal  
Safety invariant: **REAL_CAPITAL=0**  
Production paper-write policy: **NOT_ACTIVATED**

This acceptance is intentionally split into two evidence classes:

1. deterministic repository/product-contract evidence;
2. canonical UID504 stable-runtime evidence.

Stage 10 is not accepted and must not be tagged until both classes pass.

## Current code acceptance head

Main code + acceptance infrastructure was merged through PR #351 and is present on
main. The latest hosted-verified main at the time this document was prepared was
`ca18c24c88d17bd3b79ff91386037fe017d805cb`.

## Acceptance matrix

| Gate | Current state | Evidence / required closure |
| --- | --- | --- |
| Full repository gate | PASS (hosted); canonical latest UID504 pending | Hosted main full gate run 35560868419 passed full pytest, Ruff, mypy and JS. UID504 had already passed the product-code full gate before the final verifier/workflow-only commits; latest canonical sync/fulltest is queued. |
| Stable runtime deployments | PENDING | Must verify PRODUCT exact accepted main head plus LIVE/ALERTS/PAPER clean stable worktrees and launchd services on UID504. |
| Restart/recovery tests | PARTIAL PASS | Deterministic recovery tests and existing recovery soak tooling pass at repository level. Stage10 runtime workflow must restart PRODUCT + paper clocks and run live recovery soak. |
| Auto-refresh endurance | PARTIAL PASS | 15s product refresh contract exists and is tested. Stage10 runtime verifier must execute repeated real GET cycles against deployed PRODUCT. |
| Stale-data test | PASS (deterministic) | `freshness.js` classifies pending/live/stale/offline, including clock-skew handling; Node contract passes. |
| Paper-ledger reconstruction | PASS | Existing paper-state tests prove deterministic reconstruction, idempotence, accounting lineage checks and read-only reconstruction. |
| Fee/slippage determinism | PASS | Existing pretrade/execution tests bind fee, spread and slippage to the exact deterministic simulator/cost budget. |
| No-leakage checks | PASS (static); runtime OpenAPI pending | Stage10 contract proves product OpenAPI is GET-only in tests and paper-stable allowlist exposes no writeauthority/writetick. Runtime verifier repeats OpenAPI check after deploy. |
| UI beginner usability | PARTIAL PASS | Beginner wording/progressive disclosure/static contract passes. Final stable-runtime product inspection remains required. |
| Explanation/evidence consistency | PASS | Existing dashboard/Mission Control contracts bind explanations to frozen evidence and deterministic trace identities. |
| Benchmark comparison correctness | PASS | `paper_benchmarks.v1` implements same-start 100 USDT cash, BTC buy-and-hold and BTC/ETH/SOL equal-weight references with PIT-safe closed-candle marks; backend computes paper-relative return. |
| Research Lab isolation | PASS for current scope | No production `crypto_signal.research` package/surface exists; product/paper read paths do not import a Research Lab. This is isolation by absence, not a claim that Research Lab is implemented. |
| REAL_CAPITAL=0 | PASS in code; runtime reconfirmation pending | Models, product contract, Mission Control and benchmark contracts require zero real capital. Runtime acceptance must reconfirm. |
| No exchange order endpoint / credential authority exposed | PASS in code; runtime OpenAPI pending | Product exposes GET-only read surfaces; no order/credential endpoint is present; PAPER/STABLE issue workflow exposes no writer activation/tick command. |

## Benchmark acceptance

The Stage 10 benchmark gap was closed with `paper_benchmarks.v1`.

All benchmarks use the immutable paper activation cutoff as the common start time
and only Binance Spot 15m candles that were fully closed and available by the
requested point in time:

- 100 USDT cash,
- 100 USDT BTC buy-and-hold,
- 100 USDT BTC/ETH/SOL equal-weight.

The benchmark semantic is explicitly
`frictionless_reference_not_execution`. Missing start/end mark evidence fails
closed: NAV, return and relative return remain unavailable instead of being
estimated. Benchmark snapshot identity and benchmark-relative comparisons are
bound into `paper_mission_control.v4`.

## Freshness / stale-data acceptance

The browser freshness decision is a pure deterministic contract in
`src/crypto_signal/product/static/freshness.js`.

- refresh cadence: 15 seconds,
- stale threshold: 45 seconds,
- offline state overrides freshness,
- future local timestamps are clamped to zero age rather than producing negative
  freshness,
- invalid stale thresholds fail closed.

`tests/js/test_product_freshness.js` executes this contract directly under Node.

## Runtime acceptance that still must pass

The versioned workflow
`.github/workflows/crypto-stage10-runtime-acceptance.yml` is the final runtime
gate. It must run on UID504 after exact PRODUCT deployment and must prove:

- canonical main and PRODUCT exact accepted head,
- all stable worktrees clean,
- dashboard/live-evidence/alerts/paper/paper-dry-run launchd presence,
- PRODUCT restart and health recovery,
- paper clock + paper dry-run clock restart with zero paper mutations,
- live recovery soak,
- 20-cycle real read-only PRODUCT API endurance,
- runtime OpenAPI GET-only surface,
- Mission Control v4 and exact three benchmark families,
- benchmark start equals paper activation cutoff,
- paper ledger unchanged throughout endurance,
- trade_policy=NOT_ACTIVATED,
- REAL_CAPITAL=0.

Final acceptance requires:
`STAGE10_RUNTIME_ACCEPTANCE=PASS`.

## Tagging rule

Do **not** tag Stage 10 and do **not** mark it complete while runtime acceptance is
pending. A queued/offline UID504 runner is an infrastructure wait state, not a
PASS and not a project failure.
