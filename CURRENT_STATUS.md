# CURRENT STATUS

Updated: 2026-09-20
Project: Crypto Signal
Phase: Post-V1 Production Expansion
State: POST_V1_HIGHER_TF_PREPARATION_ACCEPTED
REAL_CAPITAL: 0

## Accepted foundations
- Phase 0 Environment & Constitution
- Phase 1 Data Truth
- Shared deterministic swing primitives
- PA / SMC / ICT V1
- Harmonic V1
- Elliott Wave V1

## Elliott V1 accepted evidence
- partial Wave 1 through Wave 5 structural counts
- standard impulse hard-rule evidence
- generic A-B-C endpoint candidates
- zigzag compatibility without false subdivision certainty
- competing counts preserved
- structural invalidation and Fibonacci guideline projections
- truncation evidence retained
- rule-support fractions explicitly non-probabilistic
- 127 tests PASS
- Ruff PASS
- mypy PASS
## Elliott live evidence
Long 15m Bybit:
- 4,798 closed candles
- 5,110 impulse candidates
- 1,020 completed counts
- 63 hard-price-rule-valid completed counts
- 33 valid counts with truncated fifth evidence
- 1,022 A-B-C candidates
- 316 zigzag-compatible endpoint geometries
- 870 ambiguous end pivots with multiple valid competing counts

Long 15m Binance:
- 4,798 closed candles
- 4,900 impulse candidates
- 978 completed counts
- 60 hard-price-rule-valid completed counts
- 28 valid counts with truncated fifth evidence
- 980 A-B-C candidates
- 304 zigzag-compatible endpoint geometries
- 828 ambiguous end pivots with multiple valid competing counts
Multi-timeframe deterministic smoke PASS on both providers for:
- 15m
- 1h
- 4h
- 1D
- 1W

These are structural candidate counts, not uniquely correct Elliott labels,
probabilities, win rates or execution recommendations.

## Autonomous continuity
Local wake/lease transport is active at the control-plane level:
- exact Crypto chat URL is bound in runtime state
- UID504 continuity bridge runs as a KeepAlive LaunchAgent
- exact-task immutable lease is active
- UID504 submits HMAC-authenticated events into a shared relay queue
- relay secret/target ACL allows only UID504 and UID502
- UID502 Safari exact-URL probe: one matching tab, JavaScript automation PASS
- UID502 relay watchdog runs from launchd and starts the actual relay through Terminal to preserve macOS TCC authority
- live busy-guard evidence repeatedly reports CHATGPT_BUSY while this response is active
- first post-turn real submission receipt remains the final end-to-end acceptance evidence
- generic idle wake remains disabled

Cursor Agent CLI is installed but remains not logged in; workers are optional and do not block supervisor development.

A foreign Durdurulmaz wake was reconciled as NOOP for Crypto Signal.
No Durdurulmaz or Quantum Capital project state was mutated; UID502 is used only as isolated GUI transport.

## Confluence Slice 1 accepted evidence
- methodology-neutral evidence model added
- PA current resolved structure maps to CONTEXT evidence only
- valid Harmonic matches preserve PRZ / invalidation / T1-T2 / residual metrics
- valid-so-far Elliott counts preserve invalidation / projections / competing-count ambiguity
- invalid Harmonic/Elliott artifacts are rejected at the adapter boundary
- neutral PIT invariant: market_available_at <= observed_at <= as_of
- metrics remain descriptive and unnormalized
- 133 tests PASS
- Ruff PASS
- mypy PASS

## Confluence Slice 2 accepted evidence
- latest-market-time selection per methodology
- same-timestamp alternatives preserved
- one directional vote maximum per methodology
- internal bullish/bearish conflict resolves to UNRESOLVED and casts no vote
- pairwise AGREE / CONTRADICT / INTERNAL_AMBIGUITY / INSUFFICIENT matrix
- deterministic score = (support - opposition) / 3 * 100
- score rounded to 2 decimals and explicitly tagged agreement_index_not_probability
- 140 tests PASS
- Ruff PASS
- mypy PASS
- live Bybit/Binance confluence smoke PASS
- live 15m example: PA bullish; Harmonic no valid evidence; Elliott internally conflicting; resulting score 33.33 with partial coverage flag

## Signal Slice 1 accepted evidence
- freeze-ready SignalDecision model
- initial states: NO_SIGNAL / NEUTRAL / WATCH / ACTIVE
- ACTIVE requires 2+ independent supporting methodologies, zero opposing votes and exactly one complete geometry source
- WATCH preserves one complete geometry when available but does not activate without independent support
- multiple complete geometry candidates are not silently ranked
- entry midpoint used only as descriptive R/R reference, not execution assumption
- invalidation trigger is preserved from source evidence
- probability status = NOT_CALIBRATED
- historical analogue status = NOT_EVALUATED
- deterministic SHA256 freeze identity
- 148 tests PASS
- Ruff PASS
- mypy PASS
- live Bybit/Binance signal smoke PASS
- current live 15m state on both providers: WATCH bullish, confluence score 33.33, no geometry, no fabricated probability

## Signal Slice 2 accepted evidence
- immutable SignalDecision remains unchanged
- append-only invalidation transition model
- only fully post-decision closed/observed candles may invalidate
- decision-time partial candle is skipped to prevent pre-decision OHLC contamination
- explicit NO_NEW_EVIDENCE / COMPLETE / INCOMPLETE_GAPS coverage states
- missing candle opens are explicit and never invented
- TOUCH_OR_CROSS and CLOSE_AT_OR_BEYOND semantics preserved
- deterministic transition identity
- 158 tests PASS
- Ruff PASS
- mypy PASS
- live-safe Bybit/Binance smoke PASS
- current live 15m decisions on both providers: WATCH bearish, score 33.33
- lifecycle at decision as-of: NO_NEW_EVIDENCE

## Immutable Live Ledger active evidence
- decision freeze bundle includes SignalDecision, Confluence, selected evidence, raw PA/Harmonic/Elliott and exact consumed closed candles
- signal freeze identity and broader bundle identity are separate
- SQLite WAL store is SQL-immutable: UPDATE/DELETE rejected by triggers
- same signal/source-cutoff equivalent retry is idempotent
- same source cutoff with different bundle is explicit conflict
- lifecycle evaluations append only
- live clock runner is protected by a non-blocking process lock
- LaunchAgent com.cryptosignal.liveevidenceclock is active with RunAtLoad + 120-second interval
- pilot scope: BTCUSDT 15m, Bybit Spot + Binance Spot, 500-candle window
- first production untouched-forward freezes created 2026-09-20 03:29:18-03:29:19 Europe/Istanbul
- production re-kickstart on same cutoff returned ALREADY_FROZEN for both providers
- production DB remained exactly 2 freezes + 2 lifecycle evaluations after idempotence check
- ledger/live-clock acceptance: 170 tests PASS, Ruff PASS, mypy PASS

## Outcome V1 accepted evidence
- explicit outcome vocabulary: SUCCESS_TP1/TP2/TP3, FAIL_SL, AMBIGUOUS, TIMEOUT, CANCELLED, INVALIDATED, NOT_EVALUABLE
- snapshot resolution is separate: PENDING / RESOLVED / NOT_EVALUABLE
- evidence class is explicit: RETROSPECTIVE / WALK_FORWARD / LIVE_UNTOUCHED_FORWARD
- shadow entry reference is zone midpoint and is explicitly not execution
- decision-time partial candle is excluded
- same-candle entry/stop, entry/target, and stop/new-target are AMBIGUOUS without lower-resolution evidence
- gaps are explicit and are never synthesized
- immutable outcome_evaluations table with parent freeze enforcement, idempotence, conflict detection, and SQL UPDATE/DELETE rejection
- Outcome behavior tests: 15 PASS
- Outcome + ledger focused gate: 28 PASS
- full repository: 189 tests PASS
- Ruff PASS
- mypy PASS

## LIVE/STABLE isolation
- production clock runs only from /Users/crypto-signal-agent/Crypto-Signal-Live
- live worktree is pinned to accepted commit e53c5b29ffc9301fb36c89aa85ddc3677c4e64a1
- main development worktree cannot affect production clock without explicit accepted deploy
- production DB currently continues append-only forward freezes independently of development

## Historical Evaluation V1 accepted evidence
- EvaluatedSignal binds one frozen SignalDecision to exactly one verified OutcomeEvaluation snapshot
- duplicate signal freeze identities are rejected inside one aggregation call
- evidence class is a mandatory segment dimension and cannot silently merge
- segment key includes methodology/setup/exchange/market/symbol/timeframe/direction/confluence bucket/regime/entry model/target structure
- success fraction denominator is explicit: success / (success + FAIL_SL)
- historical success fraction is descriptive_frequency_not_probability
- shadow R exists only for SUCCESS_TP1/TP2/TP3 and FAIL_SL
- FAIL_SL = -1R; success R is read from frozen target reference_rr
- ambiguous/timeout/cancelled/invalidated/not-evaluable/pending outcomes receive no invented R
- chronological average/median/cumulative R and max drawdown are deterministic
- default decisive sample threshold 30 is product visibility policy, not significance
- focused gate: 14 tests PASS
- full repository: 203 tests PASS
- Ruff PASS
- mypy PASS
- current production untouched-forward freezes: 24 WATCH / 0 ACTIVE; no live performance statistic is fabricated

## Dashboard V1 Slice 1 accepted evidence
- framework-independent read-only product contracts added
- DashboardReader uses SQLite mode=ro + PRAGMA query_only=ON
- no schema initialization/migration occurs in product reader
- Command Center / Market Radar / Asset Cockpit / Signal Archive / Signal Detail / Performance availability models exist
- frozen cards expose immutable identities, state/direction/setup, confluence score semantic, probability status and uncertainty
- signal evidence class is not inferred when freeze-level field is absent
- performance reads only explicit outcome evidence class
- missing ledger/schema/data states are explicit
- focused gate: 8 tests PASS
- full repository: 211 tests PASS
- Ruff PASS
- mypy PASS
- production read-only smoke: 24 immutable WATCH freezes, 2 radar contexts, 0 outcome snapshots, Performance=EMPTY
- no runtime mock data

## Dashboard V1 Slice 2 accepted evidence
- FastAPI 0.141.1 + Uvicorn 0.53.0 bounded dependencies
- read-only GET API over accepted DashboardReader
- /api/health reports REAL_CAPITAL=0, read_only=true and ledger presence
- static Mission Control shell with no Node build chain
- Command Center / Market Radar / Asset Cockpit / Signal Archive / Signal Detail / Performance availability rendered from real API data
- no POST order/command surface
- empty outcome evidence remains EMPTY, not 0% win rate
- focused web/read-model gate: 14 tests PASS
- full repository: 217 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- local real-ledger smoke on 127.0.0.1:48700 PASS; test server stopped and port returned FREE

## Dashboard V1 Slice 3 accepted evidence
- isolated PRODUCT/STABLE worktree at /Users/crypto-signal-agent/Crypto-Signal-Product
- PRODUCT/STABLE pinned to accepted Dashboard commit b1cd19fdecb80e8793d8b3db584f21de726c460c
- product-local .venv created from accepted uv.lock
- FastAPI 0.141.1 / Uvicorn 0.53.0 runtime imports PASS
- com.cryptosignal.dashboard LaunchAgent installed with RunAtLoad + KeepAlive
- dashboard binds only to 127.0.0.1:48700
- production ledger path is consumed read-only through accepted DashboardReader
- initial runtime health HTTP 200 with ledger_present=true / read_only=true / REAL_CAPITAL=0
- KeepAlive acceptance: original PID 58609 stopped, replacement PID 59520 started, port rebound and health returned HTTP 200
- PRODUCT/STABLE is independent from mutable development source
- LIVE/STABLE evidence clock remains independent

## Dashboard V1 Slice 4 accepted evidence
- rich Signal Detail now projects frozen methodology selections, ambiguity/contradiction flags, pairwise agreement, geometry and candle coverage
- persisted SignalDecision / OutcomeEvaluation JSON is reconstructed strictly and fail-closed
- Performance reuses accepted Historical Evaluation aggregate_segments() rather than a UI-specific formula
- latest outcome snapshot per signal is selected within explicit evidence-class + holding-horizon groups
- RETROSPECTIVE / WALK_FORWARD / LIVE_UNTOUCHED_FORWARD remain separate
- holding horizons remain separate
- symbol / timeframe / provider navigation added
- combined Slice 4 focused gate: 17 tests PASS
- full repository: 220 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- real-ledger development smoke on 127.0.0.1:48701 PASS
- smoke observed 30 immutable freezes, 2 navigation contexts and Performance=EMPTY with zero outcome snapshots
- temporary development server stopped after smoke

## Dashboard V1 integrated acceptance
- all mandatory V1 surfaces are present: Command Center, Market Radar, Asset Cockpit, Signal Detail, Signal Archive and Performance
- latest full development gate: 220 tests PASS / Ruff PASS / mypy PASS / JS syntax PASS / uv lock PASS
- PRODUCT/STABLE explicitly advanced to 2c2fc99e58d543bbf77060bb134c49b332720280
- stable product_version=dashboard-v1-slice4/1
- localhost-only 127.0.0.1:48700 listener verified
- stable health HTTP 200 / read_only=true / REAL_CAPITAL=0
- stable real-ledger navigation/rich-detail/performance smoke PASS
- Dashboard V1 is accepted and no longer on the critical path

## Alerts V1 Slice 1 accepted evidence
- alert policy is explicit/versioned and separate from signal truth
- default policy: initial ACTIVE eligible, WATCH suppressed, INVALIDATED lifecycle transition eligible
- alert identity is deterministic over immutable source + policy
- INITIAL_SIGNAL and LIFECYCLE_TRANSITION source kinds are explicit
- append-only alert_events + alert_delivery_attempts outbox
- SQL UPDATE/DELETE rejected by triggers
- RETRYABLE_FAILURE remains dispatchable; DELIVERED/PERMANENT_FAILURE are terminal per sink
- provider sink receives alert event identity as idempotency key on every retry
- LocalNoopSink validates delivery semantics without external notification
- focused gate: 14 tests PASS
- full repository: 234 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS

## Alerts V1 Slice 2 accepted evidence
- persisted SignalDecision/Outcome/Lifecycle reconstruction moved to shared ledger deserialization
- Alert Clock opens source signal ledger mode=ro + PRAGMA query_only=ON
- source ledger is never initialized/migrated by Alerts
- default runtime is materialize-only; LocalNoop dispatch is explicit acceptance-only option
- eligible events append idempotently into separate alert outbox
- malformed source evidence and identity mismatches fail closed
- focused shared-parser/clock gate: 38 tests PASS
- full repository: 241 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- production smoke: 30 WATCH freezes + 30 lifecycle evaluations -> 0 eligible / 0 alerts / 0 delivery attempts across repeated runs

## Alerts V1 Slice 3 accepted evidence
- isolated ALERTS/STABLE worktree at /Users/crypto-signal-agent/Crypto-Signal-Alerts
- ALERTS/STABLE pinned to accepted f7108384e11af85e07848197f7733ff0a2e29740
- alerts-local .venv created from accepted lockfile
- com.cryptosignal.alertclock LaunchAgent installed
- RunAtLoad + StartInterval=120s one-shot materialization
- source signal ledger remains read-only
- production outbox is runtime/alerts/alert_outbox.sqlite3
- no --dispatch-local-noop and no external provider in production runtime
- first launchd run exit 0; repeated stable run idempotent
- current source: 32 WATCH freezes / 32 lifecycle -> 0 eligible alerts / 0 attempts
- installed plist matches versioned plist
- LIVE/STABLE and PRODUCT/STABLE remain independent

## Alerts V1 Slice 4 accepted evidence
- Mission Control Alert Center reads production alert outbox read-only
- explicit NO_LEDGER / SCHEMA_UNAVAILABLE / EMPTY / READY states
- immutable alert identity/source semantics preserved
- delivery attempts projected independently per sink
- pending/no-attempt state remains explicit
- GET /api/alerts added; product API remains read-only
- product version dashboard-v1-alert-center/1
- provider secret/idempotency boundary documented in ADR 0026
- focused gate: 21 tests PASS
- full repository: 245 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- real-outbox dev smoke: alert_outbox_present=true / Alert Center EMPTY / 0 events

## Alerts V1 Slice 4 stable deployment evidence
- PRODUCT/STABLE advanced exactly to b719011047d4de2fe2bf3940e6c5daae9a789d7e
- com.cryptosignal.dashboard restarted successfully
- listener verified on 127.0.0.1:48700 only
- stable product_version=dashboard-v1-alert-center/1
- health read_only=true / alert_outbox_present=true / REAL_CAPITAL=0
- /api/alerts stable smoke: EMPTY / 0 events
- Command Center stable smoke: 32 freezes / latest WATCH
- navigation READY / 2 contexts
- Performance EMPTY / 0 explicit outcomes
- rich Signal Detail healthy
- 502 Safari opened at http://127.0.0.1:48700
- PRODUCT/STABLE clean after deploy

## Alerts V1 Slice 5 accepted evidence
- canonical NotificationMessage derived deterministically from immutable AlertEvent
- ACTIVE and INVALIDATED rendering explicit
- agreement index always labeled not probability
- probability status preserved rather than fabricated
- AlertSink receives canonical NotificationMessage, not raw AlertEvent
- event identity remains the provider idempotency key
- non-secret AlertSinkConfiguration supports environment/keychain credential references
- embedded-secret markers are rejected by configuration validation
- read-only ops/preview_alerts.py consumes no events and writes no delivery attempts
- Mission Control Alert Center uses the same canonical title/body renderer
- focused gate: 34 tests PASS
- full repository: 255 tests PASS
- Ruff PASS
- mypy PASS
- JavaScript syntax PASS
- uv lock PASS
- production preview smoke preserved 0 events / 0 attempts before and after

## Alerts V1 integrated acceptance
- PRODUCT/STABLE and ALERTS/STABLE converged on exact accepted 1d8c8757fb825c8934229b454db49bf800f2b5cf
- dashboard stable health PASS / read_only=true / alert_outbox_present=true
- Alert Clock stable materializer exit 0 across repeated runs
- latest observed source 34 signals / 34 lifecycle
- default WATCH suppression produced 0 eligible / 0 event / 0 attempt
- canonical NotificationMessage is shared by Mission Control preview and provider boundary
- stable preview is read-only and consumed nothing
- external providers remain disabled by default
- Alerts V1 is accepted end-to-end

## V1 integrated runtime isolation finding closed
- integrated gate found LIVE/STABLE source was isolated but its LaunchAgent still used development .venv
- dedicated /Users/crypto-signal-agent/Crypto-Signal-Live/.venv was created from LIVE/STABLE accepted uv.lock
- versioned liveevidenceclock plist now uses Crypto-Signal-Live/.venv/bin/python
- installed plist matches versioned plist
- real launchd one-shot exited 0 after migration
- source ledger remained 34 freezes / 34 lifecycle and current cutoff retries stayed idempotent
- live clock stderr remained empty
- LIVE/STABLE source head remains e53c5b29ffc9301fb36c89aa85ddc3677c4e64a1
- mutable development dependency changes can no longer alter LIVE/STABLE Python environment implicitly

## V1 integrated acceptance
- docs/V1_INTEGRATED_ACCEPTANCE.md published
- ops/verify_v1_integrated.py production verifier PASS
- final integrated counts: 34 freezes / 34 lifecycle / 0 outcomes / 0 alert events / 0 alert attempts
- final repository gate: 255 tests PASS / Ruff PASS / mypy PASS / JS syntax PASS / uv lock PASS
- live PA/Harmonic/Elliott/Confluence/Signal/Lifecycle verifiers all exited 0
- LIVE/STABLE dedicated .venv isolation defect found and closed before acceptance
- PRODUCT/STABLE / ALERTS/STABLE accepted runtime heads verified
- dashboard localhost/read-only/REAL_CAPITAL=0 boundaries verified
- V1 critical-path platform core is ACCEPTED

## Post-V1 live coverage matrix accepted evidence
- hard-coded live provider/symbol/timeframe scope replaced by versioned LiveCoveragePlan
- current production pilot remains BTCUSDT / 15m / Spot / Bybit + Binance
- 15m requires DIRECT_CANONICAL_15M
- 1h/4h/1D/1W require AGGREGATE_CANONICAL_15M
- direct/native higher-timeframe activation is rejected
- higher-timeframe candidates exist only as disabled contexts
- per-run canonical base-15m load budget is explicit
- 500 weekly target candles would require 336,000 base 15m candles per provider
- current live runner reads the accepted pilot plan and fails closed on unsupported aggregate contexts
- focused gate: 10 tests PASS
- full repository: 262 tests PASS
- Ruff PASS / mypy PASS / uv lock PASS
- no production coverage deployment occurred

## Post-V1 higher-timeframe preparation accepted evidence
- target windows are derived from fully completed target buckets only
- required canonical 15m range is computed exactly
- local CandleStore cache is checked before network acquisition
- only missing contiguous 15m ranges are fetched
- accepted backfill_range() provides bounded <=1000 pagination
- complete cache causes zero new API calls
- missing base opens and incomplete aggregate buckets remain explicit
- higher-timeframe candles are produced only by aggregate_closed_15m()
- focused gate: 11 tests PASS
- full repository: 267 tests PASS
- Ruff PASS / mypy PASS / uv lock PASS
- no production higher-timeframe context activated

## Canonical next frontier
Focused V2+ Birthday Edition governs post-V1 execution.

Accepted and live:
- focused BTC / ETH / SOL coverage on Bybit + Binance at 15m / 1h / 4h
- Turkish-first premium Mission Control
- frozen-evidence candlestick chart intelligence
- deterministic Turkish decision-quality explanations

PRODUCT/STABLE:
3bdee842407bf5a172e196929b2f0744a3b2569e

LIVE/STABLE:
7020413188d633b2b5a9661356c2fe319f256a34

Current product truth:
- 18 live Market Radar contexts
- Signal Detail answers neden önemli / ne destekliyor / ne eksik / ne bozabilir
- explanations use frozen evidence only
- methodology agreement is never presented as probability
- REAL_CAPITAL=0

Immediate Stage 6: useful Turkish alerts.
1. preserve conservative eligibility: initial ACTIVE and INVALIDATED transitions; WATCH remains suppressed
2. Turkish-first notification title/body from immutable AlertEvent truth
3. include symbol, timeframe, state, direction, methodology agreement and key uncertainty
4. avoid alert spam and avoid invented probability
5. retain provider-call idempotency by alert_event_identity
6. external provider remains disabled until explicit credential/provider choice
7. full alerts/product/repository gates before ALERTS/STABLE and PRODUCT/STABLE advancement

After Stage 6:
honest performance/learning -> limited V2+ intelligence -> gift-ready integrated acceptance.

REAL_CAPITAL remains 0.

## 2026-09-20 — Full Version / World-Class roadmap authorized

The user expanded the target from the focused Birthday Edition to the complete gift-quality version and asked that the project remain faithful to this direction.

New governing documents:
- docs/CRYPTO_SIGNAL_FULL_VERSION_WORLD_CLASS_ROADMAP.md
- docs/AUTONOMOUS_PAPER_FUND_V1_SPEC.md
- docs/INTELLIGENCE_ALPHA_FACTORY_ARCHITECTURE.md
- docs/BEGINNER_UX_EVIDENCE_CENTER_SPEC.md

Major authorized future capabilities:
- automatic live dashboard refresh; no routine manual F5,
- beginner-first "Bana Öğret" explanations tied to frozen chart evidence,
- fully virtual 100 USDT autonomous paper fund with immutable fills/costs/NAV and benchmarks,
- clear virtual purchase plans explaining amount, risk, fee/spread/slippage, invalidation, rationale and counter-case,
- expansion beyond PA/SMC/ICT + Harmonic + Elliott into regime, trend/momentum, mean-reversion, breakout/volatility, derivatives, order-flow, on-chain and bounded contextual engines behind separate evidence gates,
- regime-aware meta-decision and risk engines,
- Alpha Factory / champion-challenger research with walk-forward/out-of-sample/untouched-forward gates,
- interpretable learning memory; failures remain visible,
- no automatic self-promotion or uncontrolled self-modification,
- no probability claim without accepted calibration evidence.

Execution policy:
- Cursor is an optional acceleration worker, never a blocking dependency.
- Supervisor may advance independent slices directly while Cursor works in an isolated non-overlapping worktree.
- Worker outputs require fresh state/diff/test review before integration.

Immediate frontier: Stage 6A live Mission Control / automatic refresh, followed by Stage 6B evidence-teaching foundation and Stage 6C immutable 100 USDT paper fund.

REAL_CAPITAL remains 0.

## 2026-09-20 — Full Version Sprint 1 accepted and deployed

Stage 6A live Mission Control slice:
- automatic dashboard refresh every 15 seconds,
- freshness age and 45-second stale threshold,
- online/offline/stale/error UI states,
- immediate refresh when the tab becomes visible,
- concurrent refresh suppression,
- selected market navigation preserved by existing state-aware navigation logic.

Stage 6B education foundation:
- deterministic Turkish education catalog,
- 10 canonical concepts: BOS, CHoCH, liquidity sweep, FVG, Harmonic/PRZ, Elliott Wave, invalidation, risk/reward, methodology agreement vs probability, paper trading,
- typed explicit lookup/missing behavior,
- no LLM or fabricated probability,
- read-only /api/education and /api/education/{concept_id},
- visible "Bana Öğret" beginner teaching center with beginner, why-it-matters and advanced layers.

Mechanical evidence:
- focused product gate: 19 tests PASS after lint correction,
- full repository gate: 281 tests PASS,
- Ruff PASS,
- mypy PASS across 77 source files,
- JavaScript syntax PASS.

PRODUCT/STABLE:
- advanced from 3bdee842407bf5a172e196929b2f0744a3b2569e to 6f29d38be18924c34a80cfd1071eeb5a4a8f242a for Stage 6A,
- then advanced to 14942e191c5ae354f22cb1784eae4a85c0e3a8d6 for the visible Stage 6B foundation,
- rollback-safe deploy gate used,
- post-restart health PASS,
- product_version=full-version-live-education/1,
- read_only=true,
- REAL_CAPITAL=0.

The earlier one-shot contents-write integration workflow was removed immediately after use.

Current frontier:
- continue Stage 6B with evidence-linked/contextual teaching inside Signal Detail,
- in parallel begin Stage 6C immutable 100 USDT autonomous paper-fund foundation.

## 2026-09-20 — Stage 6C Slice 1 accepted: immutable 100 USDT paper-fund foundation

Stage 6C Slice 1 is accepted in canonical main as the accounting/domain foundation for the future autonomous virtual portfolio.

Accepted package:
- src/crypto_signal/paper/__init__.py
- src/crypto_signal/paper/models.py
- src/crypto_signal/paper/ledger.py
- tests/test_paper_fund.py

Accepted invariants:
- REAL_CAPITAL=0.
- Initial cash is exactly Decimal("100.00") USDT.
- Initial positions are empty.
- Initial permitted symbols are BTCUSDT, ETHUSDT, SOLUSDT.
- Permitted virtual actions are HOLD_CASH, BUY, REDUCE, EXIT.
- No leverage, borrowing, shorting, derivatives execution, martingale or real-order surface.
- Money/quantity truth uses Decimal.
- Fund creation, decision intent, simulated fill, cash/position mutation and NAV snapshots are immutable typed records.
- Deterministic canonical SHA256 identities are used.
- Fee, spread and slippage are explicit.
- Partial fills are explicitly unsupported in v1 rather than silently approximated.
- SQLite ledger is caller-path based, append-only, replayable and rejects UPDATE/DELETE via triggers.
- Exact duplicates are idempotent; divergent payload under an existing deterministic identity fails.
- Replay preserves append order and survives reopen/restart.
- NAV snapshot now requires every held position to have a mark price and mathematically enforces NAV = cash + marked position value.
- Benchmarks are reserved for CASH_100, BTC_BUY_HOLD_100 and BTC_ETH_SOL_EQUAL_WEIGHT_100.

Acceptance evidence:
- Cursor worker issue #45 completed with cursor_rc=0.
- Supervisor rejected first acceptance because current Ruff found 9 test-style violations.
- Supervisor also found and closed a NAV-truth gap before integration.
- Hardened focused gate: 12 tests PASS, Ruff PASS, mypy PASS.
- Guarded exact-scope integration commit: 09d3e68966cf7c4ff41069ae30a6aff97a1d7499.
- One-shot contents-write integration workflow was removed immediately after use.
- Canonical full regression after integration: 294 tests PASS, Ruff PASS, mypy PASS across 80 source files, JavaScript syntax PASS.
- Cursor worktree supervisor-45 was removed and pruned after acceptance.

Important scope boundary:
This slice does NOT yet mean that the virtual 100 USDT account is actively making decisions or running in production. It provides the deterministic immutable accounting foundation only.

Next Stage 6C frontier:
- reconstruct current paper-fund state from ledger,
- enforce cross-record lineage/referential integrity,
- deterministic conservative risk policy and virtual transaction planning,
- versioned simulated execution-cost policy,
- connect accepted market decisions to virtual HOLD/BUY/REDUCE/EXIT intents without any real order authority,
- only after those gates, run a persistent live paper account and expose it read-only in Mission Control.

## 2026-09-20 — Stage 6C Slice 2 accepted: deterministic state reconstruction + conservative planning

Stage 6C Slice 2 is accepted in canonical main.

Accepted files:
- src/crypto_signal/paper/state.py
- src/crypto_signal/paper/planning.py
- tests/test_paper_state.py
- tests/test_paper_planning.py

Accepted state-reconstruction invariants:
- read-only reconstruction from immutable PaperFundLedger replay;
- exactly one fund creation, exact 100.00 USDT initial cash, zero initial positions;
- strict increasing replay sequence_id;
- replay entry identity and record kind must match the typed record;
- every later record must belong to the reconstructed fund;
- a simulated fill must reference an earlier real DecisionIntentRecord, never another fill;
- fill action/symbol/quantity/reference price must match its source decision intent;
- mutation source must be an earlier decision/fill belonging to this fund;
- cash_before and positions_before must exactly equal prior reconstructed accounting state;
- negative cash/positions are rejected;
- latest valid NAV snapshot is tracked separately and must match reconstructed cash/positions;
- reconstruction never mutates the ledger.

Accepted planning invariants:
- plan is intent only: no ledger append, no exchange/network/credential surface;
- allowed outcomes remain HOLD_CASH, BUY, REDUCE, EXIT;
- default v1 limits: max single-position concentration 25%, minimum cash reserve 20 USDT, max gross exposure 50%;
- leverage, borrowing, shorting, derivatives and martingale are forbidden;
- BUY requires sufficient cash including explicit cost budget;
- REDUCE/EXIT cannot exceed holdings; EXIT closes the complete symbol holding;
- BUY concentration/gross-exposure checks use projected NAV after transaction-cost budget;
- missing evidence yields HOLD_CASH or explicit rejection, never fabricated certainty;
- deterministic plan identity;
- REAL_CAPITAL=0.

Acceptance evidence:
- Cursor issue #57 / run 35515447286 completed cursor_rc=0.
- Initial independent supervisor review: 15 focused tests PASS, Ruff PASS, mypy PASS.
- Supervisor found and closed two latent gaps before acceptance: fill→fill masquerading as decision lineage; cost budget omitted from projected NAV denominator for boundary risk checks.
- Hardened gate: 18 focused tests PASS, Ruff PASS, mypy PASS.
- Guarded exact-scope integration commit: 0b6bd6cf26b1f73c60c46b1ed1d97c4c68268e37.
- One-shot contents-write integration workflow removed immediately after use.
- Final canonical full regression after all accepted changes: 312 tests PASS, Ruff PASS, mypy PASS across 82 source files, JavaScript syntax PASS.
- supervisor-57 worktree removed and pruned.

Scope boundary:
This still does NOT activate an autonomous persistent paper account. State truth and conservative planning are accepted; simulated execution, plan→decision/fill/mutation orchestration, persistent clock/runtime and read-only portfolio UI remain subsequent gates.

## 2026-09-20 — Stage 6B contextual evidence teaching accepted and live

The signal-detail education layer is now bound to frozen decision evidence rather than showing only a generic catalog.

Accepted behavior:
- "Bu sinyali bana öğret" selects concepts only from the frozen signal's methodology, geometry or explicit evidence labels;
- supports contextual BOS, CHoCH, liquidity sweep, FVG, Harmonic/PRZ, Elliott, invalidation, risk/reward and agreement-vs-probability lessons;
- each contextual lesson explains why it appears for that specific frozen decision;
- evidence chart now includes a textual legend with kind, label and exact frozen price level;
- explicit "Neden işlem yapmamalıyız?" counter-case is shown;
- wording preserves that methodology agreement is not probability and does not force a trade;
- newer price data is explicitly prevented from rewriting historical frozen evidence.

Acceptance evidence:
- product gate: 19 tests PASS, Ruff PASS, mypy PASS;
- final canonical full regression: 312 tests PASS;
- PRODUCT/STABLE advanced from 14942e191c5ae354f22cb1784eae4a85c0e3a8d6 to 5d2bd3ae488ce0b579e4ba804be320b50d792943 with rollback protection;
- live /api/health verified status=ok, product_version=full-version-contextual-evidence/1, real_capital=0, read_only=true.

Regression note:
A prior full-suite run exposed a WAL-sensitive alert-preview test that compared raw SQLite main-file bytes. Bounded diagnostics showed 5/5 exact test repeats PASS, unchanged main/WAL payloads in controlled runs, only expected -shm coordination changes, one event row and zero delivery attempts. The test was corrected to compare logical outbox/schema truth rather than SQLite housekeeping bytes; final full regression then passed.

## 2026-09-20 — Stage 6C Slice 3 accepted: supervisor-direct deterministic execution + orchestration

The user explicitly suspended Cursor as a development worker because repeated independent review/hardening was eroding the expected speed benefit. No new Cursor development tasks should be issued unless the user explicitly re-enables it. Existing Cursor infrastructure may remain dormant for optional future use.

Issue #78 Cursor output was NOT integrated. It was treated only as disposable diagnostic reference, then supervisor-78 was removed and the issue was closed as superseded by supervisor-direct implementation.

Fresh probe of the discarded draft mechanically demonstrated two audit gaps:
- a plan carrying a risk-policy version different from the fund was accepted;
- an execution snapshot carrying a policy version different from the fund was accepted;
- two different frozen snapshot identities with identical fill math could collapse to the same SimulatedFillRecord identity.

Supervisor then implemented Slice 3 directly in canonical main.

Accepted execution foundation:
- immutable caller-supplied FrozenExecutionSnapshot;
- snapshot identity covers venue reference, symbol, quantity step, minimum quantity, minimum notional, fee, spread, slippage, execution policy and partial-fill flag;
- venue values are explicit frozen simulation inputs, never claimed live Binance/Bybit truth;
- partial fills remain unsupported in v1;
- Decimal-only execution math;
- quantity step/minimum quantity/minimum notional gates;
- adverse BUY and REDUCE/EXIT simulated prices;
- explicit fee/spread/slippage accounting;
- cost-budget fail-closed;
- execution_reference binds the snapshot SHA256 into the resulting fill provenance, preventing rule-distinct snapshots from collapsing to the same fill identity;
- REAL_CAPITAL=0 and no network/exchange/credential/order surface.

Accepted orchestration foundation:
- pure state + PaperTradePlan + frozen snapshot -> immutable in-memory record bundle;
- no ledger/database write;
- HOLD_CASH -> DecisionIntent only;
- BUY/REDUCE/EXIT -> DecisionIntent + SimulatedFill + PositionCashMutation;
- plan fund identity must equal state fund identity;
- plan risk-policy version must equal fund risk-policy version;
- execution snapshot policy version must equal fund execution-policy version;
- decision policy provenance must reconcile with plan;
- fill is bound to exact frozen snapshot provenance;
- BUY cash uses actual simulated fill notional + fee;
- sell cash uses actual simulated fill proceeds - fee;
- positions reconcile with accepted plan projection;
- actual realized execution may be better than plan's explicit cost budget but may never be worse;
- EXIT leaves zero quantity.

Direct implementation files:
- src/crypto_signal/paper/execution.py
- src/crypto_signal/paper/orchestration.py
- tests/test_paper_execution.py
- tests/test_paper_orchestration.py

Acceptance evidence:
- initial supervisor full gate found only lint/style issues after all tests passed;
- lint corrected directly by supervisor;
- final canonical full regression: 330 tests PASS;
- Ruff PASS;
- mypy PASS across 84 source files;
- JavaScript syntax PASS;
- REAL_CAPITAL remains 0.

Current Stage 6C frontier:
- atomic/idempotent append of an accepted orchestration bundle into the immutable ledger;
- deterministic current-state re-read after append;
- persistent paper-account clock/runtime only after atomicity/replay/crash-safety gates;
- read-only portfolio/NAV/benchmark Mission Control view after runtime truth exists.

## USER PAUSE CHECKPOINT — 2026-09-20 17:57 +03

User explicitly requested a break and asked for wake + lease continuity to be paused while preserving exact resume state.

Mechanical pause evidence:
- CONTINUITY_PAUSED succeeded.
- local user_pause marker present.
- shared relay user_pause marker present.
- ACTIVE_LEASES=0.
- LOCAL_WAKE_QUEUE=0.
- RELAY_WAKE_QUEUE=0.
- PAUSE_VERIFIED=YES.
- no active Cursor worker owns the frontier.
- relay daemon may remain alive, but paused markers prevent continuity/wake processing.

Resume mechanism is already present:
- allowlisted command: wakeresume
- implementation: ops/continuity/resume_continuity.py
- resume semantics: remove local/shared pause markers, state-first rearm required, stale relay replay disabled.

Exact accepted development state before pause:
- Stage 6C Slice 1 accepted: immutable 100 USDT paper accounting foundation.
- Stage 6C Slice 2 accepted: deterministic state reconstruction + conservative planning.
- Stage 6C Slice 3 accepted via supervisor-direct implementation: frozen/versioned simulated execution + pure plan→decision→fill→mutation orchestration.
- canonical full gate after Slice 3: 330 tests PASS, Ruff PASS, mypy PASS across 84 source files, JavaScript syntax PASS.
- REAL_CAPITAL=0.
- Cursor development authority remains suspended unless the user explicitly re-enables it.

Exact next frontier on resume:
Stage 6C Slice 4 — atomic/idempotent append of an accepted orchestration bundle into the immutable paper ledger, followed by deterministic current-state re-read. Do NOT start persistent paper-account runtime, Mission Control paper portfolio activation, or any later stage before this atomicity/crash-safety gate is accepted.

Resume procedure:
1. run wakeresume;
2. read READ_FIRST_CRYPTO_SIGNAL.md + this CURRENT_STATUS checkpoint + newest Chronicle;
3. inspect fresh canonical Git/worker/continuity state;
4. treat stale/duplicate wake or lease events as NOOP;
5. continue only from Stage 6C Slice 4 if fresh state still confirms it is the canonical unfinished frontier.


## 2026-09-20 — Stage 6C Slice 4 accepted: atomic/idempotent paper bundle commit

Stage 6C Slice 4 is accepted in canonical main.

Accepted files:
- src/crypto_signal/paper/ledger.py
- src/crypto_signal/paper/commit.py
- src/crypto_signal/paper/__init__.py
- tests/test_paper_commit.py

Accepted persistence invariants:
- one accepted trade orchestration bundle is committed as DecisionIntent + SimulatedFill + PositionCashMutation inside one SQLite BEGIN IMMEDIATE transaction;
- HOLD_CASH commits exactly one DecisionIntent and invents no fill/mutation;
- all bundle identities absent -> insert the complete bundle;
- all bundle identities present with exact kind/payload -> idempotent UNCHANGED;
- any partially existing bundle -> hard conflict before completing missing records;
- stale replay state is rejected inside the write transaction using the expected immutable replay count;
- bundle identities are required to remain contiguous in replay order;
- post-commit state is reconstructed from the exact replay snapshot captured inside the transaction;
- inserted trade state must exactly match the accepted mutation cash/positions/last-mutation lineage;
- injected mid-bundle SQLite failure rolls the whole transaction back, leaving no partial decision/fill/mutation;
- REAL_CAPITAL remains 0 and no exchange/network/credential/order surface was introduced.

Acceptance evidence:
- first full gate: all 338 pytest cases passed; Ruff found only 4 auto-fixable style findings.
- lint-only hardening commit: 399709187f7fbfae470708be0dae43c79fb591a6.
- final canonical full regression: 338 tests PASS.
- Ruff PASS.
- mypy PASS across 85 source files.
- JavaScript syntax PASS.
- atomic implementation commit: af5a6d45043525f1d7655567b4d1ce22365062ee.

Current Stage 6C frontier:
- persistent paper-account runtime foundation may now begin because atomicity/replay/crash-safety gate is accepted;
- first runtime slice must preserve a single durable 100 USDT virtual fund, process immutable signal evidence read-only, use process locking/idempotent restart semantics and keep REAL_CAPITAL=0;
- no autonomous BUY/REDUCE/EXIT policy may be invented implicitly: decision-to-plan eligibility, frozen execution inputs and virtual allocation policy must be explicit/versioned before the runtime is allowed to trade;
- read-only Mission Control portfolio/NAV/benchmark activation remains after persistent runtime truth exists.


## 2026-09-20 — Stage 6C Slice 5 accepted: persistent paper runtime foundation

Stage 6C Slice 5 is accepted in canonical main.

Accepted files:
- src/crypto_signal/paper/runtime.py
- ops/run_paper_clock.py
- tests/test_paper_runtime.py
- src/crypto_signal/paper/__init__.py

Accepted runtime-foundation invariants:
- one persistent virtual fund is created exactly once at 100.00 USDT and subsequent restarts reopen the same fund identity;
- initial paper-fund creation uses the accepted immutable paper ledger and race-safe replay-count gate;
- accepted immutable signal ledger is opened with SQLite mode=ro + PRAGMA query_only=ON;
- signal freezes, lifecycle evaluations and outcome evaluations are observed but never initialized, migrated or mutated by paper runtime;
- a missing or malformed signal ledger fails before a new paper fund is created;
- runtime exposes explicit signal-ledger counts/latest frozen signal metadata only;
- one-shot runner uses a non-blocking process file lock;
- runtime deliberately exposes trade_policy_activated=false / trade_policy=NOT_ACTIVATED;
- no BUY/REDUCE/EXIT decision policy, exchange venue lookup, networking, credentials or real-order path is introduced;
- REAL_CAPITAL remains 0.

Acceptance evidence:
- first full gate passed all pytest cases and failed only one Ruff import-order finding;
- lint-only hardening commit: fe4a05bb78f43a2a6a45f0f478083144bf7adc7b;
- final canonical full regression: 345 tests PASS;
- Ruff PASS;
- mypy PASS across 86 source files;
- JavaScript syntax PASS;
- runtime implementation commit: 635ff70ca8438c6c4c9f28ff67dab5fde7c8299b.

Current Stage 6C frontier:
- deploy the accepted no-trade paper clock into an isolated PAPER/STABLE worktree/LaunchAgent and prove restart/idempotent fund reuse against the production immutable signal ledger;
- only after stable runtime truth is proven, define a separate explicit/versioned decision-to-plan eligibility + virtual allocation policy and frozen execution-input source before permitting simulated BUY/REDUCE/EXIT;
- Mission Control paper portfolio/NAV/benchmark activation remains after that runtime truth exists.


## 2026-09-20 — PAPER/STABLE no-trade runtime deployed and accepted

The accepted Stage 6C Slice 5 runtime foundation is now deployed in an isolated stable lane.

Stable runtime:
- worktree: /Users/crypto-signal-agent/Crypto-Signal-Paper
- stable deployed HEAD: 69a6e874f25f8c2fbfc74a1ad5ee255a79ed3222
- LaunchAgent: com.cryptosignal.paperclock
- interval: 120 seconds
- paper ledger: /Users/crypto-signal-agent/Crypto-Signal/runtime/paper/paper_fund.sqlite3
- source signal ledger: /Users/crypto-signal-agent/Crypto-Signal/runtime/ledger/live_signal_ledger.sqlite3
- runtime code/environment: isolated PAPER/STABLE worktree + its own .venv
- REAL_CAPITAL=0
- trade policy: NOT_ACTIVATED

Mechanical deployment acceptance:
- first probe created fund identity 99eebec220597639add97080a243e98715d42e75af6be3f1785721d12da00b80 at exactly 100.00 USDT;
- immediate second probe reopened the same fund identity with bootstrap=existing;
- fresh stable state after scheduled service activity still reports the same fund identity, cash=100.00, positions=0 and records=1;
- LaunchAgent fresh state: runs=3, last exit code=0, run interval=120 seconds;
- production immutable signal ledger is observed read-only; fresh snapshot saw 312 freezes / 312 lifecycle rows / 0 outcomes and latest state WATCH on SOLUSDT;
- fresh paper DB counts: fund_creation=1, decision_intents=0, simulated_fills=0, position_cash_mutations=0, nav_snapshots=0, replay_index=1;
- no virtual trade was created during deployment or restart validation.

Deployment control:
- PAPER/STABLE uses a separate .github/workflows/crypto-paper-stable.yml allowlisted state/deploy surface;
- the generic Crypto Mac Command workflow was restored to its prior accepted scope;
- failed first deployment probe was rolled back before any paper record existed; the only fault was missing PYTHONPATH in a manual probe;
- subsequent deployment passed after binding probes to PAPER/STABLE src;
- state DB diagnostics now use the same PAPER/STABLE Python runtime.

Current Stage 6C frontier:
- define and accept the explicit, versioned decision-to-plan eligibility and virtual allocation policy required by AUTONOMOUS_PAPER_FUND_V1_SPEC;
- policy must add the still-missing cooldown, per-position-risk and no-trade conditions without weakening existing cash reserve/concentration/gross exposure gates;
- define a frozen execution-input source before any simulated BUY/REDUCE/EXIT can be activated in PAPER/STABLE;
- until that gate is accepted, PAPER/STABLE remains observation-only and trade_policy=NOT_ACTIVATED.


## 2026-09-20 — Stage 6C autonomy policy v1 accepted

The pure paper autonomy eligibility policy is accepted in canonical main.

Policy version:
- paper_autonomy_policy.v1

Accepted scope:
- 4h decision cadence only;
- exact Binance spot + Bybit spot provider set;
- exact provider agreement on symbol, timeframe, as-of and direction;
- ACTIVE-only eligibility;
- each provider must retain >=2 supporting methodologies, 0 opposing methodologies and complete geometry;
- partial_methodology_coverage is the only uncertainty flag allowed by V1;
- explicit activation watermark blocks all historical/backfill trades;
- maximum signal age: 4 hours;
- per-symbol cooldown: 4 hours;
- per-position loss budget ceiling: 1% of current marked paper NAV;
- no pyramiding;
- no shorting;
- no automatic REDUCE;
- missing mark-price truth required for NAV means HOLD_CASH;
- bullish consensus while flat -> BUY candidate;
- bearish consensus with an existing long -> EXIT candidate;
- all other bounded conditions -> HOLD_CASH.

Important boundary:
- BUY/EXIT is only a non-executable candidate;
- every trade candidate requires a separate frozen execution input;
- the policy contains no ledger append, fill simulation, network call, exchange order or credential path;
- PAPER/STABLE remains trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Acceptance evidence:
- implementation commit: a73b3ca641694d2cbe2495cf2e1ac1437c04c5bc;
- lint-only hardening head: c2744497199d77cf451b831248abe68737b6ae8a;
- 361 tests PASS;
- Ruff PASS;
- mypy PASS across 87 source files;
- JavaScript syntax PASS.

Current frontier:
- define the frozen execution-input source and exact venue/provider timing rule;
- then translate autonomy risk budget + frozen entry/invalidation truth into quantity;
- only after planner + execution simulator + atomic commit gates pass may PAPER/STABLE trading activation be considered.


## 2026-09-20 — Stage 6C frozen execution-input policy v1 accepted

Policy version:
- paper_execution_input_policy.v1

Accepted reference-price rule:
- reference exchange: Binance spot;
- source timeframe: canonical 15m base candles;
- cache access: SQLite mode=ro + PRAGMA query_only=ON;
- eligible source: first fully closed and already-ingested candle whose open_time_ms is strictly greater than autonomy signal as_of_ms;
- reference price: source candle OPEN;
- a candle beginning at or before signal as-of is never eligible;
- missing future closed candle returns WAITING_FOR_NEXT_CLOSED_CANDLE instead of fabricated price.

Audit binding:
- frozen input identity binds BUY/EXIT candidate, permitted symbol, both autonomy source freeze identities, signal as-of, source exchange/market/timeframe, source candle open/close/ingest times, adapter version, OPEN price and policy version;
- venue_reference can carry that frozen input identity into later simulated execution.

Authority boundary:
- reference price is not a fill;
- module does not choose quantity;
- module does not mutate candle cache or paper ledger;
- module has no network/exchange/order/credential path;
- PAPER/STABLE remains trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Acceptance evidence:
- implementation commit: 52cc3912df339edbe0cd7e774f42041803f9264f;
- type-narrowing hardening head: b7ac5896407cd6b8b38fe407cb7dce14bd70b417;
- first gate: 370 pytest PASS + Ruff PASS, one mypy narrowing finding;
- final gate: 370 tests PASS;
- Ruff PASS;
- mypy PASS across 88 source files;
- JavaScript syntax PASS.

Current frontier:
- conservative position sizing from autonomy max-position-risk budget + frozen Binance reference + signal invalidation geometry;
- then existing paper_risk_policy.v1 planner must independently enforce cash reserve, concentration and gross exposure;
- then frozen execution cost/rule snapshot + simulator + atomic bundle commit integration;
- PAPER/STABLE activation remains blocked until those gates and persistent activation watermark state are accepted.


## 2026-09-20 — Stage 6C conservative position sizing v1 accepted

Policy version:
- paper_position_sizing_policy.v1

Accepted BUY sizing:
- consumes only an accepted BUY autonomy candidate, its exact frozen execution input, current reconstructed paper state and the exact frozen SignalDecision lineage;
- requires both source signals to remain ACTIVE bullish decisions;
- frozen Binance execution reference must remain inside every provider entry zone;
- every provider invalidation must remain below the frozen reference;
- the lowest provider invalidation is selected as the conservative long invalidation because it creates the widest stop distance and therefore the smallest risk-based quantity;
- risk per unit = frozen reference - conservative invalidation;
- raw quantity = max-position-risk budget / risk-per-unit using explicit Decimal precision;
- the sizing result is pre-venue and pre-cost and explicitly requires venue-rule and cost adjustment;
- deterministic sizing identity binds policy, action, signal lineage, frozen execution input, reference, invalidation, risk budget and raw quantity.

Accepted EXIT sizing:
- bearish EXIT candidate sizes exactly the existing long position;
- no existing long -> REJECTED;
- no short or automatic REDUCE authority is introduced.

Important independent boundaries:
- sizing does not mutate the paper ledger;
- sizing performs no network/exchange/order/credential action;
- sizing does not claim venue quantity-step validity;
- sizing does not include fee/spread/slippage costs;
- paper_risk_policy.v1 still independently owns cash reserve, concentration and gross-exposure gates;
- PAPER/STABLE remains observation-only / trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Acceptance evidence:
- implementation commit: 5e1e2cd2b8ee88ed449ceeafd696bff62274dc90;
- first whole-repository gate: all 378 pytest cases PASS; Ruff found only 4 style findings;
- style-only hardening head: 67746b584006dd0419e4b1a460be1ed2f3637572;
- final regression: 378 tests PASS;
- Ruff PASS;
- mypy PASS across 89 source files;
- JavaScript syntax PASS.

Current frontier:
- freeze venue quantity/minimum rules for the Binance paper reference;
- round sizing quantity down without ever increasing risk;
- account explicitly for fee/spread/slippage before planner approval;
- bridge the resulting bounded quantity through paper_risk_policy.v1, execution simulator and atomic bundle commit;
- persist runtime activation/watermark/processed-event truth before PAPER/STABLE may create any virtual trade.


### Position sizing hardening acceptance

The accepted sizing gate was subsequently hardened without changing its policy intent:
- Decimal risk division now uses explicit ROUND_DOWN;
- constructed BUY sizing decisions enforce quantity * risk_per_unit <= max_position_risk_usdt;
- BUY sizing independently refuses pyramiding even if upstream autonomy is bypassed;
- source SignalDecision lineage is rechecked for exact Binance+Bybit providers, spot market, 4h timeframe and exact autonomy as-of;
- hardening head: 43f7dce447673772236aff9abeb87d0f001f52c2;
- final hardening regression: 381 tests PASS, Ruff PASS, mypy PASS across 89 source files, JavaScript PASS.

This SHA supersedes 67746b584006dd0419e4b1a460be1ed2f3637572 as the accepted sizing implementation head.


## 2026-09-20 — Stage 6C pre-trade planning bridge v1 accepted

Policy version:
- paper_pretrade_bridge_policy.v1

Accepted boundary:
- requires an externally frozen execution-rule/cost snapshot; it does not fetch or invent Binance venue metadata;
- snapshot symbol/policy must match paper state and its venue_reference must exactly bind the accepted frozen execution-input identity;
- BUY sizing quantity is rounded down only to frozen quantity_step and may never exceed the sizing ceiling;
- minimum quantity and minimum notional are enforced before planning;
- EXIT must remain a full exit and must already be an exact frozen venue step; otherwise it rejects instead of leaving silent dust;
- exact fee/spread/slippage cost budget is derived with the same adverse-price formula used by the accepted execution simulator;
- existing paper_risk_policy.v1 independently remains authoritative for cash reserve, 25% concentration and 50% gross exposure;
- plan timestamp cannot predate the frozen execution-input observation;
- PLANNED results independently recheck embedded plan action, symbol, reference price, quantity and cost-budget lineage;
- deterministic pretrade identity binds sizing, frozen execution input, frozen execution snapshot and plan/rejection truth.

Authority boundary:
- no venue metadata fetch;
- no network/exchange/order/credential path;
- no fill simulation;
- no paper-ledger write;
- PAPER/STABLE remains observation-only / trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Acceptance evidence:
- implementation: 3de13e8d921d4f546f959b4bc559e81c0cd80cc1;
- initial whole-repository gate: 389 tests PASS, Ruff PASS, mypy PASS across 90 source files, JavaScript PASS;
- semantic hardening: d58a181ab49da604313efa07d18c877d82ecaaf6;
- final hardening regression: 391 tests PASS;
- Ruff PASS;
- mypy PASS across 90 source files;
- JavaScript syntax PASS.

Current frontier:
- integrate accepted pretrade plan -> deterministic orchestration bundle -> accepted atomic/idempotent commit on a bounded ledger;
- prove end-to-end lineage and replay behavior without activating PAPER/STABLE;
- then implement persistent activation watermark / processed-event state and an authoritative frozen venue-rule snapshot source before any autonomous virtual trade is enabled.


## 2026-09-20 — Stage 6C pretrade-to-atomic-commit pipeline accepted

Accepted integration:
- accepts only PLANNED pretrade decisions;
- verifies exact fund, action, symbol, quantity, reference, frozen execution-input and frozen execution-snapshot lineage;
- deterministic orchestration must produce DecisionIntent + SimulatedFill + PositionCashMutation for a trade;
- exact committed record tuple must equal the exact orchestration bundle tuple;
- fill venue provenance must bind the exact execution snapshot;
- persistence uses the accepted atomic/idempotent paper ledger boundary;
- exact retry from the original pre-commit state is UNCHANGED;
- stale state rejects before write;
- mismatched snapshot rejects before write;
- REJECTED pretrade never reaches the ledger;
- injected mid-bundle simulated-fill INSERT failure rolls the entire pipeline write back.

Authority boundary:
- no signal selection;
- no candle or venue metadata fetch;
- no stable runtime activation;
- no network/exchange/order/credential path;
- PAPER/STABLE remains trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Acceptance evidence:
- implementation: cbffeb3e764e94ebc1ee516527140baabda04654;
- style-only head: ae7acc4d1fff43a411ec93945421db059a8433c5;
- integrity hardening head: bc57c01c072cff277725fe3493564a201c6ad13e;
- final regression: 398 tests PASS;
- Ruff PASS;
- mypy PASS across 91 source files;
- JavaScript syntax PASS.

Current frontier:
- persistent runtime activation watermark and deterministic provider-pair event identity;
- append-only event claim/resolution truth for restart/replay handling;
- authoritative frozen Binance venue-rule/cost snapshot source;
- only after those gates are accepted may PAPER/STABLE autonomous virtual trade activation be considered.


## 2026-09-20 — Stage 6C persistent activation + atomic processed-trade receipt accepted

Accepted persistent truth:
- one immutable paper activation singleton is stored in the same SQLite database as the paper fund ledger;
- activation cutoff equals activation timestamp in v1 and permanently blocks pre-activation signal events;
- activation binds fund identity plus the observed signal-ledger baseline count/latest freeze metadata;
- terminal processed-event identity binds exact activation, Binance+Bybit source freeze pair, symbol, 4h timeframe and signal as-of;
- terminal no-action receipts are append-only/idempotent and cannot advance from stale paper replay state.

Accepted crash-safe trade receipt:
- a COMMITTED_TRADE receipt is materialized only from an already-PLANNED pretrade and exact frozen execution input/snapshot lineage;
- exactly two source signal freeze identities are required;
- DecisionIntent + SimulatedFill + PositionCashMutation + processed-event receipt commit inside one SQLite transaction;
- exact retry is idempotent;
- a crash/SQL failure cannot leave the fund mutated without its processed receipt, or the receipt present without the trade bundle;
- activation/event tables are immutable against UPDATE/DELETE.

Authority boundary:
- persistent activation state existing in code does not itself enable PAPER/STABLE trading;
- no signal selection, venue metadata fetch, credentials, real exchange orders, or REAL_CAPITAL path is introduced;
- PAPER/STABLE remains trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Acceptance evidence:
- activation foundation: 850d2139c1486801242d944bd694314acdd02671;
- atomic trade+receipt integration: 59e9167a85baa738e257c05bf5c132eb83f238fe;
- dataclass/authority/static hardening: 1ec0f0269121817e5d6faa2c02fb6a9563210fda, b13691eb29c01b61a7385d635573e129bc51a6ad, 72e49e555f7cd956686c467677c621231f74d4e8;
- exact source-pair narrowing: 53460267178896e3cd3148c12de6dfd83de8e868;
- final whole-repository regression: 409 tests PASS;
- Ruff PASS;
- mypy PASS across 92 source files;
- JavaScript syntax PASS.

Current frontier:
- authoritative frozen Binance spot venue-rule snapshot source/cache for BTCUSDT, ETHUSDT and SOLUSDT;
- prove rule capture is versioned, immutable, restart-safe and bound to the same execution-input lineage used by pretrade;
- only then consider an isolated PAPER/STABLE autonomous virtual-trade activation candidate.


## 2026-09-20 — Stage 6C authoritative Binance venue-rule source/cache accepted

Accepted source/cache:
- public Binance Spot GET /api/v3/exchangeInfo is the sole V1 venue-rule source;
- no API key, account endpoint, credential or real-order path is used;
- parser fails closed unless requested symbol is exactly present, TRADING, spot-enabled, USDT-quoted and MARKET-capable;
- freezes canonical source-symbol JSON + SHA256, LOT_SIZE min/max/step, PRICE_FILTER tick size and the stricter minimum across MIN_NOTIONAL/NOTIONAL;
- append-only PaperVenueRuleStore persists snapshots immutably and deterministically selects the latest snapshot observed no later than the frozen execution input;
- future venue-rule observations cannot be backdated into an older event;
- authoritative execution snapshot venue reference binds venue-rule snapshot identity + explicit simulated-cost policy version + exact execution-input identity.

Simulation-cost policy:
- paper_simulated_cost_policy.v1;
- fee=0.001, spread=0.0005, slippage=0.0005;
- these are explicit simulation assumptions, not claims about an account-specific Binance fee tier.

Authority boundary:
- cache/source does not activate PAPER/STABLE trading;
- maxQty and tickSize are captured for audit but maxQty enforcement remains the next authoritative pretrade hardening step;
- REAL_CAPITAL=0.

Acceptance evidence:
- implementation: f0e4d3e509a00a9f555ebe00f542edd554cb1699;
- first gate: 419 pytest PASS with lint-only findings;
- style-only hardening: a5d3be3564f37e5064e488bd7c0525af306128bc;
- final regression: 419 tests PASS;
- Ruff PASS;
- mypy PASS across 93 source files;
- JavaScript syntax PASS.

Current frontier:
- enforce captured Binance maxQty in the authoritative pretrade path;
- add isolated observation-only stable venue-rule refresh/cache and verify live public BTCUSDT/ETHUSDT/SOLUSDT responses;
- only after those proofs evaluate a PAPER/STABLE autonomous virtual-trading activation candidate.


## 2026-09-20 — authoritative Binance maxQty enforcement accepted

The authoritative venue-bound pretrade path now consumes the exact cached Binance venue-rule snapshot rather than only its reduced execution snapshot.

Accepted behavior:
- PaperVenueBoundPretrade binds venue-rule snapshot identity + execution snapshot + pretrade identity;
- authoritative wrapper builds the execution snapshot from that exact cached rule snapshot;
- frozen Binance maxQty is passed into the conservative pretrade bridge;
- a step-rounded quantity above maxQty is rejected with ABOVE_MAXIMUM_QUANTITY;
- quantity is still never rounded upward;
- legacy caller/test path remains available without claiming authoritative maxQty enforcement;
- PAPER/STABLE must use the authoritative wrapper when virtual trading is eventually considered.

Acceptance evidence:
- semantic hardening: a52ab3db4df41388a96b5cabb542e8c9e0d4164e;
- lint-only head: 990436122f2bf14fff64b9a3dc2c1acb15014467;
- final regression: 421 tests PASS;
- Ruff PASS;
- mypy PASS across 93 source files;
- JavaScript syntax PASS;
- REAL_CAPITAL=0.

Current frontier:
- add observation-only PAPER/STABLE venue-rule refresh/cache for BTCUSDT, ETHUSDT and SOLUSDT using public Binance exchangeInfo only;
- verify real public responses and immutable cached snapshots while the paper fund remains 100 USDT / zero trades / trade policy not activated;
- only after that evaluate an isolated virtual-trading activation candidate.


## 2026-09-20 — observation-only PAPER/STABLE venue-rule refresh accepted

Stable deployment:
- PAPER/STABLE worktree deployed to cc69002b5b9b3a56414a317c1a71429a5365937d;
- paper clock deploy probes returned bootstrap=existing, cash=100.00, positions=0;
- trade_policy=NOT_ACTIVATED and REAL_CAPITAL=0;
- deploy no-trade invariant PASS: fund creations=1, decision intents=0, fills=0, mutations=0, NAV snapshots=0, replay index=1.

Live public Binance refresh:
- [PAPER] RULESREFRESH uses the deployed stable environment and public exchangeInfo only;
- BTCUSDT snapshot 12e987710b421c37fb04d1e67ebef41a460d0157f469c0347c03db4c7229ff8e:
  step=0.00001000, minQty=0.00001000, maxQty=9000.00000000, minNotional=5.00000000, tickSize=0.01000000;
- ETHUSDT snapshot 16c594a024fe234853136be828cd164df7c94c9d67abb126dac02e461bb18a50:
  step=0.00010000, minQty=0.00010000, maxQty=9000.00000000, minNotional=5.00000000, tickSize=0.01000000;
- SOLUSDT snapshot e8f6b6e3ad5d2bf55d063522c1d663f0b162f42b61a429dda72ad447d3bff614:
  step=0.00100000, minQty=0.00100000, maxQty=90000.00000000, minNotional=5.00000000, tickSize=0.01000000;
- all snapshots bind paper_simulated_cost_policy.v1;
- refresh workflow rechecked the no-trade invariant after the writes.

Independent state verification:
- stable HEAD=cc69002b5b9b3a56414a317c1a71429a5365937d;
- paper clock last exit code=0, interval=120 seconds;
- paper_venue_rule_snapshots=3;
- one latest cached snapshot exists for each BTCUSDT/ETHUSDT/SOLUSDT;
- paper fund remains cash=100.00, positions=0, replay records=1;
- decision/fill/mutation/NAV counts remain zero;
- trade_policy remains NOT_ACTIVATED;
- REAL_CAPITAL=0.

Code gate:
- cc69002b5b9b3a56414a317c1a71429a5365937d passed 421 tests;
- Ruff PASS;
- mypy PASS across 93 source files;
- JavaScript PASS.

Current frontier:
- build a production read-only event scanner that pairs only new post-activation 4h Binance+Bybit signal freezes by symbol/as-of;
- prove scanner ordering, provider-pair identity, historical-cutoff exclusion and processed-event skipping on fixtures/current ledger without creating trades;
- then integrate that candidate stream with frozen execution input + cached venue rules as a dry-run activation candidate before any PAPER/STABLE virtual trade policy is enabled.


## 2026-09-20 — Stage 6C read-only production signal event scanner accepted

Accepted scanner:
- paper_signal_event_scanner.v1 opens the immutable signal ledger and paper activation/processed-event tables with SQLite mode=ro + query_only;
- considers only spot 4h BTCUSDT/ETHUSDT/SOLUSDT freezes from Binance or Bybit;
- enforces signal as-of >= persistent activation cutoff and frozen_at >= activation timestamp;
- requires the supplied activation identity to equal the immutable paper activation singleton;
- groups events by exact (symbol, signal_as_of_ms);
- emits a candidate only for exactly one Binance + exactly one Bybit freeze;
- one-sided provider groups remain incomplete and emit nothing;
- duplicate provider freezes for the same event context fail closed;
- signal_decision is deserialized from immutable bundle JSON and rechecked against indexed freeze identity/provider/market/symbol/timeframe/as-of/state/direction;
- processed-event identities already present in paper_processed_events are skipped;
- candidate provider order is fixed Binance then Bybit;
- candidate order is deterministic by as-of, symbol and event identity.

Authority boundary:
- no autonomy evaluation;
- no candle read;
- no venue-rule refresh;
- no simulated execution;
- no paper-ledger writes;
- no PAPER/STABLE activation;
- REAL_CAPITAL=0.

Acceptance evidence:
- implementation: 4ddca26fa15f7cc90b4a191fe6c7e1717671e435;
- fixture correction: 2cfd9d0f411b2f548468de8f6e4c03bdd1dd3b8a;
- lint-only head: fd383be78059039312d586cc5fee491069bb6b8c;
- final regression: 429 tests PASS;
- Ruff PASS;
- mypy PASS across 94 source files;
- JavaScript syntax PASS.

Current frontier:
- compose scanner candidate -> accepted autonomy policy -> frozen execution input -> latest cached authoritative venue rules -> sizing -> authoritative pretrade as a strictly read-only/dry-run activation candidate;
- dry-run must not persist processed events or mutate the paper fund;
- prove real production ledger behavior before considering any virtual-trade activation.


## 2026-09-20 — Stage 6C read-only activation dry-run composer accepted

Accepted composition:
- paper_activation_dry_run.v1 takes one unprocessed scanner event and composes only accepted policy layers;
- paper state, activation identity, processed-event set and trade-decision timestamps are reconstructed from the paper SQLite database with mode=ro + query_only;
- held-position marks are read from finalized Binance spot 15m candles with mode=ro + query_only;
- autonomy policy is evaluated first;
- HOLD_CASH stops the chain immediately;
- BUY/EXIT candidates use the accepted first-closed-post-signal execution input;
- venue rules are selected read-only as the latest immutable cached snapshot observed no later than the execution-input observation;
- sizing and authoritative venue-bound pretrade are evaluated without persistence;
- future venue snapshots are not backdated.

Dry-run statuses:
- HOLD_CASH;
- WAITING_EXECUTION_INPUT;
- WAITING_VENUE_RULES;
- SIZING_REJECTED;
- PRETRADE_REJECTED;
- PRETRADE_READY.

Authority boundary:
- PRETRADE_READY is planning evidence only;
- no processed-event receipt is written;
- no DecisionIntent/fill/mutation/NAV is committed;
- no activation state is created/changed;
- no venue refresh or trade/account endpoint is called;
- PAPER/STABLE remains trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Acceptance evidence:
- implementation: 1c19f59fe236de81731f965a5cf694c7459d1299;
- first full gate exposed one invalid WATCH test fixture before dry-run evaluation;
- fixture-only correction: 3b0c0d78475554a8a9f96bac588fbc4ff5b835a7;
- final regression: 435 tests PASS;
- Ruff PASS;
- mypy PASS across 95 source files;
- JavaScript syntax PASS.

Current frontier:
- initialize the immutable PAPER/STABLE activation watermark from the current production signal-ledger baseline while keeping the runtime trade policy disabled;
- prove activation initialization is idempotent and leaves the 100 USDT fund with zero trades;
- then deploy the dry-run code to stable and inspect only post-watermark production candidate events.


## 2026-09-20 — immutable PAPER/STABLE activation watermark initialized

Accepted initializer:
- paper_activation_init.v1 requires the pristine virtual fund: one fund-creation replay record, 100 USDT cash, zero positions;
- production signal baseline is captured from one explicit SQLite read-only transaction;
- activation singleton is immutable and idempotent;
- rerun returns UNCHANGED and cannot rebase cutoff/baseline as new freezes arrive;
- no trade-policy authority is granted.

Code acceptance:
- implementation: be1c085749b4710befcbc9444872aed17dcbe262;
- lint-only hardening: 2b573e807aa7cc351ca97e97d1911b937c2f0c6f;
- type-only hardening: 6c2f5b9744ddb3fe3eee3793d35d2351c65f1c2c;
- final regression: 439 tests PASS;
- Ruff PASS;
- mypy PASS across 96 source files;
- JavaScript PASS.

Stable deployment and live initialization:
- PAPER/STABLE deployed to 6c2f5b9744ddb3fe3eee3793d35d2351c65f1c2c;
- deployment probes: fund=99eebec220597639add97080a243e98715d42e75af6be3f1785721d12da00b80, records=1, cash=100.00, positions=0, trade_policy=NOT_ACTIVATED, REAL_CAPITAL=0;
- activation identity: a9d5ba60fac148099ba69f75d61923e0a26252faba35438ca4a9b204ef151ca4;
- activated_at_ms / cutoff_ms: 1789928997447;
- immutable baseline freeze count: 372;
- baseline latest freeze: ed473d03651b0958cf040cea06929cfe5b805c6a78bcf5c7a9523e9be9cca4da;
- baseline latest frozen_at_ms: 1789928205551;
- first init write=INSERTED; immediate second init write=UNCHANGED with the exact same activation identity;
- paper activation singleton count=1;
- paper processed-event count=0;
- decision/fill/mutation/NAV counts remain zero;
- replay index remains 1;
- three authoritative venue-rule snapshots remain present.

Current frontier:
- expose the accepted scanner + activation dry-run composer as an allowlisted PAPER/STABLE read-only operation;
- inspect only post-cutoff production events;
- prove the dry-run does not mutate activation, processed events, fund replay or trade tables;
- do not enable autonomous virtual-trade writes yet.


## 2026-09-20 — PAPER/STABLE production read-only activation dry-run accepted

Code gate:
- stable dry-run operation implementation: 18a36286a4fcfc0df4f522c0f33a03203092456f;
- 441 tests PASS;
- Ruff PASS;
- mypy PASS across 96 source files;
- JavaScript PASS.

Stable deployment:
- PAPER/STABLE deployed to 18a36286a4fcfc0df4f522c0f33a03203092456f;
- deploy probes remained fund=99eebec220597639add97080a243e98715d42e75af6be3f1785721d12da00b80, records=1, cash=100.00, positions=0;
- trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0;
- no-trade DB invariant remained PASS.

First production [PAPER] DRYRUN:
- activation=a9d5ba60fac148099ba69f75d61923e0a26252faba35438ca4a9b204ef151ca4;
- cutoff_ms=1789928997447;
- eligible post-cutoff freezes=0;
- incomplete provider pairs=0;
- already-processed skips=0;
- candidates=0;
- statuses=-;
- paper_db_unchanged=YES;
- independent workflow no-trade invariant PASS;
- processed-event count remains 0.

Interpretation:
- there was no post-watermark 4h Binance+Bybit paper event yet at the first live dry-run;
- no historical freeze was replayed across the activation boundary;
- no dry-run observation mutated paper state;
- PRETRADE_READY has not yet been observed in production and no virtual trade activation is authorized.

Current frontier:
- install a separate read-only dry-run observation clock on PAPER/STABLE;
- the clock may repeatedly scan/evaluate post-watermark events and write only stdout/stderr logs, never paper DB state;
- prove service/restart behavior while trade_policy remains NOT_ACTIVATED;
- wait for mechanically observed post-cutoff candidate evidence before considering any virtual-trade write activation.


## 2026-09-20 — PAPER/STABLE read-only dry-run observation clock accepted

Accepted runtime behavior:
- stable worktree HEAD=e85af7e3e9a419e72948f4a9abea542aab0c2f75;
- separate launchd label com.cryptosignal.paperdryrun;
- one-shot read-only dry-run interval=120 seconds;
- service last exit code=0;
- deploy and explicit DRYRUNCLK workflow both passed;
- paper DB remains unchanged on dry-run execution;
- paper fund remains 100.00 USDT, positions=0, replay records=1;
- activation singleton remains 1;
- processed-event count remains 0;
- decision/fill/mutation/NAV counts remain zero;
- trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Observed production evidence:
- activation cutoff remains 1789928997447;
- immutable baseline freeze count=372;
- later signal ingestion reached at least 384 total freezes;
- the dry-run scanner still found eligible_freezes=0, incomplete_pairs=0, candidates=0 for its strict post-cutoff 4h Binance+Bybit event rule;
- therefore no PRETRADE_READY production evidence exists yet and no virtual-trade write authority is enabled.

Code gate:
- 441 tests PASS;
- Ruff PASS;
- mypy PASS across 96 source files;
- JavaScript PASS.

Current frontier:
- keep the dry-run clock strictly read-only while new production evidence arrives;
- harden candidate-observation visibility/log retention so a future post-cutoff event is mechanically obvious without mutating the paper ledger;
- do not enable autonomous virtual-trade writes until a real post-cutoff event has traversed the accepted dry-run path and its outcome has been inspected.


## 2026-09-20 — PAPER/STABLE dry-run candidate attention + deploy race hardening accepted

Accepted candidate visibility:
- pure dry-run observation summary counts all evaluated statuses deterministically;
- PRETRADE_READY identities are sorted and exposed explicitly;
- stable output includes ready_candidates=<count> and attention_required=YES|NO;
- each PRETRADE_READY event would emit a PAPER_DRY_RUN_ATTENTION evidence line;
- attention evidence still carries trade_policy=NOT_ACTIVATED and REAL_CAPITAL=0;
- PAPER STATE exposes the latest dry-run summary and recent attention lines.

Deploy hardening:
- first deploy attempt of 290ceb051fc13536cafac09d3efb5d66770b30a2 safely failed and auto-rolled back because launchd was still running when the workflow looked for newly emitted fields;
- rollback independently restored stable HEAD=e85af7e3e9a419e72948f4a9abea542aab0c2f75 with all no-trade invariants intact;
- 63f15ead39ec9e2a6171a71ac36e7548f7fb0048 removes this timing assumption by running the exact deployed dry-run script as a deterministic read-only probe before launchd bootstrap;
- dedicated dryrunclockdeploy uses the same probe;
- plist rollback backup filenames now use $$ rather than a literal trailing dollar sign.

Final acceptance:
- 443 tests PASS;
- Ruff PASS;
- mypy PASS across 96 source files;
- JavaScript PASS;
- PAPER/STABLE deploy to 63f15ead39ec9e2a6171a71ac36e7548f7fb0048 PASS;
- manual deploy dry-run probe: candidates=0, ready_candidates=0, attention_required=NO, paper_db_unchanged=YES;
- paper clock and dry-run clock last exit code=0, interval=120 seconds;
- paper fund remains 100.00 USDT, positions=0, replay index=1;
- activation singleton=1, processed events=0;
- decision/fill/mutation/NAV counts remain zero;
- trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Current frontier:
- continue strictly read-only production observation until a real post-cutoff provider-pair event appears;
- harden dry-run log retention so 120-second observation does not create unbounded local log growth;
- autonomous virtual-trade writes remain blocked until real post-cutoff dry-run evidence is observed and reviewed.


## PAPER/STABLE bounded dry-run log retention accepted
- implementation head: 6f677f158136c0988aaca80d76acd4b36aa9213f
- whole-repository FULLTEST PASS
- Ruff PASS
- mypy PASS across 97 source files
- JavaScript gate PASS
- PAPER/STABLE deploy PASS at the exact implementation head
- dry-run stdout/stderr are bounded independently at 5 MiB with at most one .1 backup each
- stable observation still reports candidates=0, ready_candidates=0, attention_required=NO
- dry-run paper DB fingerprint remains unchanged
- paper fund remains 100.00 USDT with zero positions
- decision/fill/mutation/NAV tables remain zero
- activation singleton remains 1 and processed-event count remains 0
- paper clock and dry-run clock both report last exit code 0 with 120-second intervals
- trade_policy=NOT_ACTIVATED
- REAL_CAPITAL=0

Current frontier:
- expose a deterministic, structured decision explanation trace from the read-only dry-run path so future product surfaces can show what evidence/rule actually caused HOLD/WAIT/REJECT/READY without fabricated narrative;
- keep this strictly read-only and do not activate virtual-trade writes until real post-cutoff production evidence traverses the accepted path.


## PAPER/STABLE factual decision trace accepted
- implementation head: 5df7fd6ab2f1c271d85f63132c0572807a5ff3a3
- deterministic paper_decision_trace.v1 projects each real dry-run candidate through autonomy, execution-input, venue-rule, sizing and pretrade stages
- each stage is PASSED / BLOCKED / NOT_REACHED / READY with the exact engine reason code and immutable evidence identity where available
- source_detail is inherited only from accepted engine reason/rejection text; no free-form or fabricated trader narrative is generated
- HOLD stops downstream stages as NOT_REACHED rather than inventing execution reasoning
- trace identity is canonical and deterministic
- dry-run logs emit PAPER_DRY_RUN_TRACE only when a real scanner candidate exists
- full gate: 448 tests PASS
- Ruff PASS
- mypy PASS across 97 source files
- JavaScript PASS
- PAPER/STABLE deploy PASS at the exact head
- deploy production probe observed signal_freezes=402, candidates=0, ready_candidates=0, attention_required=NO
- paper fund remains 100.00 USDT, positions=0, replay records=1
- decision/fill/mutation/NAV tables remain zero; activation singleton=1; processed events=0
- trade_policy=NOT_ACTIVATED
- REAL_CAPITAL=0

Current frontier:
- build a strictly read-only paper portfolio/performance projection from immutable paper state plus real cached market marks;
- expose cash, positions, marked NAV and factual PnL/return availability without fabricating 0% performance when no trades/marks exist;
- keep Dashboard wiring for the final product pass.


## PAPER/STABLE read-only marked portfolio view accepted
- implementation/stable head: 5ccc42f2f4e049697794dcd614d1d7f9ac13f87d
- paper_portfolio_view.v1 reconstructs immutable paper accounting state strictly read-only and marks held positions from the latest fully closed Binance Spot 15m candle available as-of observation time
- mark evidence carries source candle times, source timestamp, ingestion time, adapter/source metadata and a deterministic identity
- incomplete held-position marks explicitly produce availability=missing_marks and suppress aggregate NAV/PnL/return rather than estimating
- zero-position cash-only state truthfully permits NAV and capital return because no market mark is required
- portfolio snapshot identity is deterministic and canonical
- full gate: 452 tests PASS
- Ruff PASS
- mypy PASS across 98 source files
- JavaScript PASS
- PAPER/STABLE deploy PASS with no-trade invariant preserved
- live stable portfolio probe PASS:
  - cash_usdt=100.00
  - positions=0
  - marked_positions_value_usdt=0
  - nav_usdt=100.00
  - pnl_usdt=0.00
  - total_return_fraction=0
  - decisions=0
  - fills=0
  - nav_records=0
  - replayed_records=1
  - trade_success=NOT_YET_MEASURED
  - REAL_CAPITAL=0
- signal production remained at 402 freezes during deploy; strict post-watermark candidates remained 0
- trade_policy=NOT_ACTIVATED

Current frontier:
- add a deterministic trade-performance measurement layer that can remain NOT_YET_MEASURED until completed simulated round trips exist;
- when evidence exists, derive closed-trade results from immutable simulated fills/cost lineage without inventing win rates;
- keep product/dashboard wiring until the backend evidence surfaces are complete.


## PAPER/STABLE closed-trade performance truth accepted
- implementation/stable head: d1efcb93b66b1224b1db8762acfd3a65f47dcf62
- paper_trade_performance.v1 derives closed-trade truth only from immutable simulated BUY/EXIT fills plus their exact accounting mutations
- fill/mutation cash and position deltas must reconcile exactly or the performance reader fails closed
- spread/slippage stay embedded in simulated fill prices; explicit execution costs remain separately auditable and are not double-subtracted from PnL
- an open BUY without a matching EXIT remains an open trade and cannot manufacture closed-trade success
- zero completed round trips yields status=not_yet_measured with win_rate/PnL/profit-factor metrics unavailable, not zero
- when closed evidence exists, the layer computes wins/losses/breakevens, win rate, net/average PnL, average trade return, gross profit/loss, profit factor when defined, best/worst trade and total explicit execution cost
- deterministic snapshot/trade identities preserve audit lineage
- full gate: 457 tests PASS
- Ruff PASS
- mypy PASS across 99 source files
- JavaScript PASS
- PAPER/STABLE deploy PASS with no-trade invariant preserved
- deploy production evidence:
  - signal_freezes=408
  - cash_usdt=100.00
  - positions=0
  - replayed records=1
  - strict post-watermark candidates=0
  - trade_policy=NOT_ACTIVATED
  - REAL_CAPITAL=0
- first live stable performance probe PASS:
  - status=not_yet_measured
  - closed_trades=0
  - open_trades=0
  - wins=0 / losses=0 / breakevens=0
  - win_rate_fraction=unavailable
  - closed PnL / average return / profit factor / execution-cost aggregates=unavailable
  - trade_success=NOT_YET_MEASURED
  - REAL_CAPITAL=0

Current frontier:
- create one strictly read-only paper mission-control snapshot that composes production observation health, portfolio truth and closed-trade performance truth without changing any paper ledger state;
- this snapshot will become the clean backend contract for the final simple-professional Dashboard pass;
- virtual-trade writes remain blocked until a real post-cutoff production event traverses the accepted dry-run path and is mechanically reviewed.


## PAPER/STABLE unified mission-control truth accepted
- implementation/stable head: ec685df2c08907b65ee826315cfd874dd2257688
- paper_mission_control.v1 composes accepted read-only production truth into one deterministic snapshot:
  - immutable activation/watermark state
  - point-in-time signal-stream overview
  - strict post-activation 4h Binance+Bybit scanner counts
  - factual dry-run decision trace for every current candidate
  - marked paper portfolio truth
  - closed-trade performance truth
- the scanner now accepts an optional observed_at_ms boundary; Mission Control always uses it so future signal freezes cannot leak into an earlier product snapshot
- full gate: 461 tests PASS
- Ruff PASS
- mypy PASS across 100 source files
- JavaScript PASS
- PAPER/STABLE deploy PASS with no-trade invariant preserved
- first live stable mission-control snapshot:
  - snapshot=0738b9d4203267c1227a97e4ccbbcb0525119228843aad9efc4d318f25abb34e
  - activation baseline=372 freezes
  - observed signal freezes=414
  - latest signal=SOLUSDT / Binance / 15m / WATCH / bearish
  - eligible post-activation 4h freezes=0
  - incomplete provider pairs=0
  - candidates=0 / ready=0 / attention=NO
  - portfolio=available, cash=100.00, positions=0, NAV=100.00, PnL=0.00, total return=0
  - performance=not_yet_measured, closed trades=0, open trades=0, win rate unavailable
  - trade_success=NOT_YET_MEASURED
  - trade_policy=NOT_ACTIVATED
  - REAL_CAPITAL=0
- live evidence-clock logs mechanically confirm 4h production coverage is active for BTCUSDT/ETHUSDT/SOLUSDT on both Binance and Bybit
- the latest observed 4h source cutoff remained 1789905600000 and was already frozen on both providers; this context predates the paper activation watermark, explaining eligible_freezes=0 without indicating a disabled 4h pipeline

Current frontier:
- continue read-only production observation for the first post-watermark closed 4h provider pair;
- make decision-cadence readiness explicit so Mission Control can explain whether it is waiting on a new 4h close, a missing provider pair, or an evaluable event;
- do not enable virtual-trade writes until a real post-cutoff candidate traverses the accepted dry-run path and is mechanically reviewed.
