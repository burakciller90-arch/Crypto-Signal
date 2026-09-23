# v1.1 Latest-Main Release Acceptance Plan

REAL_CAPITAL=0 throughout.

## Hosted candidate evidence

The latest-main cutover candidate must prove on its exact head:

- `/` and `/galactech` serve the same accepted GALACTECH;
- `/legacy` preserves the previous accepted UI;
- R25 Decision Evidence, Shadow Journal, Cycle Manifest, Runtime Replay Observation,
  Operational Truth and canonical Epoch 2 regressions pass;
- Slice 16 Market Tape / Cold Archive Product Truth regressions pass;
- Event Source Runtime is not promoted without an exact adapter;
- complete pytest / Ruff / mypy / JavaScript / freshness regression passes.

The integrated hosted release-candidate workflow separately rechecks deterministic
forecast/capital evidence, R25 runtime contracts, Hot/Cold Market Tape storage and the
frontend cutover.

Hosted PASS does not establish live runtime health or deployment.

## UID504 live acceptance

A manual-only workflow is carried in the candidate for use **after** explicit production
cutover authority, merge to main and intended deployment.

It is not dispatched during candidate preparation.

Live acceptance is expected to verify:
- UID504 and exact-main identity;
- deployed Product source hash parity;
- SSD runtime topology and critical SQLite checks;
- live root GALACTECH + `/legacy` rollback;
- read-only / REAL_CAPITAL=0 authority truth;
- current R25 replay/operational Product endpoints;
- Market Tape / Cold Archive Product Truth when runtime paths are configured;
- runtime freshness/endurance;
- continuity remains paused.

## Release decision

v1.1.0 is not a release merely because hosted CI is green. Release requires separate
production authority, exact candidate merge/deploy and successful exact-main UID504 live
acceptance. No real-money authority is introduced.
