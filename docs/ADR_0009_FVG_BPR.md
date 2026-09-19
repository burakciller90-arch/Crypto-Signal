# ADR 0009 — FVG Lifecycle and Balanced Price Range

Status: Accepted for PA Slice 2 implementation
Date: 2026-09-20

## Raw Fair Value Gap geometry
Use a strict three-closed-candle definition on one gapless semantic series.

Bullish FVG at confirmation candle C:
- A.high < C.low
- zone = [A.high, C.low]

Bearish FVG:
- A.low > C.high
- zone = [C.high, A.low]

The middle candle participates in the formation window but does not change the raw gap bounds.

## Creation time
An FVG does not exist before the third candle closes.
- market creation time = third candle close time
- local observation time = latest ingest time among the three formation candles

## Lifecycle
Only candles strictly after the confirmation candle can change lifecycle state.

OPEN:
- no later candle range has overlapped the FVG zone

MITIGATED:
- a later candle has overlapped the zone but has not completely traversed the gap depth

FILLED:
- bullish FVG: a later candle range actually trades the zone lower boundary
- bearish FVG: a later candle range actually trades the zone upper boundary

If a later candle appears entirely beyond the far boundary without its range trading that boundary,
OHLC data does not prove the path through the zone. The engine records `gap_through_ambiguity=true`
instead of inventing a fill.

The engine records first touch, full-fill time and maximum deterministic fill fraction.
Wicks count for FVG mitigation/fill. This is intentionally different from PA Slice 1 structure breaks,
which require candle close beyond a confirmed swing.

## Balanced Price Range
A BPR exists only when:
- one bullish and one bearish FVG have a strictly positive price overlap,
- the two FVGs are temporally distinct,
- the earlier FVG was not already FILLED before the later FVG was created.

BPR zone:
- lower = max(source FVG lower bounds)
- upper = min(source FVG upper bounds)

BPR creation time is the later FVG creation time.
Its local observation time is the later of the two source-FVG observation times.

BPR lifecycle is direction-neutral:
- OPEN: no later candle overlaps the BPR
- MITIGATED: later candle overlaps part of BPR
- TRAVERSED: one later candle range spans the entire BPR zone

## Point-in-time rule
All lifecycle/BPR evaluation is bounded by the requested as-of time and local ingest availability.
No later candle may retroactively exist at an earlier as-of.

## Scope
This slice is raw deterministic imbalance geometry.
Displacement quality, reclaim/rejection, liquidity sweeps and setup scoring are separate PA slices.

REAL_CAPITAL remains 0.
