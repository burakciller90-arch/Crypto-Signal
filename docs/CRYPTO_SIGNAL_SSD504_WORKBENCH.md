# Crypto Signal — SSD-504 Development Workbench

## Canonical physical work root

`/Volumes/Crypto-504/Crypto-Signal-Workbench`

From this point forward, new Crypto Signal development work should use this workbench as the stable UID504 development root. The currently running Product/runtime is **not moved** by this setup.

## Why this exists

The project now has three major development workstreams that must stay easy to understand for fresh agents without mixing runtime data or stale roadmaps:

1. Evidence Depth / five-family proof
2. Paper Capital / Portfolio
3. Product UI / Command Center

The workbench separates those workstreams while keeping one canonical repository and one shared set of contracts.

## Directory layout

```text
/Volumes/Crypto-504/Crypto-Signal-Workbench/
├── WORKSPACE_READ_FIRST.md
├── repo/                       # stable Crypto-Signal Git working copy
├── 00_INBOX/                   # user-supplied roadmap/spec inputs before triage
├── 00_CONTEXT/                 # symlinks to canonical repo context
├── 01_EVIDENCE_DEPTH/          # evidence/proof workstream notes and handoffs; ACTIVE_ROADMAP.md
├── 02_PAPER_CAPITAL/           # portfolio/capital workstream notes and handoffs
├── 03_PRODUCT_UI/              # frontend/Command Center workstream notes and handoffs
├── 04_SHARED_CONTRACTS/        # cross-workstream API/data contracts
├── 05_ACCEPTANCE/              # acceptance packets, audit notes, browser evidence pointers
└── 99_ARCHIVE/                 # superseded local planning artifacts only
```

## Authority rules

- GitHub repository `burakciller90-arch/Crypto-Signal` remains the canonical source history.
- Code changes happen in `repo/` on a feature branch and return through PR/merge.
- `00_CONTEXT` links to canonical files inside `repo/`; do not fork authority by copying and editing those files locally.
- The live Product/runtime path, databases, services and data volumes are not relocated into this workbench.
- Do not copy secrets, credentials, runtime DBs or exchange credentials into the workbench.
- Durdurulmaz and Quantum Capital remain isolated and untouched.
- `REAL_CAPITAL=0` remains binding.

## Mandatory first read for any new agent

1. `WORKSPACE_READ_FIRST.md`
2. `00_CONTEXT/READ_FIRST_CRYPTO_SIGNAL.md`
3. `00_CONTEXT/CURRENT_STATUS.md`
4. `00_CONTEXT/PROJECT_CHRONICLE.md`
5. the active workstream's own canonical spec / user-supplied roadmap

## Workstream boundaries

### 01_EVIDENCE_DEPTH
Owns exact frozen family payloads, visual proof, five-family evidence UX contracts and source-completeness work.

Current active execution authority is exposed inside the physical workbench as:

`01_EVIDENCE_DEPTH/ACTIVE_ROADMAP.md`

It points to `docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md`. Current frontier: **RDP1 — Collector and runtime reliability**.

### 02_PAPER_CAPITAL
Owns paper-only capital allocation, execution simulation, immutable trade lifecycle, portfolio accounting and archive. No real-money authority.

### 03_PRODUCT_UI
Owns Command Center / progressive-disclosure product UX, market pulse, portfolio surface, signal workspace, evidence presentation, markets/events/history surfaces.

### 04_SHARED_CONTRACTS
Only cross-cutting contracts that two or more workstreams depend on belong here. It must not become a fourth implementation project.

## Runtime safety

This workbench is a **development workspace**, not a replacement runtime root. Do not move or delete currently deployed Product files just to make the directory structure look cleaner.

## Bootstrap behavior

The UID504 bootstrap workflow:
- verifies UID504 and `/Volumes/Crypto-504`;
- creates the directory tree;
- seeds `repo/` from the exact accepted GitHub commit only if the stable repo does not already exist;
- refuses to overwrite an existing working copy;
- installs context symlinks and workstream README files;
- emits a machine-readable report and uploads it as a GitHub Actions artifact.

