# GALACTECH Product Rail — Command Center + Evidence Room Slice 2

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product rail.
Predecessor: accepted GALACTECH foundation PR #924.
REAL_CAPITAL=0.

## Command Center

The new GALACTECH Command surface remains a sparse, read-only projection of the
existing immutable signal freeze APIs.

- Intelligence Feed cards bind exact `signal_freeze_identity`.
- Critical Radar cards bind the exact latest signal freeze exposed by the radar API.
- Asset focus filters only the rendered accepted cards; it does not alter evidence.
- Confluence remains agreement evidence, not probability.
- Missing Event Risk / advanced anomaly endpoints remain visibly unwired rather than
  inferred from unrelated signal state.

Every Command/Radar card opens the Evidence Room by exact SHA256 identity.

## Evidence Room provenance

This slice deliberately uses the accepted legacy signal-freeze detail endpoint
`/api/signals/{signal_freeze_identity}`.

It does **not** relabel that endpoint as the newer R20.5 Decision Proof artifact.
The UI says **Immutable Decision Evidence** and keeps the provenance boundary explicit.

The room exposes:

- exact immutable freeze identity;
- decision state, direction and setup type;
- confluence with its non-probability semantics;
- probability status (including NOT_CALIBRATED);
- signal as-of, source cutoff and frozen timestamps;
- deterministic frozen OHLC chart when exact candle OHLC exists in `bundle_json`;
- candle count and exact freeze range;
- concise evidence summary;
- uncertainty flags;
- accepted methodology slots and selected evidence;
- market-available and observed timestamps;
- evidence metrics/key levels;
- ambiguity/contradiction flags;
- pairwise methodology relations;
- frozen geometry when present;
- explicit no-geometry state when absent.

No later candle can rewrite issuance-time evidence.

## Frozen chart

The chart is rendered directly from the immutable frozen candle payload.

- at most the latest 40 frozen candles are visualized;
- OHLC values are never interpolated or invented;
- an absent/unparseable OHLC payload produces an explicit unavailable state;
- visual direction uses only frozen open/close relation;
- chart rendering has no trading or execution semantics.

## Explanation boundary

Evidence Room displays structured evidence and deterministic concise context.

It never:
- exposes private chain-of-thought;
- fabricates rationale;
- upgrades uncertainty;
- converts confluence into probability;
- turns geometry into an order instruction;
- submits an order or writes a ledger.

## Interaction / accessibility

- Command, Radar and Archive proof cards are semantic buttons.
- Native `dialog` semantics are used when available.
- Close returns keyboard focus to the exact launching card.
- Evidence loading and unavailable states are explicit.
- LEARN handoff closes the modal before navigating.
- Reduced-motion foundation remains preserved.

Status: CANDIDATE until exact-head hosted focused + full-repository acceptance passes.
