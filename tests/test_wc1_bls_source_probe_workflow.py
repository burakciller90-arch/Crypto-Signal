from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _bls_probe_block() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: BLS SOURCE PROBE")
    end = text.index("      - name: FRED CALENDAR PROBE", start)
    return text[start:end]


def test_bls_probe_is_explicitly_allowlisted() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "blsprobe" in text
    block = _bls_probe_block()
    assert "steps.parse.outputs.command == 'blsprobe'" in block


def test_bls_probe_is_read_only_and_bounded_to_official_urls() -> None:
    block = _bls_probe_block()

    assert "https://www.bls.gov/schedule/news_release/bls.ics" in block
    assert "https://www.bls.gov/schedule/2026/" in block
    assert "USER_AGENT" in block
    assert "status={response.status_code}" in block
    assert "bytes={len(payload)}" in block
    assert "sha256={hashlib.sha256(payload).hexdigest()}" in block
    assert "BLS_PROBE_READONLY_PASS=YES" in block
    assert 'print("REAL_CAPITAL=0")' in block


def test_bls_probe_has_no_mutation_or_secret_surface() -> None:
    block = _bls_probe_block()
    forbidden = (
        "event_source.sqlite3",
        "run_event_source_snapshot.py",
        "sqlite3",
        "open(",
        "write",
        "mkdir",
        "unlink",
        "touch ",
        "rm -",
        "cp ",
        "mv ",
        "git ",
        "launchctl",
        "kill ",
        "productdeploy",
        "api_key",
        "secret",
        "credential",
        "place_order",
        "leverage",
        "martingale",
    )

    for token in forbidden:
        assert token not in block
