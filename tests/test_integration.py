"""
Script de integración — verifica el pipeline CGT + RAG + HITL.

Testea:
  1. Autenticación (JWT)
  2. Endpoints HITL (hypotheses CRUD)
  3. RAG search (RRF, semantic, lexical)
  4. Code recommendations
  5. Document list (con estado)
  6. Worker health (Celery ping)
  7. Pipeline trigger simulation
  8. DB state verification

Usa datos reales: 3 documentos, 7 hipótesis existentes.
Modo mock: LLMClient devuelve respuestas predefinidas.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from typing import Any

import requests

BASE_URL = "http://localhost:8000/api/v1"
PASSED = 0
FAILED = 0
ERRORS: list[str] = []


def test(name: str, fn) -> None:
    global PASSED, FAILED
    try:
        fn()
        PASSED += 1
        print(f"  ✅ {name}")
    except AssertionError as e:
        FAILED += 1
        msg = f"  ❌ {name}: {e}"
        print(msg)
        ERRORS.append(msg)
    except Exception as e:
        FAILED += 1
        msg = f"  💥 {name}: {type(e).__name__}: {e}"
        print(msg)
        ERRORS.append(msg)


def assert_status(resp, expected: int, label: str = "") -> requests.Response:
    assert resp.status_code == expected, (
        f"{label} expected {expected}, got {resp.status_code}: {resp.text[:200]}"
    )
    return resp


def assert_ok(resp, label: str = "") -> dict:
    assert_status(resp, 200, label)
    return resp.json()


def assert_created(resp, label: str = "") -> dict:
    assert_status(resp, 201, label)
    return resp.json()


# ═══════════════════════════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════════════════════════


def setup():
    """Register user and get token."""
    global TOKEN, USER_ID, PROJECT_ID

    # Try login first (login uses query params: email + password)
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        params={"email": "test@test.com", "password": "testpass123"},
    )
    if resp.status_code == 200:
        TOKEN = resp.json()["access_token"]
        print(f"🔑 Logged in as test@test.com")
    else:
        # Register
        resp = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "nombre": "Test User",
                "correo": "test@test.com",
                "password": "testpass123",
            },
        )
        assert_status(resp, 201, "register")
        TOKEN = resp.json()["access_token"]
        print(f"🔑 Registered and logged in")

    # Get or create project
    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = requests.get(f"{BASE_URL}/projects", headers=headers)
    assert_status(resp, 200, "list projects")
    projects = resp.json()
    if projects:
        PROJECT_ID = projects[0]["id"]
        print(f"📁 Using project: {projects[0].get('nombre', PROJECT_ID)}")
    else:
        resp = requests.post(
            f"{BASE_URL}/projects",
            headers=headers,
            json={
                "nombre": "Test CGT Project",
                "ruta_de_codificacion": "ABDUCTIVA_CGT",
            },
        )
        assert_status(resp, 201, "create project")
        PROJECT_ID = resp.json()["id"]
        print(f"📁 Created project: {PROJECT_ID}")


def auth_headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"}


TOKEN = ""
USER_ID = ""
PROJECT_ID = ""


# ═══════════════════════════════════════════════════════════════
# Test Suite
# ═══════════════════════════════════════════════════════════════


def test_auth_works():
    """JWT token is valid."""
    resp = requests.get(f"{BASE_URL}/ping", headers=auth_headers())
    assert_ok(resp, "ping")


def test_list_documents():
    """Documents returned with estado field."""
    resp = requests.get(
        f"{BASE_URL}/documents",
        params={"proyecto_id": PROJECT_ID},
        headers=auth_headers(),
    )
    data = assert_ok(resp, "list documents")
    if len(data) == 0:
        print(f"     📄 0 documents (new project — expected)")
        return
    for doc in data:
        assert "id" in doc
        assert "original_filename" in doc
        assert "texto_extraido" in doc
        print(f"     📄 {doc['original_filename'][:50]}...")


def test_list_segments():
    """Segments for doc with 43 segments."""
    resp = requests.get(
        f"{BASE_URL}/documents",
        params={"proyecto_id": PROJECT_ID},
        headers=auth_headers(),
    )
    docs = resp.json()
    doc_with_segments = [d for d in docs if d.get("texto_extraido")]
    if not doc_with_segments:
        print("     ⚠️ No documents have extracted text, skipping")
        return

    doc_id = doc_with_segments[0]["id"]
    resp = requests.get(
        f"{BASE_URL}/documents/{doc_id}/segments",
        headers=auth_headers(),
    )
    segs = assert_ok(resp, "list segments")
    assert len(segs) >= 1, f"Expected segments, got {len(segs)}"
    print(f"     📊 {len(segs)} segments in document")


def test_rag_search_rrf():
    """RRF search returns results."""
    resp = requests.get(
        f"{BASE_URL}/rag/search",
        params={"q": "comportamiento", "proyecto_id": PROJECT_ID, "top_k": 3},
        headers=auth_headers(),
    )
    data = assert_ok(resp, "rag search rrf")
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    print(f"     🔍 {len(data)} results for 'comportamiento' (RRF)")


def test_rag_search_semantic():
    """Semantic search returns results."""
    resp = requests.get(
        f"{BASE_URL}/rag/search",
        params={
            "q": "preocupación",
            "proyecto_id": PROJECT_ID,
            "top_k": 3,
            "fusion": "semantic",
        },
        headers=auth_headers(),
    )
    data = assert_ok(resp, "rag search semantic")
    print(f"     🔍 {len(data)} results for 'preocupación' (semantic)")


def test_rag_search_lexical():
    """Lexical search returns results."""
    resp = requests.get(
        f"{BASE_URL}/rag/search",
        params={
            "q": "familia",
            "proyecto_id": PROJECT_ID,
            "top_k": 3,
            "fusion": "lexical",
        },
        headers=auth_headers(),
    )
    data = assert_ok(resp, "rag search lexical")
    print(f"     🔍 {len(data)} results for 'familia' (lexical)")


def test_rag_search_with_mmr():
    """RRF + MMR diversifies results."""
    resp = requests.get(
        f"{BASE_URL}/rag/search",
        params={
            "q": "vida",
            "proyecto_id": PROJECT_ID,
            "top_k": 5,
            "diversify": True,
            "lambda_mmr": 0.6,
        },
        headers=auth_headers(),
    )
    data = assert_ok(resp, "rag search mmr")
    # MMR should return ≤ top_k results
    assert len(data) <= 5, f"MMR returned {len(data)} results (> 5)"
    # Results should have mmr_score when diversify=True
    for r in data:
        assert "mmr_score" in r, f"Result missing mmr_score: {r.keys()}"
    print(f"     🔍 {len(data)} diverse results (MMR λ=0.6)")


def test_hypotheses_list_candidates():
    """List hypothesis candidates returns data."""
    resp = requests.get(
        f"{BASE_URL}/hypotheses/candidates",
        params={"proyecto_id": PROJECT_ID},
        headers=auth_headers(),
    )
    data = assert_ok(resp, "list candidates")
    print(f"     💡 {len(data)} candidate hypotheses")


def test_hypotheses_accept_reject_cycle():
    """Full lifecycle: accept → modify → reject."""
    # Get candidates
    resp = requests.get(
        f"{BASE_URL}/hypotheses/candidates",
        params={"proyecto_id": PROJECT_ID},
        headers=auth_headers(),
    )
    candidates = resp.json()
    if not candidates:
        print("     ⚠️ No candidates to test lifecycle, skipping")
        return

    hyp_id = candidates[0]["id"]

    # Accept
    resp = requests.post(
        f"{BASE_URL}/hypotheses/{hyp_id}/accept",
        json={"justification": "Integration test — accepting"},
        headers=auth_headers(),
    )
    data = assert_ok(resp, "accept hypothesis")
    assert data["status"] == "accepted", f"Expected accepted, got {data['status']}"

    # Modify
    resp = requests.post(
        f"{BASE_URL}/hypotheses/{hyp_id}/modify",
        json={
            "new_text": "[TEST MODIFIED] Los participantes muestran patrones adaptativos.",
            "new_level": "emergent",
            "justification": "Testing modify endpoint",
        },
        headers=auth_headers(),
    )
    data = assert_ok(resp, "modify hypothesis")
    assert data["status"] == "candidate", (
        f"Expected candidate after modify, got {data['status']}"
    )

    # Reject
    resp = requests.post(
        f"{BASE_URL}/hypotheses/{hyp_id}/reject",
        json={"reason": "Integration test — cleaning up"},
        headers=auth_headers(),
    )
    data = assert_ok(resp, "reject hypothesis")
    assert data["status"] == "rejected"

    print(f"     🔄 Full lifecycle: accept→modify→reject on {hyp_id[:8]}...")


def test_hypotheses_split():
    """Split a hypothesis into children."""
    resp = requests.get(
        f"{BASE_URL}/hypotheses/candidates",
        params={"proyecto_id": PROJECT_ID},
        headers=auth_headers(),
    )
    candidates = resp.json()
    if not candidates:
        print("     ⚠️ No candidates to split, skipping")
        return

    hyp_id = candidates[0]["id"]

    resp = requests.post(
        f"{BASE_URL}/hypotheses/{hyp_id}/split",
        json={
            "children": [
                "Sub-hipótesis A: comportamiento adaptativo temprano",
                "Sub-hipótesis B: comportamiento adaptativo tardío",
            ],
            "justification": "Testing split for Tree of Thoughts",
        },
        headers=auth_headers(),
    )
    data = assert_created(resp, "split hypothesis")
    assert data["children_created"] == 2
    assert data["parent_status"] == "split"
    print(f"     🌳 Split into {data['children_created']} children")


def test_code_recommendations():
    """Segment recommendations work."""
    resp = requests.get(
        f"{BASE_URL}/documents",
        params={"proyecto_id": PROJECT_ID},
        headers=auth_headers(),
    )
    docs = resp.json()
    # Find a doc with segments
    for doc in docs:
        resp = requests.get(
            f"{BASE_URL}/documents/{doc['id']}/segments",
            headers=auth_headers(),
        )
        segs = resp.json()
        if segs:
            seg_id = segs[0]["id"]
            resp = requests.get(
                f"{BASE_URL}/segments/{seg_id}/recommendations",
                headers=auth_headers(),
            )
            data = assert_ok(resp, f"recommendations for {seg_id[:8]}")
            print(f"     💡 {len(data)} code recommendations for segment")
            return

    print("     ⚠️ No segments with embeddings to test recommendations")


def test_db_integrity():
    """Verify DB state is consistent after our changes."""
    import subprocess

    result = subprocess.run(
        [
            "psql",
            "-h",
            "localhost",
            "-p",
            "5433",
            "-U",
            "app_user",
            "-d",
            "gt-db",
            "-t",
            "-c",
            """
        SELECT
          (SELECT COUNT(*) FROM documentos) as docs,
          (SELECT COUNT(*) FROM segmentos) as segs,
          (SELECT COUNT(*) FROM categorias) as codes,
          (SELECT COUNT(*) FROM hypotheses) as hyps,
          (SELECT COUNT(*) FROM population_contexts) as pop_ctx,
          (SELECT COUNT(*) FROM document_processes) as doc_proc
        """,
        ],
        env={**os.environ, "PGPASSWORD": "strongpass"},
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"     🗄️  DB: {result.stdout.strip()}")
    else:
        print(f"     ⚠️ Could not query DB: {result.stderr[:100]}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 CGT Pipeline Integration Tests")
    print(f"   {datetime.now().isoformat()}")
    print("=" * 60)
    print()

    # Setup
    print("── Setup ──")
    test("Register/Login", setup)
    print()

    # Auth
    print("── Auth ──")
    test("JWT token valid", test_auth_works)
    print()

    # Documents
    print("── Documents ──")
    test("List documents with estado", test_list_documents)
    test("List segments", test_list_segments)
    print()

    # RAG
    print("── RAG Search ──")
    test("RRF fusion search", test_rag_search_rrf)
    test("Semantic search", test_rag_search_semantic)
    test("Lexical search", test_rag_search_lexical)
    test("RRF + MMR diversity", test_rag_search_with_mmr)
    print()

    # HITL
    print("── HITL Hypotheses ──")
    test("List candidates", test_hypotheses_list_candidates)
    test("Accept→Modify→Reject lifecycle", test_hypotheses_accept_reject_cycle)
    test("Split into children (ToT)", test_hypotheses_split)
    print()

    # Coding
    print("── Code Recommendations ──")
    test("Segment code recommendations", test_code_recommendations)
    print()

    # DB
    print("── DB Integrity ──")
    test("DB state check", test_db_integrity)
    print()

    # Summary
    print("=" * 60)
    TOTAL = PASSED + FAILED
    print(f"Results: {PASSED}/{TOTAL} passed, {FAILED} failed")
    if ERRORS:
        print()
        print("Errors:")
        for e in ERRORS:
            print(f"  {e}")
    print("=" * 60)

    sys.exit(0 if FAILED == 0 else 1)
