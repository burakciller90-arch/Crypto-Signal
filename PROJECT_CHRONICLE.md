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

## 2026-09-19 — Repository ignore correction

A post-commit reproducibility audit found that the unanchored `data/` ignore rule also matched
`src/crypto_signal/data/`. The checkpoint would therefore have depended on ignored local source files.
The rule was corrected to root-only `/data/`, with `/runtime/` and `/secrets/` similarly anchored.
The full source package is now tracked and pytest/Ruff/mypy pass against tracked code.

## 2026-09-19 — Phase 1 Slice 2 accepted: persistence and data health

SQLite WAL persistence was added with deterministic candle finalization rules.
Equivalent duplicate delivery is idempotent; stale open updates are ignored; finalized candles cannot reopen;
and conflicting finalized payloads raise an explicit conflict rather than silently rewriting truth.

Acceptance evidence:
- 23 tests passed
- Ruff PASS
- mypy PASS
- live Bybit persistence smoke: 10 INSERTED then 10 UNCHANGED
- canonical row count remained 10
- gap detector returned no gaps
- freshness assessment returned fresh

Canonical frontier moves to Phase 1 Slice 3: WebSocket ingestion and reconnect/recovery.

## 2026-09-19 — Phase 1 Slice 3 accepted: live WebSocket ingestion

Bybit V5 Spot kline WebSocket ingestion was implemented behind the provider-neutral Candle contract.
The client sends Bybit application heartbeat packets, keeps protocol ping/pong enabled,
and uses the websockets asyncio reconnect iterator with re-subscription on each connection.

A local forced-transient-close test proved reconnect plus re-subscribe behavior.
A generic CandleIngestor now bridges live events into the canonical persistence rules.

Acceptance evidence:
- 27 tests passed
- Ruff PASS
- mypy PASS
- local reconnect test observed two subscriptions across two connections
- live Bybit BTCUSDT 15m smoke received two updates for one current candle
- persistence result: INSERTED then UPDATED, canonical row count 1

Canonical frontier moves to Phase 1 Slice 4: deterministic higher-timeframe aggregation and periodic opens.

## 2026-09-19 — Phase 1 Slice 4 accepted: deterministic aggregation and periodic opens

Closed 15m candles are now the canonical V1 base series.
1h, 4h, 1D and 1W candles are emitted only from complete closed 15m buckets.
Missing source intervals are reported as incomplete buckets rather than synthesized.

Weekly alignment was mechanically verified as Monday 00:00 UTC.
Daily/Weekly/Monthly/Yearly Opens are resolved from exact 15m boundary candles,
with market availability separated from local observation time for PIT correctness.

Acceptance evidence:
- 35 tests passed
- Ruff PASS
- mypy PASS
- live full-week base set: 672 x 15m
- exact native reconciliation: 168 x 1h, 42 x 4h, 7 x 1D, 1 x 1W
- live Daily/Weekly/Monthly/Yearly Open checks PASS

Canonical frontier moves to Phase 1 Slice 5: Binance parity and cross-provider reconciliation.
