# Crypto Signal — Message Intelligence & Family Evidence UX V1 Final Acceptance

Status: **ACCEPTED**
Date: 2026-09-27
Repository: `burakciller90-arch/Crypto-Signal`
Safety: **REAL_CAPITAL=0**

## 1. Accepted scope

The post-F10 Message Intelligence & Family Evidence UX refinement is complete.

This acceptance does **not** reopen Intelligence Stream V1 F0-F10, change trading policy, authorize real capital, complete Capital/Portfolio, or touch Durdurulmaz / Quantum Capital.

Accepted implementation phases:

- **MI1 PASS** — customer-facing message composition and primary customer surface;
- **MI2 PASS** — guarded local Turkish rewrite with deterministic fact locks;
- **MI3 PASS** — compact decision/current-view summary plus the five-family weighted table;
- **MI4 PASS** — each family row owns its own exact/frozen proof window; no generic bottom proof CTA;
- **MI5 PASS** — real deployed desktop/mobile browser acceptance;
- **MI6 PASS** — this authority freeze.

## 2. Accepted customer message contract

The normal Product Stream now prefers one forward-only deterministic `system_view_updated` message instead of exposing low-level five-family transition telemetry as separate customer bubbles.

The visible customer message:

- is concise Turkish system-view prose;
- does not expose raw state-machine vocabulary such as `sell_pressure`, `state_label`, `measured:` or arrow-heavy transitions;
- never invents trigger, target, invalidation, probability, causal attribution or evidence;
- remains deterministic when local rewrite is absent/rejected;
- keeps raw family narratives immutable and available for audit/debug/evidence lineage.

The forward-only system-view is a **presentation/evidence view**, not a new forecast authority and not a calibrated probability engine.

## 3. Accepted five-family evidence contract

The accepted matrix remains:

| Family | Weight |
| --- | ---: |
| Geometry / Market Structure | 20 |
| Liquidity | 25 |
| Order Flow / Absorption | 25 |
| Derivatives | 15 |
| On-chain / Smart Money | 15 |

Total: **100**.

Event Risk remains outside the 100-point matrix.

The displayed directional support score is explicitly semantically bound as:

`weighted_directional_family_vote_not_probability`

It must never be presented as a win probability.

Unavailable evidence remains unavailable, for example:

`— / 15 · VERİ YOK`

Missing evidence is never silently converted into directional zero.

## 4. Accepted proof interaction contract

The expanded message contains:

- **KARAR ÖZETİ**;
- **5 KANIT AİLESİ**.

There is no generic bottom proof CTA.

Each of the five family rows is independently clickable and opens only that family's explanation + proof context for the exact message lineage.

Accepted proof states remain fail-closed:

- `READY_EXACT`;
- `IDENTITY_ONLY_EXACT`;
- `UNAVAILABLE_EXPLICIT`.

Only Geometry may render its canonically bound frozen chart. A current chart/order book must never be substituted for historical/frozen message proof.

The system-view family row binds to the exact selected family snapshot's source narrative identity; it does not merely bind to whichever family narrative happened to be latest.

## 5. Ollama/local LLM boundary

The local model remains presentation-only.

Accepted MI2 behavior:

- receives a deterministic, fact-locked analyst brief;
- may improve Turkish flow;
- may not reverse stance;
- may not change/drop visible protected numbers;
- may not introduce unbriefed/new family claims;
- may not create a score, probability, market fact, target, trigger, invalidation or trading authority;
- deterministic fallback remains mandatory.

## 6. Mechanical acceptance evidence

### MI1

- customer-copy merge: `a2c317bbee1b325500b909bbe970750370a17eda`;
- primary-system-view merge: `28fa1c208e9e66173214a8bdfaa33cea4bbfe935`;
- UID504 acceptance run: `36330349505`.

### MI2

- merge: `20c1c18c3253254555708e0cbcc0c52cc04ae784`;
- UID504 acceptance run: `36331471395`;
- real loopback model smoke: `qwen2.5:3b-instruct`.

### MI3

- merge: `4dc3c2a4ebdda513f2150313f74f0f06a3a47ec6`;
- UID504 acceptance run: `36332071137`.

### MI4

- merge: `caeaf41256fe9f5d878d78f08374224e571798e4`;
- UID504 acceptance run: `36332851225`.

### MI5 implementation + deploy

- implementation merge: `93d9b1edfaf0267b6873f3aaaa2eb9e6dd455af0`;
- exact Product deploy run: `36337341847`;
- deploy evidence included:
  - Development/Product target = `93d9b1edfaf0267b6873f3aaaa2eb9e6dd455af0`;
  - dashboard supervisor-managed restart;
  - health PASS;
  - runtime topology PASS;
  - rollback not triggered;
  - `REAL_CAPITAL=0`.

### Natural live production proof

A natural supervisor/live-family cycle after deploy produced forward-only `system_view_updated` rows for live symbols. A separate UID501 read-only Product probe confirmed live Product API delivery after deployment.

No historical system-view backfill was used.

### MI5 final real-browser acceptance

UID504 post-deploy acceptance run:

`36338498776`

Artifact:

- id: `10937634080`;
- name: `message-intelligence-mi5-probe-36338498776`;
- digest: `sha256:8cb546390232c22321e0e33334bd50c78f36cb48580b4258c2d532221aeb3909`.

The run mechanically proved:

- `MI5_CANONICAL_PRIMARY_REGRESSION_PASS=YES`;
- live primary Stream contained forward-only `system_view_updated` messages;
- selected message had exactly five family contributions;
- score semantic = `weighted_directional_family_vote_not_probability`;
- `MI5_PRIMARY_RAW_TELEMETRY_LEAK=NO`;
- desktop real Chromium proof acceptance PASS;
- mobile real Chromium proof acceptance PASS;
- five family rows appeared in canonical order:
  - Geometry;
  - Liquidity;
  - Order Flow;
  - Derivatives;
  - On-chain;
- each family row opened its own family proof context;
- no generic global proof action/launcher remained;
- search, filter, sound, settings and load-older/history controls remained present;
- canonical Development/Product checkouts remained unchanged by the read-only probe;
- `REAL_CAPITAL=0`.

For the accepted live message observed in the final browser artifact:

- Geometry: `UNAVAILABLE_EXPLICIT`;
- Liquidity: `IDENTITY_ONLY_EXACT`;
- Order Flow: `IDENTITY_ONLY_EXACT`;
- Derivatives: `IDENTITY_ONLY_EXACT`;
- On-chain: `UNAVAILABLE_EXPLICIT`.

This is valid fail-closed behavior. The acceptance does not require evidence to exist where canonical persisted evidence does not exist.

## 7. Decision Evidence remains separate truth

The existing R20/R20.5 decision-evidence ledger remains authoritative for canonical persisted forecasts/proofs.

The final MI5 acceptance observed the decision-evidence store as read-only and populated, including forecast/proof/feed rows.

The new Stream system-view does not replace that canonical forecast/proof truth and does not promote itself into production trading authority.

## 8. Explicit non-claims

This acceptance does not claim:

- calibrated win probability;
- real-money trading;
- execution authority;
- complete live evidence for every family at every moment;
- Capital/Portfolio completion;
- historical rich-message reconstruction;
- automatic conversion of family support into a trade;
- that unavailable evidence is negative evidence.

## 9. Final state

Canonical final status:

**MESSAGE_INTELLIGENCE_FAMILY_EVIDENCE_UX_V1_ACCEPTED**

There is no remaining active MI phase after MI6.

Any future work on Capital/Portfolio, new product screens, trading policy, calibration, new evidence sources or different UI architecture is new scope and requires its own authority.

**REAL_CAPITAL=0**
