# CURRENT STATUS

Updated: 2026-09-19
Project: Crypto Signal
Phase: 0 — Environment & Constitution
State: PHASE0_ACCEPTED
REAL_CAPITAL: 0

## Mechanical identity
- macOS account: `crypto-signal-agent`
- UID: `504` (mechanically observed; never hard-code across machines)
- account class: Standard / non-admin
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- git branch: `main`
- project root mode: `0700`

## Accepted baseline
- Dedicated account/home and cross-project isolation verified.
- Git repository and governing project memory established.
- User-local uv + managed CPython 3.12.14; repo-local `.venv`.
- User-local fnm + Node 24.18.0; runtime pins recorded.
- Dedicated port block 48700-48709 checked free at bootstrap.
- V1 architecture boundaries and semantic contracts documented.
- Scientific constitution and V1/V2+ scope firewall documented.
- pytest, Ruff and mypy baseline installed and executed successfully.
- 3 bootstrap contract tests passed; Ruff and mypy reported no issues.

## Canonical next phase
Phase 1 — Data Truth.
First implementation work must establish exchange/data-source truth, candle correctness,
persistence/provenance, reconnect/gap/freshness handling and periodic opens.
Do not begin V2+ implementation.
