
# World-Class Completion Roadmap

Status: ACTIVE PROGRAM
Program name: World-Class Completion
Starting point: accepted R25 + Slice 16 + hosted-ready GALACTECH root-cutover candidate
Authority: development + production UI cutover approved by user
REAL_CAPITAL=0

## Mission

Turn Crypto Signal from a highly integrated evidence-first research/product platform into a production-grade, continuously measured, scientifically falsifiable trading decision system.

The target is not "more indicators". The target is a system that can answer, quickly and audibly:

1. What is happening?
2. What does the system think?
3. Is there a trade?
4. If not, why not?
5. What evidence supports the decision?
6. What capital/risk is justified?
7. What happened afterward?
8. Is the system actually calibrated and economically useful after costs?

The system must preserve missing/uncertain evidence instead of manufacturing certainty.

## Non-negotiable boundaries

- REAL_CAPITAL remains 0 throughout this roadmap.
- No exchange/broker order authority.
- No leverage/borrowing/martingale.
- No hidden automatic promotion from research to canonical production.
- No retrospective rewriting of forecasts, proofs, paper decisions or outcomes.
- No ONLINE, calibrated, profitable, world-class, or similar runtime/performance claim without exact supporting evidence.
- Real-money activation is outside this roadmap and would require a new, separate explicit authority program after all evidence gates.

# WC0 — Production Product Cutover and UID504 Truth

## Goal

Make current GALACTECH the production root while preserving rollback and proving deployed source/runtime parity.

## Deliverables

- Root path serves current GALACTECH.
- /galactech remains the same GALACTECH alias.
- /legacy preserves the previous accepted UI.
- Production Product tree hash parity with exact merged main.
- UID504 runtime topology, SQLite integrity and R25 operational truth.
- Current Market Tape / Cold Archive Product Truth visible when configured.
- Continuity pause state unchanged unless separately authorized.

## Exit gate

WC0 closes only when:
- exact candidate is merged;
- intended Product tree is deployed;
- exact-main UID504 live acceptance passes;
- root/alias/legacy routing is verified live;
- Product/runtime source hash parity passes;
- REAL_CAPITAL=0 and read-only/no-order authority remain true.

Hosted CI alone does not close WC0.

# WC1 — 24/7 Data Reliability and Event Runtime Truth

## Goal

Move from "persisted market data is readable" to "data collection quality and continuity are continuously measurable".

## Workstreams

### WC1.1 Market Tape process health
Persist/read exact collector runtime identity, heartbeat, source, start/restart state and last successful ingestion.

### WC1.2 Gap detection and recovery
Create an append-only gap ledger:
- provider;
- symbol/market;
- expected interval or sequence;
- observed gap;
- recovery attempt;
- recovered/unrecovered status;
- exact source evidence IDs.

No silent backfill.

### WC1.3 Provider redundancy and divergence
Where multiple providers support the same semantic:
- retain providers separately;
- measure disagreement;
- never invent consensus;
- expose provider-quality/freshness/divergence state.

### WC1.4 Cold Archive durability
Add bounded canonical-row replay verification where PyArrow/runtime policy permits, while retaining file SHA integrity.

### WC1.5 Event Source runtime
Add real calendar/news runtime persistence before replacing EVENT SOURCE RUNTIME = NOT EXPOSED.

## Exit gate

- collector liveness can be proven from persisted runtime evidence;
- gaps are measurable and auditable;
- recovery cannot rewrite original evidence;
- provider divergence is visible;
- Event Source is exposed only if exact runtime evidence exists;
- outage/restart drills preserve immutable evidence and deterministic recovery.

## Accepted closure evidence — 2026-09-24

**WC1 status: ACCEPTED / ENGINEERING CLOSED.**

- Exact accepted runtime/product code head at WC1 closure: `1af79d48c155de14fb51af2a3f87f39bbe7405da` (PR #1179).
- PR #1179 exact-head restart-drill static acceptance passed focused safety, whole-repository regression and Development non-mutation before merge.
- Issue #1182 / run 36053337362 deployed the exact merged target with read-only/no-order authority preserved.
- Issue #1183 / run 36053838731 / job 107815787924 physically replaced the exact canonical Market Tape lock holder and proved:
  - different PID;
  - immutable `RESTART` instance with exact predecessor identity;
  - Product-fresh persisted heartbeat without widening the <=30 s freshness rule;
  - valid append-only gap chain (66 events / 36 gaps);
  - read-only Market Tape Product Truth;
  - `ONLINE_STATUS=NOT_ASSERTED`;
  - `REAL_CAPITAL=0`.
- Earlier WC1 slices retain their narrower truth boundaries: Event Source remains source-scoped persisted evidence rather than an invented global ONLINE claim; provider divergence remains provider-separated; Cold Archive verification remains bounded and integrity-based.
- WC1 may be reopened only by new correctness evidence that falsifies this accepted closure, not to add unrelated scope.

# WC2 — Untouched-Forward Paper Evidence Program

**Engineering status: FROZEN / EVIDENCE ACCUMULATION ACTIVE. Scientific/economic status: OPEN.**

The preregistered collection/execution contract is no longer a feature-expansion target. Correctness, safety, reproducibility and evidence-preservation fixes remain allowed, but the untouched-forward boundary, cohort membership and economic evidence rules must not move in response to observed outcomes.

## Goal

Build the evidence that code/tests cannot provide: genuine forward economic performance.

## Rules

Every forward forecast is immutable before its outcome is known.

Persist:
- forecast;
- Decision Proof;
- capital assessment;
- sizing evidence;
- paper intent/decision;
- simulated execution costs;
- financial outcome;
- regime/context;
- resolution reason;
- exact evidence class.

No deletion of losses, abstains, invalidations or unresolved cases.

## Evidence cohorts

Report separately:
- retrospective;
- walk-forward;
- LIVE_UNTOUCHED_FORWARD.

Never merge them into one headline performance number.

## Minimum review gates

The platform may collect indefinitely, but promotion-quality review should require:
- meaningful decisive sample size;
- coverage across BTC/ETH/SOL where supported;
- multiple volatility/regime states;
- cost-stressed execution;
- sufficient calendar duration to avoid one-regime illusion.

The exact minimum-N policy must be versioned before looking at the final cohort statistics.

## Exit gate

WC2 does not close because time passed. It closes only when the pre-registered evidence policy has enough untouched-forward observations and regime coverage for WC3.

# WC3 — Calibration and Performance Science

## Goal

Determine whether the system's confidence, decisions and capital usage are scientifically and economically justified.

## Metrics

Where evidence supports them:
- Brier score;
- reliability/calibration buckets;
- ECE;
- log loss where probability semantics support it;
- expectancy after fees/spread/slippage;
- hit/invalidated/abstain/conflict rates;
- max drawdown;
- turnover;
- profit factor only from reconciled closed paper outcomes;
- fixed-policy periodic returns;
- Sharpe/Sortino only after the return-series policy is accepted;
- regime breakdown;
- asset breakdown;
- setup/methodology breakdown;
- transaction-cost sensitivity;
- threshold sensitivity;
- Event Block frequency and later counterfactual effectiveness only when measurable.

## Scientific rules

- Uncalibrated probabilities remain NOT_CALIBRATED.
- Missing return series means Sharpe/Sortino NOT_MEASURED.
- Descriptive success frequency is not probability.
- Threshold choice must not be selected from untouched-forward outcomes and then reported as untouched.

## Exit gate

A versioned performance dossier exists with reproducible data lineage and explicit evidence sufficiency/insufficiency.

# WC4 — Alpha Factory Champion/Challenger Program

## Goal

Make research improvement real without contaminating production evidence.

## Process

New variants remain shadow challengers.

Each challenger must bind:
- exact experiment;
- training/research data boundary;
- untouched validation boundary;
- walk-forward evidence;
- robustness tests;
- cost stress;
- regime sensitivity;
- failure cases;
- promotion dossier.

No automatic winner.

Promotion eligibility means "ready for explicit review", not "deploy".

## Exit gate

At least one full champion-vs-challenger cycle can be executed end-to-end without leaking untouched evidence and without automatic production mutation.

## Accepted engineering closure evidence — 2026-09-24

**WC4 status: ACCEPTED / ENGINEERING CLOSED / RESEARCH ONLY.**

- PR **#1189** added one immutable champion/challenger cycle manifest over the accepted Alpha Factory evidence chain.
- “Champion” is explicitly the frozen chronological research reference model, **not** mutable production champion state.
- One cycle binds:
  - data-contract and leakage-audit identity;
  - reproducibility identity;
  - in-sample sanity and out-of-sample evidence;
  - walk-forward identity;
  - transaction-cost stress identity;
  - robustness/ablation identity;
  - exact frozen untouched-forward snapshot/run;
  - immutable promotion dossier;
  - optional explicit supervisor acceptance.
- Evaluated untouched-forward evidence is required for a complete cycle but remains descriptive:
  - no aggregate winner selection;
  - no retrospective optimization;
  - no model refit or threshold/feature change from untouched outcomes.
- Cycle terminal states remain review-only:
  - `REVIEW_READY_NOT_PROMOTED`;
  - `SUPERVISOR_ACCEPTED_MANUAL_REVIEW_NOT_PROMOTED`.
- The manifest fails closed on cross-cycle untouched-forward evidence and requires distinct frozen reference/challenger model identities.
- It grants no champion-state write, automatic promotion, deploy or production authority. `REAL_CAPITAL=0`.
- PR #1189 UID504 exact-head run **36057586739** passed focused WC4, full Alpha Factory, whole-repository and Development non-mutation acceptance.
- PR **#1190** made the same gate exact-main aware; merged-main run **36058041036 / job 107829844817** passed on `c10f919fee75237282a2d020160afa59752385ef`.
- This closure proves the **research engineering cycle can execute end-to-end safely**. It does not prove challenger superiority, durable alpha or a production promotion decision.

# WC5 — 10-Second Trader UX

## Goal

Compress expert complexity into a decision surface that is fast for humans while preserving one-click proof depth.

For a selected market, the user should understand within roughly 10 seconds:

- Market state.
- System stance.
- TRADE / HOLD_CASH / insufficient evidence.
- Primary supporting evidence.
- Primary contradiction/risk.
- Event risk.
- Capital eligibility.
- Maximum shadow/paper exposure when evidence supports it.
- What must change for the decision to change.

Example product language:

PA bullish. Order flow confirms. Liquidity is context-only. Derivatives crowding raises squeeze risk. On-chain is non-directional. Event Risk is active. Result: HOLD_CASH. Tactical eligibility requires exact reclaim plus confirming flow evidence.

This text must be generated from explicit persisted product fields, not hidden chain-of-thought.

## Interaction model

- SIMPLE view: decision, risk, actionability.
- PRO view: exact domains, measurements, source quality, freshness, IDs.
- PROOF: immutable issuance evidence and later outcome kept separate.

## Exit gate

Usability acceptance proves the primary decision can be understood without visiting multiple screens, while every summary statement can drill to exact evidence.

## Engineering / production acceptance evidence — 2026-09-24

**WC5 engineering status: ACCEPTED / PRODUCTION DEPLOYED. Human usability timing: NOT_MEASURED.**

- Fresh post-WC1 PR **#1185** replaced stale candidate #1162 and merged as exact main `15fa3dca848fb9e76841f9b113f9f13a2a1ee11b`.
- Exact-head UID504 run **36055644923** passed:
  - exact-source and clean-Development guard;
  - focused WC5 pytest/Ruff/mypy/frontend contracts;
  - live read-only exact WC2 cohort Product preview;
  - byte-stability of the cohort;
  - whole-repository regression;
  - Development non-mutation;
  - `REAL_CAPITAL=0`.
- The accepted live preview used exact forecast `8c9fe8e3f4f144c1958b64cb33af6c3551f201f0e9d2bf4fa7e7bf52ba29e19f` and returned the persisted action `HOLD_CASH` / vault `CORE`; no action was inferred from `ACTIVE` state.
- Missing intent, multiple intents and unsupported maximum exposure remain explicit insufficient/unavailable states.
- The command surface mechanically exposes in one card:
  - market/system state;
  - actionability;
  - primary supporting evidence;
  - contradiction/risk;
  - event risk;
  - capital eligibility;
  - what must change;
  - one-click immutable issuance proof.
- Product deployment issue **#1186**, run **36056040911**, completed `PRODUCT_DEPLOY_PASS=YES` on exact merge commit `15fa3dca...`; live health, GALACTECH root, Intelligence Center, R25 Operational Truth and R11 runtime/SQLite acceptance passed.
- Independent Product state issue **#1187**, run **36056686776**, reconfirmed exact Product HEAD plus `status=ok`, `read_only=true`, `REAL_CAPITAL=0`.
- No exchange/broker authority, WC2 cohort mutation or real capital was introduced.
- This evidence closes the **engineering/mechanical and deployment portion** of WC5. It does not claim that a human participant study measured <=10-second comprehension. That human usability dimension remains `NOT_MEASURED` and must stay explicit if the roadmap later requires empirical UX timing evidence.

# WC6 — Execution Lab (Paper / Sandbox / Testnet Only)

## Goal

Validate execution engineering without real capital.

## Stages

1. deterministic paper execution;
2. latency/slippage/partial-fill simulation;
3. venue policy and rejection handling;
4. sandbox/testnet adapter where a venue safely supports it;
5. kill switch, duplicate-order prevention and restart idempotence;
6. reconciliation between intended order, acknowledged order, fill and paper accounting shadow.

## Explicit exclusions

- no live exchange credentials with trading permission;
- no real-money orders;
- no automatic transition from sandbox to live.

## Exit gate

A sandbox/testnet execution dossier shows deterministic recovery, duplicate prevention, reconciliation, kill-switch behavior and authority isolation.

## Engineering progress — 2026-09-25

**WC6 status: OPEN / PAPER EXECUTION-LAB CORE ACCEPTED / SANDBOX-TESTNET EVIDENCE MISSING.**

Accepted paper/lab rails:
- PR **#1192** binds one deterministic paper trade through exact decision intent, simulated fill, position/cash mutation and processed-event receipt lineage.
- Exact retry is required to return `UNCHANGED` with identical receipt, identities and reconstructed state.
- Append-only virtual paper write authority provides an explicit paper kill switch: once disabled, the same protected commit surface is rejected and paper replay/receipts remain unchanged.
- Existing frozen venue-rule and explicit fee/spread/slippage assumptions remain bound to deterministic paper execution.
- PR #1192 exact-main UID504 run **36060028438 / job 107836479650** passed focused WC6, full paper, whole-repository and Development non-mutation acceptance.
- PR **#1193** adds deterministic **lab-only** acknowledgement latency and partial-fill simulation over an already-accepted canonical paper fill:
  - two-or-more shadow fills;
  - strictly increasing fill times after acknowledgement;
  - frozen quantity-step alignment;
  - aggregate quantity exactly equals canonical fill quantity;
  - aggregate shadow notional exactly equals canonical fill notional;
  - processed-event/pretrade/snapshot/decision/fill/mutation reconciliation;
  - deterministic rerun with no canonical ledger mutation.
- Canonical Paper Fund v1 is deliberately unchanged: `partial_fills_supported=False`. Shadow partial fills are labelled `LAB_ONLY_CANONICAL_UNSUPPORTED`; they are engineering evidence, not venue evidence.
- PR #1193 exact-main UID504 run **36060806366 / job 107839002389** passed focused WC6, full paper, whole-repository and Development non-mutation acceptance.
- All accepted WC6 slices retain no network, credential, live-order or production authority and `REAL_CAPITAL=0`.

Accepted sandbox-boundary rail:
- PR **#1195** adds a fail-closed sandbox/testnet contract over the accepted shadow lifecycle.
- It deterministically prepares an immutable future order request with exact processed-event/pretrade/snapshot/fill/mutation lineage plus idempotency and client-order identities.
- The only accepted v1 adapter state is `NOT_CONFIGURED` / `SANDBOX_TESTNET_ONLY`.
- While unconfigured, endpoint, credential-reference and transport-reference fields must remain absent; dispatch is `BLOCKED_NOT_CONFIGURED`; dispatch is not attempted; venue acknowledgement/fill evidence remains absent.
- Dispatch readiness fails closed with `WC6_SANDBOX_NOT_CONFIGURED`.
- PR #1195 exact-head UID504 run **36062491109 / job 107844484263** passed focused WC6, full paper-subsystem, whole-repository and Development non-mutation acceptance.
- After merge as `cde9006f0b344c037ff093e66605d40e26ae242b`, exact-main push run **36062672930 / job 107845073963** independently passed the same gate.
- No network, credential-loaded, live-order or production authority was introduced; `REAL_CAPITAL=0`.

Remaining exit blocker:
- the adapter boundary exists, but it is intentionally **NOT_CONFIGURED**;
- no safely supported external sandbox/testnet transport plus explicit non-production credential configuration has been accepted;
- no real venue acknowledgement/fill/recovery evidence exists;
- therefore the WC6 sandbox/testnet execution dossier required by the exit gate remains open.
- Missing venue evidence must remain missing. Prepared requests and lab simulations must not be relabelled as sandbox/testnet acceptance.

The next WC6 step is now an **external dependency**, not a reason to invent more local venue evidence. Safe parallel engineering may proceed on WC7 evidence-review infrastructure only if missing WC2/WC6/usability evidence forces `INSUFFICIENT_EVIDENCE` rather than a positive edge/world-class conclusion.

# WC7 — World-Class Evidence Review

## Goal

Answer the only question that ultimately matters:

Does Crypto Signal possess a durable, cost-adjusted, risk-controlled edge?

## Required conclusion states

The review must be allowed to conclude any of:
- EDGE_SUPPORTED;
- EDGE_PARTIAL / regime-specific;
- INSUFFICIENT_EVIDENCE;
- EDGE_NOT_SUPPORTED.

"World-class" is never hardcoded as the answer.

A credible world-class claim would require, at minimum:
- production/runtime reliability;
- long untouched-forward history;
- calibrated forecasts where probabilities are used;
- positive cost-adjusted expectancy;
- controlled drawdown;
- robustness across relevant regimes;
- transparent abstention/failure cases;
- reproducible capital and execution lineage;
- strong usability without hiding uncertainty.

## Accepted review infrastructure — 2026-09-25

**WC7 infrastructure status: ACCEPTED. Current evidence conclusion: `INSUFFICIENT_EVIDENCE`.**

- PR **#1197** adds one immutable evidence-review contract over the exact nine roadmap dimensions above.
- Machine review is deliberately limited to:
  - `INSUFFICIENT_EVIDENCE`;
  - `READY_FOR_HUMAN_REVIEW`.
- The machine does **not** automatically select any final EDGE_* conclusion.
- Any required evidence in `MISSING`, `NOT_MEASURED`, or `EXTERNAL_DEPENDENCY` forces `INSUFFICIENT_EVIDENCE`.
- Probability calibration may be `NOT_APPLICABLE` only when probability claims are not used. Probability use requires applicable calibration evidence.
- A later human review may record only one of the roadmap conclusion states, and the record is guarded against the evidence-status set:
  - `EDGE_SUPPORTED` requires every applicable dimension satisfied;
  - `EDGE_PARTIAL / regime-specific` requires explicit partial evidence and cannot override negative evidence;
  - `EDGE_NOT_SUPPORTED` requires explicit negative evidence;
  - incomplete evidence cannot be rewritten as a positive or negative edge verdict.
- The accepted current-frontier review remains `INSUFFICIENT_EVIDENCE` because required evidence is still incomplete for:
  - untouched-forward history/evidence sufficiency;
  - cost-adjusted expectancy;
  - controlled drawdown;
  - regime robustness as durable edge evidence;
  - capital/execution lineage at the missing external WC6 venue-evidence boundary;
  - measured human usability.
- PR #1197 exact-head UID504 run **36063510771 / job 107847770771** passed exact-source, focused WC7, research, whole-repository and Development non-mutation acceptance with `WC7_MACHINE_EDGE_VERDICT=NONE` and `REAL_CAPITAL=0`.
- After merge as `d27563bee4418c4fef2a6e7fcb351fa8f7e96686`, exact-main push run **36063771392 / job 107848618741** independently passed the same gate.
- This acceptance proves the review process itself is fail closed. It does **not** prove `EDGE_SUPPORTED`, “world-class achieved”, or any other positive edge conclusion.

### Typed provenance hardening — 2026-09-25

- PR **#1199** binds each WC7 claim to an allowed typed evidence source or explicit blocker boundary.
- Satisfied/partial/negative claims cannot use an unrelated evidence class.
- Human usability can only be supported by a human-usability-study source.
- Capital/execution lineage can only be supported by a WC6 sandbox/testnet dossier; paper/lab simulation cannot be relabelled as venue evidence.
- Missing, not-measured and external-dependency claims cannot invent an artifact identity.
- Probability calibration `NOT_APPLICABLE` requires an explicit no-probability-use boundary.
- The final packet must match all nine exact claim identities, statuses and artifact identities.
- Exact-head UID504 run **36064310603** passed; after merge as `441dd9d5da20c4d5645d63f6975079992d2981f2`, exact-main run **36064416622 / job 107850699031** independently passed focused/research/full-repository/non-mutation acceptance.
- `WC7_MACHINE_EDGE_VERDICT=NONE` and `REAL_CAPITAL=0` remain mandatory.
- Typed provenance strengthens the review boundary; it does **not** change the current `INSUFFICIENT_EVIDENCE` conclusion or remove any existing blocker.

### Canonical read-only adapters — 2026-09-25

- PR **#1201** adds read-only WC7 adapters for accepted WC2 and WC6 artifacts.
- WC2 `REVIEW_ELIGIBLE` may satisfy only untouched-forward-history sufficiency and retains the explicit “not edge/profitability claim” semantic.
- WC2 `INSUFFICIENT_EVIDENCE` remains a missing WC7 dimension; its readiness identity is blocker-boundary provenance, not evidence.
- WC6 `NOT_CONFIGURED / BLOCKED_NOT_CONFIGURED` remains `CAPITAL_EXECUTION_LINEAGE = EXTERNAL_DEPENDENCY`; the sandbox-boundary identity proves the blocker rather than pretending to be venue evidence.
- Provenance now separates `source_artifact_identity` from `blocker_boundary_identity`.
- Exact-head run **36065071631** passed; after merge as `3d0283ab180255e5eca12955814985cab04c3548`, exact-main run **36065254385 / job 107853404508** passed focused/research/full-repository/non-mutation acceptance.
- The current conclusion remains `INSUFFICIENT_EVIDENCE`; no EDGE_* verdict or production authority is introduced.

## Final boundary

Real-money authority is not part of World-Class Completion.

If WC7 eventually supports proceeding, real capital would require a new separately authorized program with explicit capital limits, legal/operational review, kill-switches and staged exposure.
