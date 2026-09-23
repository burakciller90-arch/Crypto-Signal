# Event Risk + NLP — Slice 3: Circuit-breaker Composition

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Compose accepted structured-calendar evidence, News/NLP evidence and measured
market-quality evidence into one deterministic safety/veto state.

This slice does not create a trading strategy. It decides only whether research context is
clear, cautionary, event-blocked, degraded, or should abstain.

## Inputs

### Structured Event Risk

Consumes the accepted Slice 1 `EventRiskAnalysis` state and identity.

### News/NLP

Consumes the accepted Slice 2 `NewsEvidenceAnalysis` state and identity.

### Market-quality observation

A `MarketQualityRiskObservation` freezes:

- asset;
- observation time;
- spread in bps;
- depth-loss fraction;
- feed delay;
- price-gap fraction;
- cross-provider disagreement in bps;
- exact source evidence identities;
- measurement version.

Individual market-quality fields may be unavailable. Missing values are explicit and
produce fail-closed behavior rather than being treated as zero.

## Policy configuration

There are deliberately **no built-in numeric market-quality thresholds** in this engine.

Every evaluation must supply a versioned `CircuitBreakerConfig` containing:

- maximum market-quality age;
- maximum spread;
- maximum depth loss;
- maximum feed delay;
- maximum price gap;
- maximum provider disagreement.

Those thresholds are research policy inputs that must later be evaluated in Shadow Lab.
They are not universal laws and are not implied by this implementation.

## State precedence

The bounded composition policy is:

1. `ABSTAIN` — explicit News/NLP provider disagreement or any measured market-quality
   threshold breach.
2. `EVENT_BLOCK` — accepted structured calendar is inside the configured event block
   and no higher-priority abstain condition is present.
3. `DEGRADED_DATA` — calendar/news evidence is degraded/unresolved, or market-quality
   evidence is missing, stale or incomplete.
4. `CAUTION` — pre-event/post-event calendar caution or single-source news context.
5. `CLEAR` — structured calendar clear, multi-source news context accepted and complete
   market quality remains within the caller-supplied versioned thresholds.

All active triggers remain visible even when a higher-precedence state wins.

## Safety boundaries

- `ABSTAIN` is a research safety state, not an exchange order.
- `EVENT_BLOCK` does not predict event direction.
- A market-quality threshold breach does not predict future return.
- Missing evidence is never converted to a zero-risk value.
- Provider disagreement is surfaced, not averaged away.
- The policy stores exact upstream evidence identities.
- Source asset/as-of context must match.
- Future market-quality observations are rejected.
- No probability, confluence promotion, capital sizing, leverage or order authority.
- REAL_CAPITAL=0.

## Acceptance checklist

1. CLEAR requires complete healthy upstream context.
2. Calendar caution and event block remain distinct.
3. Single-source news is caution, not multi-source confirmation.
4. News provider disagreement forces ABSTAIN.
5. Each caller-supplied market-quality threshold can independently trigger ABSTAIN.
6. ABSTAIN has precedence over EVENT_BLOCK when both are present.
7. Missing/incomplete/stale market-quality evidence fails closed.
8. Degraded or unresolved upstream news fails closed.
9. Asset/as-of mismatch and future market-quality evidence fail closed.
10. Deterministic identities and REAL_CAPITAL=0 invariant.
11. Focused pytest/Ruff/mypy plus full repository Python/JavaScript/freshness regression.
12. Temporary hosted workflow removed after PASS.

After this slice, the locked Event Risk + NLP core exit is satisfied. The next intelligence
frontier is **M6 Confluence Matrix 2.0**, where Event Risk remains outside the 100-point
matrix as veto/context.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
