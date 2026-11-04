"""Shared fixtures for the Geno CGT document-workflow test suite.

Why host-run?

The API/worker containers ship without pytest, and the frontend talks to the
backend through the rsbuild proxy on port 3000. Running from the host exercises
exactly the same HTTP surface the UI uses, with no extra image rebuild.

Every test needs a live docker-compose stack:

    docker compose up -d
    docker compose watch          # only if you also want worker file sync

Run the suite:

    python -m pytest tests/workflow -v                # fast, no LLM calls
    python -m pytest tests/workflow -v --run-slow     # includes E2E pipeline
    python -m pytest tests/workflow -v --run-slow -m slow

Useful overrides:

    --base-url http://localhost:3000
    --project-id <uuid>

The suite is intentionally read-mostly. The E2E test creates its own project
and uploads its own document, then deletes both, so it does not touch the
project you are manually testing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

import httpx
import pytest

DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_USER_ID = "9385195a-f6ee-4d0c-a3fc-16bf1468997a"
DEFAULT_PROJECT_ID = "5ab006b2-62fe-4e10-b45a-8f6fdb8c216f"
POSTGRES_USER = "app_user"
POSTGRES_DB = "gt-db"


# ── Options / markers ──────────────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="run tests that dispatch Celery/LLM work (marked slow)",
    )
    parser.addoption(
        "--base-url",
        default=os.environ.get("GENO_BASE_URL", DEFAULT_BASE_URL),
        help="API root (rsbuild proxy by default)",
    )
    parser.addoption(
        "--project-id",
        default=os.environ.get("GENO_PROJECT_ID", DEFAULT_PROJECT_ID),
        help="project used by read-only contract tests",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: dispatches Celery/LLM work")
    config.addinivalue_line("markers", "e2e: exercises a full estado transition")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="pass --run-slow to run this test")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


# ── Docker helpers ─────────────────────────────────────────────────────


def docker_compose_exec(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    """Run `docker compose exec -T ...` from the repo root."""
    return subprocess.run(
        ["docker", "compose", "exec", "-T", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=os.getcwd(),
    )


@pytest.fixture(scope="session")
def docker() -> bool:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is not on PATH")
    proc = subprocess.run(
        ["docker", "compose", "ps", "-q", "fastapi"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip("the fastapi container is not running (docker compose up -d)")
    return True


# ── Auth ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def user_id() -> str:
    return os.environ.get("GENO_USER_ID", DEFAULT_USER_ID)


@pytest.fixture(scope="session")
def token(docker: bool, user_id: str) -> str:
    """Mint a JWT with the same helper the API uses.

    The token is intentionally long-lived: tests only need to prove auth wiring,
    they are not testing token expiry.
    """
    code = (
        "from app.core.security import create_access_token;"
        f"print(create_access_token({{'sub': '{user_id}'}}))"
    )
    proc = docker_compose_exec("fastapi", "python", "-c", code)
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip(f"cannot mint a test JWT: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip().splitlines()[-1]


@pytest.fixture(scope="session")
def base_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--base-url").rstrip("/")


@pytest.fixture(scope="session")
def project_id(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--project-id")


@pytest.fixture(scope="session")
def api(base_url: str, token: str) -> httpx.Client:
    """Authenticated HTTP client pointed at the API root."""
    with httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def anon_api(base_url: str) -> httpx.Client:
    """Unauthenticated client, for negative auth tests."""
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        yield client


# ── Database ─────────────────━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture(scope="session")
def db(docker: bool):
    """Return ``query(sql)`` -> stripped psql output (tuples only)."""

    def query(sql: str) -> str:
        proc = docker_compose_exec(
            "postgres", "psql", "-U", POSTGRES_USER, "-d", POSTGRES_DB, "-tAc", sql
        )
        if proc.returncode != 0:
            pytest.fail(f"psql failed: {proc.stderr.strip()[:400]}")
        return proc.stdout.strip()

    return query


# ── HTTP helpers ───────────────────────────────────────────────────────


def wait_for_task(
    api: httpx.Client,
    task_id: str,
    timeout: float = 120.0,
    interval: float = 1.0,
) -> dict:
    """Poll ``GET /documents/tasks/{id}`` until SUCCESS/FAILURE.

    Raises AssertionError with the last payload on timeout.
    """
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        resp = api.get(f"/api/v1/documents/tasks/{task_id}")
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last.get("status") in ("SUCCESS", "FAILURE", "REVOKED"):
            return last
        time.sleep(interval)
    raise AssertionError(f"task {task_id} did not finish in {timeout}s: {last}")


@pytest.fixture(scope="session")
def wait_task():
    return wait_for_task


# ── Fixtures over the seeded project ───────────────────────────────────


@pytest.fixture(scope="session")
def documents(api: httpx.Client, project_id: str) -> list[dict]:
    resp = api.get("/api/v1/documents", params={"proyecto_id": project_id})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    return payload if isinstance(payload, list) else payload.get("items", [])


@pytest.fixture(scope="session")
def any_doc(documents: list[dict]) -> dict:
    if not documents:
        pytest.skip("the test project has no documents")
    return documents[0]


@pytest.fixture(scope="session")
def doc_by_state(documents: list[dict]):
    def find(estado: str) -> dict | None:
        for doc in documents:
            if str(doc.get("estado", "")).strip() == estado:
                return doc
        return None

    return find


# ── Ephemeral project for E2E ──────────────────────────────────────────


@pytest.fixture
def temp_project(api: httpx.Client) -> str:
    """Create a throw-away project and delete it afterwards."""
    name = f"workflow-test-{uuid.uuid4().hex[:8]}"
    resp = api.post("/api/v1/projects", json={"nombre": name})
    assert resp.status_code in (200, 201), resp.text
    pid = resp.json()["id"]
    try:
        yield pid
    finally:
        api.delete(f"/api/v1/projects/{pid}")


SAMPLE_TEXT = (
    "El cambio climatico afecta la vida cotidiana en la comunidad. "
    "Los entrevistados describen sequias mas largas y lluvias irregulares "
    "que complican la siembra y la cosecha. Tambien mencionan problemas de "
    "salud respiratoria por el polvo y el calor extremo. Las familias "
    "organizan horarios de trabajo para evitar las horas de mayor radiacion. "
    "Algunos participantes piden apoyo tecnico y capacitacion para adaptar "
    "sus cultivos. Otros senalan que la migracion de los jovenes deja menos "
    "mano de obra disponible en la comunidad."
)


@pytest.fixture
def uploaded_doc(api: httpx.Client, temp_project: str) -> dict:
    """Upload SAMPLE_TEXT as a plain-text document into the temp project."""
    resp = api.post(
        f"/api/v1/documents/upload/{temp_project}",
        files={
            "file": ("workflow_sample.txt", SAMPLE_TEXT.encode("utf-8"), "text/plain")
        },
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    # Upload may answer with the document or with a list/batch wrapper.
    if isinstance(body, list):
        body = body[0]
    return body
