# PROJECT CHRONICLE

## 2026-09-19 — Phase 0 bootstrap begins

The Crypto Signal master handoff was accepted as governing project context.
V1/V2+ scope firewall was confirmed before implementation.

A dedicated macOS Standard account named `crypto-signal-agent` was created.
Mechanical verification observed UID `504`; admin-group membership is false.
Home is `/Users/crypto-signal-agent`.

A dedicated repository was initialized at:
`/Users/crypto-signal-agent/Crypto-Signal`

The repository uses branch `main`.
The project root was tightened to mode `0700`.
No cross-project symlinks were found in the new home.

System observations at bootstrap:
- Apple Git 2.50.1
- system Python 3.9.6
- Node 24.18.0
- npm 11.16.0
- no Homebrew, uv, pyenv, PostgreSQL, Redis, Docker or Colima detected
- system SQLite is available

No product code has been written yet.

## 2026-09-19 — Isolated runtime baseline ready

User-local `uv 0.12.17` was installed without modifying the shared system Python.
Managed CPython 3.12.14 and repository-local `.venv` were created; `.python-version` pins 3.12.

User-local `fnm 1.39.0` was installed without Homebrew or shared Node mutation.
Node 24.18.0 was installed for this user and pinned by `.node-version`.

Ports 48700-48709 were mechanically bind-tested as free and reserved by project convention.
The isolated runtime baseline is now ready; no product code exists yet.

## 2026-09-19 — Phase 0 accepted

Core V1 architecture boundaries and semantic contracts were documented before product implementation.
A Python quality baseline was established with pytest, Ruff and mypy under the repo-local environment.

Mechanical acceptance evidence:
- bootstrap contract tests: 3 passed
- Ruff: all checks passed
- mypy: no issues found
- REAL_CAPITAL remains 0

Phase 0 is accepted.
The canonical frontier is now Phase 1 — Data Truth.

## 2026-09-19 — Phase 1 Slice 1 accepted: REST data contract

Bybit V5 Spot was selected as the first canonical adapter behind a provider-neutral Candle contract.
Binance remains a planned second adapter rather than a product dependency.

The Candle contract preserves Decimal market values, source event time, local ingest time,
closed/open state, adapter version and stable provider-neutral identity.
Impossible OHLC/time/volume states are rejected.

Acceptance evidence:
- 13 tests passed
- Ruff PASS
- mypy PASS
- live Bybit BTCUSDT 15m REST probe: 5 sequential candles, 900000 ms spacing
- live state: 4 closed candles + 1 current open candle

Canonical frontier moves to Phase 1 Slice 2: persistence/provenance and gap/freshness detection.
