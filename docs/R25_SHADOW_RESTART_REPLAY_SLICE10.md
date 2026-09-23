# R25 Slice 10 — Deterministic Shadow Restart / Replay

Status: development candidate. REAL_CAPITAL=0.

This slice composes the accepted shadow path into one deterministic orchestration:

immutable R20/R20.5 issuance
→ Capital Science
→ source-bound Position Sizing
→ explicit sizing-method review
→ R22 intent preview
→ isolated shadow intent journal.

## Restart contract

The orchestrator receives immutable evidence objects and explicit timestamps/inputs. It does not fetch live providers and does not invent missing risk, price, quantity or review state.

Re-running the same cycle after process restart must reproduce the same:
- Capital Science bridge identity;
- Position Sizing bridge identity;
- reviewed selection identity;
- R22 preview identity;
- shadow journal record identity;
- overall cycle identity.

The first append is `INSERTED`; exact replay is `IDEMPOTENT` and leaves journal count unchanged.

## Explicit review

The caller may provide a `reviewed_method`; the orchestrator never ranks methods.

A method can be reviewed only if the exact vault is `ASSESSED_SHADOW` and that method's exact result is `AVAILABLE_SHADOW`.

If no reviewed method is provided, the cycle produces the accepted HOLD_CASH preview path.

## Failure behavior

- unavailable Kelly cannot be upgraded by review;
- missing risk evidence cannot be bypassed;
- restart backfill/fork is rejected by the journal;
- a failed backfill leaves the existing journal record intact;
- all canonical sizing-selection fields remain null/false.

## Authority

The orchestration has no:
- canonical Epoch 2 writer;
- R22 fill writer;
- exchange/network/credential access;
- order authority;
- leverage/borrowing;
- production deployment authority.

REAL_CAPITAL=0 throughout.

## Next frontier

After hosted focused + whole-repository acceptance, expose this accepted shadow replay lineage read-only through Product API/GALACTECH so the UI can show whether a decision is:
- evidence-complete or missing;
- capital-eligible or HOLD_CASH;
- sized or unsized;
- explicitly reviewed or not reviewed;
- previewed and journaled;
- replay-verified.

The UI must not imply canonical paper mutation until a separate production activation gate exists.