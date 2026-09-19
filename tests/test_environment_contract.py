from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_runtime_pins() -> None:
    assert (ROOT / ".python-version").read_text().strip() == "3.12"
    assert (ROOT / ".node-version").read_text().strip() == "24.18.0"

def test_governing_memory_exists() -> None:
    required = [
        "READ_FIRST_CRYPTO_SIGNAL.md",
        "CURRENT_STATUS.md",
        "PROJECT_CHRONICLE.md",
        "PROJECT_CONSTITUTION.md",
        "ROADMAP_V1.md",
        "ENVIRONMENT_REGISTRY.md",
    ]
    assert all((ROOT / name).is_file() for name in required)

def test_real_capital_is_zero() -> None:
    status = (ROOT / "CURRENT_STATUS.md").read_text()
    assert "REAL_CAPITAL: 0" in status
