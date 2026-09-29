# Crypto Signal — FP3 Canonical Paper Capital Autopilot Forward Runtime Matrix

Status: **FP3-A ACCEPTED / FP3-B NEXT**
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


## 9. FP3-A UID504 acceptance

Status: **PASS**

Accepted exact-head:
- head SHA: `5bcad4b766f41bcdf6c3b2deb2432a404f317087`;
- run: `36590509829`;
- job: `109482068773`;
- conclusion: **SUCCESS**.

Mechanical markers:
- exact-source checkout PASS;
- focused/regression pytest 100% PASS;
- Ruff: **All checks passed!**;
- strict mypy: **Success: no issues found in 5 source files**;
- Product/Development non-mutation PASS;
- project isolation PASS;
- `REAL_CAPITAL=0`.

Cleanup:
- temporary UID504 branch wiring restored in `08fc8491bd3dd32ee21f8ff550755a7dba3a01dd`;
- branch workflow blob equals current-main workflow blob `394051a78c665d84cf78830cedc8799a13474baa`.

Accepted FP3-A result:
- one canonical forward owner composes the already accepted Capital forward runtime;
- isolated activation/receipt store is append-only and immutable;
- pre-activation issuance cannot backfill;
- exact replay returns receipt without re-touching canonical ledgers;
- crash after accepted front-half writes but before receipt is recoverable by idempotent rerun + missing-receipt append;
- no sizing/trade execution was added yet;
- no R21/R22/S11 engine was duplicated;
- no Product/Development deploy or RDP11 soaked-runtime mutation occurred.

Next mechanically allowed slice:
**FP3-B — eligible fixed-fractional sizing bridge**.


## 10. FP3-B frozen sizing bridge contract

Status: **AUDIT COMPLETE / IMPLEMENTATION AUTHORIZED**

Canonical input boundary:
- exact accepted FP3-A receipt for the forecast;
- exact `UnifiedDecisionIssuance` + Event Risk used by FP3-A;
- existing `PositionSizingPolicy`;
- caller-supplied measured risk inputs with exact evidence identities;
- exact target `PaperVaultId`;
- sizing selection/process timestamps.

Fail-closed lineage:
- recompute accepted Capital Science assessment with the same FP3-A inputs;
- recomputed candidate/assessment identities must equal the FP3-A receipt;
- target FP3-A vault disposition must be `eligible`;
- `promote_vault_eligibility` remains the sole ELIGIBLE promotion function;
- risk context allocator candidate + assessment identities must equal FP3-A;
- risk context time cannot predate allocator assessment;
- caller-reported current drawdown must equal the latest canonical R21 target-vault drawdown;
- sizing selection time cannot predate risk observation, eligibility assessment or current R21 vault snapshot.

Sizing behavior:
- evaluate existing Position Sizing Intelligence;
- no calibrated probability is required or promoted for fixed-fractional;
- only `SizingMethod.FIXED_FRACTIONAL` may become canonical;
- if fixed-fractional is not `AVAILABLE_SHADOW`, persist an isolated FP3-B HOLD receipt only;
- if available, reuse `promote_fixed_fractional_sizing`;
- reuse `build_canonical_sizing_event` + `CanonicalSizingEventLedger.append`;
- reuse `project_sizing_event_to_stream`;
- do not call BUY/REDUCE/EXIT commit functions in FP3-B.

Persistence/replay:
- FP3-A receipt is never rewritten;
- add isolated append-only sizing-stage receipts in the same .fp3-paper-autopilot.sqlite3 store;
- unique key is exact forecast + vault;
- exact replay returns prior receipt without duplicate sizing/Stream writes;
- if canonical sizing event exists but FP3-B receipt is missing, deterministic rerun must append only the missing receipt/projector state and return RECOVERED;
- conflicting policy/risk context for the same forecast+vault fails closed.

FP3-B PASS:
- eligible vault can produce canonical fixed-fractional selection/event;
- HOLD/BLOCK vault cannot enter sizing;
- risk gate can HOLD without event/trade;
- fixed-fractional is the only promoted method;
- R21 drawdown lineage is exact;
- sizing event + Stream sizing projection are idempotent;
- no R21/R22 trade/fill/accounting mutation;
- REAL_CAPITAL=0;
- no RDP11 soaked-runtime mutation.

Exact nextAction:
Implement the isolated FP3-B sizing bridge + sizing-stage receipt and focused tests. Do not implement FP3-C action/trade commits in this slice.


## 11. FP3-B UID504 acceptance

Status: **PASS**

Accepted exact-head:
- head SHA: `d73cde9dd8d3a42dadac4fe85704c2a112d98e42`;
- run: `36595609945`;
- job: `109499792310`;
- conclusion: **SUCCESS**.

Mechanical markers:
- exact-source checkout PASS;
- focused/regression pytest PASS;
- Ruff: **All checks passed!**;
- strict mypy: **Success: no issues found in 5 source files**;
- Product/Development non-mutation PASS;
- project isolation PASS;
- `REAL_CAPITAL=0`.

Cleanup:
- temporary UID504 workflow wiring restored in `2faa27fe79685ba42b4ab0905d68d675e74fba0c`;
- branch workflow blob equals current-main workflow blob `394051a78c665d84cf78830cedc8799a13474baa`.

Accepted FP3-B result:
- only canonical ELIGIBLE vaults enter sizing;
- exact R21 drawdown lineage is enforced;
- fixed-fractional is the only promotable sizing method;
- HOLD/BLOCK/risk-gated outcomes do not create a trade;
- CanonicalSizingEvent + Stream sizing projection are idempotent;
- sizing chronology cannot precede the latest canonical vault decision;
- replay/recovery cannot duplicate sizing event or Stream sizing message;
- no R21/R22 trade/fill/accounting mutation was introduced;
- no Product/Development deploy or RDP11 soaked-runtime mutation occurred.

Next mechanically allowed slice:
**FP3-C — preregistered action bridge + canonical R21/R22 commit.**
