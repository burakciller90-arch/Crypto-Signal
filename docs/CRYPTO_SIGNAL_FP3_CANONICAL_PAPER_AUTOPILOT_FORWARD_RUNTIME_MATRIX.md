# Crypto Signal — FP3 Canonical Paper Capital Autopilot Forward Runtime Matrix

Status: **AUDIT COMPLETE / FP3-A IMPLEMENTATION AUTHORIZED**
Date: 2026-09-29
Base main: `439f304d423a643597b089653bbf53f030981a45`
Active branch: `fp3/canonical-paper-autopilot-forward-runtime`
Safety: **REAL_CAPITAL=0**
Historical backfill: **FORBIDDEN**
RDP11 soaked-runtime mutation/deploy: **FORBIDDEN**

## 1. Purpose

FP3 composes already accepted S11/R21/R22 paper-capital truth into one canonical forward-only virtual-capital runtime.

It must not create a second accounting engine, second tape, second allocator, second sizing engine or second evidence engine.

## 2. Reuse / extend / unavailable map

### REUSE — canonical truth
- `IntelligenceStreamCapitalForwardRuntime`: forward activation, candidate projection, three-vault canonical ELIGIBLE/HOLD/BLOCK decisions, HOLD/BLOCK R22 HOLD_CASH intent and Stream messages.
- `CanonicalVaultDecisionLedger` / `commit_canonical_hold`: canonical vault decisions + HOLD_CASH lineage.
- `promote_vault_eligibility`: exact ELIGIBLE-only execution proof.
- `PositionSizingAssessment` + `promote_fixed_fractional_sizing`: fixed-fractional-only canonical sizing promotion.
- `CanonicalSizingEventLedger`: append-only sizing evidence.
- `commit_canonical_paper_buy`: exact BUY -> sizing event + R22 intent/fill/bundle + R21 accounting.
- `commit_canonical_paper_sell`: exact REDUCE/EXIT -> R22 intent/fill/bundle + S11 outcome + R21 accounting.
- Decision Proof / UnifiedDecisionIssuance lineage.
- existing Capital Stream candidate/decision/sizing/lifecycle projectors.
- WC2 future-bound activation / liveness watermark / event de-dup patterns.
- R25 restart/replay idempotence proof patterns.

### EXTEND — FP3 only
- one isolated canonical forward orchestration owner;
- one isolated append-only processing/activation receipt store;
- deterministic orchestration state reconstruction from canonical ledgers;
- exact replay detection before any re-commit;
- versioned action policy mapping accepted source state to canonical PaperAction;
- final genuine-forward liveness audit.

### EXPLICITLY UNAVAILABLE / NOT INVENTED
The roadmap names `SCALE_IN`, `STOP_UPDATE`, `PARTIAL_TAKE_PROFIT`, `TAKE_PROFIT`, `STOP`, `CLOSE`.
Current canonical `PaperAction` supports only:
- `HOLD_CASH`
- `BUY`
- `REDUCE`
- `EXIT`

Therefore:
- OPEN -> BUY is representable;
- SCALE_IN -> BUY is representable only when the preregistered action policy explicitly permits another BUY and all current canonical risk/sizing gates pass;
- PARTIAL_TAKE_PROFIT -> REDUCE is representable only when an exact preregistered exit reason exists;
- TAKE_PROFIT / STOP / CLOSE -> EXIT are representable only when an exact preregistered exit reason exists;
- STOP_UPDATE is **UNAVAILABLE_EXPLICIT** in FP3 because no accepted canonical stop-order state/update event exists.
No new stop/TP order engine is invented in FP3.

## 3. Canonical owner boundary

New module:
`src/crypto_signal/paper/autopilot_forward_runtime.py`

It may orchestrate accepted functions but may not duplicate their calculations.

Canonical flow:
1. future-bound activation;
2. receive a genuine post-activation `UnifiedDecisionIssuance`;
3. run/reuse `IntelligenceStreamCapitalForwardRuntime.project_issuance`;
4. read exact three vault decisions;
5. HOLD/BLOCK ends with accepted HOLD_CASH lineage;
6. ELIGIBLE vault requires exact eligibility proof;
7. exact caller/source-produced sizing risk context is evaluated by existing sizing intelligence;
8. fixed-fractional result is promoted automatically by accepted S11 policy;
9. action policy chooses only accepted `PaperAction`;
10. exact execution snapshot / mark / price inputs are required;
11. canonical BUY or REDUCE/EXIT commit owns all R21/R22 mutation;
12. accepted Stream sizing/lifecycle projections run from persisted canonical records;
13. append one orchestration receipt referencing canonical identities only.

## 4. Authority rules

- REAL_CAPITAL=0 always.
- production_authority=false always.
- no network/exchange/order API.
- no backfill before FP3 activation.
- no discretionary fear veto after exact preregistered gates pass.
- no gate weakening to manufacture liveness.
- missing exact sizing/execution/action evidence => HOLD/WAIT/BLOCK explicitly; never fabricate.
- FP3 isolated branch/tests may use temp/copy-on-write DBs while RDP11 is active.
- no Product/Development deploy before soak-compatible release authority.

## 5. Replay / idempotence

Underlying HOLD projection is already idempotent.

For executed canonical trades:
- before any BUY/REDUCE/EXIT commit, FP3 must scan verified R22 history for exact forecast/proof/decision/sizing/action lineage;
- if the exact canonical bundle already exists, return REPLAYED/UNCHANGED and do not call a stale-state commit path;
- conflicting lineage fails closed;
- FP3 receipt append is exact-idempotent;
- crash after canonical R22/R21 commit but before FP3 receipt must recover by canonical R22 history lookup and append only the missing receipt.

## 6. FP3 implementation slicing

### FP3-A — owner + activation + processing receipt + replay contract
Build:
- future-bound isolated activation;
- append-only receipt store;
- exact issuance key;
- phase/status vocabulary;
- replay lookup helpers over canonical R22;
- composition with front-half CapitalForwardRuntime without executing trades.

PASS:
- no backfill;
- same issuance replay is unchanged;
- restart reconstructs existing HOLD/decision state;
- receipt UPDATE/DELETE forbidden;
- no canonical DB mutation beyond already accepted front-half HOLD/decision writes in isolated fixtures.

### FP3-B — eligible fixed-fractional sizing bridge
Build:
- exact sizing-risk input contract;
- ELIGIBLE-only proof promotion;
- existing sizing intelligence;
- automatic fixed-fractional canonical promotion;
- canonical sizing event + Stream sizing projection;
- no trade commit yet.

PASS:
- all three sleeves independently HOLD/BLOCK/ELIGIBLE;
- risk gate can HOLD without weakening;
- only fixed-fractional can become canonical;
- sizing replay idempotent.

### FP3-C — preregistered action bridge + canonical R21/R22 commit
Build:
- versioned action policy;
- BUY / REDUCE / EXIT only;
- exact execution snapshot/mark/reference inputs;
- pre-commit R22 replay detection;
- call existing canonical buy/sell commit functions;
- project persisted lifecycle to Stream.

PASS:
- canonical lineage reaches R22/R21 for genuine eligible action;
- no duplicate fill/accounting on replay;
- no unsupported STOP_UPDATE invention;
- no fear veto / no gate weakening.

### FP3-D — genuine forward liveness acceptance
No fixture can satisfy this gate.

PASS:
- at least one genuine post-activation candidate processed;
- correct silence/HOLD counts as healthy when policy says no trade;
- if genuine eligible action occurs, exact lineage reaches R22/R21;
- restart/replay idempotence observed;
- FP3 activation remains future-bound and immutable;
- RDP11 soaked target remains untouched during isolated development.

## 7. FP3-A persistence

Separate caller-supplied SQLite path with dedicated suffix:
`.fp3-paper-autopilot.sqlite3`

Tables:
- meta;
- singleton activation;
- append-only processing receipts.

Activation freezes:
- FP3 runtime version;
- activated_at_ms;
- Stream capital-forward activation identity;
- Epoch2 activation identity;
- no-backfill flag;
- REAL_CAPITAL=0.

Receipt freezes:
- receipt identity;
- forecast/proof identity;
- issuance/source time;
- observed/process time;
- front-half allocator candidate identity;
- exact three decision identities;
- decision dispositions;
- HOLD intent identities when present;
- canonical sizing/trade identities when later slices add them;
- terminal phase/status;
- reason codes;
- REAL_CAPITAL=0.

Truth tables are UPDATE/DELETE protected.

## 8. Exact next action

Implement FP3-A only: isolated activation/receipt/replay owner over the already accepted `IntelligenceStreamCapitalForwardRuntime`. Add focused tests for future-bound activation, no backfill, HOLD/decision composition, exact-idempotent replay, crash-style missing-receipt recovery and immutable receipt storage.

Do not implement FP3-B/C trade execution in the same commit.
