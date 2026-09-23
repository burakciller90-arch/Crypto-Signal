# M4 Derivatives Intelligence 2.0 — Slice 1: Temporal Dynamics

Status: development slice  
REAL_CAPITAL: 0  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`

## Scope

This slice preserves the accepted `derivatives_context.py` engine and adds a separate
v1.1 temporal evidence layer.

It measures only point-in-time observed derivatives history:

- OI x mark-price state;
- funding percentile inside the consumed observation window;
- one-step funding acceleration;
- current mark/index basis;
- basis change over the consumed window.

## OI x price states

Supported context states include:

- price up / OI up;
- price up / OI down;
- price down / OI up;
- price down / OI down;
- price flat / OI expanding;
- price flat / OI contracting;
- flat/stable combinations;
- unavailable.

These are context states, not trade commands.

OI x price is calculated only when at least two PIT observations contain both open
interest and mark/index price. Missing temporal history is not fabricated.

## Funding

Funding percentile is the rank of the latest observed funding value inside the exact
consumed PIT window. It is not a universal historical percentile and not a forecast.

Funding acceleration is the latest observed funding change in basis points.

## Basis

This slice measures mark/index basis and its change over the consumed window.

Cross-venue basis, predicted funding and venue divergence are not claimed here; they
require separately accepted evidence.

## PIT / fail-closed rules

Evidence must have event, source and ingestion timestamps <= as-of, one exact
exchange/instrument/symbol context and unique observation identities.

Stale or insufficient evidence resolves to UNRESOLVED / UNAVAILABLE rather than an
invented value. Future or late-ingested evidence cannot rewrite a historical freeze.

## Authority boundary

This slice does not alter production confluence, probability, paper capital or order
authority. REAL_CAPITAL remains 0.
