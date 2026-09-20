# PAPER/STABLE READ-ONLY ACTIVATION DRY RUN

Command:
- issue title: `[PAPER] DRYRUN`
- body: `command: dryrun`

This stable operation requires the already-persisted immutable activation
watermark. It does not create or modify activation state.

The command:
1. fingerprints all paper-state, replay, activation, processed-event and cached
   venue-rule rows from SQLite `mode=ro/query_only`;
2. loads the activation singleton read-only;
3. scans only unprocessed post-cutoff 4h Binance+Bybit provider pairs;
4. evaluates each bounded candidate through the accepted autonomy -> execution
   input -> cached authoritative venue rules -> sizing -> pretrade dry-run
   composition;
5. fingerprints the paper DB again and fails unless the two fingerprints match.

The command reports one of the accepted dry-run statuses for each candidate:
`hold_cash`, `waiting_execution_input`, `waiting_venue_rules`,
`sizing_rejected`, `pretrade_rejected`, or `pretrade_ready`.

`pretrade_ready` is observation/planning evidence only. The operation cannot
write a processed-event receipt, DecisionIntent, simulated fill, cash/position
mutation, NAV record, activation row or venue-rule snapshot.

The command is bounded to at most 100 unprocessed candidates per invocation and
fails closed if that limit would be exceeded.

Required final markers:
- `paper_db_unchanged=YES`;
- `trade_policy=NOT_ACTIVATED`;
- `REAL_CAPITAL=0`.
