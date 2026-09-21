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

## 2026-09-20 — Alerts V1 Slice 1 accepted: immutable alert/outbox foundation

Alerts now have a deterministic domain model independent from signal truth.

Default V1 notification policy:
- initial ACTIVE eligible
- initial WATCH suppressed
- lifecycle transition to INVALIDATED eligible

The policy is versioned product behavior, not market truth.

Alert identity binds immutable source identities and policy version.
Equivalent source + policy reproduces the same SHA256 event identity.

A separate append-only alert outbox now stores:
- alert_events
- alert_delivery_attempts

Both tables reject UPDATE and DELETE.

Delivery semantics:
- DELIVERED terminal per sink
- PERMANENT_FAILURE terminal per sink
- RETRYABLE_FAILURE remains dispatchable
- different sinks maintain independent state
- every provider call receives alert_event_identity as idempotency key

LocalNoopSink proves dispatch/idempotency without external network delivery.

Mechanical evidence:
- focused Alerts tests: 14 PASS
- full repository: 234 PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS

Canonical frontier advances to Alerts V1 Slice 2:
a read-only Alert Clock over immutable signal/lifecycle evidence, writing only
to the separate alert outbox and using LocalNoopSink for runtime acceptance.
REAL_CAPITAL remains 0.

## 2026-09-20 — Alerts V1 Slice 2 accepted: read-only Alert Clock

Alert Clock now materializes notification events from immutable signal/lifecycle
evidence without mutating the signal ledger.

Persisted evidence parsing was centralized in crypto_signal.ledger.deserialization
so Dashboard and Alerts reconstruct the same stored SignalDecision/Outcome/
Lifecycle objects through one strict implementation.

Alert Clock source boundary:
- SQLite mode=ro
- PRAGMA query_only=ON
- no source schema initialization or migration
- source identity/row mismatches fail closed

Default runtime is materialize-only.
LocalNoopSink remains explicit acceptance-only behavior.

Mechanical evidence:
- shared-parser/Alert Clock focused tests: 38 PASS
- full repository: 241 PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS

Real production-ledger acceptance smoke:
- 30 signal freezes
- 30 lifecycle evaluations
- WATCH=30
- three repeated runs
- eligible alerts=0
- outbox events=0
- delivery attempts=0

This proves default policy does not turn WATCH evidence into notification spam.

Canonical frontier advances to Alerts V1 Slice 3:
an isolated ALERTS/STABLE materialize-only LaunchAgent runtime.
REAL_CAPITAL remains 0.

## 2026-09-20 — Alerts V1 Slice 3 accepted: isolated stable materializer

Alerts now have an isolated stable runtime:
- /Users/crypto-signal-agent/Crypto-Signal-Alerts
- detached clean worktree at f7108384e11af85e07848197f7733ff0a2e29740
- own .venv from accepted uv.lock
- LaunchAgent com.cryptosignal.alertclock
- RunAtLoad + 120-second one-shot schedule
- materialize-only production arguments

The source signal ledger remains read-only.
Eligible events are written only to the separate production alert outbox.

Runtime acceptance:
- first launchd run last exit code 0
- first run: 32 signals / 32 lifecycle / 0 eligible / 0 inserted
- stable manual rerun reproduced 0 eligible / 0 events / 0 attempts
- source state remained WATCH=32
- installed plist matches versioned plist

No no-op or external sink is configured in the production runtime, so a future
real alert cannot be accidentally consumed by a test delivery adapter.

Canonical frontier advances to Alert Center / provider-ready presentation.
REAL_CAPITAL remains 0.

## 2026-09-20 — Alerts V1 Slice 4 accepted in development: Alert Center

Mission Control now has a read-only Alert Center over the separate production
alert outbox.

Accepted projection:
- explicit EMPTY/READY/schema/missing states
- immutable alert event/source identities
- signal state/direction/setup and agreement-index semantics
- delivery state independently per sink
- pending/no-attempt remains visible instead of being inferred as delivered

Product API adds GET /api/alerts and health reports alert_outbox_present.
The API remains read-only.

Provider configuration ADR 0026 establishes:
- external providers disabled by default
- no secrets in Git/outbox/API/logs/checkpoints
- stable non-secret sink aliases
- alert event identity as provider idempotency key
- production adapters require native or durable adapter-side deduplication
- no execution semantics

Mechanical evidence:
- Alert Center focused tests: 21 PASS
- full repository: 245 PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS

Real production-outbox dev smoke:
- dashboard-v1-alert-center/1
- alert_outbox_present=true
- Alert Center EMPTY
- zero events
- no synthetic rows

Canonical frontier is explicit PRODUCT/STABLE deploy of the accepted Alert
Center commit.

## 2026-09-20 — Alert Center explicitly deployed to PRODUCT/STABLE

PRODUCT/STABLE was advanced exactly from 2c2fc99 to
b719011047d4de2fe2bf3940e6c5daae9a789d7e after Alert Center acceptance.

Stable evidence:
- com.cryptosignal.dashboard running
- listener 127.0.0.1:48700 only
- product_version dashboard-v1-alert-center/1
- read_only=true
- alert_outbox_present=true
- REAL_CAPITAL=0
- /api/alerts = EMPTY / 0 events
- Command Center observed 32 freezes, latest WATCH
- navigation READY with 2 contexts
- Performance EMPTY / 0 outcome snapshots
- rich Signal Detail healthy
- PRODUCT/STABLE clean at exact accepted commit

The dashboard was opened in Safari on the UID502 user-facing session.

Canonical frontier advances to provider-neutral notification presentation and
Alerts V1 integrated acceptance. External providers stay disabled by default.

## 2026-09-20 — Alerts V1 Slice 5 accepted: canonical notification presentation

All provider adapters now share one deterministic NotificationMessage rendering
contract derived from immutable AlertEvent truth.

The renderer explicitly preserves:
- ACTIVE / INVALIDATED state
- market identity
- direction and setup
- agreement index with not-probability label
- probability status
- source kind and UTC as-of
- uncertainty
- immutable alert identity

AlertSink now receives NotificationMessage rather than raw AlertEvent.
The immutable event identity remains the idempotency key for every provider call.

A non-secret AlertSinkConfiguration supports environment/keychain credential
references and rejects common embedded-secret markers.

ops/preview_alerts.py is a read-only dry-run path. Mission Control Alert Center
projects the same canonical title/body as future delivery adapters.

Mechanical evidence:
- Slice 5 focused tests: 34 PASS
- full repository: 255 PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS

Production outbox preview smoke:
- before: 0 events / 0 attempts
- preview count: 0
- after: 0 events / 0 attempts

Canonical frontier is stable convergence of PRODUCT/STABLE and ALERTS/STABLE on
the exact accepted Slice 5 commit, followed by Alerts V1 integrated acceptance.

## 2026-09-20 — Alerts V1 integrated acceptance

Alerts V1 is accepted end-to-end.

Stable convergence:
- PRODUCT/STABLE = 1d8c8757fb825c8934229b454db49bf800f2b5cf
- ALERTS/STABLE = 1d8c8757fb825c8934229b454db49bf800f2b5cf
- PRODUCT/STABLE dashboard healthy/read-only on localhost
- ALERTS/STABLE materializer remains one-shot materialize-only
- latest Alert Clock source observation: 34 signals / 34 lifecycle
- default WATCH policy generated 0 eligible alerts
- production alert outbox stayed at 0 events / 0 attempts
- read-only preview consumed nothing

Canonical notification semantics, provider idempotency and secret boundaries are
accepted. External provider selection remains explicit configuration, not a V1
core-truth blocker.

Project phase advances to V1 Integrated Acceptance.

## 2026-09-20 — V1 integrated gate closed LIVE/STABLE dependency-isolation gap

Integrated acceptance inspection found that com.cryptosignal.liveevidenceclock
correctly executed source from Crypto-Signal-Live but still used the mutable
development worktree's .venv interpreter.

This was treated as a real isolation defect, not waived.

Fix:
- created Crypto-Signal-Live/.venv from the LIVE/STABLE accepted uv.lock
- updated the versioned liveevidenceclock plist to use that interpreter
- reinstalled/rebootstrapped the LaunchAgent
- installed plist exact-match verified
- real one-shot launch exited 0
- live stderr empty
- existing cutoff returned idempotent already_frozen
- production ledger remained 34 freezes / 34 lifecycle

LIVE/STABLE source remains pinned at e53c5b29ffc9301fb36c89aa85ddc3677c4e64a1.
Development dependency changes can no longer implicitly change the live runtime.

## 2026-09-20 — V1 Integrated Acceptance PASS

The complete V1 critical path passed final integrated acceptance.

Final production verifier:
- ops/verify_v1_integrated.py
- V1_INTEGRATED_ACCEPTANCE=PASS

Final integrated counts:
- 34 immutable signal freezes
- 34 lifecycle evaluations
- 0 outcome evaluations
- 0 alert events
- 0 alert delivery attempts

Final repository gate:
- 255 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- all three runtime plist lints PASS

Final live methodology gates:
- Price Action integrated PASS
- Harmonic PASS
- Elliott PASS
- Confluence PASS
- Signal Semantics PASS
- Lifecycle PASS

Current live evidence was not forced into a trade:
PA bearish + Elliott bullish + Harmonic unresolved produced unresolved
confluence and a NEUTRAL signal with score 0.

A real LIVE/STABLE dependency-isolation defect was discovered during the final
gate and fixed before acceptance by moving the live clock from the development
.venv to a dedicated Crypto-Signal-Live/.venv.

V1 critical-path platform core is accepted.
Phase advances to Post-V1 Production Expansion, beginning with an explicit
untouched-forward coverage matrix rather than immediate scope expansion.

## 2026-09-20 — Post-V1 live coverage matrix accepted

The live evidence runner no longer hard-codes BTCUSDT/15m/provider parameters.
It now reads an explicit versioned LiveCoveragePlan.

The accepted stable default is intentionally unchanged:
- BTCUSDT
- 15m
- Spot
- Bybit + Binance

Data Truth is enforced in the coverage contract:
- 15m may use direct canonical 15m
- 1h/4h/1D/1W must use deterministic canonical-15m aggregation
- native higher-timeframe activation is rejected

All higher-timeframe candidates remain disabled.

Load budgeting is explicit. A 500-candle 1W analysis window would require
336,000 base 15m candles per provider, so naive one-shot REST expansion is
explicitly rejected as an activation path.

Mechanical evidence:
- coverage/live-freeze focused tests: 10 PASS
- full repository: 262 PASS
- Ruff PASS
- mypy PASS
- uv lock PASS

No production coverage change was deployed.
Canonical frontier advances to canonical higher-timeframe preparation and
bounded base-history acquisition.

## 2026-09-20 — Post-V1 canonical higher-timeframe preparation accepted

Higher-timeframe live evidence preparation now uses only canonical closed 15m
truth.

The preparation path:
- derives the exact completed target window from the latest 15m source cutoff
- checks local CandleStore cache first
- groups only missing base opens into contiguous ranges
- reuses accepted backfill_range() pagination
- performs zero API calls when the cache is complete
- aggregates only through aggregate_closed_15m()
- reports missing base opens and incomplete target buckets explicitly

Mechanical evidence:
- focused preparation/aggregation/recovery gate: 11 PASS
- full repository: 267 PASS
- Ruff PASS
- mypy PASS
- uv lock PASS

No higher-timeframe production context was enabled.
Canonical frontier advances to decoupling immutable analysis/freezing from
adapter acquisition so prepared canonical candles can later reuse one pipeline.

## 2026-09-20 — Focused V2+ Birthday Edition product direction recorded

The user confirmed that Crypto Signal is intended as a birthday gift for a friend and asked that the project
finish beyond V1 as a genuinely useful, world-class product without uncontrolled feature expansion.

Product decision:
- V1 remains accepted technical foundation, not final UX.
- Turkish-first presentation is now the default product direction.
- World-class is defined by scientific integrity + monitoring coverage + product usefulness, not feature count.
- The Birthday Edition should surface what matters now, explain why, preserve uncertainty, make frozen evidence
  visually inspectable and materially reduce manual chart chasing.
- Scope is deliberately focused: multi-timeframe truth, a small high-liquidity asset universe, premium Turkish
  Mission Control, chart intelligence, decision-quality signal explanations, conservative alerts, honest
  performance and only limited V2+ intelligence that directly improves the product.
- Broad ML, autonomous trading, Bloomberg-scale breadth and deep microstructure research are deferred.
- No fabricated probability/win-rate is authorized; REAL_CAPITAL remains 0.

The governing documents are:
- docs/POST_V1_PRODUCT_VISION_BIRTHDAY_EDITION.md
- ROADMAP_V2_PLUS_BIRTHDAY_EDITION.md

The immediate engineering frontier is unchanged: complete and accept the in-progress canonical
freeze_live_candles() refactor before any higher-timeframe production activation.

## 2026-09-20 — Post-V1 canonical freeze path accepted

The pre-pause freeze-path refactor was resumed from the exact SHA-verified frontier and completed.
freeze_live_candles() is now the canonical decision/bundle/freeze/lifecycle path; provider acquisition delegates to it.

A real higher-timeframe boundary was found by the focused gate: PA period/session levels intentionally require
canonical 15m source candles. The implementation now preserves aggregated higher-timeframe PA evidence without
fabricating coarser period/session identities; explicit non-15m session requests fail closed.

Acceptance evidence:
- focused live freeze: 7 PASS
- full repository: 271 PASS
- Ruff PASS
- mypy PASS across 119 source files
- uv lock PASS
- git diff check PASS

Canonical aggregated 1h history can now enter the immutable freeze pipeline.
Higher-timeframe production was not activated by this slice.
The next frontier is Birthday Edition Stage 1 Slice 1: integrate accepted higher-timeframe preparation into the
live runner behind fail-closed coverage and prove BTCUSDT 1h/4h before stable activation.
REAL_CAPITAL remains 0.

## 2026-09-20 — Stage 1 Slice 1 accepted: higher-timeframe live-runner integration

The post-V1 live runner now has a tested AGGREGATE_CANONICAL_15M runtime path without activating it in production.
Higher-timeframe contexts discover the latest closed 15m cutoff, prepare exact canonical base history through
CandleStore/backfill, fail closed on missing truth, aggregate complete buckets and enter freeze_live_candles().

The runtime logic was placed in crypto_signal.ledger.live_coverage rather than importing ops as a test package.
Production current_pilot remains unchanged at BTCUSDT 15m on Bybit + Binance.

Acceptance evidence:
- focused higher-timeframe runner/preparation/freeze: 14 PASS
- full repository: 273 PASS
- Ruff PASS
- mypy PASS across 121 source files
- uv lock PASS
- runner py_compile PASS
- git diff check PASS

Next: isolated real-data BTCUSDT 1h/4h acceptance on both providers before any stable activation.
REAL_CAPITAL remains 0.

## 2026-09-20 — BTC multi-timeframe production accepted

BTCUSDT production coverage was expanded from the original 15m pilot to 15m + 1h + 4h on both Bybit and Binance.
The activation followed isolated real-data acceptance rather than enabling candidate contexts directly.

Pre-production live proof:
- Bybit 1h/4h and Binance 1h/4h first pass FROZEN
- second pass ALREADY_FROZEN
- four freeze rows and four lifecycle rows
- 1,920 cached canonical 15m candles per provider

Activation code gate:
- 21 focused tests PASS
- 273 full repository tests PASS
- Ruff, mypy, uv lock and diff check PASS

LIVE/STABLE advanced to b9b8ba1662cbdb387c380318d14bba0d40f151a7.
Manual production smoke created the new 1h/4h evidence; subsequent launchd run 34 exited 0
and returned ALREADY_FROZEN for all six BTC provider/timeframe contexts.
The read-only Dashboard Market Radar immediately exposed all six contexts.
No order path was introduced and REAL_CAPITAL remains 0.

Canonical frontier advances to focused ETHUSDT + SOLUSDT 15m/1h/4h acceptance before activation.

## 2026-09-20 — Stage 2 accepted: focused BTC/ETH/SOL production universe

The Birthday Edition live universe is now deliberately small but materially useful:
BTCUSDT, ETHUSDT and SOLUSDT on Bybit + Binance Spot, each at 15m / 1h / 4h.

ETH/SOL were first proven on isolated real-data acceptance paths:
12/12 first-pass freezes, 12/12 second-pass ALREADY_FROZEN and 12 lifecycle rows.
SOL 4h resolved NEUTRAL on both providers, confirming that expansion did not force artificial signal states.

The activation code passed 21 focused tests and 273 full repository tests plus Ruff, mypy, uv lock and diff checks.
LIVE/STABLE then advanced to 7020413188d633b2b5a9661356c2fe319f256a34.

Production smoke produced 60 total freezes / 60 lifecycle rows and 18 distinct live contexts.
Dashboard Market Radar immediately exposed all 18.
A launchd kickstart completed as run 36 with last exit code 0; every owned context was idempotent and stderr was empty.

Coverage expansion is now intentionally paused at three assets and three timeframes.
The canonical frontier moves to the Turkish-first premium Mission Control requested for the Birthday Edition.
REAL_CAPITAL remains 0.

## 2026-09-20 — Stage 3 Slice 1 accepted: Turkish-first Mission Control

The product surface has begun its Birthday Edition transformation.
This is not a translation-only pass: the information hierarchy now leads with what matters in the market
instead of database telemetry.

The shell is Turkish-first and the top summary shows monitored contexts, attention states,
strong methodology agreement and latest evidence. Market Radar now groups the 18 provider contexts
into symbol/timeframe attention cards while keeping Bybit and Binance evidence separately visible.
Provider disagreement is never collapsed into false consensus.

The attention ordering is explicitly a presentation heuristic, not a probability or price forecast.
Confluence remains methodology agreement, and empty outcome evidence remains honestly empty.
No order/execution path was introduced; REAL_CAPITAL remains 0.

Acceptance evidence:
- 21 focused dashboard tests PASS
- 273 full repository tests PASS
- Ruff PASS
- mypy PASS
- uv lock PASS
- Node JavaScript syntax PASS
- git diff check PASS

Next: exact PRODUCT/STABLE deployment, live rendering verification and bounded visual polish,
then visual chart intelligence.

## 2026-09-20 — Stage 3 Slice 1 accepted: Turkish-first premium Mission Control

The Birthday Edition dashboard was reorganized around user usefulness rather than raw engineering telemetry.

Accepted changes:
- Turkish-first title, labels, states and explanatory copy
- top-level counts for monitored contexts, attention-required states, strong methodology agreement and latest evidence
- grouped Market Radar cards by asset/timeframe while preserving provider-specific evidence rows
- BTC/ETH/SOL x 15m/1h/4h focus remains explicit
- uncertainty and agreement-index-not-probability semantics remain visible
- no execution/order surface added

Quality gate:
- focused dashboard tests: 21 PASS
- full repository: 273 PASS
- Ruff, mypy, uv lock, JavaScript syntax and diff check PASS

Development smoke against the real ledger returned 18 contexts and the expected Turkish markers.
PRODUCT/STABLE advanced to 4f6394160032ba22c07056651d4052d64618be34.
Persistent dashboard health returned HTTP 200 with product_version birthday-edition-mission-control-tr/1.
Final smoke observed 66 immutable freezes.

Canonical frontier advances to Stage 4: visual chart intelligence over frozen evidence only.
REAL_CAPITAL remains 0.

## 2026-09-20 — Stage 4 accepted: frozen-evidence visual chart intelligence

Signal Detail now renders useful candlestick context from the exact immutable decision bundle.
The chart does not call an exchange or reconstruct newer market truth.

Accepted visuals:
- latest 120 frozen OHLC candles
- explicit selected-methodology key levels
- explicit invalidation prices
- frozen signal entry/invalidation/targets only when complete geometry exists
- explicit empty/fail-closed behavior when drawable truth is absent

Quality gate:
- focused dashboard tests: 21 PASS
- full repository: 273 PASS
- Ruff, mypy, uv lock, JavaScript syntax and diff check PASS

Real production-ledger development smoke:
- 499 valid frozen OHLC candles in the latest tested freeze
- 120 candles selected for chart display
- 4 explicit methodology key levels
- no new market fetch

PRODUCT/STABLE advanced to 29e70af686b73b3b4650c128397692a2f6d7b4cc.
Persistent health returned birthday-edition-chart-intelligence/1, read_only=true, REAL_CAPITAL=0
and 18 live Market Radar contexts.

Canonical frontier advances to Stage 5: deterministic Turkish decision-quality explanations.

## 2026-09-20 — Stage 5 accepted: deterministic Turkish decision-quality explanations

Signal Detail now converts immutable frozen evidence into a concise Turkish decision brief.

The product explicitly answers:
- why the setup matters now
- which independent methodologies support the frozen direction
- which methodologies are unresolved, internally conflicted or opposing
- which uncertainty flags remain
- what explicit invalidation can break the idea, when such a price actually exists

WATCH is explicitly described as incomplete relative to ACTIVE.
No LLM or newer market data participates in the explanation.
No agreement index is converted into probability and no missing invalidation is fabricated.

Quality gate:
- focused dashboard tests: 21 PASS
- full repository: 273 PASS
- Ruff, mypy, uv lock, JavaScript syntax and diff check PASS

PRODUCT/STABLE advanced to 3bdee842407bf5a172e196929b2f0744a3b2569e.
Persistent dashboard returned birthday-edition-decision-explanation/1, read_only=true,
REAL_CAPITAL=0 and 18 live Market Radar contexts.

Canonical frontier advances to Stage 6: useful Turkish alerts while preserving conservative eligibility.


## 2026-09-20 — Full Version gift vision becomes canonical roadmap

The user requested that Crypto Signal be completed as the full version rather than stopped at the earlier focused Birthday Edition. The product is still a gift for a close friend, but the full target now includes an explainable autonomous paper portfolio, beginner education, richer independent analysis engines, disciplined learning and research-driven strategy discovery.

Recorded product decisions:
- initial autonomous paper capital is exactly 100 USDT and remains fully virtual,
- REAL_CAPITAL=0 and no real exchange-order authority remains a hard boundary,
- paper performance must include fees, spread/slippage and benchmark comparison,
- cash/no-trade is a valid professional decision,
- the UI must auto-refresh and explicitly show connection/staleness state,
- Signal Detail must show frozen chart evidence, rationale, counter-case, invalidation and beginner lessons,
- PA/SMC/ICT, Harmonic and Elliott are the core, not the ceiling,
- future engines may include trend/momentum, mean-reversion, breakout/volatility, derivatives, order-flow/microstructure, on-chain/network, bounded sentiment/attention and cross-market context,
- a deterministic regime engine and meta-decision layer must prevent naive vote-counting and duplicated evidence,
- an Alpha Factory may generate new challenger strategies, but no challenger may self-deploy or self-promote,
- promotion requires leakage audit, transaction-cost stress, out-of-sample, walk-forward and untouched-forward paper evidence,
- calibrated probabilities remain forbidden until a separate sufficient-sample calibration design is accepted,
- Cursor is optional acceleration; it may work concurrently only on isolated, non-overlapping slices and never owns acceptance authority.

The canonical roadmap is now:
docs/CRYPTO_SIGNAL_FULL_VERSION_WORLD_CLASS_ROADMAP.md

Supporting contracts:
docs/AUTONOMOUS_PAPER_FUND_V1_SPEC.md
docs/INTELLIGENCE_ALPHA_FACTORY_ARCHITECTURE.md
docs/BEGINNER_UX_EVIDENCE_CENTER_SPEC.md

Canonical next engineering frontier is Stage 6A: automatic live Mission Control refresh with explicit freshness/connection semantics. Stage 6B and Stage 6C follow without weakening scientific gates.

## 2026-09-20 — Full Version Sprint 1: live refresh + beginner education reaches PRODUCT/STABLE

The first execution sprint under the governing Full Version roadmap completed successfully.

Accepted Stage 6A behavior:
- Mission Control no longer depends on routine manual F5; it performs bounded automatic refresh,
- freshness and stale/offline state are visible,
- decision truth still comes from closed/frozen evidence and was not weakened.

Accepted Stage 6B foundation:
- deterministic Turkish "Bana Öğret" lesson catalog integrated,
- education API is GET-only/read-only,
- beginner lessons explicitly distinguish methodology agreement from probability,
- paper-trading lesson states REAL_CAPITAL=0 and explains the fully virtual 100 USDT direction,
- UI exposes progressive-disclosure lesson cards rather than cluttering the primary dashboard.

Acceptance evidence:
- focused product gate PASS (19 tests plus JavaScript/Ruff/mypy),
- full repository gate PASS (281 tests; Ruff; mypy 77 source files; JavaScript),
- PRODUCT/STABLE exact SHA 14942e191c5ae354f22cb1784eae4a85c0e3a8d6,
- health status ok with product_version full-version-live-education/1,
- real_capital=0 and read_only=true.

Parallel-development lesson:
Cursor successfully produced the isolated Stage 6B education core; supervisor independently reviewed content, exact worktree scope, tests, Ruff and mypy before guarded integration. Cursor worktree was then cleaned. Cursor remains optional acceleration rather than acceptance authority.

Next:
- Stage 6B contextual teaching bound to actual frozen signal evidence,
- Stage 6C 100 USDT virtual fund domain/ledger foundation in a separate non-overlapping slice.

## 2026-09-20 — Stage 6C Slice 1: 100 USDT immutable paper accounting foundation accepted

Cursor issue #45 produced the first bounded paper-fund package in isolated worktree supervisor-45. The worker returned cursor_rc=0 and its own focused tests passed, but supervisor acceptance intentionally did not trust that result alone.

Fresh supervisor review found:
1. the new code scope was correctly limited to the paper package plus focused tests;
2. current repository Ruff rules found nine test-only style violations;
3. more importantly, the initial NAV snapshot model did not prove that declared NAV equaled cash plus marked holdings.

The slice was therefore NOT accepted as first returned.

Supervisor hardening:
- applied bounded lint corrections,
- added an invariant requiring a mark price for every held position,
- added exact NAV accounting validation: cash + sum(quantity × mark price),
- added tests rejecting inconsistent NAV and missing marks.

After hardening:
- 12 focused tests PASS,
- Ruff PASS,
- mypy PASS,
- exact-scope final review PASS.

A one-shot guarded contents-write workflow copied only the four reviewed files into canonical main. Integration commit:
09d3e68966cf7c4ff41069ae30a6aff97a1d7499

The one-shot workflow was then removed. Canonical repository was synchronized and full regression produced:
- 294 tests PASS,
- Ruff PASS,
- mypy PASS for 80 source files,
- JavaScript syntax PASS.

The isolated Cursor worktree was then removed and pruned.

This is a foundation acceptance, not activation of an autonomous trader. REAL_CAPITAL remains 0 and no persistent paper account is yet making decisions. The next paper-fund work must add deterministic state reconstruction, lineage integrity, conservative risk/planning and simulated execution policy before a persistent virtual account can run.

## 2026-09-20 — Stage 6C Slice 2 and contextual evidence UI acceptance

Cursor issue #57 produced the bounded state reconstruction + conservative planning slice in supervisor-57. Cursor completed successfully and reported 15 focused tests PASS. Supervisor did not accept this result on worker status alone.

Fresh review confirmed exact four-file scope and independently reproduced 15 focused test PASS, Ruff PASS and mypy PASS. Semantic review then found two gaps not covered by the original tests.

First, state reconstruction stored decision and fill identities in one generic known-source set. This allowed a malformed simulated fill to point its decision_identity at a prior fill identity. The hardened reconstruction now keeps typed decision lineage, requires each fill to source an earlier DecisionIntentRecord, and requires action/symbol/quantity/reference-price agreement with that decision. Replay sequence, entry identity and typed record-kind consistency were also made explicit.

Second, the BUY risk path subtracted explicit transaction cost budget from projected cash but used pre-cost NAV as the denominator for concentration and gross-exposure checks. Boundary trades could therefore be slightly less conservative than the declared policy. The hardened planner uses projected NAV after cost budget.

Hardening was fail-closed:
- one patch attempt stopped on a missing anchor before product modification;
- a second attempt exposed an error in a newly added supervisor test fixture;
- after fixing only that fixture, the final hardened gate passed 18/18 focused tests, Ruff and mypy.

The four reviewed files were integrated through a one-shot guarded workflow. Feature integration commit:
0b6bd6cf26b1f73c60c46b1ed1d97c4c68268e37

The one-shot write workflow was removed immediately afterward.

In parallel, the product signal-detail layer gained contextual evidence-linked teaching. Lessons are selected from frozen evidence, the chart exposes a textual level legend, and the detail view now includes an explicit "Neden işlem yapmamalıyız?" counter-case while preserving agreement != probability.

Product-specific gate passed 19 tests plus Ruff/mypy.

The first post-integration full-suite run produced one failure in an older alert-preview raw SQLite-file hash assertion. A bounded temporary-DB diagnostic ran the exact test five times successfully and showed the read-only preview left event truth unchanged and delivery attempts at zero; WAL/main content was unchanged in controlled runs while SQLite -shm coordination bytes changed as expected. The test was changed to compare logical alert-event, delivery-attempt and schema snapshots rather than physical WAL-mode housekeeping bytes.

Final canonical regression:
- 312 tests PASS,
- Ruff PASS,
- mypy PASS across 82 source files,
- JavaScript syntax PASS.

PRODUCT/STABLE was then advanced with rollback protection to 5d2bd3ae488ce0b579e4ba804be320b50d792943. Health verified:
- status=ok,
- product_version=full-version-contextual-evidence/1,
- REAL_CAPITAL=0,
- read_only=true.

The supervisor-57 worktree was removed and pruned.

Next Stage 6C frontier is simulated execution + deterministic plan→decision→fill→mutation orchestration. Persistent autonomous paper-account runtime must remain gated behind those correctness tests; no real-capital authority is introduced.

## 2026-09-20 — Cursor development suspended; Slice 3 rebuilt directly by supervisor

The user observed that using Cursor and then independently reviewing every result was reducing rather than improving delivery speed. Operational decision: Cursor is suspended as a development worker. Do not issue new Cursor coding tasks unless the user explicitly re-enables it.

The already-completed Cursor #78 worktree was not accepted or integrated. Before disposal, a bounded provenance probe confirmed three audit weaknesses: plan risk policy could differ from fund policy, execution policy could differ from fund policy, and rule-distinct frozen snapshots could produce identical fill identities when their immediate price/cost outcome matched.

The worktree was then removed and #78 closed as superseded.

Supervisor implemented Stage 6C Slice 3 directly on canonical main:
- deterministic frozen execution snapshot;
- snapshot-bound fill provenance;
- adverse full-fill simulation;
- explicit Decimal fee/spread/slippage accounting;
- venue-rule minimum/step checks;
- policy-bound pure plan→decision→fill→mutation orchestration;
- no database write, network, exchange or credential surface.

The first whole-repository gate passed pytest but Ruff found 20 fixable Decimal-literal style findings and one SIM102 simplification. Supervisor corrected them directly.

Final full gate:
- 330 tests PASS,
- Ruff PASS,
- mypy PASS on 84 source files,
- JavaScript syntax PASS.

This slice is accepted as pure execution/orchestration truth only. It still does not run a persistent autonomous paper account. Next work is atomic/idempotent ledger append and crash/replay safety before any continuously running virtual portfolio loop.

## 2026-09-20 — User-requested continuity pause checkpoint

The user requested a break and explicitly asked that wake and lease continuity be paused while preserving exact restart position.

pause_continuity.py was executed through the allowlisted GitHub→UID504 command path. It reported:
CONTINUITY_PAUSED leases_archived=0 queued_wakes_archived=0 relay_wakes_archived=0 worker_untouched=YES

A separate PAUSECHECK then mechanically verified:
- LOCAL_PAUSED=YES
- SHARED_PAUSED=YES
- ACTIVE_LEASES=0
- LOCAL_WAKE_QUEUE=0
- RELAY_WAKE_QUEUE=0
- PAUSE_VERIFIED=YES

The relay daemon remains allowed to exist as an idle process; pause authority is enforced by local/shared user_pause markers.

No new development work is authorized while this pause remains active.

Exact resume frontier is Stage 6C Slice 4:
atomic/idempotent append of an accepted in-memory orchestration bundle into the immutable paper ledger, plus deterministic state re-read and crash/replay safety evidence.

Accepted prior state remains:
- Slices 1–3 accepted,
- Slice 3 full gate 330 tests PASS,
- REAL_CAPITAL=0,
- Cursor development authority suspended unless explicitly re-enabled by user.

Resume must be state-first via wakeresume, then fresh READ_FIRST/CURRENT_STATUS/Chronicle/Git/continuity inspection. Stale or duplicate events must not replay completed work.


## 2026-09-20 — Stage 6C Slice 4: atomic paper-bundle persistence accepted

After the user resumed development in the new ChatGPT conversation, continuity was rebound to the supplied current chat URL and mechanically verified. UID504 canonical Git was fast-forwarded to remote main before development resumed. Cursor development authority remained suspended.

Supervisor implemented the atomic persistence boundary directly:
- PaperFundLedger gained a private multi-record atomic append primitive;
- trade bundles persist DecisionIntent, SimulatedFill and PositionCashMutation in one BEGIN IMMEDIATE transaction;
- exact retries are idempotent UNCHANGED;
- partially pre-existing bundles fail closed;
- stale replay count is checked inside the transaction;
- replay is captured from the same transaction and reconstructed deterministically after commit;
- HOLD_CASH persists decision only;
- an injected failure on simulated-fill INSERT proved SQLite rollback removes the earlier decision insert from the same transaction.

The first full repository run passed every pytest case but Ruff rejected four style-only findings (__all__ ordering and Decimal literal style). No behavioral failure occurred. Supervisor applied only the lint corrections.

Final acceptance:
- 338 tests PASS;
- Ruff PASS;
- mypy PASS across 85 source files;
- JavaScript syntax PASS;
- REAL_CAPITAL=0;
- implementation commit af5a6d45043525f1d7655567b4d1ce22365062ee;
- lint-only acceptance head 399709187f7fbfae470708be0dae43c79fb591a6.

Stage 6C may now advance to the persistent paper-account runtime foundation. That next slice must establish durable virtual-fund lifecycle/locking/restart behavior and read immutable signal evidence without silently inventing a trading/allocation policy or execution venue truth.


## 2026-09-20 — Stage 6C Slice 5: persistent no-trade paper runtime foundation accepted

With Slice 4 atomicity accepted, supervisor implemented the next bounded runtime foundation without activating a trading policy.

The new runtime:
- creates the 100 USDT virtual fund once and reuses the same fund identity on restart;
- reads the immutable live signal ledger strictly in SQLite read-only/query-only mode;
- reports freeze/lifecycle/outcome counts and latest signal metadata;
- refuses missing/malformed source ledgers before creating paper state;
- performs no decision-to-trade mapping and explicitly reports trade_policy=NOT_ACTIVATED;
- has a one-shot CLI runner protected by a non-blocking process lock;
- contains no exchange/network/credential/order surface.

The first whole-repository gate passed every pytest case; Ruff found only an import-group formatting issue in the package export file. Supervisor changed only that formatting.

Final acceptance:
- 345 tests PASS;
- Ruff PASS;
- mypy PASS across 86 source files;
- JavaScript syntax PASS;
- REAL_CAPITAL=0;
- implementation 635ff70ca8438c6c4c9f28ff67dab5fde7c8299b;
- lint-only head fe4a05bb78f43a2a6a45f0f478083144bf7adc7b.

Next safe frontier is an isolated PAPER/STABLE deployment of this no-trade clock. Stable runtime must prove one-fund restart/idempotence and production signal-ledger read-only consumption before any virtual trade eligibility policy is introduced.


## 2026-09-20 — isolated PAPER/STABLE runtime became live without activating trading

Supervisor created a dedicated Crypto Paper Stable workflow rather than overloading the general Mac command workflow. The first deployment attempt built the detached worktree and isolated virtualenv successfully but the manual acceptance probe omitted PYTHONPATH and failed at import time. Rollback executed before paper state was created.

The probe was corrected to bind PYTHONPATH to the stable worktree source. Deployment then passed:
- detached PAPER/STABLE HEAD 69a6e874f25f8c2fbfc74a1ad5ee255a79ed3222;
- isolated .venv installed from the locked project environment;
- first paper clock probe created the sole 100.00 USDT virtual fund;
- second probe returned bootstrap=existing with the exact same fund identity;
- DB no-trade invariant passed: one fund creation and zero decision/fill/mutation/NAV rows;
- com.cryptosignal.paperclock loaded with StartInterval=120 seconds and last exit code 0;
- later fresh state showed runs=3 and the same single-fund/no-trade state.

Stable fund identity:
99eebec220597639add97080a243e98715d42e75af6be3f1785721d12da00b80

The state diagnostic itself needed two non-product fixes: Python f-string quoting, then switching the DB probe from system Python to the stable runtime. Fresh state after those fixes reported:
- paper_fund_creations=1
- paper_decision_intents=0
- paper_simulated_fills=0
- paper_position_cash_mutations=0
- paper_nav_snapshots=0
- paper_replay_index=1

The stable runtime observes production immutable signal evidence but remains deliberately unable to trade. Next frontier is the explicit/versioned eligibility + allocation + cooldown/per-position-risk/no-trade policy and a frozen execution-input source. REAL_CAPITAL remains 0.


## 2026-09-20 — paper_autonomy_policy.v1 accepted

Supervisor deliberately avoided mutating the already-frozen paper_risk_policy.v1 semantics recorded in the persistent fund creation. The missing cooldown/per-position-risk/no-trade layer was added as a separate versioned pure policy.

The accepted V1 policy requires exact 4h Binance+Bybit spot consensus and fails closed on provider mismatch, mixed context, WATCH/NEUTRAL/NO_SIGNAL, stale or pre-activation evidence, unsafe uncertainty, cooldown, missing NAV marks, pyramiding and shorting.

A fresh bullish consensus while flat may emit only a BUY candidate with a maximum risk budget of 1% of marked NAV. A bearish consensus may emit only EXIT when an actual long position already exists. Automatic REDUCE is deliberately disabled.

The policy explicitly carries an activation cutoff so the existing historical signal corpus can never be replayed into retroactive paper trades. Trade candidates remain non-executable and declare that a frozen execution input is still required.

Whole-repository acceptance:
- first run: all 361 pytest cases passed; only Ruff ordering findings remained;
- style-only commit c2744497199d77cf451b831248abe68737b6ae8a fixed those findings;
- final: 361 tests PASS, Ruff PASS, mypy PASS across 87 source files, JavaScript PASS;
- REAL_CAPITAL=0.

Next gate is frozen execution-input truth. PAPER/STABLE remains observation-only until that gate and subsequent quantity/planner/execution/atomic-commit integration are accepted.


## 2026-09-20 — paper_execution_input_policy.v1 accepted

Supervisor added a deterministic read-only execution-reference layer without granting trade authority.

The policy selects the first fully closed Binance spot 15m candle that begins strictly after the accepted autonomy signal as-of and freezes that candle's OPEN as reference price. Strictly-after timing prevents using a candle that began before the signal existed. If that future candle is not yet finalized/ingested, the policy returns WAITING rather than fabricating price truth.

The source candle cache is opened mode=ro + query_only. The frozen identity binds signal lineage, candle timing, adapter version and reference price. Bybit remains signal-consensus evidence only; Binance is the explicit V1 paper execution reference venue.

First repository gate:
- all 370 pytest cases PASS;
- Ruff PASS;
- mypy found one static Optional narrowing issue after candidate validation.

A source-only narrowing fix added local non-None bindings without changing execution semantics.

Final acceptance:
- 370 tests PASS;
- Ruff PASS;
- mypy PASS across 88 source files;
- JavaScript PASS;
- REAL_CAPITAL=0.

Next gate is pure conservative position sizing. No runtime trade activation occurred.


## 2026-09-20 — paper_position_sizing_policy.v1 accepted

Supervisor accepted the pure position-sizing gate after whole-repository verification.

BUY sizing preserves exact autonomy/execution/signal lineage, requires the frozen execution reference to sit inside both provider entry zones, and uses the lowest provider invalidation as the conservative long invalidation. This maximizes stop distance and minimizes risk-based raw quantity. The output remains explicitly pre-venue and pre-cost.

EXIT sizing returns the complete existing long quantity only; missing holdings reject safely. No shorting or automatic REDUCE was added.

The first full gate passed all 378 pytest cases. Ruff found only import/style findings. A style-only hardening commit changed no sizing semantics.

Final acceptance:
- implementation 5e1e2cd2b8ee88ed449ceeafd696bff62274dc90;
- style-only head 67746b584006dd0419e4b1a460be1ed2f3637572;
- 378 tests PASS;
- Ruff PASS;
- mypy PASS across 89 source files;
- JavaScript PASS;
- REAL_CAPITAL=0.

Next gate is the venue-rule/cost/planner bridge. PAPER/STABLE remains observation-only; no virtual trade activation has occurred.


### 2026-09-20 — position sizing defense-in-depth hardening

A post-acceptance semantic review found two defense-in-depth improvements: Decimal division should explicitly round down, and sizing should independently recheck upstream lineage/pyramiding invariants rather than relying solely on autonomy.

Commit 43f7dce447673772236aff9abeb87d0f001f52c2 added explicit ROUND_DOWN, an internal max-risk product invariant, exact provider/market/timeframe/as-of checks and independent BUY pyramiding refusal.

Whole-repository hardening gate:
- 381 tests PASS;
- Ruff PASS;
- mypy PASS across 89 source files;
- JavaScript PASS;
- REAL_CAPITAL=0.


## 2026-09-20 — paper_pretrade_bridge_policy.v1 accepted

The pre-trade bridge now connects accepted sizing to the existing conservative planner without inventing venue metadata.

It requires an externally frozen execution snapshot cryptographically bound to the accepted frozen execution-input reference. BUY quantity can only round downward; frozen minimum quantity/notional are enforced. EXIT must remain a true full exit and exact venue-step quantity. The bridge derives the exact simulator-compatible fee/spread/slippage budget and passes it into the existing paper_risk_policy.v1 planner.

The first whole-repository gate passed 389 tests, Ruff, mypy across 90 source files and JavaScript. A semantic review then added causal plan-time enforcement plus independent embedded-plan lineage checks.

Final hardening head d58a181ab49da604313efa07d18c877d82ecaaf6 passed:
- 391 tests;
- Ruff;
- mypy across 90 source files;
- JavaScript;
- REAL_CAPITAL=0.

The bridge remains pure planning only. PAPER/STABLE is not activated for virtual trading. Next gate is bounded integration through deterministic orchestration and the already-accepted atomic/idempotent ledger commit, followed by persistent activation/processed-event truth and authoritative venue-rule snapshot sourcing.


## 2026-09-20 — accepted pretrade-to-atomic-commit pipeline

The accepted pretrade plan is now connected end-to-end to deterministic simulated execution and the existing atomic paper ledger boundary, without activating PAPER/STABLE trading.

Pipeline proofs include exact record-tuple binding, first-write INSERTED, exact retry UNCHANGED, stale-state rejection, snapshot-lineage rejection and an injected simulated-fill SQLite failure proving complete rollback at pipeline level.

Final accepted head:
bc57c01c072cff277725fe3493564a201c6ad13e

Whole-repository acceptance:
- 398 tests PASS;
- Ruff PASS;
- mypy PASS across 91 source files;
- JavaScript PASS;
- REAL_CAPITAL=0.

Next frontier is persistent activation watermark + append-only event claim/resolution truth, followed by authoritative frozen venue-rule sourcing. Stable virtual trading remains disabled.


## 2026-09-20 — persistent activation and atomic processed-trade receipt accepted

The paper fund now has crash-safe persistent activation/idempotency truth without enabling stable trading.

Activation is an immutable singleton in the same SQLite file as the paper ledger. V1 cutoff equals activation time, so historical freezes before activation can never be replayed into paper events. Processed events are identified from activation identity + exact source freeze pair + symbol + 4h as-of.

The critical trade path was then tightened so the simulated decision/fill/mutation records and the COMMITTED_TRADE processed receipt share one SQLite transaction. Exact retries are idempotent, stale replay state rejects, and partial commit states are prevented. The final static narrowing requires exactly two provider freeze identities.

Final accepted head 53460267178896e3cd3148c12de6dfd83de8e868 passed:
- 409 pytest cases;
- Ruff;
- mypy across 92 source files;
- JavaScript;
- REAL_CAPITAL=0.

PAPER/STABLE is still observation-only. The remaining production blocker is authoritative frozen Binance venue-rule/cost snapshot sourcing before any autonomous virtual-trade activation is considered.


## 2026-09-20 — authoritative Binance spot venue-rule cache accepted

The paper execution layer now has a real public source for venue rules instead of caller-invented quantity/minimum values. V1 reads Binance Spot /api/v3/exchangeInfo without credentials, freezes the exact symbol payload/hash, LOT_SIZE rules, tick size and minimum notional, and persists immutable rule snapshots.

A deterministic as-of selector prevents a venue-rule observation made after an execution input from being retroactively used for that event. The execution snapshot venue reference also binds the rule snapshot identity and versioned simulated-cost policy before ending in the exact execution-input identity.

The cost policy remains explicitly simulated: fee 0.001, spread 0.0005 and slippage 0.0005. It is not represented as an account-specific Binance fee tier.

Final accepted head a5d3be3564f37e5064e488bd7c0525af306128bc passed 419 tests, Ruff, mypy across 93 source files and JavaScript. REAL_CAPITAL=0.

Next: enforce captured maxQty in the authoritative planning path, then add observation-only stable refresh and validate live public rule responses for BTCUSDT/ETHUSDT/SOLUSDT.


## 2026-09-20 — authoritative maxQty pretrade hardening accepted

The cached Binance rule snapshot is now carried through an authoritative wrapper into pretrade so LOT_SIZE maxQty is enforced rather than merely archived. A rounded quantity above frozen maxQty fails closed with ABOVE_MAXIMUM_QUANTITY.

Final head 990436122f2bf14fff64b9a3dc2c1acb15014467 passed 421 tests, Ruff, mypy across 93 source files and JavaScript. REAL_CAPITAL remains 0.

Next is observation-only stable venue-rule refresh/cache and live public verification for BTCUSDT/ETHUSDT/SOLUSDT. Stable trade activation remains disabled.


## 2026-09-20 — observation-only stable venue-rule refresh accepted

The authoritative venue-rule source is now proven in the actual PAPER/STABLE environment without enabling paper trading.

Stable was deployed to cc69002b5b9b3a56414a317c1a71429a5365937d. Deploy probes kept the existing 100 USDT fund unchanged and explicitly passed trade_policy=NOT_ACTIVATED / REAL_CAPITAL=0 plus the zero-trade DB invariant.

The new [PAPER] RULESREFRESH command fetched public Binance Spot exchangeInfo metadata in the stable environment and inserted exactly one immutable snapshot for BTCUSDT, ETHUSDT and SOLUSDT. The refresh then re-ran the paper no-trade invariant.

Fresh [PAPER] STATE confirmed:
- stable HEAD cc69002b5b9b3a56414a317c1a71429a5365937d;
- paper_venue_rule_snapshots=3;
- fund creation=1;
- decision/fill/mutation/NAV=0;
- replay index=1;
- cash=100.00, positions=0;
- paper clock exit=0;
- trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Whole-repository gate for the stable refresh head passed 421 tests, Ruff, mypy across 93 source files and JavaScript.

Next frontier is a read-only production event scanner for new post-activation 4h Binance+Bybit consensus events. It must prove ordering/cutoff/processed-event behavior before any stable virtual trading activation is considered.


## 2026-09-20 — production post-activation event scanner accepted

A strict read-only scanner now defines the production event frontier without activating paper trading.

The scanner requires the immutable paper activation singleton, reads both SQLite sources query-only, filters to post-cutoff 4h spot events, pairs exact Binance+Bybit contexts, validates each persisted signal decision against its signal_freezes index row, skips already-processed event identities and orders remaining candidates deterministically.

The first scanner gate exposed one test-fixture construction mistake rather than a scanner defect. The fixture was corrected to use a valid but mismatched activation identity. All 429 behavioral tests then passed; only one Ruff import-order finding remained. Final head fd383be78059039312d586cc5fee491069bb6b8c passed:
- 429 tests;
- Ruff;
- mypy across 94 source files;
- JavaScript;
- REAL_CAPITAL=0.

Next frontier is a dry-run composition of scanner -> autonomy -> execution input -> authoritative venue rules -> sizing -> pretrade. It must remain read-only and create no processed receipt or paper mutation.


## 2026-09-20 — read-only activation dry-run composer accepted

The accepted policies can now be composed end-to-end through PRETRADE_READY without writing any paper-trade state.

Dry-run reconstruction bypasses mutating ledger/store initialization and opens paper/candle SQLite inputs query-only. One scanner event flows through autonomy, frozen execution input, as-of cached venue rules, sizing and authoritative pretrade. HOLD/WAIT/REJECT/READY states are explicit and future venue metadata cannot be backdated.

The initial full gate found one malformed WATCH fixture whose agreement counts violated the SignalAgreementSummary model before the dry-run ran. The fixture was corrected only.

Final head 3b0c0d78475554a8a9f96bac588fbc4ff5b835a7 passed:
- 435 tests;
- Ruff;
- mypy across 95 source files;
- JavaScript;
- REAL_CAPITAL=0.

PAPER/STABLE still has no trading activation. Next is an immutable watermark-initialization operation that captures the current signal-ledger baseline but grants no trade execution authority.


## 2026-09-20 — stable activation watermark initialized without trade authority

The persistent production cutoff is now real rather than hypothetical.

paper_activation_init.v1 captures the signal-ledger baseline in one read-only SQLite snapshot and creates the immutable activation singleton only if the paper fund is still pristine. The full code gate passed 439 tests, Ruff, mypy across 96 source files and JavaScript.

PAPER/STABLE was deployed to 6c2f5b9744ddb3fe3eee3793d35d2351c65f1c2c and remained a 100 USDT / zero-position / zero-trade fund. The production activation identity is a9d5ba60fac148099ba69f75d61923e0a26252faba35438ca4a9b204ef151ca4 with cutoff 1789928997447. Its frozen baseline contains 372 signal freezes and ends at ed473d03651b0958cf040cea06929cfe5b805c6a78bcf5c7a9523e9be9cca4da.

The initializer was executed twice in the same gate: first INSERTED, second UNCHANGED with the exact same identity. Fresh PAPER STATE then independently confirmed activation singleton=1, processed events=0, replay index=1 and all trade/NAV tables still zero. trade_policy remains NOT_ACTIVATED and REAL_CAPITAL=0.

Next is an allowlisted stable read-only dry-run command using only post-watermark production candidates. It may report PRETRADE_READY but must not persist any event or virtual trade.


## 2026-09-20 — first production activation dry-run completed read-only

The accepted dry-run path is now deployed in PAPER/STABLE and proven against the actual production ledgers.

Head 18a36286a4fcfc0df4f522c0f33a03203092456f passed 441 tests, Ruff, mypy across 96 source files and JavaScript, then deployed successfully with the 100 USDT fund unchanged.

The first [PAPER] DRYRUN used activation a9d5ba60fac148099ba69f75d61923e0a26252faba35438ca4a9b204ef151ca4 and cutoff 1789928997447. It found zero eligible post-cutoff freezes and therefore zero candidates. Its before/after paper-DB fingerprint matched exactly, and the independent workflow invariant confirmed zero decision/fill/mutation/NAV records, replay index=1 and processed events=0.

This is a valid production result, not a blocker: the watermark is intentionally fresh, so historical 4h decisions are excluded. PAPER/STABLE trade policy remains NOT_ACTIVATED and REAL_CAPITAL=0.

Next is a separate launchd read-only dry-run observation clock so new post-cutoff 4h provider pairs are evaluated automatically as evidence arrives, without creating paper trades.


## 2026-09-20 — read-only dry-run observation clock accepted

A separate PAPER/STABLE launchd clock now executes the accepted activation dry-run every 120 seconds without paper-ledger mutation.

Head e85af7e3e9a419e72948f4a9abea542aab0c2f75 passed 441 tests, Ruff, mypy across 96 source files and JavaScript, then deployed successfully. The dedicated dry-run clock reported last exit code 0 and the deployment/no-trade invariant passed.

Fresh state inspection showed signal ingestion had continued beyond the activation baseline (at least 384 total freezes versus baseline 372), while the strict post-cutoff 4h Binance+Bybit scanner still emitted zero eligible events and zero candidates. The paper DB stayed exactly at one fund-creation replay record, 100 USDT cash, zero positions, zero processed events and zero trade/NAV records.

This is an observation milestone only. trade_policy remains NOT_ACTIVATED and REAL_CAPITAL=0. The next safe work is candidate-observation visibility/retention while waiting for a real post-cutoff dry-run event; virtual-trade writes remain blocked.


## 2026-09-20 — dry-run candidate attention and deploy-race hardening accepted

The read-only observation clock can now make a future PRETRADE_READY candidate mechanically obvious without granting paper-trade authority. A deterministic summary exposes status counts, ready candidate identities and an attention flag; stable logs emit PAPER_DRY_RUN_ATTENTION only for PRETRADE_READY evidence.

The first stable deployment of this change exposed an operational timing race: launchd was still executing the fresh one-shot when the deploy workflow searched stdout for the new fields. The workflow failed safely and its rollback restored the prior accepted stable head with the 100 USDT zero-trade fund unchanged.

The deploy path was hardened so the exact deployed dry-run executable is probed synchronously before launchd bootstrap. The same pattern now protects the dedicated dry-run-clock deployment. Rollback backup names were also corrected to use the process PID.

Final head 63f15ead39ec9e2a6171a71ac36e7548f7fb0048 passed 443 tests, Ruff, mypy across 96 source files and JavaScript, then deployed successfully. Fresh PAPER STATE showed ready_candidates=0, attention_required=NO, paper_db_unchanged=YES, activation singleton=1, processed events=0 and all trade/NAV tables zero. Both clocks remain healthy and trade_policy remains NOT_ACTIVATED / REAL_CAPITAL=0.

Next safe work is bounded log-retention hardening while the clock waits for real post-cutoff provider-pair evidence.


## 2026-09-20 — bounded PAPER/STABLE dry-run log retention accepted

Head 6f677f158136c0988aaca80d76acd4b36aa9213f bounds the 120-second dry-run observation clock logs without altering paper decision truth. A pure single-backup rotator keeps each dry-run stdout/stderr stream at a 5 MiB threshold with at most one .1 backup, and PAPER STATE reads both the backup and current stdout when locating the newest dry-run summary/attention evidence.

Whole-repository FULLTEST passed, Ruff passed, mypy passed across 97 source files, and the JavaScript gate passed. PAPER/STABLE deployment to the exact head also passed. Fresh stable state showed both paper clocks healthy at 120-second cadence, a successful retention line, candidates=0 / ready_candidates=0 / attention_required=NO, paper_db_unchanged=YES, one activation singleton, zero processed events and zero decision/fill/mutation/NAV records. The virtual fund remains 100 USDT with zero positions. trade_policy remains NOT_ACTIVATED and REAL_CAPITAL=0.

Next safe work is a strictly read-only, structured decision-explanation trace derived from the already accepted scanner/autonomy/execution-input/venue/sizing/pretrade chain. This trace is intended to become the factual source for the future Dashboard “why did the trader do this?” experience; it must never invent thoughts or bypass the evidence lineage.


## 2026-09-20 — factual paper decision trace accepted and deployed

The read-only production path now has a deterministic explanation contract intended for the future Dashboard “what did the trader see and why did it act?” surface. paper_decision_trace.v1 projects every real dry-run candidate through the accepted autonomy, execution-input, venue-rule, sizing and pretrade chain. Each stage is explicitly PASSED, BLOCKED, NOT_REACHED or READY and carries the engine’s actual reason code plus immutable evidence identity where one exists. It does not generate free-form trader thoughts.

The first full gate exposed only one test expectation typo (the real PaperAction enum is BUY, not lowercase buy). After correcting the test contract, the complete suite passed: 448 tests, Ruff, mypy across 97 source files and JavaScript.

PAPER/STABLE then deployed successfully to 5df7fd6ab2f1c271d85f63132c0572807a5ff3a3. The production probe saw 402 signal freezes but still no strict post-watermark 4h Binance+Bybit candidate, so no PAPER_DRY_RUN_TRACE line was fabricated. The fund remains 100.00 USDT, zero positions and zero decision/fill/mutation/NAV records; activation singleton remains one; processed events remain zero; trade_policy=NOT_ACTIVATED and REAL_CAPITAL=0.

Next safe slice is a read-only portfolio/performance projection over immutable paper state and real cached market marks. This becomes the factual backend for a future simple-professional portfolio Dashboard while virtual-trade activation remains gated on real production evidence.


## 2026-09-20 — marked paper portfolio truth accepted and deployed

paper_portfolio_view.v1 now provides the factual backend for the future Dashboard portfolio. It reconstructs the immutable virtual-fund ledger through SQLite mode=ro/query_only and marks every held position only from an actually cached, fully closed Binance Spot 15m candle that existed by the requested observation time. Each mark carries deterministic source-candle evidence. If any held symbol lacks a valid mark, aggregate NAV/PnL/return are deliberately unavailable instead of estimated.

The implementation passed 452 tests, Ruff, mypy across 98 source files and the JavaScript gate. PAPER/STABLE deployed successfully to 5ccc42f2f4e049697794dcd614d1d7f9ac13f87d with the existing no-trade invariant intact.

The first production portfolio truth snapshot was snapshot 14457ea66b2213850c53a6be23d672b7854173eeb9fec57ac5b30ba367e7da95: 100.00 USDT cash, zero positions, marked position value 0, NAV 100.00, PnL 0.00, total-return fraction 0, zero decisions/fills/NAV records and one replay record. This is factual capital state, not a success claim; trade_success is explicitly NOT_YET_MEASURED. REAL_CAPITAL remains 0 and trade_policy remains NOT_ACTIVATED.

Next safe slice is a closed-trade performance layer that remains unavailable until immutable simulated round-trip evidence exists, then computes success metrics from that evidence rather than from narrative or signal confidence.


## 2026-09-20 — closed-trade performance truth accepted and deployed

paper_trade_performance.v1 now measures virtual-fund trade success only from immutable simulated BUY/EXIT fills and their exact position/cash mutations. Every fill must have one matching accounting mutation whose cash and quantity deltas reconcile to the recorded simulated fill; mismatches fail closed. Spread and slippage remain embedded in the simulated fill prices, while explicit costs remain separately visible for audit so PnL is not charged twice.

The contract deliberately separates capital state from trading success. A cash-only portfolio can truthfully report 100 USDT NAV and 0 capital return, but no completed BUY->EXIT round trip means trade performance remains NOT_YET_MEASURED. An open BUY also remains unscored until an immutable EXIT exists. When completed evidence exists, the reader deterministically exposes win/loss/breakeven counts, win rate, closed net and average PnL, average trade return, gross profit/loss, profit factor when mathematically defined, best/worst trade and explicit execution-cost totals.

The accepted head d1efcb93b66b1224b1db8762acfd3a65f47dcf62 passed 457 tests, Ruff, mypy across 99 source files and the JavaScript gate, then deployed successfully to PAPER/STABLE. Deploy evidence still showed a pristine 100.00 USDT fund with zero positions, one replay record, no trade/NAV records, 408 production signal freezes, zero strict post-watermark candidates, trade_policy=NOT_ACTIVATED and REAL_CAPITAL=0.

The first production [PAPER] PERFORMANCE probe produced snapshot 76b0b5535bbb00fe0ba3ef0a61b1376c46b5bddd7d7b570034cb90ddd9a34dac with status=not_yet_measured, zero closed/open trades and no fabricated win-rate, PnL, average return, profit-factor or execution-cost aggregate. This is the intended production truth until real paper round trips exist.

Next safe slice is a single read-only paper mission-control snapshot that composes observation health, factual portfolio state and factual closed-trade performance for the future final Dashboard pass. It must not grant paper-trade write authority.


## 2026-09-20 — unified PAPER/STABLE mission-control truth accepted

paper_mission_control.v1 now provides one strictly read-only product contract over the accepted paper evidence chain. It composes immutable activation state, a point-in-time signal-stream overview, strict post-activation event scanning, factual dry-run decision traces, marked portfolio state and closed-trade performance. A candidate can therefore eventually be shown as a real sequence of engine gates rather than a fabricated trader monologue.

The scanner was also hardened with an optional observed_at_ms cutoff. Mission Control always supplies this boundary, so freezes created after the requested observation instant cannot enter candidate counts or explanations. The final head ec685df2c08907b65ee826315cfd874dd2257688 passed 461 tests, Ruff, mypy across 100 source files and JavaScript, then deployed successfully to PAPER/STABLE with the no-trade invariant intact.

The first production mission-control snapshot was 0738b9d4203267c1227a97e4ccbbcb0525119228843aad9efc4d318f25abb34e. It observed 414 total signal freezes against activation baseline 372. The latest signal was Binance SOLUSDT 15m WATCH bearish. Strict paper eligibility remained zero: no eligible 4h post-watermark freezes, no incomplete pair, no candidate, no ready attention. The fund remained 100.00 USDT cash, zero positions, NAV 100.00, PnL 0.00 and total-return fraction 0. Closed-trade performance correctly remained NOT_YET_MEASURED with no win rate. trade_policy remained NOT_ACTIVATED and REAL_CAPITAL=0.

A separate live-clock log inspection verified that this zero-candidate state is not caused by missing 4h production coverage. BTCUSDT, ETHUSDT and SOLUSDT 4h contexts are actively executed for both Binance and Bybit and currently return already_frozen at source cutoff 1789905600000. That latest closed 4h context predates the paper activation watermark, so scanner eligibility of zero is mechanically explained. The next safe slice is to expose this decision-cadence readiness directly in Mission Control while waiting for the first genuine post-watermark 4h pair.


## 2026-09-20 — cross-provider paper event pairing corrected to immutable market cutoff

Production cadence evidence exposed an important semantic defect before any paper trade write authority was enabled. Binance and Bybit were both producing the same closed 4h market context, but their SignalDecision.as_of_ms values differed by several seconds because the live evidence clock correctly timestamps each provider at its own observation time. The paper scanner had incorrectly used that wall-clock field as the cross-provider event key, creating six incomplete groups from three genuine market events.

The immutable signal ledger already carries the correct market-event identity component: source_cutoff_open_time_ms, and its uniqueness contract is keyed by exchange/market/symbol/timeframe/source cutoff. The scanner was therefore upgraded to paper_signal_event_scanner.v2 and now groups exact Binance+Bybit evidence by symbol + shared source cutoff. It preserves each provider's original as-of time unchanged and defines the combined event availability time as max(provider as-of), so no decision can become usable before both source decisions existed. paper_autonomy_policy.v2 accepts provider as-of skew only when that exact shared market cutoff context is supplied; otherwise mixed context still fails closed.

The final head 30b05251af9fc2ac05fd007dbd6ac6d0519c2e58 passed 467 tests, Ruff, mypy across 100 source files and the JavaScript gate, then deployed successfully to PAPER/STABLE with the zero-trade invariant intact.

The live deploy probe converted six eligible freezes into exactly three complete production events: BTCUSDT HOLD_CASH / signal_not_active, ETHUSDT HOLD_CASH / signal_not_active and SOLUSDT HOLD_CASH / unsafe_uncertainty. No downstream execution-input, venue-rule, sizing or pretrade stage was fabricated for these blocked events; each factual decision trace marked them NOT_REACHED. ready_candidates remained zero, attention_required remained NO and the paper DB fingerprint stayed unchanged.

A fresh Mission Control snapshot 99f1c8652c301ddba226df79ef1c38a5a9f7d7dff2c2e39a4b7efcc90cc212c5 proved the production semantics directly. BTC, ETH and SOL each had Binance and Bybit evidence with identical shared cutoff 1789920000000 while retaining distinct provider as-of timestamps. All three cadence rows were post_activation_pair with candidate_available=YES. The virtual fund remained 100.00 USDT cash, zero positions, NAV 100.00, PnL 0.00; closed-trade performance remained NOT_YET_MEASURED. trade_policy remained NOT_ACTIVATED and REAL_CAPITAL=0.

This is the first mechanically reviewed genuine post-watermark production event set. The next safe frontier is a bounded, explicit virtual-paper write-authority gate using the already accepted atomic processed-event/trade pipeline. It must remain structurally incapable of real exchange execution and must be proven against terminal HOLD handling and simulated-trade paths before stable activation.

## 2026-09-20 — virtual-paper write gate received two fail-closed hardening passes on main

State-first recovery reconfirmed the handoff before changing development code. UID504 canonical main was clean at 320c80ad4cd9990bea2c0011fc9a6f2bf8314549, PAPER/STABLE remained 30b05251af9fc2ac05fd007dbd6ac6d0519c2e58, both paper observation clocks were healthy, and the production paper DB still contained one fund creation with zero decision/fill/mutation/NAV/processed-event records. Fresh Mission Control snapshot e271ecc65b51f1fa613378f3e96b1098d874c3eb3b934a4b9268151a83646380 observed 450 signal freezes and the same three real 4h candidates: BTC and ETH HOLD_CASH / signal_not_active, SOL HOLD_CASH / unsafe_uncertainty. ready_candidates remained zero, trade_policy remained NOT_ACTIVATED and REAL_CAPITAL=0.

A static review of the development-only write gate found two fail-closed gaps before any production activation. First, load_current_paper_write_authority validated only the latest authority row even though full-chain continuity validation existed separately. Main was hardened so current authority is derived only after validating the complete append-only chain, with a regression test that injects a structurally valid but discontinuous row and requires rejection.

Second, the write tick loaded revocable authority once before scanning/evaluation. A concurrent revoke could therefore arrive after that read but before mutation. Main was hardened again so the exact enabled authority is re-read after the read-only evaluation and immediately before every event mutation. A regression test revokes authority during evaluation and proves that the tick raises fail-closed with zero processed-event or paper-trade mutation.

The final development head for these two hardenings is 86477fd13aa21bad604de34a9d92dacd5c220632. UID504 sync passed and the whole repository gate then completed successfully: pytest 100%, Ruff PASS, mypy PASS across 102 source files, JavaScript PASS and FULL_TEST_PASS=YES.

This is development acceptance only. PAPER/STABLE was not deployed, the paper workflow still exposes no writeauthority/writetick command, no authority row was written to production, and no virtual trade or processed-event mutation was executed. Separate explicit user production authorization remains required before crossing that boundary.

## 2026-09-21 — atomic paper authority TOCTOU closed and terminal continuity rebound

The Crypto-Signal terminal continuation path was rebound to the current ChatGPT conversation before overnight autonomous work. The repository rebind workflow replaced the stale chat target with https://chatgpt.com/c/6ab046e7-34a4-83eb-96b1-2952e2b9bca6. UID504 completed the rebind and UID502 relay reload. A later bridge-state probe mechanically confirmed the same URL in both shared and local target files, relay state RUNNING with current heartbeat, the UID504 continuity bridge active, and the self-hosted runner enabled. Disk inspection showed 44 GiB free, so the historical no-space failure is no longer current.

The allowlisted Mac command workflow gained a narrowly validated wakearm command. It accepts only a bounded task identifier, a 10..86400 second delay and a bounded note, then delegates to the existing arm_exact.py/continuation_arm.sh path. It does not expose arbitrary shell. An exact immutable checkpoint was successfully armed for paper-write-authority-atomic-toctou-hardening-v1. Delayed or duplicate wakes remain state-first hints only and must NOOP when their task is already complete or superseded.

The development-only virtual-paper writer then received its final known authority-race hardening. Earlier code re-read the complete append-only authority chain after evaluation and immediately before mutation, but a narrow gap still existed between that recheck and opening the SQLite mutation transaction. Main now threads the required authority-event identity through the writer, activation and commit layers into the atomic ledger boundary. Once BEGIN IMMEDIATE is acquired, the transaction verifies that the latest authority exists, is still enabled, has the exact expected identity and matches the activation before any processed-event or simulated-trade mutation is permitted.

Two regressions revoke authority after the outer precheck but directly before terminal-no-action and simulated-trade persistence. Both paths fail closed and leave processed-event count, replay count, cash and positions unchanged. PR #294 was squash-merged as 0d89fb371fff0cbfe23176eddca760db55f0a182.

UID504 synced exactly to that head. The complete repository gate passed: pytest reached 100%, Ruff passed, mypy reported no issues across 102 source files, JavaScript passed and FULL_TEST_PASS=YES.

This remains development acceptance only. PAPER/STABLE is still 30b05251af9fc2ac05fd007dbd6ac6d0519c2e58, production write authority is not enabled, production mutation commands were not added, and no production paper event/trade was written. REAL_CAPITAL remains 0.

With the writer gate hardened but production activation intentionally closed, the next autonomous safe frontier is the beginner-facing dashboard/product pass over the already accepted read-only Mission Control, factual decision trace, marked portfolio and honest performance surfaces.

## 2026-09-21 — beginner virtual trade-plan explainability merged, tested and deployed

Stage 9 moved from a summary-only paper Mission Control into a progressively disclosed virtual-plan experience without widening paper authority. PR #311 merged as de590b15349ed3ac171eface0cb06087243d23da after an isolated UID504 feature-worktree gate passed focused pytest, JavaScript syntax, Ruff, focused mypy, the complete pytest suite, full Ruff and full mypy across 102 source files.

paper_mission_control.v2 now carries only structured accepted downstream lineage from the existing dry-run chain. A PRETRADE_READY candidate must bind its execution input, venue-rule snapshot, sizing result, venue-bound pretrade result and a new exact cost preview. The cost preview is calculated by the existing pure deterministic paper simulator against the already accepted virtual plan and frozen execution snapshot; it fails closed if fee + spread + slippage does not equal total cost or if the total differs from the accepted plan cost budget. No ledger mutation, network trade, credential or exchange-order path is introduced.

The product UI now hides complexity behind an İşlem planı disclosure. When no plan exists it explains why the engine stopped and what evidence could change the decision. When an accepted virtual plan exists it can show action, quantity, reference price, virtual notional, projected cash/quantity, sizing risk, invalidation and explicit fee/spread/slippage in both USDT and simulation-rate form. The financial amounts are backend truth from the deterministic simulator rather than duplicated browser math. Narrow-screen responsive layout was added.

Canonical UID504 sync, producttest and fulltest all passed after merge. PRODUCT then deployed exactly from 45b20084eab0bd38e14f5ca3fd4a8d799e429920 to de590b15349ed3ac171eface0cb06087243d23da. Post-deploy health reported status=ok, read_only=true and REAL_CAPITAL=0 with the dashboard service running on the exact deployed head.

PAPER/STABLE was deliberately not changed and remains 30b05251af9fc2ac05fd007dbd6ac6d0519c2e58. Fresh production state still has one fund creation, zero decision intents, zero simulated fills, zero cash/position mutations, zero NAV snapshots, one replay record, three venue-rule snapshots, one activation state and zero processed events. A fresh Mission Control snapshot ca07228c22903d46f6b626fd2255d3f73e16898d3e035be86d0184036a2a1d16 observed 498 signal freezes and the same three complete post-activation candidates: BTC and ETH HOLD_CASH / signal_not_active, SOL HOLD_CASH / unsafe_uncertainty. ready_candidates=0, attention_required=NO, cash/NAV remain 100.00 USDT, positions remain zero and performance remains NOT_YET_MEASURED. trade_policy remains NOT_ACTIVATED and REAL_CAPITAL=0.

The next safe product frontier is a beginner-facing portfolio exposure and Performance Lab slice over this immutable truth. Empty/no-trade states must remain explicit rather than presenting a zero win rate as measured performance. Production virtual-write activation remains a separate closed gate.

## 2026-09-21 — paper portfolio exposure and honest Performance Lab accepted and deployed

A delayed exact wake for dashboard-v2-paper-trade-plan-explainability-v1 was reconciled state-first rather than replayed. The exact local checkpoint was mechanically read on UID504 and its SHA256 matched 8cb66cc0e221b50b2cee2812c7a1b97a4a83e219e06ca39c544350f0417b0049. Its own resume rule required NOOP when complete or superseded, while current status and the active continuation lease identified dashboard-v2-paper-portfolio-exposure-and-performance-lab-v1 as the real frontier.

That frontier was implemented as Mission Control v3 plus two beginner-facing read-only surfaces. The new backend portfolio_exposure projection is derived only from the already accepted marked PaperPortfolioSnapshot. Cash and invested NAV shares are deterministic; every marked position carries its immutable mark identity, mark price and source closed-candle close time. Missing mark evidence closes the aggregate exposure view instead of estimating it. The exposure payload is included in the Mission Control snapshot identity, and an early full-gate failure caught the missing hash binding before integration; the identity contract was then corrected and the full isolated UID504 gate passed.

The UI now presents Sanal Portföy · Maruziyet ve nakit dengesi separately from Paper Performans Laboratuvarı. The performance lab scores only immutable completed virtual BUY→EXIT round trips. With no closed trade sample it explicitly says HENÜZ ÖLÇÜLMEDİ and leaves win rate / profit factor undefined rather than displaying 0%. When evidence eventually exists, the surface is ready to show win/loss/breakeven counts, net closed PnL, average return, profit factor, best/worst trade and explicit execution-cost totals from the accepted performance snapshot.

PR #323 merged as 0047bbae075a6fed7f5067d4263bd7cf447c45b4. Canonical UID504 sync, producttest and fulltest all passed after merge. PRODUCT deployed exactly from de590b15349ed3ac171eface0cb06087243d23da to 0047bbae075a6fed7f5067d4263bd7cf447c45b4, and post-deploy health remained status=ok, read_only=true and REAL_CAPITAL=0.

PAPER/STABLE remained untouched at 30b05251af9fc2ac05fd007dbd6ac6d0519c2e58. Fresh production state still contains one fund creation, zero decision intents, zero simulated fills, zero position/cash mutations, zero NAV snapshots, one replay record, three venue-rule snapshots, one activation singleton and zero processed events. Fresh Mission Control snapshot 9cfc86d0038ab60391f183d0a435c485a37d823a8a4fec63729526986d82afa3 observed 510 signal freezes and the same three complete post-activation candidates: BTC and ETH HOLD_CASH / signal_not_active and SOL HOLD_CASH / unsafe_uncertainty. The fund remains 100.00 USDT cash, zero positions, NAV 100.00 USDT and performance NOT_YET_MEASURED. trade_policy remains NOT_ACTIVATED and REAL_CAPITAL=0.

The next safe Stage 9 product frontier is to finish the history/operations side of the Gift Edition: clearly separate immutable signal history from virtual-trade history and expose dedicated System Health / freshness evidence. This remains read-only and does not cross the production paper-write gate.

## 2026-09-21 — Signal/Trade Archive and System Health complete the current Stage 9 product pass

The final identified Stage 9 history/operations gap was completed without introducing a new backend mutation surface. The product now presents SİNYAL / İŞLEM ARŞİVİ as two explicitly different evidence domains: signal history remains immutable market-decision truth from the signal ledger, while virtual-trade history is rendered only from existing Mission Control paper portfolio/performance truth. No fill evidence produces an explicit “Henüz sanal işlem kaydı yok” state rather than a fabricated 0% trading result. Open virtual positions, if they later exist, remain unscored and separate from completed BUY→EXIT round trips.

A dedicated SİSTEM SAĞLIĞI surface was added using only already exposed read-only product truth. It reports the product API read-only/REAL_CAPITAL state, signal-ledger availability, paper Mission Control availability, production paper write-policy closure, alert outbox presence and immutable signal-freeze age. Missing evidence is surfaced as attention rather than silently declared healthy. It does not inspect or control launchd, does not grant authority and does not expose any new order or credential path.

Feature head a6e48128d850368be573c8021ed839a80932a03f passed the isolated UID504 focused/full pytest, JavaScript, Ruff and mypy gate. PR #337 merged as 38327ee46f7d9ae7c97e019bf13391084cb0b9d5. Canonical UID504 sync, producttest and fulltest all passed. PRODUCT then deployed exactly from 0047bbae075a6fed7f5067d4263bd7cf447c45b4 to 38327ee46f7d9ae7c97e019bf13391084cb0b9d5; post-deploy health remained status=ok, read_only=true and REAL_CAPITAL=0.

PAPER/STABLE remained unchanged at 30b05251af9fc2ac05fd007dbd6ac6d0519c2e58. Paper DB counts still show one fund creation and zero decision intents, simulated fills, position/cash mutations, NAV snapshots or processed events. Fresh Mission Control snapshot 8da165c4e08fa5fda52ee8e3813688dbc59edbeb233c32e1754933ae87cafb85 observed 510 signal freezes, the same three HOLD_CASH candidates, zero ready candidates, 100.00 USDT cash, zero positions and NOT_YET_MEASURED paper performance. trade_policy remains NOT_ACTIVATED and REAL_CAPITAL=0.

With the current Stage 9 product-facing surfaces materially complete, the next safe frontier is Stage 10 Full Integrated Acceptance: a read-only acceptance program across repository gates, stable runtime health/recovery, auto-refresh/staleness, deterministic paper reconstruction/cost semantics, no-leakage and UI/evidence consistency. The separate production paper-write activation boundary remains closed.

## 2026-09-21 — Stage 10 Full Integrated Acceptance closed PASS

Stage 10 is now mechanically accepted at code/PRODUCT head `8ca23e612ba36b4ebcb0c3cb41a166d78add5cff`. The final acceptance was not inferred from static tests alone: it followed several runtime failures that exposed and closed real integration defects.

The first Stage 10 endurance attempt exposed read-surface latency on the live PRODUCT API. Subsequent bounded-read/scaling work removed unbounded expensive reads while preserving immutable evidence semantics. A later runtime attempt then passed PRODUCT restart, paper-clock restart/no-write and live recovery soak but reported live PRODUCT Mission Control as unavailable. State-first diagnosis showed that the launchd dashboard invoked `run_dashboard.py --ledger ...`; because `create_app` deliberately treats an explicitly supplied signal ledger as a custom/test runtime unless paper/candle sources are also explicit, the PRODUCT process had no paper ledger or candle cache configured. PAPER/STABLE Mission Control itself remained healthy throughout.

PR #386 closed that integration gap without changing PAPER/STABLE or its write boundary. `ops/run_dashboard.py` now supplies the existing default read-only paper ledger and candle cache to `create_app` even when launchd provides the signal ledger. The installed launchd plist contract was intentionally left unchanged, so normal PRODUCT checkout + service restart was sufficient. The feature branch passed the hosted full gate, then main synchronized and passed canonical UID504 producttest/fulltest before exact PRODUCT deployment.

The final Stage 10 runtime acceptance was GitHub Actions run `35566415433`, job `106229013172`, on exact head `8ca23e612ba36b4ebcb0c3cb41a166d78add5cff`. It completed successfully and emitted:
- `STAGE10_PRODUCT_RESTART_PASS=YES`
- `STAGE10_PAPER_RESTART_NO_WRITE_PASS=YES`
- `STAGE10_LIVE_RECOVERY_PASS=YES`
- `STAGE10_RUNTIME_ACCEPTANCE_PASS=YES`
- `PRODUCT_FRESHNESS_CONTRACT_PASS=YES`
- `STAGE10_RUNTIME_ACCEPTANCE=PASS`

The real endurance gate executed 20 read-only PRODUCT cycles, observed `paper_mission_control.v4`, and bound the accepted benchmark snapshot `066204f6753dfd6e09ca03b88ed5e1990d75471f1fa66b1ea42a0557fcd881aa`. Runtime stable heads were DEV/PRODUCT `8ca23e612ba36b4ebcb0c3cb41a166d78add5cff`, LIVE `7020413188d633b2b5a9661356c2fe319f256a34`, ALERTS `1d8c8757fb825c8934229b454db49bf800f2b5cf`, and PAPER `30b05251af9fc2ac05fd007dbd6ac6d0519c2e58`.

Most importantly, the paper database stayed unchanged across the runtime acceptance: one fund creation, zero decision intents, zero simulated fills, zero position/cash mutations, zero NAV snapshots, one replay record, one activation singleton and zero processed events. The production virtual-paper write policy is still `NOT_ACTIVATED`, no writer command is exposed through PAPER/STABLE, no real exchange authority exists and `REAL_CAPITAL=0`.

This closes Stage 10 itself. It does not by itself assert that every aspirational Full Version roadmap stage outside the Stage 10 acceptance matrix has been implemented. The next safe action is a whole-roadmap completeness audit, especially the Stage 8 / 8.5 / 8.75 intelligence, Alpha Factory and Learning Memory scopes, before declaring the overall project finished.

## 2026-09-21 — first Stage 8 engine accepted: deterministic regime labeling

The whole-roadmap audit correctly prevented Stage 10 product acceptance from being mistaken for completion of Stage 8/8.5/8.75. The first bounded Stage 8 frontier, regime labeling, is now accepted at main head `4cdfbd134597a8329fb90d08eed5643161cd4926`.

The new `crypto_signal.intelligence.regime` engine is deliberately observation-only. It consumes one homogeneous candle context, sorts by market open time, rejects duplicate opens, and admits only candles that are closed and whose close/source/ingestion timestamps are all available at the requested as-of time. It produces explicit unresolved states for insufficient history or candle gaps instead of interpolating or inventing evidence.

Resolved evidence carries deterministic directional displacement, path length, efficiency, baseline/recent range and volatility ratio. Labels are trend_up, trend_down, range or transition, with compressed/normal/expanded volatility tracked separately. Analysis and frozen consumed-candle bundles are independently SHA-bound. Tests also prove that future evidence cannot change a historical freeze and that the new intelligence module is not imported into production confluence/signal-ledger decision surfaces.

The first hosted acceptance run failed usefully: stepwise returns had been normalized by each local price while endpoint displacement was normalized by the first price, allowing the derived efficiency ratio to exceed its theoretical upper bound on a monotonic trend. The metric was corrected to raw first-to-last displacement divided by raw path length, with path_length_bps normalized to the same first-price base. This preserves directional/displacement semantics while enforcing the triangle-inequality bound [0,1].

After the correction, the hosted full repository gate passed, then PR #400 merged and UID504 canonical sync/fulltest passed on the exact accepted main head. No production weighting, broker path, paper write authority, Alpha Factory promotion or learning authority was introduced. REAL_CAPITAL remains 0.

The next bounded Stage 8 frontier is trend/momentum evidence. It must follow the same discipline: deterministic source contract, PIT-safe inputs, frozen evidence, explicit uncertainty, independent tests and no silent production contribution.

## 2026-09-21 — second Stage 8 engine accepted: trend / momentum

PR #403 merged the bounded `crypto_signal.intelligence.trend_momentum` engine as
`f8b525e355a7fb587e9c0913965326a67630576a`. The engine is observation-only and
adds deterministic multi-horizon trend/momentum evidence with short, medium and
long returns, directional consistency, acceleration/deceleration phase and
explicit mixed/unresolved uncertainty. Inputs are restricted to point-in-time-safe
closed candles and accepted evidence is identity-bound/frozen.

The branch passed the hosted full repository gate, then UID504 canonical sync and
fulltest passed on the merged head. Canonical evidence includes pytest 100%, Ruff
PASS, mypy PASS across 106 source files, the product freshness contract and
`FULL_TEST_PASS=YES`.

No production confluence weighting, exchange authority, paper writer activation,
Alpha Factory promotion or learning-memory authority was introduced.
`REAL_CAPITAL=0` remains invariant.

The true next bounded Stage 8 frontier is `stage8-mean-reversion-v1`.

## 2026-09-21 — third Stage 8 engine accepted: mean reversion

PR #406 merged the bounded `crypto_signal.intelligence.mean_reversion` engine as
`4e6d25df7f6aa2f36bf4ee86dba5c9023dd055d4`. The engine uses a robust median
center, signed/absolute price displacement, bounded range-position evidence and a
short-horizon phase that distinguishes snapback, extension and stalled behavior.
It emits stretched-high, stretched-low, neutral, mixed or unresolved states and
does not emit probability claims.

Inputs are restricted to PIT-safe closed candles. Insufficient history and candle
gaps fail closed, and future candles cannot alter historical evidence freezes.
Analysis and consumed-candle freezes are independently SHA-bound. A production
isolation/ablation test proves the engine contributes zero to the current stable
confluence path until a later separately accepted integration policy exists.

The hosted full repository gate passed with pytest 100%, Ruff PASS, mypy PASS
across 108 source files and the product freshness contract. After merge, UID504
canonical sync and fulltest also passed on the exact accepted head, including
pytest 100%, Ruff, mypy across 107 source files and `FULL_TEST_PASS=YES`.

No production weighting, paper writer activation, exchange authority, Alpha
Factory promotion or learning-memory authority was introduced.
`REAL_CAPITAL=0` remains invariant.

The next bounded Stage 8 frontier is `stage8-breakout-volatility-v1`.

