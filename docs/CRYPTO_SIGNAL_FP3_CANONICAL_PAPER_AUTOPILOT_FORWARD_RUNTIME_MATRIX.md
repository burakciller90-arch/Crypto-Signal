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


## 12. FP3-C frozen action / replay contract

Status: **AUDIT COMPLETE / IMPLEMENTATION AUTHORIZED**

### 12.1 Preregistered action vocabulary

Accepted customer/policy reasons:
- `OPEN` -> canonical `BUY`;
- `SCALE_IN` -> canonical `BUY`, only when an exact current position already exists and FP3-B produces a new eligible fixed-fractional sizing selection;
- `PARTIAL_TAKE_PROFIT` -> canonical `REDUCE`;
- `TAKE_PROFIT` -> canonical `EXIT`;
- `STOP` -> canonical `EXIT`;
- `CLOSE` -> canonical `EXIT`;
- `WAIT` -> no trade commit;
- `STOP_UPDATE` -> **UNAVAILABLE_EXPLICIT** in FP3 because no accepted canonical stop-order update state/event exists.

No other reason/action pair is accepted.

The policy is versioned and immutable. Runtime cannot reinterpret an unknown reason.

### 12.2 BUY source contract

BUY requires:
- exact FP3-A receipt;
- exact FP3-B sized receipt for the same forecast + vault;
- exact canonical fixed-fractional sizing selection/event;
- exact canonical eligibility proof;
- exact `UnifiedDecisionIssuance`;
- exact caller-supplied reference-price evidence, mark evidence and frozen execution snapshot;
- chronology satisfying accepted S11 commit guards.

`OPEN` requires no existing open quantity in the target vault/symbol.
`SCALE_IN` requires existing positive open quantity.

Mutation owner:
`commit_canonical_paper_buy` only.

### 12.3 REDUCE / EXIT source contract

REDUCE/EXIT must use the exact original open-position lineage already enforced by
`commit_canonical_paper_sell`:
- original forecast;
- original Decision Proof;
- original fixed-fractional sizing assessment/result;
- current R21 position;
- reconstructed R22 open cost basis;
- exact caller-supplied exit evidence identity;
- sorted unique preregistered exit reason codes;
- exact mark/reference/execution snapshot inputs.

`PARTIAL_TAKE_PROFIT` requires REDUCE and an exact quantity that leaves positive holdings.
`TAKE_PROFIT`, `STOP`, `CLOSE` require EXIT.
No new exit forecast or current-market reconstruction is invented.

Mutation owner:
`commit_canonical_paper_sell` only.

### 12.4 Replay / crash recovery

Before mutation:
- scan verified `R22Epoch2AtomicTape.read_trade_history(vault, symbol)`;
- match exact action + forecast + proof + sizing-decision lineage;
- for sell, also require exact preregistered exit reason/evidence lineage.

When an exact fill already exists:
- resolve its bundle identity through a read-only lookup of the canonical
  `r22_epoch2_bundles` fill-identity index;
- immediately validate the resolved identity with
  `R22Epoch2AtomicTape.audit_bundle_read_only`;
- do not call BUY/SELL commit again;
- project missing Stream lifecycle state idempotently;
- append only the missing FP3-C stage receipt.

The read-only bundle lookup creates no truth and performs no write.

### 12.5 Stream projection sequence

After a new or recovered canonical bundle:
`project_capital_bundle_lifecycle_to_stream(epoch2_path, stream_path, bundle_identity)`

This owns:
- execution story;
- accounting lifecycle;
- optional sell outcome lifecycle.

Projection is replay-safe and must not be replaced by custom messages.

### 12.6 FP3-C persistence

Use the existing isolated FP3 autopilot SQLite file.
Add append-only action-stage receipts keyed by exact action-intent identity.

Receipt references only:
- FP3-A receipt identity;
- optional FP3-B sizing receipt/selection/event identities;
- action policy version;
- action reason;
- canonical PaperAction;
- action evidence identity;
- exit reason codes where applicable;
- R22 intent/fill/bundle identities;
- optional S11 outcome identity;
- R21 after-vault / after-consolidated snapshot identities;
- terminal disposition NEW / RECOVERED / REPLAYED;
- REAL_CAPITAL=0.

Receipt rows are UPDATE/DELETE protected.

### 12.7 FP3-C PASS

- WAIT produces no R21/R22 mutation;
- STOP_UPDATE remains explicit unavailable;
- OPEN -> BUY only with zero prior position;
- SCALE_IN -> BUY only with positive prior position and new accepted FP3-B sizing;
- PARTIAL_TAKE_PROFIT -> REDUCE only with exact quantity/reason/evidence;
- TAKE_PROFIT / STOP / CLOSE -> EXIT only with exact reason/evidence;
- exact R22 replay preflight prevents duplicate accounting;
- crash after canonical commit but before FP3-C receipt recovers exact bundle read-only and appends only missing receipt/projection;
- Stream lifecycle projection is canonical/idempotent;
- no second accounting/execution engine;
- REAL_CAPITAL=0;
- no RDP11 soaked-runtime mutation.

Exact nextAction:
Implement FP3-C action policy + action-stage receipt + read-only R22 bundle recovery adapter and focused tests. Do not start FP3-D genuine-forward liveness until FP3-C mechanical acceptance PASS.


## 13. FP3-C contract correction — single-entry C1 / multi-entry C2

Status: **AUTHORITATIVE CORRECTION BEFORE CODE**

The prior section allowed `SCALE_IN -> BUY` when fresh FP3-B sizing exists.
That is not yet mechanically safe with the current accepted sell lineage.

Reason:
- a fresh SCALE_IN requires a distinct canonical sizing/forecast lineage;
- current `commit_canonical_paper_sell` reconstructs all active BUY intents and
  requires them to share the supplied forecast/proof/sizing-assessment lineage;
- multiple active BUY lineages therefore become ambiguous at REDUCE/EXIT.

Therefore FP3-C is split:

### FP3-C1 — single-entry action bridge
Supported:
- `WAIT` -> no trade;
- `OPEN` -> `BUY`, only when no position exists;
- `PARTIAL_TAKE_PROFIT` -> `REDUCE`;
- `TAKE_PROFIT` / `STOP` / `CLOSE` -> `EXIT`;
- `STOP_UPDATE` -> `UNAVAILABLE_EXPLICIT`;
- `SCALE_IN` -> `UNAVAILABLE_EXPLICIT_MULTI_ENTRY_LINEAGE`.

C1 never creates a second BUY while a position is already open.

### FP3-C2 — multi-entry lineage extension
Required before SCALE_IN can be marked supported:
- extend canonical R22/open-position lineage to represent multiple accepted BUY
  sizing/forecast lineages without ambiguity;
- extend canonical sell lineage validation to verify the full active-entry set;
- preserve weighted-average cost basis and exact evidence for every entry;
- prove REDUCE/EXIT after multiple entries remains deterministic/idempotent.

No SCALE_IN claim is allowed before FP3-C2 acceptance PASS.

Exact next action:
Implement FP3-C1 only, then mechanically accept it before opening FP3-C2.


## 14. FP3-C1 UID504 acceptance

Status: **ACCEPTED / REVIEW READY**

Accepted exact head:
- SHA: `0d982d0fcf0456deabae332db1da9bb3763fd857`;
- UID504 run: `36600881901`;
- job: `109517801922`;
- conclusion: **SUCCESS**.

Mechanical markers:
- exact-source checkout PASS;
- focused/regression pytest gate PASS;
- Ruff: **All checks passed!**;
- strict mypy: **Success: no issues found in 7 source files**;
- Product/Development non-mutation PASS;
- project isolation PASS;
- `REAL_CAPITAL=0`.

Cleanup:
- temporary UID504 wiring restored in `afd9c632c7e53e6e08199633fca706453ac70b56`;
- branch workflow blob equals current-main workflow blob `394051a78c665d84cf78830cedc8799a13474baa`.

Accepted C1 behavior:
- OPEN -> canonical BUY only with accepted FP3-A/FP3-B lineage and zero prior position;
- WAIT -> explicit no-trade;
- STOP_UPDATE -> explicit unavailable;
- SCALE_IN -> explicit unavailable pending FP3-C2 multi-entry lineage;
- PARTIAL_TAKE_PROFIT -> canonical REDUCE;
- TAKE_PROFIT / STOP / CLOSE -> canonical EXIT;
- base forward Stream decision context is a fail-closed prerequisite before any R21/R22 mutation;
- action evidence is bound into canonical R22 source lineage;
- exact preflight replay + fill-to-bundle recovery prevents duplicate accounting after crash;
- canonical Stream lifecycle projection owns execution/accounting/outcome messages;
- action receipts are append-only in the isolated FP3 store;
- no second accounting/execution/order engine exists.

Exact next action:
Open and merge FP3-C1 as an isolated PR after current-main/overlap checks. Then start FP3-C2 on fresh main with a new task-start checkpoint; do not claim SCALE_IN support until C2 acceptance PASS.
