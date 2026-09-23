# v1.1 Release Acceptance Plan

This plan separates evidence that can be proven in hosted CI from evidence that requires
the authorized UID504 production runtime. REAL_CAPITAL=0 throughout.

## Hosted release candidate

`.github/workflows/crypto-v1_1-release-candidate-hosted.yml` proves on the exact candidate
tree:

- deterministic forecast and Decision Proof regressions;
- outcome/archive replay;
- Epoch 2 accounting and read-only projection;
- transaction-tape replay + atomicity;
- probability calibration boundary;
- Market Tape Hot/Cold storage contracts;
- runtime recovery/verifier contracts;
- GALACTECH production-root cutover contract;
- accessibility/reduced-motion/product regressions;
- whole-repository pytest/Ruff/mypy/JS/freshness gate.

It does not claim live runtime health.

## UID504 live release acceptance

`.github/workflows/crypto-v1_1-live-release-acceptance.yml` is manual-only and must be run
on exact merged `main` only after the production cutover is intentionally deployed.

It is read-only acceptance. It checks:

- UID504 owner and exact main identity;
- deployed product-source hash parity;
- SSD runtime topology / critical SQLite audit through the accepted R11 verifier;
- live root is GALACTECH and `/legacy` remains rollback evidence;
- API read-only / REAL_CAPITAL truth;
- runtime freshness/endurance;
- deterministic replay / transaction tape / probability / frontend acceptance;
- continuity remains paused with no active leases or wake backlog.

The workflow itself does not merge, deploy, restart, reboot/logout, detach SSD, enable
credentials/orders, or enable real money.

## Release decision

A hosted PASS is necessary but not sufficient. v1.1.0 is releasable only after:

1. production cutover authority is explicitly satisfied;
2. exact candidate is merged to main;
3. intended deployment/restart is performed under production authority;
4. UID504 live release acceptance passes on the exact deployed main;
5. final source/runtime identity is recorded in Status/Chronicle;
6. REAL_CAPITAL remains 0.
