# RDP6 BTC/ETH Options — Implementation Preparation

Status: **PREP ONLY — NO PRODUCTION ACTIVATION**
Prepared against main: `19cc65f9b5dbcbf8ee05ba57368145c3f12f6722`
Branch: `prep/rdp6-options`
Safety: **REAL_CAPITAL=0**
Execution authority: `docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md`

## 1. Scope and guardrails

RDP6 remains blocked from production implementation until RDP5 is formally PASS. This prep must not modify RDP5 runtime ownership, Market Tape collector behavior, live supervisor logic, production activation, score weights, or merge authority.

RDP6 enriches the existing **Derivatives** family only. It does not create a sixth family and it does not make options OI, max-pain, public Greeks, or inferred dealer positioning directional proof.

Current acceptance target from the roadmap:

- BTC/ETH options surface freshness: <=120s where a real-time provider permits;
- ATM IV;
- IV term structure;
- correctly defined call/put skew such as 25-delta risk reversal;
- OI by expiry/strike;
- volume by expiry/strike where source semantics permit;
- put/call OI and volume context;
- major expiry concentration;
- volatility index only where a provider actually supplies one;
- exact immutable freezes;
- no unsupported dealer-gamma/max-pain claim.

## 2. Verified repository reality

### Production-live / reusable now

1. `src/crypto_signal/data/source_contract.py`
   - append-only `SourceRawPayload`, `SourceCapability`, `SourceEnvelope`, coverage and freshness contracts;
   - raw -> normalized identity lineage;
   - PIT timestamps and explicit freshness states;
   - REAL_CAPITAL=0 / no production authority.

2. `src/crypto_signal/data/market_tape.py`
   - append-only normalized market evidence persistence;
   - derivatives rows are immutable and replayable;
   - current derivatives schema is designed for perpetual observations.

3. `src/crypto_signal/data/derivatives.py`
   - immutable `DerivativesObservation`;
   - currently only `DerivativesInstrumentType.LINEAR_PERPETUAL`;
   - fields cover funding/OI/mark/index, not option expiry/strike/type/IV surface semantics.

4. `src/crypto_signal/data/adapters/bybit_derivatives.py`
   - read-only Bybit linear-perpetual REST adapter;
   - not an option adapter.

5. `src/crypto_signal/intelligence/derivatives_context.py`,
   `derivatives_dynamics.py`, `derivatives_crowding.py`
   - PIT-safe immutable derivatives evidence/freeze patterns;
   - reusable design pattern, but not option-surface engines.

6. `src/crypto_signal/product/intelligence_stream_family_sources.py`
   - one existing `ConfluenceFamily.DERIVATIVES` projection;
   - current source is Bybit linear-perpetual Market Tape plus observed liquidation coverage;
   - RDP6 should extend this same family, not add another family.

### Research-only / not an Options substitute

- `src/crypto_signal/intelligence/breakout_volatility.py` measures candle/range volatility state. It is **not implied volatility**, not an option volatility surface, and must not be reused or relabeled as options IV.
- Public per-contract Greeks do not prove dealer inventory or dealer gamma positioning.
- Historical volatility does not equal a volatility index and must not be presented as one.

### Missing on current main

- accepted BTC/ETH options provider contract;
- normalized option instrument/surface model;
- immutable option-surface persistence;
- option raw/envelope/coverage wiring;
- PIT options-volatility engine;
- options evidence freeze;
- Derivatives-family options projection;
- exact options proof resolver/renderer.

## 3. Provider preparation decision

### Primary implementation candidate: Bybit public Options market data

Reason: it matches the existing provider/runtime conventions and currently exposes public Option market surfaces without trading authority.

Candidate REST surfaces:

- `GET /v5/market/instruments-info?category=option&baseCoin=BTC|ETH`
  - instrument symbol, option type, base/quote/settle coin, delivery time, status and contract metadata.

- `GET /v5/market/tickers?category=option&baseCoin=BTC|ETH`
  - option mark IV, bid/ask IV where present, mark/index/underlying prices, OI, 24h volume/turnover and per-contract Greeks.

- `GET /v5/market/historical-volatility?category=option&baseCoin=BTC|ETH`
  - provider historical-volatility series only.
  - **Do not call this a volatility index or implied-volatility index.**

Candidate public WS surface:

- public option endpoint + `tickers.{symbol}`, currently documented at 100ms push frequency for Options.

### Minimal provider sequence

Start RDP6 with read-only REST surface snapshots because a full `baseCoin=BTC|ETH` ticker snapshot can satisfy the roadmap <=120s freshness budget with a bounded polling cadence and gives a simpler exact raw-snapshot lineage. Add WS only after REST correctness/coverage is accepted.

No credentials, account Greeks, private endpoints, order endpoints, or trading authority are required.

## 4. Canonical source -> proof chain

Use this exact chain:

```text
Bybit public Option REST snapshot
    -> SourceRawPayload (immutable canonical raw response)
    -> SourceCapability / SourceEnvelope / SourceCoverageEvent
    -> OptionSurfaceObservation (normalized PIT-safe whole-surface identity)
    -> OptionsSurfaceStore (append-only)
    -> OptionsVolatilityEvidenceFreeze
    -> existing Derivatives family snapshot
    -> immutable decision/family evidence identities
    -> RDP10 exact proof projection / visual rendering
```

### Why whole-surface normalization

Do **not** extend `DerivativesObservation` by pretending each option contract is a linear perpetual.

Do **not** build one immutable `SourceCapability` containing a permanently fixed list of every expiring option symbol. The option universe rolls continuously and would churn capability identity.

Instead, use a base-asset surface contract:

- capability symbols: `BTC`, `ETH`;
- one normalized `OptionSurfaceObservation` per base-asset source snapshot;
- child contract quotes remain inside the immutable surface payload;
- the envelope maps the exact raw response to the exact normalized surface identity.

This keeps the source contract stable while preserving the complete dynamic instrument universe.

## 5. Proposed normalized contracts

Implementation files after RDP5 PASS:

- `src/crypto_signal/data/options.py`
- `src/crypto_signal/data/adapters/bybit_options.py`
- `src/crypto_signal/data/options_surface_store.py`
- `src/crypto_signal/data/options_source_contract.py`
- `src/crypto_signal/intelligence/options_volatility.py`

### OptionInstrumentSpec

Minimum fields:

- `instrument_identity`
- provider / venue
- instrument symbol
- base / quote / settle asset
- option type: call | put
- strike
- expiry/delivery timestamp
- trading status
- source timestamp / observed / ingested
- adapter version

### OptionContractQuote

Minimum fields:

- instrument identity / symbol
- mark IV
- bid IV / ask IV when present
- mark price
- index price
- underlying price
- delta
- gamma / vega / theta as descriptive per-contract fields only
- open interest
- 24h volume / turnover where source semantics are explicit

All numeric fields use `Decimal`. Missing provider fields stay `None`; never coerce blanks into zero.

### OptionSurfaceObservation

Minimum fields:

- `surface_identity` = canonical SHA256 of normalized payload;
- provider / venue;
- base asset: BTC | ETH;
- source snapshot timestamp;
- observed timestamp;
- ingested timestamp;
- adapter version;
- exact instrument-metadata identity/version used;
- canonical sorted tuple of contract quotes.

PIT invariant: every source/observed/ingested timestamp consumed by an analysis must be <= analysis `as_of_ms`.

## 6. Persistence design

Use a new append-only `OptionsSurfaceStore` during initial RDP6 implementation rather than changing the live RDP5 `MarketTapeStore` schema.

Suggested tables:

- `option_instrument_specs`
- `option_surface_snapshots`

Required properties:

- identity-keyed immutable insert or exact idempotent replay;
- conflict on same identity with different canonical payload;
- read-only `latest_surface_as_of(base_asset, as_of_ms)`;
- never substitute a current surface for a historical `as_of_ms`;
- indexes on `base_asset, source_timestamp_ms, ingested_at_ms`;
- no UPDATE/DELETE business path.

Future consolidation into Market Tape may be considered only after RDP6 acceptance; it is not required for first implementation.

## 7. PIT options-volatility engine

Proposed engine output: `OptionsVolatilityEvidenceFreeze`.

### Required state

For each BTC/ETH surface:

1. **Surface status**
   - MEASURED
   - PARTIAL
   - STALE
   - UNAVAILABLE
   - NOT_EVALUABLE

2. **ATM IV term structure**
   - per-expiry ATM IV points;
   - choose nearest valid strike to underlying/forward reference;
   - prefer paired call+put IV when both are valid;
   - if only one side exists, mark partial rather than fabricate the pair.

3. **25-delta skew**
   - define sign explicitly as `25D risk reversal = call_25d_IV - put_25d_IV`;
   - select contracts nearest +0.25 call delta and -0.25 put delta within a configured maximum delta-distance;
   - if either leg is missing/outside tolerance, skew is unavailable for that expiry.

4. **OI / volume structure**
   - total OI;
   - put/call OI ratio;
   - put/call 24h volume ratio when valid volume exists;
   - OI by expiry;
   - top-expiry OI share;
   - optionally top strike concentrations as descriptive context.

5. **Expiry concentration**
   - top expiry and its share of measured OI;
   - never convert concentration into deterministic price-target language.

6. **Volatility index**
   - `UNAVAILABLE` unless a separately accepted provider field/source explicitly supplies one.
   - Bybit historical volatility is not accepted as a substitute.

### Scientific boundaries

Never emit:

- inferred dealer gamma positioning from public OI + per-contract gamma;
- max-pain directional targets;
- "calls bullish / puts bearish" shortcuts;
- OI as directional proof by itself;
- stale last-known IV as if current.

## 8. Derivatives-family projection

After the options engine is accepted, extend the existing `derivatives_change` family snapshot only.

Add evidence domain:

- `options_volatility`

Add exact identities:

- option raw/envelope lineage identity where projection contract permits;
- option surface identity;
- options analysis identity;
- options freeze identity.

Suggested state components:

- `options_status`
- `options_surface_age_ms`
- `options_front_atm_iv`
- `options_next_atm_iv`
- `options_term_structure_shape`
- `options_25d_rr`
- `options_put_call_oi_ratio`
- `options_put_call_volume_ratio`
- `options_top_expiry`
- `options_top_expiry_oi_share`
- `options_volatility_index_status`

If options are stale/unavailable, fail closed **for the options enrichment**. Do not reuse the previous options measurement. Do not invent a second family or change the 15-point Derivatives weight.

Exact customer payload rendering belongs to RDP10; RDP6 must nevertheless freeze enough immutable payload/identities so RDP10 can resolve them without current-data substitution.

## 9. Test / gate matrix

| Gate | Required proof |
|---|---|
| Contract identity | canonical identities stable; mutation changes identity; invalid timestamps/blank symbols rejected |
| Adapter fixture | official-shaped BTC + ETH instrument/ticker fixtures normalize deterministically; blanks remain None |
| Dynamic universe | rolling expiries/new symbols do not change source contract meaning or break base-asset capability |
| Raw lineage | each normalized surface resolves to exact immutable raw payload + envelope |
| PIT | future source/observed/ingested timestamps are rejected; historical as-of never sees later surface |
| Persistence | insert/idempotent replay/conflict/read-only as-of covered |
| Freshness | >120s surface becomes STALE/UNAVAILABLE; no last-known carry-forward |
| ATM IV | paired and partial cases deterministic |
| 25D RR | sign convention and delta tolerance explicitly tested |
| Term structure | expiry ordering and missing-expiry handling deterministic |
| OI/volume | ratios handle zero denominator as unavailable, never infinity/fabricated zero |
| Expiry concentration | share math exact and bounded [0,1] |
| Scientific boundary | no dealer-positioning/max-pain directional fields or labels |
| Family ownership | output stays `ConfluenceFamily.DERIVATIVES`; no sixth family/weight change |
| RDP5 regression | existing derivatives/liquidation family tests remain unchanged/pass |
| Static quality | focused pytest + Ruff + mypy + py_compile |
| Live acceptance | BTC and ETH real provider surface fresh <=120s, explicit coverage, REAL_CAPITAL=0 |

## 10. Minimal implementation order after RDP5 PASS

### RDP6-A — contracts and fixtures
- add option instrument/surface dataclasses;
- add official-shaped BTC/ETH REST fixtures;
- identity/PIT/unit tests only;
- no runtime activation.

### RDP6-B — read-only provider + immutable source/persistence
- Bybit public REST instrument/ticker adapter;
- SourceRawPayload + SourceEnvelope + coverage wiring;
- append-only OptionsSurfaceStore;
- bounded snapshot command for manual/CI proof;
- still no family activation.

### RDP6-C — PIT intelligence freeze
- ATM IV curve;
- term structure;
- 25D risk reversal;
- OI/volume ratios;
- expiry concentration;
- deterministic immutable freeze;
- explicit unavailable/partial/stale states.

### RDP6-D — existing Derivatives family wiring
- add options evidence/components to `derivatives_change`;
- no new family;
- no score/weight change;
- fail closed when options rail is unavailable.

### RDP6-E — exact-main live acceptance
- BTC + ETH source coverage;
- <=120s freshness;
- raw -> normalized -> store -> engine -> family identity proof;
- existing RDP5 derivatives/liquidation gates still PASS;
- REAL_CAPITAL=0.

### Optional RDP6-F — WebSocket upgrade
Only after REST acceptance:
- public option ticker subscriptions for active universe;
- exact connect/disconnect coverage;
- REST remains bootstrap/reconciliation/gap-repair;
- do not make WS a prerequisite for initial RDP6 PASS if REST meets freshness/coverage budget.

## 11. RDP6 PASS checklist

RDP6 can be marked PASS only when all are true:

- accepted provider/source semantics documented;
- BTC and ETH both covered;
- raw immutable source lineage exists;
- normalized surface is PIT-safe;
- persistence is append-only and historical replayable;
- freshness/coverage fail closed;
- IV term structure and correctly defined 25D skew are measured when evaluable;
- OI/volume/expiry concentration are descriptive and exact;
- volatility index is either real or explicitly unavailable;
- no dealer-gamma/max-pain unsupported claim exists;
- options enrich the existing Derivatives family only;
- exact freeze identities are available for later RDP10 proof rendering;
- RDP5 regression remains green;
- REAL_CAPITAL=0.

## 12. Prep conclusion

The repository already has the correct safety patterns for RDP6, but it does **not** currently have a production options rail. The smallest safe implementation is a separate BTC/ETH whole-surface contract/store built on the existing source-contract lineage, followed by a PIT options-volatility freeze and then one additive projection into the existing Derivatives family.

No RDP6 production feature should be activated before RDP5 PASS.
