# Crypto Signal

Crypto Signal Full Version is a Turkish-first, explainable, evidence-driven
crypto intelligence platform. It combines immutable signal history, beginner
education, a 100 USDT virtual paper-fund domain, honest performance/benchmark
evidence, independent market-intelligence engines, Alpha Factory research,
Learning Memory and a read-only Research Lab.

## Current release state

R13 Full Version Integrated Acceptance v2 is **PASS** on main
`f95efc358ac396e50d0bfdb920b0187706cd2af2` through canonical issue #704 /
run `35672790463`.

R14 is the final release/documentation frontier. The reserved immutable release
tag is `crypto-signal-full-version-v1.0.0`; the release is final only after the
canonical release-freeze workflow verifies exact current main and emits
`R14_FULL_VERSION_RELEASE_FREEZE_PASS=YES`.

Live Gift Edition Product code remains the accepted head
`f15cbafd9f4359d385eca097a6a2635bf815ded1`; R13 proved product/runtime-code
parity against current main.

## Open the product

```bash
open http://127.0.0.1:48700
curl -fsS http://127.0.0.1:48700/api/health
```

Expected safety truth includes `status=ok`, `read_only=true`,
`ledger_present=true`, `alert_outbox_present=true` and `real_capital=0`.

## Canonical runtime

- SSD root: `/Volumes/Crypto-504/Crypto-Signal`
- Development: `/Volumes/Crypto-504/Crypto-Signal/Development`
- Product: `/Volumes/Crypto-504/Crypto-Signal/Product`
- Runner: `/Volumes/Crypto-504/Crypto-Signal/Runner`
- Dashboard: `http://127.0.0.1:48700`
- Runtime owner: `crypto-signal-agent` / observed UID504
- Dashboard/service owner: SSD supervisor
- Self-hosted control channel: `crypto-signal-uid504`

## Read order

1. `READ_FIRST_CRYPTO_SIGNAL.md`
2. `CURRENT_STATUS.md`
3. newest relevant entry in `PROJECT_CHRONICLE.md`
4. `docs/FINAL_RELEASE_MANIFEST_V1.md`
5. `docs/OPERATOR_RUNBOOK_FULL_VERSION_V1.md`
6. `docs/KNOWN_AUTHORITY_GATES_V1.md`
7. `docs/PROJECT_COMPLETION_EXECUTION_ROADMAP.md`
8. `ENVIRONMENT_REGISTRY.md`

## Hard boundaries

- `REAL_CAPITAL=0`.
- No exchange-order or credential authority is exposed.
- Paper policy remains evidence-governed and may be `NOT_ACTIVATED`.
- Agreement/confluence and shadow weighted balance are not calibrated probability.
- Missing evidence is never invented.
- Research cannot promote or deploy itself.
- Durdurulmaz and Quantum Capital remain isolated projects.
- Physical reboot/logout/SSD detach-remount are not claimed as autonomously tested.

For operations and recovery, start with
`docs/OPERATOR_RUNBOOK_FULL_VERSION_V1.md`.
