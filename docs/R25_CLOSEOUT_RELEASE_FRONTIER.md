# R25 Closeout and Latest-Main Release Frontier

## Accepted development rail

The current R25 development rail is accepted through component-wise Operational Runtime Truth.

The product can preserve and expose exact immutable lineage across:
1. intelligence evidence and Event Risk;
2. Unified Decision Runtime;
3. R20 Forecast and R20.5 Decision Proof;
4. Capital Science;
5. source-bound Position Sizing;
6. explicit review;
7. non-mutating R22 preview;
8. isolated Shadow Intent Journal;
9. deterministic restart/replay;
10. immutable Shadow Cycle Manifest;
11. restart-safe persisted cycle;
12. exact forecast-to-capital-cycle Product linkage;
13. persisted Runtime Replay Observation;
14. GALACTECH replay truth;
15. component-wise Operational Truth.

This acceptance does not establish profitability, positive expectancy, calibrated probability, production deployment or real-money authority.

## Superseded cutover

PR #932 is closed and must not be used. It predates the R25 rail and was mechanically observed 20 commits behind current R25 main.

## Current development frontier

Create a new root-cutover candidate from the latest accepted main:
- `/` -> current GALACTECH;
- `/galactech` -> same current GALACTECH;
- `/legacy` -> previous accepted UI for rollback/audit;
- all Product APIs stay read-only;
- REAL_CAPITAL=0.

The candidate must pass:
- focused routing/static acceptance;
- R25 decision/capital/replay Product truth acceptance;
- full repository pytest/Ruff/mypy/JS regression;
- integrated release-candidate checks.

## Authority boundary

Candidate creation, hosted testing and PR preparation are development work.

Merging/deploying the production-root cutover, dispatching UID504 live release acceptance, changing wake/lease state, enabling exchange credentials/orders or changing REAL_CAPITAL require separate explicit authority.