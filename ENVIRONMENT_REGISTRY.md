# ENVIRONMENT REGISTRY

Updated: 2026-09-22
Project: Crypto Signal Full Version
Safety invariant: `REAL_CAPITAL=0`

## Identity

- macOS account: `crypto-signal-agent`
- observed UID: `504`
- admin: no
- home: `/Users/crypto-signal-agent`
- self-hosted runner: `crypto-signal-uid504`

## Canonical SSD layout

Authoritative root: `/Volumes/Crypto-504/Crypto-Signal`

- Development: `/Volumes/Crypto-504/Crypto-Signal/Development`
- Product: `/Volumes/Crypto-504/Crypto-Signal/Product`
- Live: `/Volumes/Crypto-504/Crypto-Signal/Live`
- Alerts: `/Volumes/Crypto-504/Crypto-Signal/Alerts`
- Paper: `/Volumes/Crypto-504/Crypto-Signal/Paper`
- Runner: `/Volumes/Crypto-504/Crypto-Signal/Runner`
- Service logs: `/Volumes/Crypto-504/Crypto-Signal/ServiceLogs`
- Runner logs: `/Volumes/Crypto-504/Crypto-Signal/RunnerLogs`

The SSD layout is runtime authority. There is no accepted fallback to old
internal Macintosh Live/Product/Alerts/Paper or canonical database payloads.

An internal compatibility/continuity skeleton may exist at
`/Users/crypto-signal-agent/Crypto-Signal/runtime/continuity`; it is not
project/runtime database authority.

## Canonical databases

Under `Development`:

- signal ledger: `runtime/ledger/live_signal_ledger.sqlite3`
- candle cache: `runtime/data/live_base_15m_cache.sqlite3`
- alert outbox: `runtime/alerts/alert_outbox.sqlite3`
- paper ledger: `runtime/paper/paper_fund.sqlite3`

R11/R13 mechanically verified the live topology plus SQLite quick-check /
WAL-aware backup-restore evidence.

## Runtime ownership

- supervisor: `/Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh`
- supervisor PID: `/Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.pid`
- dashboard PID: `/Volumes/Crypto-504/Crypto-Signal/dashboard.pid`
- dashboard URL: `http://127.0.0.1:48700`
- runtime watchdog label: `com.cryptosignal.runtime-terminal-watchdog`
- runner watchdog label: `com.cryptosignal.github-runner-terminal-watchdog`

Dashboard startup must explicitly bind all four SSD Development runtime stores.

## Continuity

Canonical state:
`/Volumes/Crypto-504/Crypto-Signal/Development/runtime/continuity`

Shared relay boundary:
`/Users/Shared/.crypto-signal-wake-relay`

R12 accepted the self-hosted GitHub `:00/:20/:40` cadence fallback plus a
verified detached UID504 bridge because launchd bootstrap from the UID504
self-hosted-runner context returned rc=5. GUI transport may cross UID502 only
through the namespace-bound shared relay; Crypto project/runtime authority
remains UID504.

## Toolchain

- Git: Apple Git 2.50.1+ in accepted Mac evidence
- Python pin: 3.12; project virtualenv: `.venv`
- Node pin: 24.x for product/static checks
- system Python/Node are not the project runtime contract

## Ports

- dashboard: `127.0.0.1:48700`
- reserved project block: `48700-48709`

## Release identity

Reserved final tag: `crypto-signal-full-version-v1.0.0`.

See `docs/FINAL_RELEASE_MANIFEST_V1.md` for the exact freeze rule.
