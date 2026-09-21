from __future__ import annotations

import inspect
from pathlib import Path

from fastapi.testclient import TestClient

from crypto_signal.paper.models import REAL_CAPITAL
from crypto_signal.product import web as product_web
from crypto_signal.product.web import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_stage10_product_api_exposes_get_only_read_surfaces(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200

    api_paths = {
        path: set(operations)
        for path, operations in spec.json()["paths"].items()
        if path.startswith("/api/")
    }
    assert api_paths
    assert all(methods == {"get"} for methods in api_paths.values())

    forbidden_path_terms = (
        "order",
        "broker",
        "credential",
        "api-key",
        "api_key",
        "secret",
        "execute",
        "write-authority",
    )
    assert all(
        token not in path.lower()
        for path in api_paths
        for token in forbidden_path_terms
    )

    source = inspect.getsource(product_web).lower()
    assert "@app.post" not in source
    assert "@app.put" not in source
    assert "@app.patch" not in source
    assert "@app.delete" not in source
    assert "place_order" not in source
    assert "submit_order" not in source
    assert "cancel_order" not in source
    assert "api_key" not in source
    assert "api_secret" not in source
    assert REAL_CAPITAL == 0


def test_stage10_paper_stable_surface_keeps_writer_commands_unexposed() -> None:
    workflow = (ROOT / ".github/workflows/crypto-paper-stable.yml").read_text()
    parse_block = workflow.split("- name: PAPER STATE", maxsplit=1)[0].lower()

    for allowed in (
        "state",
        "deploy",
        "rulesrefresh",
        "activationinit",
        "dryrun",
        "dryrunclockdeploy",
        "portfolio",
        "performance",
        "missioncontrol",
    ):
        assert allowed in parse_block

    assert "writeauthority" not in parse_block
    assert "writetick" not in parse_block
    assert "run_paper_write_tick" not in parse_block


def test_stage10_research_lab_is_not_in_production_product_surface() -> None:
    research_root = ROOT / "src/crypto_signal/research"
    assert not research_root.exists()

    production_paths = (
        ROOT / "src/crypto_signal/product",
        ROOT / "src/crypto_signal/paper/mission_control.py",
        ROOT / "src/crypto_signal/paper/portfolio.py",
        ROOT / "src/crypto_signal/paper/performance.py",
        ROOT / "src/crypto_signal/paper/benchmarks.py",
    )
    for path in production_paths:
        if path.is_dir():
            files = tuple(path.rglob("*.py")) + tuple(path.rglob("*.js"))
        else:
            files = (path,)
        for file in files:
            source = file.read_text().lower()
            assert "crypto_signal.research" not in source


def test_stage10_beginner_truth_and_freshness_contract_are_wired() -> None:
    index = (ROOT / "src/crypto_signal/product/static/index.html").read_text()
    script = (ROOT / "src/crypto_signal/product/static/app.js").read_text()
    freshness = (
        ROOT / "src/crypto_signal/product/static/freshness.js"
    ).read_text()

    assert index.index('/static/freshness.js') < index.index('/static/app.js')
    assert "const AUTO_REFRESH_MS = 15_000" in script
    assert "const STALE_AFTER_MS = 45_000" in script
    assert "CryptoSignalFreshness.classifyRefreshFreshness" in script
    assert "classifyRefreshFreshness" in freshness
    assert "SİMÜLASYON · GERÇEK SERMAYE YOK" in index
    assert "Metodoloji uyumu ≠ olasılık" in index
    assert "SİSTEM SAĞLIĞI" in index
    assert "Paper Performans Laboratuvarı" in index
    assert "Bu %0 başarı oranı değildir." in script
    assert "Gerçek emir, credential veya gerçek sermaye yetkisi yoktur." in script
    assert "frictionless referanslardır" in script
