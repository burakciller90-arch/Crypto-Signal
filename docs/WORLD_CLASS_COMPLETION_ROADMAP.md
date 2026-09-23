
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

# WC2 — Untouched-Forward Paper Evidence Program

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

## Final boundary

Real-money authority is not part of World-Class Completion.

If WC7 eventually supports proceeding, real capital would require a new separately authorized program with explicit capital limits, legal/operational review, kill-switches and staged exposure.
