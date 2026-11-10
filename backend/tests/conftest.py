import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Must be set before app.core.config.get_settings is first evaluated.
os.environ.setdefault("AUTH_RATE_LIMIT_ENABLED", "false")

import pytest
import pytest_asyncio
from app.main import create_app
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

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


@pytest.fixture(scope="session")
def ingested_qdrant(integration_env: Path) -> None:
    if not os.getenv("QDRANT_URL"):
        pytest.skip("QDRANT_URL is not set")
    run_script("ingest_documents.py")


@pytest.fixture
def application():
    return create_app()


@pytest_asyncio.fixture
async def api_client(application):
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def live_client():
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")

    application = create_app()
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
