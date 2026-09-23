# GALACTECH Product Rail — Foundation Slice 1

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product rail.
REAL_CAPITAL=0.

## Purpose

This slice starts the locked from-first-principles customer frontend rebuild without
patching the accepted legacy root UI in place.

The new surface is mounted at:

- `/galactech`
- `/galactech-static/app.css`
- `/galactech-static/app.js`

The accepted existing root UI remains at `/` until the new product rail passes all
integration, accessibility, responsive, hosted and live runtime acceptance gates.

## Locked information architecture

The preview implements the exact eight primary product destinations:

1. COMMAND
2. MARKETS
3. INTELLIGENCE
4. CAPITAL
5. ARCHIVE
6. PERFORMANCE
7. LEARN
8. SYSTEM

Global asset focus begins with ALL / BTC / ETH / SOL.

## Truth-first foundation

The preview consumes only existing read-only product APIs:

- `/api/health`
- `/api/command-center`
- `/api/market-radar`
- `/api/paper/epoch-contract`
- `/api/paper/mission-control`
- `/api/archive/proof-wall`
- `/api/education`
- `/api/intelligence-center`

Foundation rules:

- no fake LIVE state;
- no fake latency;
- no fake freshness;
- no fake probability;
- no inferred Paper NAV when the endpoint does not expose one;
- no fabricated market layers;
- no hidden missing evidence;
- no exchange/order/credential authority;
- REAL_CAPITAL=0.

The cold-start screen reports verified API/ledger/market-evidence/real-capital states.
Anything not measured or not exposed remains labelled as such.

## Visual system

The foundation establishes the locked product language:

- deep-space `#06080C -> #0B0F17` background;
- calm dark surfaces;
- Cyan = intelligence/data;
- Emerald = positive/safe;
- Crimson = negative/risk;
- Amber = caution/event/uncertainty;
- Purple reserved for research/shadow context;
- restrained glass treatment;
- mono typography for IDs/status/technical truth;
- neon remains semantic rather than decorative.

## Accessibility / motion

- skip link;
- visible `:focus-visible`;
- semantic buttons;
- `aria-current`, `aria-pressed`, status live regions;
- responsive breakpoints;
- reduced-motion contract;
- cold boot never blocks normal route navigation after initial load.

## Cutover boundary

This slice is intentionally **not** a production UI cutover.

The old root remains untouched while the isolated GALACTECH surface is proven.
A later cutover may occur only after the roadmap's full frontend acceptance:
Command Center, Evidence Room, Markets, Capital, Archive, Performance, Learn/System,
accessibility/responsive/performance polish, full integrated acceptance and live runtime
verification.

Status: CANDIDATE until exact-head hosted focused + full-repository acceptance passes.
