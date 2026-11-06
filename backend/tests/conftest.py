import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

load_dotenv(ROOT / ".env")


def run_script(name: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"{name} failed with exit {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


@pytest.fixture
def script_runner() -> Any:
    return run_script


@pytest.fixture(scope="session")
def integration_env() -> Path:
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    return ROOT


@pytest.fixture(scope="session")
def seeded_postgres(integration_env: Path) -> None:
    run_script("seed_postgres.py")


@pytest.fixture(scope="session")
def seeded_mongodb(integration_env: Path) -> None:
    run_script("seed_mongodb.py")
