# Full Version Roadmap Completeness Audit

Date: 2026-09-21  
Project: Crypto Signal  
Safety invariant: **REAL_CAPITAL=0**

## Executive result

**Stage 10 Full Integrated Acceptance is PASS, but the entire Full Version roadmap
is not yet complete.**

The runtime-accepted Stage 10 code is tagged
`stage10-accepted-20260921` and resolves to commit
`8ca23e612ba36b4ebcb0c3cb41a166d78add5cff`.

The bounded Stage 8 engine sequence is complete. The remaining material roadmap
gaps are Stage 8.5 Alpha Factory and Stage 8.75 Learning Memory. The governing architecture remains
`docs/INTELLIGENCE_ALPHA_FACTORY_ARCHITECTURE.md`; accepted Stage 8 engines stay
observation-only until a separately accepted integration/meta policy exists.

This audit prevents Stage 10 success from being misrepresented as completion of
roadmap stages that were intentionally outside the accepted Stage 10 runtime
matrix.

## Accepted / materially complete areas

The current repository and runtime evidence support these accepted areas:

- core immutable signal/evidence pipeline,
- point-in-time-safe live evidence and frozen signal ledger,
- core Price Action / Harmonic / Elliott evidence stack,
- historical evaluation and honest evidence classes,
- immutable 100 USDT paper-fund domain,
- deterministic execution cost / fee / spread / slippage contracts,
- paper portfolio and closed-trade performance truth,
- same-start cash / BTC / equal-weight benchmarks,
- Mission Control v4,
- beginner Gift Edition UX,
- signal/trade archive,
- System Health / freshness semantics,
- Stage 10 repository + runtime integrated acceptance,
- production product remains read-only,
- production paper write policy remains `NOT_ACTIVATED`,
- `REAL_CAPITAL=0`.

## Remaining Stage 8 implementation sequence

The governing roadmap explicitly requires the following engines to be introduced
one at a time behind isolated gates:

1. deterministic regime labeling — **ACCEPTED** at `4cdfbd134597a8329fb90d08eed5643161cd4926`,
2. trend/momentum — **ACCEPTED** at `f8b525e355a7fb587e9c0913965326a67630576a`,
3. mean reversion — **ACCEPTED** at `4e6d25df7f6aa2f36bf4ee86dba5c9023dd055d4`,
4. breakout/volatility — **ACCEPTED** at `f44157fa2b8a3788b85608a872eb8fa8fde7d5b3`,
5. bounded derivatives context — **ACCEPTED** at `011f2c4c7be2bd00410c5a0f3f578e20bd84c891`,
6. order-flow/microstructure if data quality supports it — **ACCEPTED** at `f0b27d41980714ffc42fe394ed3a3485acc6d5fe`,
7. on-chain/network — **ACCEPTED** at `589dd427c4f75641c1598e02afc103b238f74cd9`,
8. bounded sentiment/attention — **ACCEPTED** at `4c3357aeab24f8ce18bb87bf5ea8e91276b43a0f`,
9. cross-market context — **ACCEPTED** at `e97bd99a1384880c901b658ddfb1b7dd910ccd40`.

Every engine must have:

- deterministic source contract,
- point-in-time safety,
- frozen evidence,
- independent tests,
- contribution/ablation evidence,
- explicit uncertainty.

The bounded Stage 8 engine sequence is now complete. Acceptance of these isolated
engines does not imply production weighting; integration/meta policy remains a
separate future authority boundary.

## Remaining Stage 8.5 — Alpha Factory

The isolated research foundation is **ACCEPTED** at
`15f79052359a337c3b0457c214de7fe0ade96eb7`. It establishes immutable
experiment/challenger/partition identities, leakage-audit state, reproducibility
metadata and a non-self-promoting supervisor gate outside the production package.

The deterministic symbolic challenger slice is **ACCEPTED** at
`47c1ecdd31b1ffe490611abcf40f5d309c45663a`. The bounded shallow-tree
challenger slice is **ACCEPTED** at
`8ee89f4ee8de581bfacec1f7e62613ec96be065c`. The bounded
clustering/regime slice is **ACCEPTED** at
`4b8014e7f26a288e7cecb3806d46877ddb4174cc`. The bounded feature-interaction
slice is **ACCEPTED** at `35914060d4a4dd985ca9a0966588356b891a55f1`.
Bounded evolutionary search is **ACCEPTED** at
`7e32c5a689d88298e258e674bc0508c9021f2552`. The first bounded deterministic
ML research foundation is **ACCEPTED** at
`c445022b4a41aa3b9961768f41c3614f6dca115a`. Remaining Stage 8.5 work must
continue through bounded evaluation/robustness evidence before any broader ML
search, while RL remains separately closed.

Required promotion boundary remains:

1. data-contract and leakage audit,
2. deterministic/reproducible rule/training generation,
3. transaction-cost/slippage stress,
4. in-sample sanity,
5. out-of-sample evaluation,
6. walk-forward evaluation,
7. untouched-forward paper evaluation,
8. robustness/ablation checks,
9. explicit supervisor acceptance.

A challenger must not self-promote or modify the stable champion.

## Remaining Stage 8.75 — Learning Memory

The accepted implementation still needs a versioned and reproducible knowledge
layer that records both success and failure by:

- method,
- asset,
- timeframe,
- regime,
- version,
- uncertainty,
- redundancy / overlap,
- before-vs-after policy/model changes.

Learning Memory is evidence, not authority. It may influence future weighting
only through a separately tested policy.

## Stage 8.5 bounded ML cost-stress — ACCEPTED

Bounded deterministic ML transaction-cost/slippage stress is **ACCEPTED** at
`97af8105a8c5408bfbe2b19bd64d97bbbf384e17`.

It uses the fixed 1.0x / 1.5x / 2.0x cost multiplier grid over accepted
OOS/walk-forward evidence, preserves gross/cost/net evidence, never refits a
model or changes predictions, and provides no winner-selection or production
authority. Branch and merged-main research gates, merged-main Stage10
regression, UID504 sync and UID504 fulltest all passed.

## Stage 8.5 bounded ML robustness/ablation — ACCEPTED

Bounded deterministic ML robustness/ablation evidence is **ACCEPTED** at
`a385d7789af11aa7b124e5c52eb4731c868df615`.

It binds the accepted cost-stress chain, ablates every accepted feature exactly
once without refitting, records changed-prediction sensitivity, describes fold
sensitivity, and preserves explicit regime OBSERVED / NO_EVIDENCE states.
Branch and merged-main research gates, merged-main Stage10 regression, UID504
sync and UID504 fulltest all passed.

## Stage 8.5 bounded ML two-family expansion — ACCEPTED

Bounded deterministic two-family ML expansion is **ACCEPTED** at
`3672f44b1e30be9f916f54882fe0650054e4c567`.

The accepted categorical-count model remains the exact reference family and one
deterministic categorical sign-vote challenger is added. Training is TRAIN-only;
comparison is descriptive over OOS walk-forward evidence; multiple-testing state
is explicit; there is no automatic winner/model/hyperparameter selection.
Branch/merged-main research gates, merged-main Stage10 regression, UID504
current-head verification and UID504 fulltest all passed.

## Stage 8.5 bounded two-family ML cost-stress — ACCEPTED

Two-family deterministic transaction-cost/slippage stress is **ACCEPTED** at
`8659ef2b69aed8d9eedb3037235e0fcab186437f`.

Both accepted families are stressed on the same immutable 1.0x / 1.5x / 2.0x
grid over accepted OOS/walk-forward selections. Family/model/evaluation
identities and original gross/cost/net-R evidence are preserved; models are not
refit; predictions are not changed; there is no family/scenario winner
selection. Branch and merged-main research gates, Stage10 regression, UID504
sync and UID504 fulltest all passed.

## Stage 8.5 bounded two-family ML robustness/ablation — ACCEPTED

Two-family deterministic robustness/ablation evidence is **ACCEPTED** at
`86448100df5805a7e9a9b36eef486afe07ee8a99`.

It binds the exact accepted two-family expansion and family cost-stress chain,
ablates every accepted feature exactly once for both families without refitting,
records changed-prediction sensitivity, preserves fold sensitivity and explicit
regime OBSERVED / NO_EVIDENCE states, and retains favorable and unfavorable
evidence. There is no automatic family/feature/fold/regime/model selection.
Branch/merged-main research gates, merged-main Stage10 regression, UID504
current-head verification and UID504 fulltest all passed.

## Stage 8.5 two-family untouched-forward paper — ACCEPTED

Frozen two-family untouched-forward paper evidence is **ACCEPTED** at
`ef56069e2021ea0c2d8d16e93bc4e6610b8d994a`.

The evaluator consumes the exact accepted two-family expansion/cost-stress/
robustness chain, freezes the latest accepted chronological walk-forward models,
requires the forward partition to start after accepted OOS closes, and permits
no refit, feature/threshold change, retrospective optimization or family
selection. Branch/merged research gates, Stage10 regression and UID504
sync/fulltest all passed.

## Canonical next frontier

The next bounded roadmap slice is:

`stage8.5-ml-promotion-dossier-closure-v1`

Requirements:

- bind immutable identities for data-contract/leakage, reproducibility,
  transaction-cost stress, in-sample sanity, OOS, walk-forward,
  untouched-forward and robustness/ablation evidence;
- no missing required machine evidence may be silently treated as complete;
- machine evidence alone may reach only `READY_FOR_SUPERVISOR_REVIEW`;
- explicit supervisor evidence may reach only
  `SUPERVISOR_ACCEPTED_FOR_MANUAL_PROMOTION`;
- no PROMOTED state;
- no champion mutation, production import, deploy or order authority;
- no automatic family/model winner selection;
- REAL_CAPITAL=0.

## Safety boundary

This audit does not reopen the accepted Stage 10 code or authorize production
paper writes.

- Stage 10 tag remains immutable evidence of the accepted product/runtime line.
- PAPER/STABLE remains at its accepted stable head unless separately authorized
  through its own gate.
- No real exchange endpoint/credential authority is introduced.
- `REAL_CAPITAL=0`.