# ADR 0010 — Equal Liquidity Pools and Sweep/SFP Evidence

Status: Accepted for PA Slice 3 implementation
Date: 2026-09-20

## Source geometry
EQH/EQL uses confirmed alternating swing pivots from the shared PIT-safe primitive layer.

For each pair of chronologically adjacent pivots of the same kind:
- HIGH pair may form an Equal High (EQH) pool.
- LOW pair may form an Equal Low (EQL) pool.

A pair is equal-liquidity-compatible when the absolute price difference divided by pair midpoint
is less than or equal to the configured tolerance in basis points.

V1 default tolerance: 5 bps.
The tolerance is an explicit analysis parameter and is stored on every result; it is not presented as universal truth.

## Pool formation
A pool contains exactly two anchor pivots in V1.
This deliberately avoids retroactively merging a later third touch into an older pool.

Pool formation time:
- market time = second anchor pivot market-confirmation time
- observation time = second anchor pivot local observation time

No candle before pool formation may consume the pool.

## Pool zone
- lower = min(anchor prices)
- upper = max(anchor prices)
- representative level = pair midpoint

Exact equal prices are valid and produce a zero-width anchor zone.

## Sweep / SFP
EQH:
- liquidity is taken when a later candle high is strictly above pool upper bound.
- if candle close <= upper bound: SFP_REJECTION, expected reaction direction bearish.
- if candle close > upper bound: CLOSE_THROUGH / structural consumption, not SFP.

EQL:
- liquidity is taken when a later candle low is strictly below pool lower bound.
- if candle close >= lower bound: SFP_REJECTION, expected reaction direction bullish.
- if candle close < lower bound: CLOSE_THROUGH / structural consumption, not SFP.

Wick equality to the boundary alone is not a sweep.

## Lifecycle
AVAILABLE -> SWEPT_SFP or BROKEN_CLOSE.
The first qualifying post-formation event consumes the V1 pool.
Event market time is candle close time; local observation time is candle ingest time.

## Scope
This is deterministic liquidity evidence only.
It does not turn a sweep into a trade signal and does not use Harmonic/Elliott logic.

REAL_CAPITAL remains 0.
