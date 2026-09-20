# PAPER DEPLOY DRY-RUN PROBE HARDENING

The stable deploy and dedicated dry-run-clock deploy no longer assume that a
fresh one-shot launchd process must finish within an arbitrary 2-3 second sleep.

Before service bootstrap, both workflows execute the exact deployed
`run_paper_activation_dry_run.py` manually and require:
- PAPER_DRY_RUN_OK;
- paper_db_unchanged=YES;
- ready_candidates=...;
- attention_required=...;
- trade_policy=NOT_ACTIVATED;
- REAL_CAPITAL=0.

Only after that deterministic probe passes is the launchd service bootstrapped.
Immediate service validation checks launchd registration/state rather than
racing the service's stdout completion.

The plist rollback backup paths also use the shell PID (`$$`) instead of a
literal trailing dollar sign, preventing accidental backup-name collisions.

No paper trading authority is added.
