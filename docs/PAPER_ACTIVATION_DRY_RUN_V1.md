# PAPER ACTIVATION DRY RUN V1

Status: candidate composition gate. It does not enable PAPER/STABLE trading.

Version: `paper_activation_dry_run.v1`.

For one unprocessed `paper_signal_event_scanner.v1` candidate, V1 composes the accepted layers in this order:

1. reconstruct paper fund state and per-symbol last trade-decision timestamps from the paper SQLite file using `mode=ro + query_only`;
2. derive current marks for held positions from finalized Binance 15m candles using the canonical candle cache read-only;
3. evaluate `paper_autonomy_policy.v1`;
4. if BUY/EXIT candidate, freeze `paper_execution_input_policy.v1` from the first fully closed Binance 15m candle strictly after signal as-of;
5. read the latest cached authoritative Binance venue-rule snapshot observed no later than the execution-input observation;
6. run `paper_position_sizing_policy.v1`;
7. run the authoritative venue-bound pretrade bridge.

Possible terminal dry-run statuses:
- HOLD_CASH;
- WAITING_EXECUTION_INPUT;
- WAITING_VENUE_RULES;
- SIZING_REJECTED;
- PRETRADE_REJECTED;
- PRETRADE_READY.

PRETRADE_READY means only that the accepted deterministic planning gates would permit a simulated trade from the supplied immutable state. V1 never:
- writes a processed-event receipt;
- commits a DecisionIntent/fill/mutation bundle;
- refreshes venue rules;
- creates or updates activation state;
- contacts a trading/account endpoint;
- changes PAPER/STABLE trade authority.

Already processed event identities are rejected rather than re-dry-run.

The paper DB and candle cache are opened query-only for all reads performed by this module. REAL_CAPITAL remains 0.
