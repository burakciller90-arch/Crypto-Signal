# PAPER DRY-RUN CANDIDATE VISIBILITY V1

This hardening keeps the PAPER/STABLE dry-run observation path read-only while
making a future executable-looking virtual candidate mechanically obvious.

The pure dry-run layer now exposes a deterministic observation summary:
- total evaluated events;
- sorted status counts;
- sorted PRETRADE_READY event identities;
- attention_required, which is true if and only if at least one PRETRADE_READY
  event is present.

The stable one-shot runner adds:
- ready_candidates=<count>;
- attention_required=YES|NO;
- one PAPER_DRY_RUN_ATTENTION line per PRETRADE_READY event.

PAPER_DRY_RUN_ATTENTION is evidence only. It does not authorize or perform a
paper trade. Every attention line still prints trade_policy=NOT_ACTIVATED and
REAL_CAPITAL=0.

PAPER STATE exposes the latest dry-run summary and the latest five attention
lines directly. No paper DB table, activation row, processed-event receipt,
trade record, venue rule or signal ledger row is written by this feature.
