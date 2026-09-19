# ENVIRONMENT REGISTRY

Updated: 2026-09-19

## Identity
- macOS account: `crypto-signal-agent`
- observed UID: `504`
- admin: no
- home: `/Users/crypto-signal-agent`
- project root: `/Users/crypto-signal-agent/Crypto-Signal`
- project root mode: `0700`

## Isolated toolchain
- Git: Apple Git 2.50.1
- uv: 0.12.17 at `~/.local/bin/uv`
- Python pin: `3.12`; managed CPython currently 3.12.14
- project venv: `.venv`
- fnm: 1.39.0 at `~/.local/share/fnm/fnm`
- Node pin: `24.18.0`; npm 11.16.0
- system Python/Node are not the project runtime contract

## Reserved identities
- launchd prefix: `com.cryptosignal`
- DB namespace/name: `crypto_signal`
- Redis namespace: `crypto_signal:` if Redis is introduced
- credentials must live outside Git and other project homes

## Port block
Mechanically free at bootstrap: `48700-48709`.
Reserved for Crypto Signal by convention; individual service assignments will be recorded before first launch.
