# CURRENT STATUS

Updated: 2026-09-20
Project: Crypto Signal
Phase: Post-V1 Production Expansion
State: POST_V1_COVERAGE_MATRIX_ACCEPTED
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

## Canonical next frontier
Post-V1 canonical higher-timeframe preparation:
1. build target timeframe candles only from canonical closed 15m
2. keep incomplete target buckets explicit and non-freezable
3. preserve aggregated observation/provenance timing
4. implement bounded paginated base-history acquisition
5. avoid oversized one-shot REST requests
6. prove requested target-window completeness deterministically
7. keep all higher-timeframe coverage contexts disabled in production
8. run focused/full gates before any activation proposal

V2+ research remains behind production coverage expansion.
REAL_CAPITAL remains 0.
