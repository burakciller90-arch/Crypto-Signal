# V1 DEPENDENCY ROADMAP

Status: governing execution order for V1.

0. Isolated macOS Bootstrap
1. Constitution + architecture contracts
2. Data Truth
3. Shared deterministic primitives
4A. Price Action / SMC / ICT
4B. Harmonic
4C. Elliott
5. Confluence + signal semantics
6. Immutable live-forward ledger activation
7. Outcome + historical evaluation
8. Dashboard V1
9. Alerts
10. Integrated V1 acceptance — ACCEPTED 2026-09-20

## Critical path
Isolation -> contracts -> data truth -> primitives -> three independent engines ->
confluence/signal -> immutable forward freeze -> outcome/evaluation -> wired dashboard -> acceptance.

## Parallelism
The three methodology engines may advance in parallel only after shared inputs/contracts are stable.
Dashboard design-system work may begin after Data Truth, but mock data must never masquerade as product truth.

## Scope rule
If a feature does not improve V1 correctness, evidence integrity, reliability, one of the three core methods,
confluence/signal semantics, or required UX, park it in V2+.


## Acceptance
V1 critical-path platform core accepted on 2026-09-20.
See docs/V1_INTEGRATED_ACCEPTANCE.md.
