# RDP7 Real On-chain + Stablecoin Capital Flow — Implementation Preparation

Status: **PREP ONLY — NO PRODUCTION ACTIVATION**
Prepared against main: `19cc65f9b5dbcbf8ee05ba57368145c3f12f6722`
Branch: `prep/rdp7-onchain`
Safety: **REAL_CAPITAL=0**
Execution authority: `docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md`

## 1. Scope and sequencing

RDP7 follows the locked Reality-Backed Evidence Data Plane sequence after RDP6. This preparation must not modify RDP5 runtime ownership, Market Tape collection, liquidation runtime, production supervisor behavior, score weights, or live activation.

RDP7 may mark the On-chain family **OBSERVED** only from accepted, fresh, forward-observed provider evidence. Research fixtures, synthetic observations, notebooks, historical replays assembled after the fact, and provider-neutral contracts are not production-live source truth.

The five-family matrix remains unchanged. RDP7 enriches the existing **On-chain** family only.

## 2. Verified repository reality

### 2.1 Real-source capable but not production-live

#### Bitcoin network

Files:

- `src/crypto_signal/data/adapters/blockstream_bitcoin.py`
- `src/crypto_signal/data/onchain.py`
- `src/crypto_signal/intelligence/onchain_network.py`

Reality:

- the adapter calls the public Blockstream Esplora Bitcoin API;
- the normalized Bitcoin block-window model and PIT-safe freeze engine are real-source capable;
- the evidence measures Bitcoin block cadence/utilization/network activity;
- there is no accepted always-on persistence/runtime rail on current main;
- this evidence is **not exchange inflow/outflow, stablecoin flow, wallet attribution, whale flow or capital-flow evidence**.

Current Stream policy explicitly marks `bitcoin_network_context` as `DEFERRED_SOURCE`.

### 2.2 Accepted research contracts — not live provider rails

#### Exchange flow

Files:

- `src/crypto_signal/data/exchange_flows.py`
- `src/crypto_signal/intelligence/exchange_flow.py`
- `docs/M5_EXCHANGE_FLOW_SLICE1.md`

Good reusable properties:

- provider-neutral immutable `ExchangeFlowObservation`;
- source window start/end;
- inflow/outflow amounts;
- provider identity;
- attribution method;
- source/ingestion timestamps;
- PIT-safe freeze and stale/insufficient fail-closed engine;
- explicit zero-gross measured windows are valid when a provider really reported them.

Not live:

- no source adapter;
- no credentials/provider entitlement;
- no raw payload lineage;
- no source coverage persistence;
- no append-only production store;
- no scheduler/runtime activation.

The M5 document explicitly says no live provider is invented or activated.

#### Wallet cohorts

Files:

- `src/crypto_signal/data/wallet_cohorts.py`
- `src/crypto_signal/intelligence/wallet_cohorts.py`
- `docs/M5_WALLET_COHORT_REGISTRY_SLICE2.md`

Good reusable properties:

- immutable cohort admission;
- basis evidence must predate admission;
- forward-only post-admission measurement;
- no hindsight cohort selection;
- provider/attribution/admission-rule version retained.

Not live:

- no accepted cluster provider;
- no live cluster/admission feed;
- no persistence/runtime scheduler;
- no provider-backed basis evidence pipeline.

#### Large transfers

Files:

- `src/crypto_signal/data/large_transfers.py`
- `src/crypto_signal/intelligence/large_transfer_clusters.py`
- `docs/M5_LARGE_TRANSFER_CLUSTERS_SLICE3.md`

Good reusable properties:

- provider transfer ID;
- source/destination cluster IDs;
- provider-declared cluster roles;
- exact amount and event/source/ingestion times;
- attribution-method version;
- PIT-safe bounded clustering;
- no directional price/actor-intent claim.

Not live:

- no real provider adapter;
- no real cluster-label provider;
- no event coverage interval;
- no append-only production persistence;
- no runtime.

The current engine requires actual observations; an empty input must never be converted into "zero transfers observed."

### 2.3 Existing proof/family scaffolding is research-only

`src/crypto_signal/intelligence/family_proof_adapters.py` can adapt a fresh `ExchangeFlowEvidenceFreeze` into the existing On-chain family and Decision Proof `ONCHAIN` domain.

However:

- the module declares itself a research adapter;
- it assumes an already accepted exchange-flow freeze;
- it is not a collector, persistence layer or provider truth;
- current product Stream policy marks `m5_smart_money_research` as `RESEARCH_ONLY`;
- the live F3 Stream intentionally deferred unsupported On-chain truth.

### 2.4 Stablecoin rail is missing

No accepted stablecoin supply/bridge/exchange-flow production rail was found on current main.

Missing:

- stablecoin supply observation model;
- mint/burn observation model;
- stablecoin exchange-flow adapter;
- bridge-flow observation model;
- raw source contract;
- coverage contract;
- persistence/replay;
- PIT engine;
- On-chain family projection.

## 3. Provider/source preparation

Provider selection must be explicit. No provider is accepted merely because its website displays a chart.

### 3.1 Blockstream Esplora — accessible now, public/no credential

Use for:

- BTC blocks;
- BTC transaction facts where needed.

Do not use as proof of:

- exchange attribution;
- wallet owner identity;
- institution/whale identity;
- exchange inflow/outflow without an independently accepted label registry.

Role in RDP7:

- retain as network-context source;
- optional raw BTC transaction source;
- not sufficient for RDP7 capital-flow PASS.

### 3.2 Glassnode Point-in-Time API — strongest exchange-flow candidate, credentialed

Verified provider semantics:

- Point-in-Time exchange inflow/outflow/netflow metrics exist;
- PiT series are described as append-only/immutable historical observations;
- exchange metrics rely on Glassnode-labelled exchange addresses and clustering methodology;
- API access requires Professional plus API add-on/API key.

Why it fits existing code:

- maps naturally into `ExchangeFlowObservation`;
- provider identity + attribution method can be versioned;
- source window/bucket timestamps can be preserved;
- native PiT semantics reduce historical revision risk.

Blocker:

- credential and entitlement are not present/verified in this prep;
- supported asset/metric/resolution entitlements must be queried before implementation;
- do not assume every stablecoin has the same PiT endpoint coverage.

### 3.3 CryptoQuant — real provider candidate, credentialed, PIT caveat

Verified provider semantics:

- BTC exchange inflow/outflow/netflow endpoints exist;
- stablecoin/ERC-20 exchange-flow families exist;
- API uses bearer authentication;
- on-chain data requires a paid plan tier;
- CryptoQuant explicitly states its ERC-20 exchange-flow history is **not PIT accurate** because exchange-wallet clustering is updated and historical values can change.

Allowed use if selected:

- forward collection only;
- freeze exact response first seen at observation time;
- never reconstruct an old decision using a later revised historical response;
- provider revision state must be an uncertainty/source-quality attribute.

Not allowed:

- backfilling revised ERC-20 history and presenting it as what the system knew historically.

### 3.4 DefiLlama — accessible stablecoin supply candidate

Verified source availability:

- free API requires no authentication;
- free stablecoin endpoints include stablecoin list/circulating amounts, historical total supply/market-cap series, chain-level history, asset history/chain distribution and chain totals;
- bridge endpoints are currently Pro/API-key surfaces.

Use candidate for:

- stablecoin aggregate supply;
- chain distribution;
- supply change/capital-liquidity context.

Do not use it as:

- exchange attribution;
- exact exchange inflow/outflow;
- individual actor/whale evidence;
- proof that issuance automatically enters crypto risk assets.

Bridge data:

- treat as separate provider-gated rail;
- bridge volume is not automatically stablecoin-only capital flow;
- token-level/route semantics must be verified before accepting a bridge metric into RDP7.

### 3.5 Etherscan V2 / raw EVM source — possible exact transfer source, not accepted attribution yet

Current public documentation exposes multichain API-key access, token-transfer workflows and address name-tag/label capabilities.

Potential use:

- exact USDT/USDC/PYUSD transfer observations;
- mint/burn candidates from exact token events when contract semantics are explicitly supported;
- independently frozen raw transaction/log evidence.

Blockers before acceptance:

- API-key entitlement/rate limits for required endpoints;
- exact label/name-tag licensing and stability;
- contract registry and decimals/versioning;
- chain reorg/finality policy;
- no assumption that a display name proves legal/person identity.

Do not couple Etherscan transfer facts to exchange roles until attribution coverage is contractually accepted.

## 4. Canonical RDP7 source-to-proof architecture

```text
Accepted provider/source
    -> exact raw response / raw event
    -> SourceRawPayload
    -> SourceCapability
    -> SourceEnvelope
    -> SourceCoverage / gap truth
    -> normalized PIT-safe observation
    -> append-only OnchainCapitalFlowStore
    -> bounded evidence engine / freeze
    -> existing ConfluenceFamily.ONCHAIN
    -> immutable decision/family evidence identities
    -> RDP10 exact proof projection
```

Every accepted observation must preserve:

- provider;
- provider endpoint/channel;
- asset/network;
- provider-native metric/transfer identity where present;
- provider attribution methodology/version;
- source window start/end where applicable;
- event timestamp;
- provider/source timestamp semantic;
- local observed time;
- local ingested time;
- adapter version;
- raw identity;
- normalized identity;
- coverage state.

## 5. Missing coverage versus measured zero — non-negotiable rule

### 5.1 Exchange flow

A zero inflow/outflow observation is valid **only** when:

- the provider returned an explicit zero for the exact completed source window;
- the raw response is frozen;
- the source envelope is present;
- coverage for that window is OBSERVED;
- timestamps are inside PIT bounds.

These cases are not equivalent:

```text
provider says inflow=0, outflow=0 + complete observed window
    => measured zero flow

HTTP error / timeout / missing entitlement / missing row / stale source
    => unavailable or gap

provider response exists but requested asset/window omitted
    => partial/unavailable, never zero
```

### 5.2 Large-transfer event feeds

Existing `LargeTransferCluster` research code cannot prove an observed-zero event window.

Add a coverage interval contract analogous to liquidation coverage:

- `coverage_identity`;
- provider/source;
- asset/network;
- coverage_start_ms;
- coverage_end_ms;
- observed_at_ms;
- completeness state;
- reason codes;
- raw/source-envelope parent identities.

Only complete observed coverage may support:

- `NONE_OBSERVED` for a zero-event interval.

No coverage means:

- `UNAVAILABLE` / `GAP`, never zero transfers.

### 5.3 Stablecoin supply

A zero supply change requires two valid, accepted supply snapshots whose values are equal.

Missing one snapshot is not zero supply change.

### 5.4 Bridge flow

Zero bridge flow is permitted only when the provider explicitly supplies a complete zero-volume/statistics window under an accepted token/chain definition.

## 6. Proposed normalized models

Implementation should reuse current M5 data models where their semantics already match.

### 6.1 Reuse unchanged where possible

- `ExchangeFlowObservation`
- `WalletCohortAdmission`
- `WalletCohortForwardObservation`
- `LargeTransferObservation`
- existing PIT engines/freezes

Do not fork these models merely to add provider code.

### 6.2 Add StablecoinSupplyObservation

Minimum fields:

- observation identity;
- stablecoin asset;
- network/chain scope;
- provider;
- provider metric identity;
- total/circulating amount;
- optional USD amount if provider supplies it;
- source snapshot/bucket timestamp;
- observed_at_ms;
- ingested_at_ms;
- adapter version;
- source-envelope/raw identity lineage.

Scientific meaning:

- descriptive liquidity/supply context only;
- supply increase != bullish;
- supply decrease != bearish.

### 6.3 Add StablecoinCapitalFlowFreeze

Possible components:

- supply level;
- short-horizon supply delta;
- chain-distribution change;
- accepted exchange inflow/outflow for USDT/USDC when a provider exists;
- accepted bridge context only when token-level semantics are exact;
- mint/burn facts only when raw-chain semantics are accepted.

States:

- MEASURED;
- PARTIAL;
- STALE;
- GAP;
- UNAVAILABLE;
- CONFLICT.

### 6.4 Add OnchainEventCoverage

Use for event-like sources:

- large transfers;
- raw stablecoin mint/burn events;
- provider transfer streams;
- optional bridge transaction streams.

This is necessary so "no event" is distinguishable from "no collection."

## 7. Persistence and replay

Do not overload the RDP5 Market Tape schema during first RDP7 implementation.

Create a separate append-only store, for example:

`src/crypto_signal/data/onchain_capital_flow_store.py`

Suggested tables:

- `onchain_exchange_flow_observations`
- `onchain_large_transfer_observations`
- `onchain_event_coverage`
- `onchain_wallet_cohort_admissions`
- `onchain_wallet_cohort_forward_observations`
- `stablecoin_supply_observations`
- optional `stablecoin_bridge_observations`

Required behavior:

- immutable identity-key insert;
- exact idempotent replay;
- conflict if same identity maps to different canonical payload;
- read-only as-of queries;
- historical replay never substitutes a later provider revision;
- no UPDATE/DELETE business path;
- indexes include asset/network/provider and event/window/ingestion time;
- source contract DB keeps raw/envelope/coverage lineage.

## 8. Timestamp and PIT semantics

Each adapter must document the timestamp semantic per endpoint.

### Window metrics

For exchange/stablecoin bucket metrics:

- `window_start_ms` / `window_end_ms` = provider metric period;
- `source_timestamp_ms` = provider data timestamp or documented bucket timestamp;
- `observed_at_ms` = local time response became visible to collector;
- `ingested_at_ms` = append time.

Never infer a server-generation timestamp if the provider does not publish one.

### Event sources

For exact transfers:

- `event_at_ms` = chain/provider event time;
- `source_timestamp_ms` = provider/source availability timestamp when supplied, otherwise adapter contract must document its exact semantic;
- local observation/ingestion remain separate.

### Revised attribution sources

If labels can revise historical classification:

- freeze provider attribution version/semantic at observation time;
- do not mutate old evidence;
- a later revision becomes a new observation;
- historical decision replay uses the old frozen observation.

## 9. Provider-specific freshness preparation

Roadmap target for on-chain exchange/transfer feeds is provider-specific, nominally <=10 minutes.

Do not hard-code one universal SLA before endpoint cadence is verified.

Suggested initial gates:

- public Bitcoin network snapshot: provider cadence aware; no false stale claim merely because Bitcoin block production is slow;
- exchange-flow metric: <= provider update cadence + bounded collector delay;
- large-transfer event feed: target <=10m if provider supports it;
- stablecoin supply aggregate: slower context allowed if provider is daily/hourly; it must be labelled slow context and cannot masquerade as intraday flow;
- bridge statistics: provider completion cadence aware.

Freshness policy is versioned per capability, not a model-accuracy score.

## 10. On-chain family projection

After accepted live source freezes exist, wire them into the existing `ConfluenceFamily.ONCHAIN`.

Do not create a sixth family.

Evidence domains may include:

- `bitcoin_network_context`;
- `exchange_flow`;
- `large_transfer_context`;
- `wallet_cohort_forward`;
- `stablecoin_capital_flow`.

Suggested components:

- `onchain_status`;
- `exchange_flow_status`;
- `exchange_flow_net_direction`;
- `exchange_flow_latest_age_ms`;
- `large_transfer_status`;
- `large_transfer_coverage_status`;
- `large_transfer_event_count`;
- `wallet_cohort_status`;
- `wallet_cohort_measurement_coverage`;
- `stablecoin_status`;
- `stablecoin_supply_delta`;
- `stablecoin_exchange_flow_status`;
- `stablecoin_bridge_status`.

Direction must remain neutral unless a separately accepted scientific rule explicitly justifies a directional contribution. Existing exchange-flow research semantics are context, not automatic long/short votes.

Exact raw/customer rendering is completed under RDP10, but RDP7 must freeze enough lineage to make that resolution possible without current-data substitution.

## 11. Minimum implementation sequence after RDP6 PASS

### RDP7-A — source/coverage contracts and persistence

- reuse `SourceContractStore`;
- add `OnchainEventCoverage`;
- add append-only `OnchainCapitalFlowStore`;
- add stablecoin supply contract;
- contract/persistence fixtures only;
- no live provider activation.

### RDP7-B — first real exchange-flow provider

Preferred path if entitlement exists:

- Glassnode PiT exchange-flow adapter for accepted BTC/ETH metrics;
- exact raw payload -> envelope -> `ExchangeFlowObservation`;
- manual bounded collector;
- forward-only persistence;
- explicit stale/gap behavior.

Fallback provider path must meet the same PIT/coverage contract. If using mutable historical providers, only first-seen forward snapshots count as PIT decision evidence.

### RDP7-C — stablecoin supply/capital context

Low-friction candidate:

- DefiLlama public stablecoin supply/history;
- USDT/USDC first;
- supply/chain distribution freeze;
- no directional shortcut.

Separate credentialed extensions:

- exact stablecoin exchange flow;
- bridge flow;
- mint/burn.

### RDP7-D — large transfer coverage + provider adapter

Only activate when provider supplies defensible transfer IDs and attribution semantics.

- persist exact coverage interval;
- persist exact transfer observations;
- zero-event windows require complete coverage;
- run existing large-transfer engine over forward observations.

If no accepted labelled-transfer provider exists, keep this rail UNAVAILABLE.

### RDP7-E — wallet cohort forward rail

Only after real provider cluster identities and immutable admission basis exist.

- freeze admission before forward measurements;
- persist provider methodology version;
- never select cohort membership using future outcome/performance.

If provider cluster identity is unavailable, remain `REGISTRY_ONLY/UNAVAILABLE` rather than inventing "smart wallets."

### RDP7-F — existing On-chain family + proof wiring

- promote only accepted live freezes;
- preserve neutral/context semantics;
- no score-family addition;
- no current-data substitution;
- no synthetic fallback.

### RDP7-G — exact-main live acceptance

For each activated rail:

- raw response exists;
- source envelope exists;
- coverage state exists;
- normalized identity resolves;
- append-only persistence resolves;
- PIT freeze resolves;
- On-chain family points at exact accepted identities;
- stale/gap/no-coverage tests fail closed;
- REAL_CAPITAL=0.

## 12. Minimum test/gate matrix

| Gate | Required proof |
|---|---|
| Provider contract | provider/endpoint/metric/attribution version is explicit |
| Raw lineage | normalized observation resolves to exact immutable raw payload and source envelope |
| PIT | future/late/revised observations cannot rewrite historical as-of |
| Missing vs zero | missing row/timeout/gap never creates zero flow |
| Zero exchange flow | zero is accepted only from explicit provider zero + complete observed window |
| Event zero coverage | zero-event transfer window requires complete interval coverage |
| Persistence | insert/idempotent replay/conflict/as-of read-only behavior |
| Exchange-flow engine | existing M5 anomaly/balanced/mixed semantics preserved |
| Large-transfer engine | real provider observations only; no actor-intent labels |
| Wallet cohorts | admission basis predates admission; measurement starts after admission |
| Stablecoin supply | unchanged valid snapshots produce zero delta; missing snapshot does not |
| Stablecoin semantics | mint/supply/exchange/bridge metrics remain separate, not silently combined |
| Provider revisions | new provider attribution revision becomes new evidence, old freeze remains immutable |
| Freshness | provider-capability SLA enforced; stale input cannot retain last vote |
| Family ownership | output remains `ConfluenceFamily.ONCHAIN` |
| Direction | no automatic buy/sell from exchange flow, mint, whale transfer or bridge flow |
| Proof lineage | On-chain proof resolves exact freeze/source identities |
| RDP5 regression | no RDP5/live runtime file or behavior changed |
| Static quality | focused pytest + Ruff + mypy + py_compile |
| Live acceptance | forward real observations + explicit coverage + REAL_CAPITAL=0 |

## 13. Open blocker list

### BLOCKER 1 — no accepted exchange-attribution credential/provider on current main

The research model exists; live source does not.

Resolution:

- provision/approve a provider entitlement and API secret outside Git;
- verify assets, metrics, cadence and usage rights;
- bind provider methodology version.

### BLOCKER 2 — large-transfer zero-event coverage does not exist

Existing large-transfer model represents events, not proof of a fully observed empty interval.

Resolution:

- add `OnchainEventCoverage` before live large-transfer activation.

### BLOCKER 3 — no accepted provider for exact cluster transfer identities

Glassnode/CryptoQuant aggregate metrics do not automatically satisfy the existing per-transfer `provider_transfer_id + source/destination cluster_id` contract.

Resolution:

- select a provider that exposes exact attributed transfer events, or
- keep large-transfer/wallet-cluster rails explicitly unavailable.

Do not fabricate cluster IDs from addresses and call them provider attribution.

### BLOCKER 4 — wallet cohort source/admission basis is absent

The anti-hindsight contract exists but there is no real provider-driven admission feed.

Resolution:

- define provider cluster identity;
- define immutable admission rule;
- define exact basis evidence;
- begin forward measurement only after admission.

### BLOCKER 5 — stablecoin model/persistence/runtime absent

Resolution:

- implement supply observation + freeze first;
- add exchange/bridge/mint-burn rails independently;
- never collapse distinct semantics into one "stablecoin bullishness" number.

### BLOCKER 6 — bridge data access/semantics

DefiLlama bridge API is provider-gated and generic bridge volume is not automatically stablecoin-specific.

Resolution:

- verify token/chain/route fields and entitlement before accepting bridge flow.

### BLOCKER 7 — current Product Stream intentionally defers On-chain

Current policy is correct.

Resolution:

- do not change `DEFERRED_SOURCE/RESEARCH_ONLY` until real provider + persistence + coverage + PIT acceptance passes.

### BLOCKER 8 — source freshness is provider-specific

Resolution:

- capture actual provider update cadence during live acceptance;
- version freshness per `SourceCapability`;
- do not claim <=10m if provider itself publishes slower.

## 14. RDP7 PASS boundary

RDP7 can be marked PASS only when:

- at least one accepted real exchange/capital-flow provider is active;
- raw payload and normalized observation lineage is immutable;
- source coverage and gap truth are explicit;
- missing coverage never becomes zero flow;
- forward real observations exist;
- stablecoin capital-flow context comes from an accepted real source;
- provider attribution and methodology are versioned;
- replay is PIT-safe with no current-data substitution;
- stale/missing inputs fail closed;
- no synthetic whale/institution/insider claim exists;
- On-chain family uses only accepted fresh evidence;
- exact proof lineage is available for RDP10;
- existing RDP5 runtime remains untouched;
- REAL_CAPITAL=0.

If an acceptable attribution/provider source cannot be obtained, On-chain remains explicitly unavailable. That is a correct production state and is preferable to a fabricated replacement.
