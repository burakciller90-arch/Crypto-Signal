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

## 2026-09-20 — PA Slice 3 accepted: EQH/EQL liquidity and sweep/SFP

Confirmed alternating swings now feed deterministic equal-liquidity pools.
Equality uses an explicit configurable tolerance; V1 default is 5 bps and is stored in every analysis result.

A pool forms only after the second anchor swing is confirmed.
The first post-formation strict boundary take consumes the V1 pool:
- wick through + close back inside -> SFP_REJECTION
- close through -> CLOSE_THROUGH, not SFP

Acceptance evidence:
- 74 tests PASS
- Ruff PASS
- mypy PASS
- Bybit 900 closed 15m: 24 pools = 14 EQH / 10 EQL; 9 SFP / 13 close-through / 2 available
- Binance 900 closed 15m: 22 pools = 10 EQH / 12 EQL; 7 SFP / 11 close-through / 4 available
- deterministic repeat equality PASS
- all event timestamps are after pool formation and no later than local observation

Canonical frontier moves to PA Slice 4: displacement/reclaim/rejection and deterministic prior-period/session levels.

## 2026-09-20 — PA Slice 4A accepted: prior-period and explicit-session levels

The PA engine now computes Previous Day/Week/Month high-low evidence from closed canonical 15m truth.
A numeric high/low is emitted only when the full expected candle grid is present and observed by as-of.

Session ranges are explicitly configured with name, IANA timezone and local start/end.
The core does not silently invent universal Asia/London/New York hours.
Cross-midnight windows and timezone offsets are handled deterministically.

Acceptance evidence:
- 80 tests PASS
- Ruff PASS
- mypy PASS
- Bybit and Binance live source: 4,794 closed 15m candles each
- Previous Day 96/96 complete
- Previous Week 672/672 complete
- Previous Month 2,976/2,976 complete
- explicit Europe/Istanbul 09:00-11:00 verification session 8/8 complete
- deterministic repeat equality PASS

Canonical frontier moves to PA Slice 4B: displacement and level reclaim/rejection evidence.

## 2026-09-20 — PA Slice 4B accepted: displacement and level interactions

Displacement is now explicit deterministic evidence with a prior-only rolling baseline.
The V1 default configuration is stored in the result rather than hidden in code semantics.

Reclaim/rejection runs only against explicit ReferenceLevel objects carrying market and local availability.
Incomplete prior-period/session ranges cannot become numeric levels.

Acceptance evidence:
- 94 tests PASS
- Ruff PASS
- mypy PASS
- Bybit: 4,794 closed 15m; 86 displacement events; 11 levels; 194 interactions
- Binance: 4,794 closed 15m; 87 displacement events; 11 levels; 189 interactions
- deterministic repeat equality PASS
- all interactions respect level market/local availability

Canonical frontier moves to the integrated PA result and PA V1 acceptance gate.

## 2026-09-20 — PA / SMC / ICT V1 accepted

The integrated Price Action engine now combines PIT-safe market structure, FVG/BPR,
EQH/EQL sweep evidence, complete prior-period/session levels, periodic opens,
displacement and explicit-level reclaim/rejection under one shared as-of.

Final acceptance:
- 96 tests PASS
- Ruff PASS
- mypy PASS
- all individual PA live probes PASS
- integrated PA live gate independently reverified PASS

Integrated live evidence:
- Bybit 4,794 closed 15m: 848 breaks / 1,138 FVG / 92 BPR / 145 liquidity pools /
  57 SFP / 500 displacement / 11 reference levels / 194 interactions
- Binance 4,794 closed 15m: 823 breaks / 1,195 FVG / 104 BPR / 121 liquidity pools /
  45 SFP / 506 displacement / 11 reference levels / 189 interactions

These values remain descriptive evidence only; no probability, win rate or confluence score is created.
Canonical frontier moves to Harmonic V1.

## 2026-09-20 — Autonomous continuity control-plane implemented; OS transport gate pending

The user explicitly authorized autonomous 7/24 continuation and bounded Cursor Composer workers for Crypto Signal.

Implemented under UID504 and Crypto-only paths:
- exact immutable continuation leases with checkpoint SHA256
- same-task supersession
- wake queue dedupe and event receipts
- exact-chat transport design with busy/draft guards
- no generic idle wake
- pause/archive and stale-free resume semantics
- stale worker-state recovery
- isolated Cursor worktree dispatcher and completion queue
- Terminal bootstrap helper for exact Safari chat binding

Mechanical evidence:
- continuity behavior self-test PASS
- zsh syntax PASS
- Python compile PASS
- continuity Ruff PASS
- cross-project path scan found no Durdurulmaz/Quantum path coupling
- full repo: 96 tests PASS, Ruff PASS, mypy PASS

Current human gates:
- macOS denies Terminal -> Safari Apple Events with -1743; Automation settings pane opened for user approval.
- exact chat is not yet bound and bridge is not yet running.
- Cursor Agent 2026.09.18-9a7762b installed under UID504, but status is Not logged in.

No autonomous wake is claimed active until a real exact-chat delivery test passes.

## 2026-09-20 — Harmonic V1 accepted; weekly grid bug repaired

Harmonic V1 was completed and mechanically accepted.

Implemented:
- PIT-safe XABCD candidate enumeration from shared alternating swings
- Gartley, Bat, Butterfly, Crab and Deep Crab explicit ratio contracts
- per-ratio residual evidence
- PRZ projection envelope and clustering width
- AB/CD time-symmetry evidence
- pattern-specific invalidation and 38.2% / 61.8% reaction levels
- explicit valid versus invalid match semantics
- nonphysical theoretical projections retained as invalid evidence rather than clamped or allowed to crash analysis

During live validation, the original Crab-family CD/AB contract was found mathematically over-constrained and corrected.
The common 1W grid validator was also found to use an epoch-zero assumption while exchange weekly candles open Monday 00:00 UTC.
The weekly anchor is now centralized in the shared timeframe contract and reused by aggregation, recovery, swings and PA validators.

Acceptance evidence:
- full repo pytest: 117 PASS
- Ruff: PASS
- mypy: PASS
- long Bybit 15m: 4,797 closed / 1,021 candidates / 5,105 pattern evaluations / 0 valid
- long Binance 15m: 4,797 closed / 979 candidates / 4,895 pattern evaluations / 0 valid
- both long probes deterministic and PIT-safe
- multi-timeframe live smoke PASS on Bybit and Binance for 15m / 1h / 4h / 1D / 1W
- Binance 1D smoke produced one valid live Harmonic match
- weekly nonphysical candidate geometry remained explicit invalid evidence without terminating analysis

Zero valid matches in the long 15m samples is accepted evidence, not a failure; the engine must not manufacture setups.

A Durdurulmaz completion wake was delivered into this chat during the work.
It was classified as foreign/stale and NOOP for Crypto Signal.
Only read-only transport evidence was inspected; no Durdurulmaz or Quantum Capital state was changed.

Canonical frontier moves to Elliott Wave V1.
REAL_CAPITAL remains 0.

## 2026-09-20 — Elliott Wave V1 accepted

Elliott V1 was implemented as a structural candidate engine rather than a forced single count.

Accepted scope:
- partial impulse counts from Wave 1 through Wave 5
- standard impulse hard-price rules
- explicit NOT_APPLICABLE semantics for rules not yet testable
- truncation evidence without false hard invalidation
- generic A-B-C endpoint candidates
- zigzag compatibility without pretending endpoint geometry proves 5-3-5
- competing counts and ambiguity preservation
- structural invalidation boundaries
- Wave 5 equality / 0.618 Wave 1 guidelines
- C=A correction guideline
- descriptive rule-support fractions only

Final quality:
- 127 tests PASS
- Ruff PASS
- mypy PASS
- focused Elliott tests 10/10 PASS

Live evidence:
- Bybit long 15m: 4,798 closed; 5,110 impulse candidates; 1,020 complete;
  63 hard-price-rule-valid complete; 33 truncated-valid; 1,022 A-B-C;
  316 zigzag-compatible; 870 ambiguous end pivots
- Binance long 15m: 4,798 closed; 4,900 impulse candidates; 978 complete;
  60 hard-price-rule-valid complete; 28 truncated-valid; 980 A-B-C;
  304 zigzag-compatible; 828 ambiguous end pivots
- Bybit and Binance 15m / 1h / 4h / 1D / 1W deterministic smoke PASS

Interpretation:
These counts are structural compatibility evidence, not uniquely correct Elliott labels,
probabilities, win rates or execution authority. High ambiguity is preserved by design.

Canonical frontier moves to Confluence + Signal Semantics V1.
REAL_CAPITAL remains 0.

## 2026-09-20 — Exact-chat local wake relay activated

The previously blocked Safari wake path was replaced with an isolated shared relay design.

Mechanical evidence:
- exact Crypto chat is bound in runtime state
- UID502 Safari found exactly one matching Crypto chat tab and JavaScript automation passed
- shared relay secret and target are mode 600 with explicit UID502 ACL; UID501 read test is denied
- UID504 continuity bridge runs under com.cryptosignal.continuitybridge with RunAtLoad + KeepAlive
- UID502 direct launchd Safari relay was rejected after real TCC timeout evidence
- architecture was corrected: launchd now runs only a health watchdog; the actual relay is started through Terminal so Safari TCC permission is inherited correctly
- watchdog successfully started the relay; heartbeat is live
- the relay repeatedly reports CHATGPT_BUSY while the assistant is actively responding, proving exact-tab lookup and busy guard on live Safari
- one exact Confluence Slice 1 lease is queued and will submit only after the chat becomes idle

No Durdurulmaz project files/state were mutated. UID502 is used only as GUI transport.
The first actual post-turn receipt will complete end-to-end acceptance.

## 2026-09-20 — Confluence Slice 1 accepted: methodology-neutral evidence contracts

A neutral evidence contract now adapts independent PA, Harmonic and Elliott outputs
without changing source-methodology validity.

Accepted semantics:
- PA emits current resolved market-structure CONTEXT evidence only
- valid Harmonic matches preserve PRZ, invalidation, targets and descriptive geometry metrics
- valid-so-far Elliott counts preserve structural invalidation, projections and ambiguity
- invalid source artifacts cannot enter confluence evidence
- one neutral PIT invariant enforces market availability <= observation <= analysis as-of
- evidence metrics remain unnormalized and explicitly non-probabilistic

Mechanical evidence:
- focused confluence evidence tests: 6 PASS
- full repository: 133 tests PASS
- Ruff PASS
- mypy PASS

Canonical frontier advances to Confluence Slice 2:
evidence selection, agreement/contradiction matrix and deterministic score semantics.

## 2026-09-20 — Confluence Slice 2 accepted: selection, agreement matrix and score

Confluence now applies an explicit latest-market-time selection policy independently per methodology.
Alternatives at the same timestamp are preserved.

Directional rules:
- each methodology gets at most one vote
- internal bullish/bearish disagreement makes that methodology unresolved
- pairwise relations are AGREE / CONTRADICT / INTERNAL_AMBIGUITY / INSUFFICIENT

V1 confluence score:
(score support - opposition) / 3 * 100, rounded to 2 decimals.
The score semantic is explicitly agreement_index_not_probability.

Mechanical evidence:
- focused agreement tests: 7 PASS
- combined Confluence focused tests: 13 PASS
- full repository: 140 tests PASS
- Ruff PASS
- mypy PASS
- Bybit/Binance live 15m smoke PASS

Live smoke on both providers:
- PA selected bullish context
- Harmonic had zero valid current evidence
- Elliott latest endpoint had opposing competing counts and therefore no vote
- dominant direction bullish from PA only
- confluence score 33.33 with partial_methodology_coverage and Elliott internal-conflict flags

Canonical frontier advances to Signal Semantics V1.

## 2026-09-20 — Signal Slice 1 accepted: freeze-ready creation semantics

Signal creation now converts one ConfluenceAnalysisResult into one immutable-style
SignalDecision with deterministic state and freeze identity.

Initial decision states:
- NO_SIGNAL
- NEUTRAL
- WATCH
- ACTIVE

ACTIVE requires at least two independent supporting methodology votes, zero
opposition and exactly one complete geometry source. The rule is expressed in
methodology counts rather than an arbitrary score threshold.

Geometry is atomic: entry zone, invalidation trigger and targets come from one
MethodologyEvidence item. Cross-method geometry splicing is forbidden.

Expected R/R uses only the entry-zone midpoint as a descriptive reference and is
explicitly marked not execution.

Scientific separation:
- confluence score remains agreement_index_not_probability
- probability status is NOT_CALIBRATED
- historical analogue status is NOT_EVALUATED
- no numeric probability is fabricated

Mechanical evidence:
- focused signal/confluence tests: 21 PASS
- full repository: 148 tests PASS
- Ruff PASS
- mypy PASS
- Bybit/Binance live signal smoke PASS
- both live 15m examples currently resolve to WATCH bullish / score 33.33 /
  no geometry because Harmonic has no valid selected setup and Elliott is internally conflicted

Canonical frontier advances to Signal Slice 2 lifecycle and append-only INVALIDATED semantics.

## 2026-09-20 — Signal Semantics V1 accepted

Signal Slice 2 completed the PIT-safe invalidation lifecycle.

Accepted lifecycle rules:
- SignalDecision is never rewritten
- WATCH/ACTIVE may append an INVALIDATED transition only
- only fully post-decision, closed and locally observed candles participate
- the candle already open at decision time is skipped to avoid pre-decision OHLC contamination
- expected canonical opens are checked explicitly
- coverage is NO_NEW_EVIDENCE / COMPLETE / INCOMPLETE_GAPS
- missing candles are never synthesized
- TOUCH_OR_CROSS and CLOSE_AT_OR_BEYOND triggers remain source-owned semantics
- gap before an observed breach allows INVALIDATED but marks first-trigger timing uncertain

Mechanical evidence:
- focused lifecycle tests: 10 PASS
- full repository: 158 tests PASS
- Ruff PASS
- mypy PASS
- Bybit/Binance live-safe lifecycle smoke PASS
- current live 15m decision on both providers at acceptance: WATCH bearish / score 33.33
- lifecycle at the same decision as-of: NO_NEW_EVIDENCE
- historical REST ingestion timestamps were not backdated or presented as live-forward evidence

Signal Semantics V1 is accepted.
Canonical frontier moves immediately to Immutable Live Ledger activation.
REAL_CAPITAL remains 0.

## 2026-09-20 — Immutable Live Ledger activated; untouched-forward clock started

Immutable decision/audit storage and the live evidence clock are now active.

Accepted mechanics:
- canonical DecisionFreezeBundle hashes the decision, confluence, selected evidence,
  raw PA/Harmonic/Elliott outputs and exact consumed closed candle snapshots
- signal freeze identity is distinct from bundle identity
- SQLite WAL store rejects UPDATE and DELETE via SQL triggers
- equivalent retries are idempotent
- same source cutoff with different payload raises conflict
- lifecycle evaluations append only
- live runner refuses candle gaps and duplicate source cutoffs
- launchd runs the one-shot clock every 120 seconds under UID504 with an overlap lock

Acceptance evidence:
- immutable ledger focused tests: 9 PASS
- live clock focused tests: 3 PASS
- pre-activation full repository: 170 PASS
- Ruff PASS
- mypy PASS
- real acceptance DB: first run inserted two provider freezes; second run returned ALREADY_FROZEN
- production kickstart after activation also returned ALREADY_FROZEN and counts remained unchanged

First production untouched-forward freezes:
- Bybit: 2026-09-20T00:29:18.775Z / WATCH bearish / score 33.33
  signal=b15be217623c72c592188315e20f7731f68f3b0fafd76dbb83ce7b70ecefe304
  bundle=4a977fbdfac5e1f2202eccfb9b74980dab38fab143655a0a93a13cbe96bda1fc
- Binance: 2026-09-20T00:29:19.955Z / WATCH bearish / score 33.33
  signal=51e80cf6c98f4a8e0aeb7d8421040f1d16f601cc470544c6f65c97c6c5dd4022
  bundle=58914695eac84d2bc50e05681f2f8207d7e6bdc2ce0939764544b672901fc9b1

The evidence clock remains active while development continues.
Canonical frontier moves to Outcome + Historical Evaluation V1.
REAL_CAPITAL remains 0.

## 2026-09-20 — Outcome V1 accepted; LIVE/STABLE lane isolated

Outcome V1 now evaluates ACTIVE shadow signals without guessing intrabar order.

Accepted semantics:
- outcome vocabulary remains SUCCESS_TP1/TP2/TP3, FAIL_SL, AMBIGUOUS,
  TIMEOUT, CANCELLED, INVALIDATED and NOT_EVALUABLE
- PENDING / RESOLVED / NOT_EVALUABLE is a separate snapshot-resolution axis
- evidence class is explicit and never inferred from dates
- entry uses the frozen zone midpoint only as a shadow reference, not an execution fill
- decision-time partial candle is excluded
- entry+stop, entry+target and stop+new-target in one candle are AMBIGUOUS
- only the contiguous observed prefix before a gap is used for event ordering
- missing candles are never synthesized
- timeout requires complete configured horizon coverage
- evidence class participates in deterministic outcome identity

Immutable ledger integration:
- append-only outcome_evaluations table added
- parent signal freeze is mandatory
- equivalent retry is UNCHANGED
- same signal/evidence-class/as-of/horizon with differing payload is conflict
- SQL UPDATE/DELETE is rejected by immutability triggers

Mechanical evidence:
- Outcome behavior tests: 15 PASS
- Outcome + ledger focused gate: 28 PASS
- full repository: 189 PASS
- Ruff PASS
- mypy PASS

A production isolation risk was also corrected:
the live evidence clock no longer imports the mutable development working tree.
A clean detached LIVE/STABLE worktree was created at
/Users/crypto-signal-agent/Crypto-Signal-Live and pinned to
e53c5b29ffc9301fb36c89aa85ddc3677c4e64a1.
The installed LaunchAgent now executes the stable worktree only.
Stable manual and launchd smoke both returned ALREADY_FROZEN on an already-owned cutoff.

Canonical frontier advances to Historical Evaluation V1.
REAL_CAPITAL remains 0.

## 2026-09-20 — Historical Evaluation V1 accepted

Historical Evaluation now summarizes explicit frozen SignalDecision +
OutcomeEvaluation pairs without rerunning methodology logic.

Accepted evidence firewall:
- RETROSPECTIVE, WALK_FORWARD and LIVE_UNTOUCHED_FORWARD are mandatory
  segment dimensions
- one aggregation call rejects duplicate signal freeze identities rather than
  choosing one outcome snapshot implicitly

Accepted segmentation:
- evidence class
- geometry source methodology
- setup type
- exchange / market type / symbol / timeframe
- signal direction
- descriptive confluence-score bucket
- nullable regime label
- nullable entry reference model
- target count / labels

Accepted descriptive performance:
- success fraction = success / (success + FAIL_SL), only when decisive N > 0
- historical frequency is explicitly not probability
- SUCCESS_TPn uses the frozen corresponding target reference_rr
- FAIL_SL = -1R
- ambiguity, timeout, cancellation, invalidation, not-evaluable and pending
  outcomes receive no invented shadow R
- R-evaluable observations are chronologically ordered
- average, median, cumulative R, min/max R and peak-to-trough max drawdown are deterministic

Sample-size visibility:
- default decisive threshold = 30
- promotion_eligible is product visibility policy only, not statistical significance

Mechanical evidence:
- Historical Evaluation focused tests: 14 PASS
- full repository: 203 PASS
- Ruff PASS
- mypy PASS
- git diff check PASS

Read-only production inspection at acceptance:
- 24 untouched-forward immutable freezes
- 24 WATCH
- 0 ACTIVE
- 20 bearish WATCH / 4 bullish WATCH

Therefore no live untouched-forward success fraction or shadow-R performance is
reported yet. The system does not manufacture one from WATCH observations.

A disk-full interruption during wake delivery was also recovered safely:
only regenerable Puppeteer/uv/npm caches were removed; source, venv, runtimes,
immutable production ledger and checkpoints were preserved. The delivered wake
was reconciled exactly once after space returned.

Canonical frontier advances to Dashboard V1 / Product Command Center Slice 1:
real-data read model and information architecture before visual expansion.
REAL_CAPITAL remains 0.

## 2026-09-20 — Dashboard V1 Slice 1 accepted: read-only product model

The Product/Command Center lane now has framework-independent read models over
immutable ledger evidence.

Accepted read-only boundary:
- SQLite is opened with mode=ro and PRAGMA query_only=ON
- product code does not initialize or migrate the production ledger
- missing ledger/schema/data is represented explicitly
- runtime mock data is forbidden

Accepted surfaces:
- Command Center
- Market Radar
- Asset Cockpit
- Signal Archive
- Signal Detail
- Performance availability

Signal cards preserve decision truth:
- immutable identities and market context
- state/direction/setup
- confluence score and agreement_index_not_probability semantic
- probability_status
- uncertainty flags

The current signal-freeze schema has no separate explicit evidence-class field.
Dashboard code therefore marks signal evidence class as not explicit instead of
inferring it from timestamp, file path or runtime lane.

Performance availability reads only explicit outcome_evaluations evidence class.
An empty outcome table remains EMPTY and does not become a zero win rate.

Mechanical evidence:
- focused Dashboard tests: 8 PASS
- full repository: 211 PASS
- Ruff PASS
- mypy PASS

Production read-only smoke:
- Command Center READY
- 24 immutable freezes
- WATCH=24
- bearish=20 / bullish=4
- Market Radar contexts=2
- outcome snapshots=0
- Performance=EMPTY

Canonical frontier advances to Dashboard V1 Slice 2:
bounded FastAPI/Uvicorn API plus a static Mission Control shell.
REAL_CAPITAL remains 0.

## 2026-09-20 — Dashboard V1 Slice 2 accepted: local read-only Mission Control

Dashboard V1 now has a thin FastAPI/Uvicorn web layer over the accepted
DashboardReader plus a static HTML/CSS/JavaScript Mission Control shell.

Accepted API:
- GET /api/health
- GET /api/command-center
- GET /api/market-radar
- GET /api/assets/{symbol}/{timeframe}
- GET /api/signals
- GET /api/signals/{signal_freeze_identity}
- GET /api/performance

There is no POST order/command surface.

The shell renders only real API data and visibly preserves:
- REAL_CAPITAL=0
- Confluence != probability
- agreement-index semantics
- probability_status
- explicit empty-performance state

Mechanical evidence:
- Dashboard focused tests: 14 PASS
- full repository: 217 PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS

Real production-ledger local smoke on 127.0.0.1:48700:
- health OK / read_only=true / ledger_present=true
- Command Center READY with 24 immutable freezes
- latest cards preserve not_calibrated probability status
- latest cards preserve agreement_index_not_probability semantic
- Performance EMPTY with zero outcome snapshots
- index contains Mission Control, REAL_CAPITAL=0 and Confluence != probability markers

The temporary smoke server was stopped and port 48700 returned FREE.

Canonical frontier advances to Dashboard Slice 3:
a separate PRODUCT/STABLE worktree and persistent local LaunchAgent runtime.
LIVE/STABLE evidence clock remains independent.
REAL_CAPITAL remains 0.

## 2026-09-20 — Dashboard V1 Slice 3 accepted: isolated persistent PRODUCT/STABLE runtime

The accepted local Mission Control web surface is now isolated from the mutable
development worktree.

PRODUCT/STABLE:
- /Users/crypto-signal-agent/Crypto-Signal-Product
- detached clean worktree pinned to b1cd19fdecb80e8793d8b3db584f21de726c460c
- own .venv created from accepted uv.lock
- FastAPI 0.141.1 / Uvicorn 0.53.0 import gate PASS

Persistent runtime:
- LaunchAgent com.cryptosignal.dashboard
- RunAtLoad + KeepAlive
- localhost only: 127.0.0.1:48700
- read-only production ledger path
- runtime logs isolated under runtime/dashboard

Acceptance:
- initial PID 58609 served health HTTP 200
- listener verified on 127.0.0.1:48700 only
- child PID 58609 was intentionally terminated
- launchd runs advanced to 2 and replacement PID 59520 appeared
- after startup, port returned LISTEN and /api/health returned HTTP 200
- Uvicorn log recorded clean old shutdown and clean replacement startup

LIVE/STABLE forward evidence clock remains a separate worktree/runtime.
PRODUCT/STABLE does not mutate signal freezes or exchange/data state.

Canonical frontier advances to Dashboard V1 Slice 4:
richer frozen-evidence detail, Historical Evaluation performance projection,
explicit evidence-class views, navigation and further visual polish.
REAL_CAPITAL remains 0.

## 2026-09-20 — Dashboard V1 Slice 4 accepted in development

Slice 4 extends Mission Control with richer immutable evidence rather than new
signal truth.

Accepted rich detail:
- methodology source/selected counts and resolved direction
- selected evidence summaries, ambiguity/contradiction flags, key levels and metrics
- pairwise methodology relations
- frozen geometry only when it really exists
- candle coverage and uncertainty visibility

Accepted Performance projection:
- persisted SignalDecision and OutcomeEvaluation are strictly reconstructed
- accepted Historical Evaluation aggregate_segments() remains the sole metric engine
- newest snapshot per signal is selected inside evidence-class + holding-horizon groups
- evidence classes and holding horizons never silently merge
- historical success fraction remains descriptive frequency, not probability

Accepted navigation:
- real ledger contexts grouped by exchange/market/symbol/timeframe
- symbol/timeframe/provider selection without cross-provider synthesis

Mechanical evidence:
- Slice 4 data gate: 11 PASS
- Slice 4 combined focused gate: 17 PASS
- full repository: 220 PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS

Real-ledger development smoke on 127.0.0.1:48701:
- product_version dashboard-v1-slice4/1
- read_only=true
- freeze count 30
- navigation contexts 2
- Performance EMPTY / zero explicit outcome snapshots
- latest rich detail: PA 1/1 bullish, Harmonic 0/0 unresolved,
  Elliott 195 source / 2 selected bullish, 3 pairwise relations,
  no complete signal geometry, 499 frozen candles

No live performance claim was fabricated from the empty outcome set.

Canonical frontier is explicit PRODUCT/STABLE deployment of the accepted
Slice 4 commit followed by Dashboard V1 integrated acceptance.
REAL_CAPITAL remains 0.

## 2026-09-20 — Dashboard V1 integrated acceptance and stable deploy

Dashboard V1 is now accepted as a persistent read-only Mission Control.

PRODUCT/STABLE was explicitly advanced from b1cd19f to
2c2fc99e58d543bbf77060bb134c49b332720280 only after Slice 4 acceptance.

Stable deployment evidence:
- com.cryptosignal.dashboard state running
- PRODUCT/STABLE clean at exact accepted commit
- listener only on 127.0.0.1:48700
- /api/health HTTP 200
- product_version dashboard-v1-slice4/1
- read_only=true
- REAL_CAPITAL=0
- navigation READY with 2 real contexts
- 30 immutable freezes observed during stable smoke
- Performance EMPTY with zero explicit outcome snapshots
- rich PA/Harmonic/Elliott detail and pairwise evidence projection healthy

Mandatory V1 product surfaces are all present:
Command Center, Market Radar, Asset Cockpit, Signal Detail, Signal Archive and
Performance.

Dashboard V1 is no longer on the critical path.
Canonical frontier advances to Alerts V1.
