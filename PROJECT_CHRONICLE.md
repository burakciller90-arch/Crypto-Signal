# PROJECT CHRONICLE

## 2026-09-19 — Phase 0 bootstrap begins

The Crypto Signal master handoff was accepted as governing project context.
V1/V2+ scope firewall was confirmed before implementation.

A dedicated macOS Standard account named `crypto-signal-agent` was created.
Mechanical verification observed UID `504`; admin-group membership is false.
Home is `/Users/crypto-signal-agent`.

A dedicated repository was initialized at:
`/Users/crypto-signal-agent/Crypto-Signal`

The repository uses branch `main`.
The project root was tightened to mode `0700`.
No cross-project symlinks were found in the new home.

System observations at bootstrap:
- Apple Git 2.50.1
- system Python 3.9.6
- Node 24.18.0
- npm 11.16.0
- no Homebrew, uv, pyenv, PostgreSQL, Redis, Docker or Colima detected
- system SQLite is available

No product code has been written yet.

## 2026-09-19 — Isolated runtime baseline ready

User-local `uv 0.12.17` was installed without modifying the shared system Python.
Managed CPython 3.12.14 and repository-local `.venv` were created; `.python-version` pins 3.12.

User-local `fnm 1.39.0` was installed without Homebrew or shared Node mutation.
Node 24.18.0 was installed for this user and pinned by `.node-version`.

Ports 48700-48709 were mechanically bind-tested as free and reserved by project convention.
The isolated runtime baseline is now ready; no product code exists yet.
