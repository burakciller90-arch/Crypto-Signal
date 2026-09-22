# M2 Liquidity Intelligence 2.0 — Slice 4: Observed Liquidation Heatmap

Status: development slice on top of accepted M2 Slice 3  
REAL_CAPITAL: 0  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`

## Purpose

This slice adds a distinct liquidation research layer without fabricating future
liquidation levels.

It separates three concepts required by the locked roadmap:

1. **Observed liquidation** — supported in this slice.
2. **Estimated leverage concentration** — `NOT_ESTIMATED` in this slice.
3. **Future liquidation-risk zone** — `NOT_ESTIMATED` in this slice.

Observed historical liquidation is not future liquidation risk.

## Provider contract

The initial normalizer targets Bybit V5 public linear `allLiquidation.{symbol}` evidence.

The provider payload supplies:

- system message timestamp;
- liquidation update timestamp;
- symbol;
- position side;
- executed size;
- bankruptcy price.

Provider `S=Buy` is normalized as **a long position liquidated** and `S=Sell`
as **a short position liquidated**. This is not public-trade aggressor side.

No trading credential is required for this public evidence model.

## Point-in-time truth

A liquidation event is usable only when event/source/ingestion timestamps are all
<= `as_of_ms`.

A mark reference is usable only when its event/source/ingestion timestamps are all
<= `as_of_ms` and the mark is fresh enough.

A zero-event heatmap is measurable only when explicit feed coverage proves the entire
requested window was observed. Missing feed coverage is not interpreted as zero
liquidations.

Late or future evidence cannot rewrite a historical freeze.

## Heatmap semantics

Observed events are binned by bankruptcy-price distance from the frozen mark reference.
For each bin retain:

- distance band in basis points;
- event count;
- long-liquidation count;
- short-liquidation count;
- bankruptcy notional;
- share of observed liquidation notional;
- min/max bankruptcy price;
- bounded `observed_cluster` flag.

An observed cluster is a concentration of already-observed liquidation evidence. It is
not a forecast of where future traders will be liquidated.

## Fail-closed rules

Return `UNRESOLVED` when:

- feed coverage does not include the whole analysis window;
- feed coverage was only observed after the PIT cutoff;
- mark price is unavailable;
- mark reference is future or stale;
- event/coverage/mark context disagrees;
- duplicate event identity is present.

## No-estimation boundary

This slice deliberately does **not** infer:

- retail stop locations;
- leverage distributions;
- future liquidation prices;
- liquidation cascades;
- actor identity or intent.

Those require separate data/model evidence and later acceptance.

## Acceptance

- deterministic Bybit payload normalization;
- explicit Buy -> liquidated LONG / Sell -> liquidated SHORT semantics;
- deterministic identities;
- complete-coverage zero-event truth;
- price-distance heatmap bins;
- future/late evidence exclusion;
- stale/incomplete evidence fail-closed;
- immutable freeze identity;
- estimated leverage concentration = NOT_ESTIMATED;
- liquidation risk zone = NOT_ESTIMATED;
- no production deployment;
- REAL_CAPITAL=0.
