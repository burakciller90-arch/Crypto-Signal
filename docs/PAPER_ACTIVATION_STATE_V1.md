# PAPER ACTIVATION STATE V1

Status: candidate persistent activation/idempotency foundation. It does not enable PAPER/STABLE trading.

Schema version: `paper_activation_state.v1`.

## Same-database rule

Activation watermark and processed-event receipts live in the **same SQLite file** as the paper fund ledger. They are immutable insert-only tables. This is deliberate: later a committed trade and its processed-event receipt can share one SQLite transaction, eliminating a crash gap between "fund mutated" and "event marked processed".

## Activation singleton

The activation row is created once and cannot be updated, deleted or silently rebased.

V1 binds:
- fund identity;
- activation timestamp;
- activation cutoff, exactly equal to activation timestamp;
- signal-ledger freeze count observed at activation;
- latest signal freeze identity/frozen timestamp observed at activation.

Any event with signal as-of before the cutoff is permanently ineligible for processing. This is the persistent counterpart of the autonomy policy's no-historical-backfill rule.

## Processed-event identity

A terminal event identity binds:
- activation identity;
- the exact pair of source signal freeze identities;
- paper symbol;
- 4h decision timeframe;
- signal as-of timestamp.

Changing the terminal reason/outcome while keeping the same event identity is an immutable conflict.

V1 supports terminal outcome classes:
- `terminal_no_action`;
- `committed_trade` (reserved for the next atomic trade+receipt slice).

The current slice persists only terminal no-action receipts. Recording a receipt requires the supplied paper replay state to still be current; a stale state cannot advance the processed-event set.

## Remaining next gate

Wire `committed_trade` receipt persistence into the already-accepted trade bundle transaction so decision/fill/mutation + processed receipt are all-or-nothing.

PAPER/STABLE remains observation-only and REAL_CAPITAL remains 0.
