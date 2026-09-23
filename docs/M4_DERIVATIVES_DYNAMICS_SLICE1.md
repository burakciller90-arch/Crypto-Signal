# M4 Derivatives Intelligence 2.0 — Slice 1: Temporal Dynamics

Status: development slice after M3 completion
REAL_CAPITAL: 0
Parent roadmap: docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md

This slice reuses the accepted bounded derivatives context and adds the missing
temporal M4 evidence.

It adds:
- OI x same-exchange spot-price states: price-up/OI-up, price-up/OI-down,
  price-down/OI-up, price-down/OI-down, price-flat/OI-expanding, other;
- current funding plus empirical percentile and change from the previous observed
  funding value when sufficient PIT history exists;
- mark-vs-index basis plus perpetual-mark-vs-spot basis when a bounded closed
  spot reference exists.

The current derivatives source model does not collect a predicted/next funding
rate. Predicted funding therefore remains explicitly unavailable and is never
fabricated. Cross-venue basis is deferred to a later M4 slice.

Scientific boundaries:
- spot price is explicitly a proxy in OI x Price state;
- funding percentile is relative only to the frozen observed sample;
- these states are context, not universal directional rules;
- no probability or trading authority is emitted;
- only PIT-safe derivative observations and closed candles may enter a freeze;
- REAL_CAPITAL=0.
