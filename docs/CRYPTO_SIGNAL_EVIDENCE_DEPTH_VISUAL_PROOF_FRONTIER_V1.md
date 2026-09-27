# Crypto Signal — Evidence Depth & Visual Proof Frontier V1

Status: **ACTIVE USER-APPROVED FRONTIER**
Date opened: 2026-09-27
Company: GALACTECH
Product: Crypto Signal
Repository: `burakciller90-arch/Crypto-Signal`
Safety: **REAL_CAPITAL=0**

## 0. Why this frontier exists

Message Intelligence & Family Evidence UX V1 remains accepted and must not be replayed.

A post-acceptance live audit identified a deeper evidence-quality gap:

1. the five family rows open the correct family-owned proof context, but normal customer proof is often only `IDENTITY_ONLY_EXACT` / SHA lineage rather than a human-usable frozen visual;
2. several richer intelligence engines already exist in the repository, but the current live Product family chain uses narrower engines;
3. some source families are currently stale, unavailable, research-only or not connected to a live provider.

The user explicitly wants the proof layer to show **what the system actually measured and why that measurement supported/contradicted the view**, not merely a cryptographic identity.

This frontier fixes that gap without inventing data, backfilling historical evidence, weakening scientific policy or granting real-money authority.

## 1. Locked product outcome

For every family row, the proof window must prefer a **human-readable exact frozen payload** over SHA-only evidence.

A SHA256 remains provenance, not the primary proof UX.

Target behavior:

- **Geometry** → frozen candles + exact structure/trigger/target/invalidation annotations when bound;
- **Liquidity** → exact frozen order-book depth and measured liquidity dynamics; later richer pool/sweep evidence when canonically produced;
- **Order Flow** → exact frozen book + public-trade measurement; later CVD/divergence/absorption visualization when canonically produced;
- **Derivatives** → exact frozen OI/funding/basis observations and stale/unavailable state;
- **On-chain** → only real accepted provider/network evidence; otherwise explicit unavailable;
- **Event Risk** remains outside the 100-point matrix and must show exact fresh source evidence when available.

Current data may never be substituted for a historical/frozen message proof.

## 2. Live audit — 2026-09-27

### 2.1 Market Tape

Read-only UID504 freshness run: `36339584811`.

At the observed cutoff:

- Bybit SPOT order books were live at sub-second age;
- Bybit SPOT public trades were live at ~1–2 second age;
- derivatives observations existed but were ~22 hours stale;
- liquidation rows = 0;
- liquidation coverage rows = 0;
- collector heartbeat was live with zero-age successful ingestion.

Therefore:
- Liquidity and basic Order Flow have genuine fresh source truth;
- Derivatives must not be presented as fresh;
- no real liquidation heatmap proof is currently authorized.

### 2.2 Event Risk

Read-only event-source run: `36339587758`.

Observed truth:
- event-source DB exists;
- `runtime_status=PERSISTED_EVIDENCE_ONLY`;
- `online_status=NOT_ASSERTED`;
- `process_status=NOT_MEASURED`;
- coverage = `SOURCE_SCOPED_ONLY`;
- latest successful source fetch was roughly one day old;
- persisted Fed/FRED evidence exists; one BLS fetch failed with HTTP 403.

Therefore Event Risk code/persistence exists, but fresh continuous live-source operation is not currently proven.

### 2.3 On-chain / Smart Money

Current live Stream path explicitly records:

`ONCHAIN_STANDALONE=DEFERRED_SOURCE`

The wallet-cohort layer is provider-neutral research infrastructure and explicitly does not activate a live wallet provider or assert “insider/institutional” identity.

Therefore current Product must not pretend to have live exchange-flow / whale / profitable-wallet evidence.

## 3. Existing engine capability versus current live wiring

### 3.1 Liquidity

**Current live Product family**
- recent Bybit SPOT order books;
- `liquidity_dynamics`;
- depth addition/removal, depletion/replenishment, persistence and bounded liquidity-take candidate.

**Existing richer engines not yet part of the live family chain**
- liquidity structure / persistent pool candidates;
- spoofing candidate evidence;
- hidden-liquidity candidate evidence;
- liquidity sweep evidence;
- observed liquidation heatmap.

Scientific boundary:
- spoofing / hidden liquidity are **candidates**, not actor-intent proof;
- observed liquidation clusters are not estimated future stop locations.

### 3.2 Order Flow

**Current live Product family**
- exact Bybit SPOT order book + public trades;
- book imbalance;
- taker buy/sell flow;
- mixed / buy-pressure / sell-pressure state.

**Existing richer engines not yet part of the live family chain**
- local PIT CVD;
- price/CVD divergence candidate;
- bounded absorption candidate.

Scientific boundary:
- absorption is not proof of iceberg execution, manipulation or actor identity.

### 3.3 Derivatives

**Current live Product family**
- bounded OI/funding/basis context.

**Existing richer engines**
- price/OI dynamics;
- funding percentile/acceleration;
- basis dynamics;
- crowding and liquidation context.

Current blocker:
- live derivatives source is stale;
- liquidation collection/coverage is absent.

### 3.4 On-chain

Existing code covers Bitcoin network activity and provider-neutral wallet cohort contracts, but the live Stream has no accepted standalone on-chain/smart-money provider.

No synthetic “whale” or exchange-flow signal is authorized.

### 3.5 Event Risk

Event/news/calendar engines and circuit-breaker logic exist, but fresh always-on source operation must be proven before Product can rely on them as live context.

## 4. Confluence / threshold boundary

The accepted five-family weights remain:

- Geometry 20
- Liquidity 25
- Order Flow 25
- Derivatives 15
- On-chain 15

Event Risk remains outside the 100-point matrix.

The current score semantic remains **support/opposition evidence points, not calibrated probability**.

Thresholds 70 / 75 / 80 / 85 are forward-research hypotheses. The system must not silently convert “80 points” into “80% accuracy” or automatic production activation.

Conflict / abstain / partial / not-evaluable truth remains explicit.

## 5. Evidence UX rule

The customer should not have to interpret SHA256 strings as the proof itself.

For every available family proof:

1. show one short Turkish explanation of what was measured;
2. show the exact frozen visualization/measurement;
3. show source time / as-of time / freshness;
4. keep SHA lineage under a secondary “Provenance / teknik kimlikler” disclosure.

If exact payload cannot be resolved:
- show `IDENTITY_ONLY_EXACT` only as an explicit limitation;
- do not draw reconstructed current data.

If source evidence does not exist:
- show `UNAVAILABLE_EXPLICIT`.

## 6. Implementation phases

### ED0 — Authority + live capability ledger

Goal:
- freeze the audited truth above;
- distinguish code capability, live source availability, live Product wiring and visual-proof capability.

PASS:
- no engine/source is called live merely because code exists;
- no other project is touched.

### ED1 — Exact family payload resolution

Goal:
- diagnose and repair the family-proof path so live Liquidity / Order Flow / Derivatives source narratives resolve their exact persisted Market Tape payloads when available.

PASS:
- a family source narrative with bound orderbook/trade/derivatives identities returns actual exact frozen source objects;
- historical as-of bounds are verified;
- no current-data substitution;
- SHA remains provenance rather than the only visible payload.

### ED2 — Family visual renderers

Goal:
- add deterministic visual renderers over exact ED1 payloads.

Minimum target:
- Liquidity: frozen bid/ask depth view and measured depletion/replenishment summary;
- Order Flow: frozen book pressure + taker-flow view;
- Derivatives: exact OI/funding/basis observation panel/series when fresh enough;
- Geometry: retain exact frozen OHLC;
- On-chain: explicit unavailable until real source exists.

PASS:
- each rendered number/shape traces to the exact message source payload;
- stale/unavailable data is visibly labeled;
- provenance identities are secondary.

### ED3 — Rich intelligence live wiring

Goal:
- safely promote already-built richer engines into the forward-only family pipeline where source truth is sufficient.

Candidate work:
- Liquidity Structure + Sweep;
- CVD divergence + bounded absorption;
- Derivatives Dynamics/Crowding after fresh derivatives restoration;
- liquidation heatmap only after real feed coverage exists;
- no on-chain promotion without a real accepted provider.

PASS:
- exact PIT freezes;
- no hindsight;
- richer result is evidence, not actor-intent proof or probability.

### ED4 — Source completion

Goal:
- repair/complete missing live evidence rails.

Focus:
- fresh derivatives collection;
- liquidation public-feed collection + explicit coverage;
- fresh Event Risk source process;
- separately scoped real on-chain/exchange-flow/wallet provider evidence if later authorized.

### ED5 — Confluence integration

Goal:
- feed richer accepted family evidence into the existing locked five-family matrix without loosening conflict/missing-data semantics.

No automatic threshold promotion.

### ED6 — Real Product acceptance

Goal:
- prove on desktop/mobile that each family window shows the strongest real exact visual available, not merely hashes.

PASS:
- real live message;
- real frozen payload;
- family-specific rendering;
- explicit stale/unavailable truth;
- no raw telemetry leak;
- `REAL_CAPITAL=0`.

### ED7 — Authority freeze

Goal:
- close this frontier only after real visual proof and live-source claims are mechanically demonstrated.

## 7. Explicit non-claims

This frontier does not claim:
- 80%+ achieved accuracy;
- market-maker intent can be known;
- liquidity automatically “magnetically” determines price;
- absorption automatically means short/long;
- funding extremes prove the next move;
- wallet clusters are insiders/institutions;
- observed liquidation heatmap predicts future liquidation zones;
- confluence score is probability;
- real-money or execution authority.

## 8. Project isolation

Only `burakciller90-arch/Crypto-Signal` is in scope.

Durdurulmaz and Quantum Capital must not be touched.

**REAL_CAPITAL=0**
