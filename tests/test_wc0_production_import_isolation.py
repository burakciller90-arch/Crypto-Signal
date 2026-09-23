from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_production_product_imports_with_src_only_pythonpath(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import crypto_signal.forecast_stream as forecast; "
                "import crypto_signal.product.web as web; "
                "assert forecast.R20_PROBABILITY_CALIBRATED == 'calibrated'; "
                "print(web.PRODUCT_VERSION)"
            ),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "full-version-contextual-evidence/1" in result.stdout


def test_production_dashboard_help_works_without_repo_root_on_pythonpath(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")

    result = subprocess.run(
        [sys.executable, str(repo / "ops" / "run_dashboard.py"), "--help"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--runtime-replay-observation" in result.stdout
    assert "--market-tape" in result.stdout
    assert "--market-tape-collector-runtime" in result.stdout
    assert "--cold-archive" in result.stdout
