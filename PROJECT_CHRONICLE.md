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

## 2026-09-19 — Phase 1 Slice 5 accepted: Binance parity

Binance Spot REST and WebSocket adapters now normalize into the same Candle contract used by Bybit.
REST uses Binance server time to keep exchange source time separate from local ingest time.
WebSocket preserves event time, native close flag, quote volume and trade count.

Cross-provider reconciliation intentionally does not demand identical exchange prices.
It verifies the shared UTC grid and reports observed price spread.

Acceptance evidence:
- 43 tests passed
- Ruff PASS
- mypy PASS
- latest BTCUSDT 15m grid: 20/20 overlap, no provider-only timestamps
- median absolute close spread ~0.56 bps
- maximum absolute close spread ~1.88 bps
- Binance weekly alignment: Monday 00:00 UTC
- live Binance WS persistence: INSERTED then UPDATED, one canonical row

Canonical frontier moves to Phase 1 Slice 6: restart/recovery and integrated acceptance.

## 2026-09-19 — Phase 1 Data Truth accepted

The complete Data Truth acceptance chain passed in one integrated run.

Integrated gate:
- 45 tests PASS
- Ruff PASS
- mypy PASS
- Bybit REST live probe PASS
- persistence/idempotence live probe PASS
- Bybit WebSocket live probe PASS
- full-week deterministic aggregation/native reconciliation PASS
- Binance REST/WebSocket parity and cross-provider grid reconciliation PASS
- Bybit + Binance restart recovery PASS
- bounded concurrent dual-feed ingestion PASS

Recovery evidence:
- one deliberate historical candle gap was created for each provider
- REST backfill reduced each gap from 1 to 0
- the second backfill returned 30/30 unchanged for each provider

Phase 1 is accepted.
The canonical frontier is shared deterministic swing/peak/trough primitives before methodology engines.

## 2026-09-19 — Shared deterministic swing primitives accepted

A methodology-neutral pivot/swing layer was implemented after Phase 1 Data Truth.
Strict fractal pivots require closed, gapless, chronologically aligned candle truth.
Each pivot records market confirmation time and local observation time, preventing source-candle hindsight.

Outside bars that qualify as both HIGH and LOW are marked as same-bar ambiguity.
Alternating compression reports ambiguous source indices and keeps more-extreme consecutive same-kind swings.

Acceptance evidence:
- 51 tests PASS
- Ruff PASS
- mypy PASS
- Bybit live sample: 200 closed candles -> 52 pivots -> 41 alternating swings
- Binance live sample: 200 closed candles -> 50 pivots -> 39 alternating swings
- identical input produced identical pivot tuples

Canonical frontier moves to PA / SMC / ICT V1.

## 2026-09-19 — PA Slice 1 accepted: market structure

The first PA/SMC/ICT slice was completed as deterministic structure evidence only.
Confirmed PIT-safe swings feed HH/LH/EH and HL/LL/EL labels plus close-based BOS and CHOCH/MSB.
Wick-only penetration is not classified as a structure break in this slice.

Acceptance evidence:
- 55 tests PASS
- Ruff PASS
- mypy PASS
- Bybit live sample: 700 closed 15m candles -> 187 pivots -> 149 swings -> 117 breaks
- Bybit: 89 BOS / 28 CHOCH-MSB, current structure bearish
- Binance live sample: 700 closed 15m candles -> 180 pivots -> 139 swings -> 110 breaks
- Binance: 80 BOS / 30 CHOCH-MSB, current structure bearish
- all live breaks obey pivot-confirmation and observation-time ordering

Canonical next slice is PA Slice 2: deterministic FVG lifecycle/mitigation and BPR where valid.

## 2026-09-19 — User-requested pause after PA Structure Slice 1

Development was paused immediately after the accepted PA market-structure checkpoint
`ea58566937b9c2afdb94ea868c2930ad761b0d91`.

Mechanical continuation audit found:
- no project-level wake files/directories
- no continuation lease files/directories
- no Crypto Signal wake/lease launchd label
- no Crypto Signal continuation worker

Therefore there is no autonomous project mechanism to pause further; continuation is already disabled by absence.
Desktop Commander/Cursor are left available only so manual state-first recovery can occur when the user says
`Devam edebiliriz`.

Exact recovery instructions are recorded in `.project/PAUSE_CHECKPOINT.md`.
Canonical resume frontier: PA Slice 2 — deterministic FVG lifecycle/mitigation, then BPR where valid.
No new development is authorized while paused.

## 2026-09-20 — Resume after user-requested pause

The user resumed Crypto Signal development.
UID 504 identity, pause/development checkpoint ancestry, clean working tree and absence of project wake/lease workers were mechanically verified.
The resume gate passed: 55 tests, Ruff and mypy all PASS.

Development resumes only at PA Slice 2: deterministic FVG lifecycle/mitigation, then BPR where valid.

## 2026-09-20 — PA Slice 2 accepted: FVG lifecycle and BPR

Strict three-candle bullish/bearish Fair Value Gap geometry was implemented with point-in-time creation,
local observation timestamps and deterministic lifecycle state.

Lifecycle:
- OPEN -> MITIGATED -> FILLED
- first touch, fill time and maximum fill fraction are preserved
- a candle entirely beyond the far boundary does not prove path through the zone and is recorded as gap-through ambiguity

Balanced Price Range detection requires strictly positive overlap between opposing FVGs and rejects
cases where the earlier FVG had already filled before or at the later FVG creation time.

Acceptance evidence:
- 66 tests PASS
- Ruff PASS
- mypy PASS
- Bybit: 900 closed 15m -> 189 FVG / 6 BPR
- Binance: 900 closed 15m -> 211 FVG / 7 BPR
- deterministic repeat equality PASS on both providers
- lifecycle/PIT ordering PASS
- all BPRs in the sampled live history were later traversed

Canonical frontier moves to PA Slice 3: EQH/EQL liquidity pools and sweep/SFP evidence.
