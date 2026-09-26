# Crypto Signal — Final F5 Capital Story Preparation Packet

Status: **PREP ONLY — DO NOT MERGE UNTIL F4 CLOSES**  
Roadmap: `CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_FINAL_COMPLETION_ROADMAP.md`  
Target phase: **F5 — Three-Vault Capital Story Live Closure**  
Prepared in parallel while F4 is active.  
Safety: **REAL_CAPITAL=0**

---

## 1. Parallel-work boundary

This preparation branch must not modify files currently owned by the active F4 Risk/System work unless F4 has already merged and this branch is rebased on that accepted main.

During F4, F5 preparation is limited to:

- read-only capital topology audit;
- exact source/persistence/identity map;
- acceptance criteria;
- isolated diagnostic/test helpers if needed;
- no production runtime hook activation;
- no mutation of canonical R21/R22 ledgers;
- no Product deploy;
- no historical backfill.

This branch must be rebased/merged from the accepted post-F4 main before any shared runtime file is changed.

---

## 2. F5 target behavior

F5 must make the original Stream promise mechanically true:

> Core, Tactical and Opportunity Reserve can each explain what they did, what they did not do, and why, using exact canonical paper-capital lineage.

The required forward chain is:

**Decision / exact candidate**  
→ **vault-specific eligibility**  
→ **canonical sizing decision**  
→ **simulated R22 intent/fill**  
→ **R21 Epoch 2 accounting commit**  
→ **Capital Stream projection**  
→ **SSE / read model / UI**

F5 does not authorize real trading.

`REAL_CAPITAL=0`.

---

## 3. Existing capital components to reuse

The repository already contains substantial S11 implementation and these components must be reused rather than rebuilt:

### Canonical three-vault paper truth

- Core;
- Tactical;
- Opportunity Reserve;
- vault-specific eligibility;
- canonical fixed-fractional sizing;
- simulated R22 intent/fill;
- R21 Epoch 2 vault accounting;
- consolidated Epoch 2 accounting;
- immutable outcome evidence.

### Existing Stream capital projector code

- `src/crypto_signal/product/intelligence_stream_capital.py`
- `src/crypto_signal/product/intelligence_stream_capital_lifecycle.py`
- `src/crypto_signal/product/intelligence_stream_capital_decisions.py`
- `src/crypto_signal/product/intelligence_stream_capital_sizing.py`

Existing accepted lifecycle vocabulary:

- `capital_candidate`
- `capital_eligible`
- `capital_hold`
- `capital_blocked`
- `capital_sized`
- `capital_executed`
- `capital_reduced`
- `capital_exited`
- `capital_accounting_updated`
- `capital_outcome`

Existing execution/accounting projector explicitly requires already-persisted, read-verified R22/R21 truth.

---

## 4. Current F5 gap

F0 classified Capital as:

`CODE_EXISTS_NOT_LIVE`

The reason is not absence of capital projector code.

The missing closure is the **canonical production caller** that observes already-committed R21/R22 forward truth and invokes the Stream capital lifecycle exactly once.

F5 must not silently use the WC2 paper-execution journal as a substitute for R21/R22 Epoch 2 canonical capital truth.

Required authority separation:

- WC2 execution evidence rail = evaluation/paper-execution evidence;
- R22 + R21 Epoch 2 = canonical three-vault paper-capital mutation;
- CAPITAL Stream message = read-only explanation of already-committed canonical paper truth.

---

## 5. Required source and identity lineage

Every actionable CAPITAL message must preserve exact lineage to the canonical objects that justify it.

### Candidate / hold / blocked / eligible

Must bind, where applicable:

- forecast identity;
- Decision Proof identity;
- allocator candidate identity;
- vault assessment identity;
- eligibility proof identity;
- source evidence identities;
- exact vault id.

### Sized

Must additionally bind:

- sizing assessment identity;
- sizing selection identity;
- fixed-fractional inputs;
- invalidation/risk geometry identity where required.

### Executed / reduced / exited

Must bind:

- R22 bundle identity;
- R22 intent identity;
- R22 fill identity;
- before R21 vault snapshot identity;
- after R21 vault snapshot identity;
- before consolidated snapshot identity;
- after consolidated snapshot identity.

### Outcome

Must additionally bind:

- immutable capital outcome identity;
- source fill lineage;
- realized PnL delta;
- position quantity before/after;
- fee/spread/slippage lineage already present in canonical paper truth.

No Stream message may create any of these identities.

---

## 6. Canonical persistence authority

Target canonical paper database:

`Development/runtime/paper/paper_fund_epoch2.sqlite3`

Expected relevant persisted families include:

- R22 intents;
- R22 fills;
- R22 bundles;
- R21 vault snapshots;
- R21 consolidated snapshots;
- capital outcome evidence;
- accepted candidate / eligibility / sizing records where persisted by the canonical runtime.

F5 must verify actual current table names and schema from the post-F4 main before live wiring.

---

## 7. Production-caller design constraint

The production caller must be **post-commit and read-only**.

Correct order:

1. canonical capital runtime validates a candidate/action;
2. canonical R22/R21 transaction commits;
3. transaction is read back and exact lineage is verified;
4. Stream projector is invoked;
5. Stream append is idempotent;
6. replay returns unchanged rather than creating a duplicate.

Incorrect designs:

- projecting before accounting commit;
- letting Stream projection decide whether capital executes;
- mutating R21/R22 from the Stream layer;
- deriving an execution message only from WC2 execution journal;
- backfilling historical capital messages;
- reconstructing old capital truth from current account state.

---

## 8. Candidate/non-action story requirement

F5 is not complete if Stream only talks when a trade executes.

It must be able to explain meaningful forward state changes such as:

- candidate appeared;
- vault held;
- vault blocked;
- candidate became eligible;
- sizing became available;
- action executed;
- position reduced;
- position exited;
- accounting changed;
- outcome finalized.

However, repeated identical non-action state must remain silent.

The existing story/materiality machinery must prevent routine spam.

---

## 9. Zero-activity observability

If no vault action occurs for a prolonged period, canonical read-only diagnostics must be able to explain:

- number of candidates evaluated;
- strongest current candidate when this is an accepted deterministic field;
- Core blocker/reason;
- Tactical blocker/reason;
- Opportunity blocker/reason;
- last eligible candidate;
- last simulated execution;
- current canonical cash/exposure;
- current source/data-quality state.

This diagnostic truth is not a synthetic CAPITAL message.

It exists so “nothing happened” is explainable.

---

## 10. Three-vault separation

F5 must verify each vault independently.

### Core

Must preserve Core-specific eligibility/risk rules.

### Tactical

Must preserve Tactical-specific short-timeframe evidence requirements and its own eligibility/sizing path.

### Opportunity Reserve

Must preserve Opportunity-specific recovery/evidence requirements.

No vault may inherit another vault’s eligibility state merely because they share the same forecast.

---

## 11. Exact acceptance cases

F5 acceptance must cover forward-only examples of:

1. one candidate event;
2. one meaningful hold or blocked state;
3. one eligibility transition;
4. one sizing event;
5. one canonical simulated BUY if/when genuine canonical rules allow it;
6. one REDUCE/EXIT only when naturally available in forward paper truth;
7. one accounting update;
8. one outcome when naturally available.

Rare execution/outcome events are not fabricated to close the gate.

Where a real forward event has not yet occurred, the phase may close the implementation path but the corresponding real-event E2E remains open for F8 acceptance.

---

## 12. Required negative tests

F5 must prove:

- no Stream capital projection can mutate R21/R22;
- no execution message without exact R22 bundle/intent/fill lineage;
- no canonical action message from WC2 journal alone;
- no duplicate message on replay;
- no historical rich backfill;
- stale/mismatched Decision Proof lineage fails closed;
- wrong vault lineage fails closed;
- sizing identity mismatch fails closed;
- outcome/source-fill mismatch fails closed;
- Product and Stream remain read-only;
- `REAL_CAPITAL=0`.

---

## 13. Shared-file handoff after F4

Do not implement shared runtime wiring until F4 merges.

After F4 acceptance:

1. rebase this branch on exact accepted main;
2. re-audit current capital runtime entrypoints;
3. identify the smallest post-commit canonical hook;
4. integrate only at that hook;
5. keep F4 Event Risk/System wiring untouched;
6. run focused F5 gate;
7. run broad regression;
8. controlled Development activation;
9. physical live proof;
10. only then mark F5 PASS.

Likely shared files may include live supervisor/runtime entrypoints, so they must be edited only after rebase.

---

## 14. Coordination rule

The active F4 agent owns F4 until its acceptance is merged.

This F5 prep branch owns only F5-specific preparation.

GitHub main + CURRENT_STATUS + final roadmap remain the inter-agent coordination surface.

No agent should infer another phase complete from branch code alone; only merged acceptance + canonical status may advance the frontier.

---

## 15. Prep conclusion

F5 does **not** need a new capital architecture.

The hard capital machinery already exists.

The phase is fundamentally:

> bind already-accepted canonical three-vault R21/R22 forward truth to the live Intelligence Stream, post-commit, idempotently, without confusing WC2 execution evidence with canonical capital mutation.

Preparation status:

**F5_PREP_READY / WAITING_FOR_F4_ACCEPTED_MAIN**

`REAL_CAPITAL=0`.
