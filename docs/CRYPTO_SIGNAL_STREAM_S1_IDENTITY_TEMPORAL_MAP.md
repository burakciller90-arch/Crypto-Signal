# Crypto Signal — Stream S1 Identity & Temporal Lineage Map

Status: **S1 CLOSEOUT EVIDENCE**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
Observed main baseline: `2a61ad47e1f09640f3b36e4ccf09f6ed46dde7ef`

Purpose: freeze the exact identity/time relationships that future Stream messages must preserve.

---

## 1. Core decision lineage

The accepted issuance path is:

`SignalDecision.freeze_identity`
-> `ConfluenceMatrixSnapshot.snapshot_identity`
-> `CircuitBreakerAnalysis.evidence_identity`
-> `ImmutableForecast.forecast_identity`
-> `DecisionProofSnapshot.proof_identity`
-> `LiveIntelligenceFeedEvent.event_identity`

The accepted runtime enforces one exact market context:

- signal symbol/timeframe/as-of;
- M6 asset/timeframe/regime/as-of;
- Event Risk base asset/as-of;
- forecast source cutoff;
- proof issuance lineage.

### 1.1 Signal freeze

Identity:
- `signal_freeze_identity`

Temporal anchor:
- `signal.as_of_ms`

Carries/derives:
- symbol;
- timeframe;
- state;
- direction;
- frozen entry zone;
- frozen targets;
- frozen invalidation;
- immutable source bundle/candles.

### 1.2 M6 five-family confluence

Identity:
- `ConfluenceMatrixSnapshot.snapshot_identity`

Context:
- asset;
- timeframe;
- regime;
- `as_of_ms`;
- candidate direction.

Source lineage:
- exactly five `family_evidence_identities`;
- each family evidence carries `source_evidence_identities`;
- family evidence may carry `market_available_at_ms` and `observed_at_ms`;
- observed evidence must satisfy:
  `market_available_at_ms <= observed_at_ms <= as_of_ms`.

Full snapshot contains:
- five `ConfluenceFamilyContribution` records;
- prior weight;
- support points;
- opposition points;
- evidence quality;
- freshness;
- material-conflict count;
- source evidence identities.

Important persistence finding:
- the full M6 snapshot is available in `UnifiedDecisionIssuance.confluence`;
- R20/R20.5 Decision Ledger persists only Forecast, Proof and feed event;
- Forecast persists the confluence identity plus aggregate support/opposition/resolution/freshness;
- Decision Proof persists the confluence identity plus domain evidence slices;
- the Decision Ledger does **not** persist the full five-family contribution snapshot.

Therefore future Stream historical score-component windows require a new immutable decision-context/M6 persistence projection. Recomputing old contributions from current data is not acceptable.

### 1.3 Event Risk

Identity:
- `event_context_identity = CircuitBreakerAnalysis.evidence_identity`

Temporal anchor:
- Event Risk `as_of_ms` must equal the signal/M6 source as-of used by unified issuance.

Proof binding:
- the Decision Proof EVENT_CONTEXT slice must include the exact Event Risk identity.

### 1.4 Forecast

Identity:
- `forecast_identity`

Direct lineage:
- `signal_freeze_identity`;
- `confluence_identity`;
- `event_context_identity`;
- sorted `source_evidence_identities`.

Times:
- `source_as_of_ms = signal.as_of_ms`;
- `issued_at_ms >= source_as_of_ms`.

Frozen decision values:
- trigger zone;
- target zone;
- invalidation;
- horizon;
- support score;
- opposition score;
- resolution;
- freshness;
- event state/triggers;
- uncertainty.

### 1.5 Decision Proof

Identity:
- `proof_identity`

Direct lineage:
- forecast identity;
- signal freeze identity;
- confluence identity;
- Event Risk identity;
- optional probability identities;
- domain evidence slices.

Times:
- `issued_at_ms`;
- `source_as_of_ms`;
- every AVAILABLE slice carries:
  - `market_available_at_ms`;
  - `observed_at_ms`;
  - freshness;
  - source quality.

Proof invariant:
- future evidence cannot be attached to an issuance-time proof.

### 1.6 Existing feed event

Identity:
- `event_identity`

Direct lineage:
- forecast identity;
- proof identity;
- optional resolution identity.

Current kinds:
- FORECAST_ISSUED;
- FORECAST_RESOLVED.

Time:
- issuance event `event_at_ms = forecast.issued_at_ms`;
- resolution event time is the later resolution/evaluation time.

Current ledger invariant:
- at most one event of each kind per forecast;
- append chronology cannot backfill/fork.

---

## 2. Outcome lineage

Resolution identity:
- `ForecastResolution.resolution_identity`

Links:
- forecast identity;
- signal freeze identity;
- immutable source outcome identity.

Temporal rule:
- outcome is later evidence and never rewrites issuance truth.

Stream rule:
- an OUTCOME message references the original story/forecast but is a new append-only message.

---

## 3. Capital lineage

The accepted research/shadow lineage is:

Forecast / Proof / M6 / Event Risk
-> Capital Science Bridge
-> Position Sizing Bridge
-> optional reviewed sizing selection
-> R22 Intent Preview
-> Shadow Intent Journal / Shadow Cycle Manifest
-> separate runtime-replay evidence.

The accepted canonical Epoch 2 mutation lineage is:

R22 Intent
-> R22 Fill
-> R21 per-vault snapshots
-> R21 consolidated snapshot
-> R22 accounting bundle.

These two paths are related but are **not yet one canonical three-vault forward runtime**.

### 3.1 Capital Science Bridge

Identity:
- `CapitalScienceBridgeResult.bridge_identity`

Direct links:
- forecast identity;
- proof identity;
- confluence identity;
- Event Risk identity;
- Smart Capital candidate identity;
- allocation assessment identity.

Time:
- `assessed_at_ms >= candidate.as_of_ms`.

Important persistence finding:
- the rich bridge object contains the candidate and full allocation assessment in memory;
- existing Shadow Cycle Manifest persists bridge identity, not the complete Capital Science payload;
- no dedicated Product read route exposes the full historical bridge object.

### 3.2 Position Sizing Bridge

Identity:
- `PositionSizingBridgeResult.bridge_identity`

Direct links:
- capital bridge identity;
- forecast identity;
- proof identity;
- optional sizing policy identity;
- exactly three vault result identities.

Time:
- `sized_at_ms >= max(capital.assessed_at_ms, forecast.issued_at_ms)`.

Per-vault risk evidence:
- explicit `AcceptedSizingRiskInputs.risk_identity`;
- `measured_at_ms`;
- source evidence identities.

Temporal rule:
- risk input must satisfy:
  `forecast.issued_at_ms <= measured_at_ms <= sized_at_ms`.

Persistence finding:
- rich sizing result exists in the runtime object;
- current shadow manifest persists only the sizing bridge identity;
- historical Stream detail therefore needs a dedicated persisted/read-only sizing context projection.

### 3.3 Reviewed sizing selection

Identity:
- `ReviewedSizingSelection.selection_identity`

Links:
- sizing bridge;
- vault result;
- assessment;
- sizing result;
- vault.

Time:
- `reviewed_at_ms >= sizing.sized_at_ms`.

Current semantics:
- explicit research review;
- not automatic canonical sizing authority.

### 3.4 R22 preview

Identity:
- `R22IntentPreview.preview_identity`

Links:
- activation;
- forecast;
- proof;
- sizing bridge;
- sizing vault result;
- optional review selection;
- optional market reference;
- R22 intent;
- optional decision record.

Time:
- `previewed_at_ms`.

Persistence:
- `R25ShadowIntentJournal` stores the canonical preview payload append-only.

Important limitation:
- the preview does not persist the complete upstream Capital Science and Position Sizing objects.

### 3.5 Canonical R22 intent

Identity:
- `PaperTapeIntent.intent_identity`

Links for trade actions:
- activation identity;
- vault;
- forecast;
- proof;
- signal freeze;
- policy;
- sizing assessment;
- sizing decision/result;
- allocator candidate;
- paper decision;
- exact source evidence identities.

Time:
- `decided_at_ms`.

HOLD_CASH invariant:
- HOLD intent intentionally carries no fabricated trade/sizing/forecast lineage.

### 3.6 Canonical R22 fill

Identity:
- `PaperTapeFill.fill_identity`

Links:
- intent;
- activation;
- vault;
- source fill;
- mutation;
- before/after snapshot identities;
- mark evidence;
- optional outcome evidence.

Times:
- `filled_at_ms <= mutated_at_ms <= snapshot_at_ms`.

Financial evidence:
- quantity;
- reference price;
- simulated fill price;
- notional;
- fee;
- spread;
- slippage;
- cash before/after;
- position before/after;
- NAV before/after;
- realized/unrealized PnL deltas.

### 3.7 R21 Epoch 2 snapshots

Per-vault identity:
- `Epoch2VaultAccountingSnapshot.snapshot_identity`

Consolidated identity:
- `Epoch2ConsolidatedAccountingSnapshot.snapshot_identity`

Time:
- `snapshot_at_ms`.

Lineage:
- source record identities;
- previous snapshot identity;
- consolidated snapshot references exactly three vault snapshots.

### 3.8 Atomic accounting bundle

Identity:
- `R22Epoch2AccountingBundle.bundle_identity`

Links:
- intent;
- fill;
- before state;
- exact three after-vault snapshots;
- consolidated after snapshot.

Persistence:
- `R22Epoch2AtomicTape` stores:
  - `r22_epoch2_intents`;
  - `r22_epoch2_fills`;
  - `r22_epoch2_bundles`;
  - new R21 vault snapshots;
  - new R21 consolidated snapshot;
  in one local SQLite transaction.

Read evidence:
- `audit_bundle_read_only(bundle_identity)` already provides a verification path.

---

## 4. Stream temporal field policy

Future Stream message schemas must keep these concepts separate.

### Source/evidence time
When did the underlying market/source fact become true/available?

Examples:
- Market Tape `event_at_ms`;
- provider/source timestamp;
- evidence `market_available_at_ms`;
- event calendar/news source time.

### Observation/ingestion time
When did Crypto Signal observe/store it?

Examples:
- `observed_at_ms`;
- `ingested_at_ms`;
- adapter ingestion snapshot.

### Decision cutoff
What was the latest evidence allowed for the decision?

Canonical field:
- `source_as_of_ms` / shared M6/signal/Event Risk `as_of_ms`.

### Decision publication time
When was the forecast/message emitted?

Canonical:
- `issued_at_ms`;
- existing feed issuance `event_at_ms`.

### Capital assessment times
- `assessed_at_ms`;
- `sized_at_ms`;
- `reviewed_at_ms`;
- `decided_at_ms`.

### Execution/accounting times
- `filled_at_ms`;
- `mutated_at_ms`;
- `snapshot_at_ms`.

### Outcome time
- later resolution/evaluation time.

Stream V1 must never collapse these into one generic “timestamp”.

---

## 5. Required Stream identity graph

Every rich Stream message must bind one root source event plus zero or more typed references:

- `message_identity`;
- `source_event_identity`;
- `story_identity`;
- forecast identity when decision-related;
- proof identity when proof-related;
- signal freeze identity when geometry-related;
- decision-context/M6 snapshot identity when score-related;
- Event Risk identity when risk-related;
- evidence object identities when technical;
- capital bridge/sizing/R22/R21 identities when capital-related;
- resolution/outcome identity when outcome-related.

A message must not rely on time proximity alone to infer these relations.

---

## 6. S1 persistence conclusions

Mechanically established:

1. Signal/Forecast/Proof/issuance-feed history is persisted.
2. Full M6 family contributions are **not** persisted in the Decision Ledger.
3. Proof stores evidence identities/status, not a universal rich evidence-object registry.
4. Market Tape and Event Source persist several important raw/normalized evidence classes.
5. M5 provider-neutral Exchange Flow / Wallet Cohort / Large Transfer contracts are accepted but do not have live provider collectors.
6. Rich Capital Science and Position Sizing objects exist at runtime but are not fully persisted in the shadow manifest/read model.
7. R22 preview is persisted in the isolated shadow intent journal.
8. Canonical R22/R21 intent/fill/accounting persistence infrastructure exists.
9. Current automatic WC2 forward execution remains separate from one canonical all-vault R22/R21 runtime.

These conclusions become S2/S11 design inputs; they are no longer S1 discovery unknowns.
