# R25 Slice 8 — Reviewed R22 Intent Preview

Status: development candidate. REAL_CAPITAL=0.

This slice connects the accepted Position Sizing bridge to the existing R22 immutable transaction contract **without writing any ledger**.

## Exact review boundary

A BUY preview can be created only when all of the following are true:
- the exact vault is `ASSESSED_SHADOW`;
- one exact `AVAILABLE_SHADOW` sizing result is explicitly selected;
- the selection is frozen as a review artefact;
- the immutable forecast is ACTIVE and BULLISH;
- a permitted paper symbol matches the forecast;
- reference price comes from an immutable source-bound market-reference artefact;
- the market reference is observed between forecast issuance and preview time;
- explicit paper quantity is positive and its notional does not exceed the reviewed shadow sizing envelope.

The bridge does **not** rank sizing methods, choose a winner, invent a price, infer quantity, or upgrade disabled Kelly output.

## HOLD_CASH behavior

If no explicit reviewed sizing selection exists, the preview deterministically produces R22 HOLD_CASH with no forecast/proof/sizing/decision trade lineage attached to the R22 intent. This preserves the accepted R22 rule that HOLD_CASH must not fabricate trade evidence.

## Invalidation lineage

The paper DecisionIntent invalidation context is derived from the immutable R20 forecast invalidation trigger + price. The decision reason binds the exact reviewed selection identity and source-bound market-reference identity.

## Non-mutation guarantee

The result is an in-memory `R22IntentPreview`. This module never calls:
- `R22DevelopmentTape.append_intent`;
- `R22Epoch2AtomicTape`;
- any Epoch 2 accounting writer;
- any exchange/network/credential API.

The preview explicitly carries:
- `tape_write_authority=false`;
- `canonical_epoch2_write_authority=false`;
- `production_authority=false`;
- `REAL_CAPITAL=0`.

## Next frontier

After exact-head and whole-repository acceptance, build a crash-safe **shadow intent journal** separate from canonical Epoch 2. It may persist only these reviewed preview artefacts and must remain isolated from R21/R22 canonical mutation until a separate human-authorized activation gate.