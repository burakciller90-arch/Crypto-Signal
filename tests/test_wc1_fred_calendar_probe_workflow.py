from pathlib import Path

WORKFLOW = Path(".github/workflows/crypto-mac-command.yml")


def _fred_probe_block() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("      - name: FRED CALENDAR PROBE")
    end = text.index("      - name: NETWORK DIAG", start)
    return text[start:end]


def test_fred_probe_is_explicitly_allowlisted() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "fredprobe" in text
    block = _fred_probe_block()
    assert "steps.parse.outputs.command == 'fredprobe'" in block


def test_fred_probe_is_read_only_and_release_scoped() -> None:
    block = _fred_probe_block()

    assert "fred.stlouisfed.org/releases/calendar?rid=10" in block
    assert "fred.stlouisfed.org/releases/calendar?rid=50" in block
    assert "Consumer Price Index" in block
    assert "Employment Situation" in block
    assert "contains_expected_title=" in block
    assert "FRED_PROBE_READONLY_PASS=YES" in block
    assert 'print("REAL_CAPITAL=0")' in block


def test_fred_probe_has_no_mutation_or_secret_surface() -> None:
    block = _fred_probe_block()
    forbidden = (
        "event_source.sqlite3",
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
