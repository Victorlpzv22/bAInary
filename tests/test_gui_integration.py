"""End-to-end integration test for the bAInary GUI.

One test exercises the full path: load binary via REST → list functions
→ fetch function detail → graph → RAG build+search → refine → settings.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bainary.gui.server import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "loops_elf64" / "loops.elf"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BAINARY_GUI_CACHE_DIR", str(tmp_path / "gui-cache"))
    return TestClient(create_app())


def _wait_for_job(client: TestClient, jid: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{jid}")
        if r.status_code == 200:
            st = r.json()
            if st["status"] != "running":
                return st
        time.sleep(0.05)
    raise AssertionError(f"job {jid} did not finish in {timeout}s")


def test_full_lift_to_refine_flow(client: TestClient) -> None:
    # 1. Lift via REST (lief_capstone, no Ghidra)
    r = client.post("/api/lift/path", json={"path": str(FIXTURE), "backend": "lief_capstone"})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    st = _wait_for_job(client, jid)
    assert st["status"] == "done"

    # 2. Binary info
    r = client.get("/api/binary")
    assert r.status_code == 200
    info = r.json()
    assert info["format"] == "ELF"
    assert info["functions_count"] > 0

    # 3. Function list
    r = client.get("/api/functions")
    assert r.status_code == 200
    fns = r.json()
    assert fns
    target = fns[0]
    addr = target["address"]

    # 4. Function detail
    r = client.get(f"/api/functions/{addr}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["address"] == addr
    assert "assembly" in detail

    # 5. Graph
    r = client.get("/api/graph")
    assert r.status_code == 200
    g = r.json()
    assert g["nodes"]

    # 6. RAG build + search
    r = client.post("/api/rag/build")
    assert r.status_code == 200
    r = client.post("/api/rag/search", json={"query": "main", "k": 5})
    assert r.status_code == 200
    hits = r.json()
    assert isinstance(hits, list)

    # 7. Settings
    r = client.get("/api/settings")
    assert r.status_code == 200
    s = r.json()
    assert "lift_backend" in s
    assert "llm_provider" in s

    # 8. Meta (imports / exports / strings)
    r = client.get("/api/imports")
    assert r.status_code == 200
    r = client.get("/api/exports")
    assert r.status_code == 200
    r = client.get("/api/strings")
    assert r.status_code == 200


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_session_replaced_on_relift(client: TestClient) -> None:
    # First lift
    r = client.post("/api/lift/path", json={"path": str(FIXTURE), "backend": "lief_capstone"})
    _wait_for_job(client, r.json()["job_id"])
    sess = client.app.state.session
    assert sess.artifact is not None
    first_artifact = sess.artifact
    # Re-lift same path — should keep the artifact (sha matches)
    r = client.post("/api/lift/path", json={"path": str(FIXTURE), "backend": "lief_capstone"})
    _wait_for_job(client, r.json()["job_id"])
    assert sess.artifact is not None
    # Same sha, so the artifact is replaced with an equivalent instance
    assert sess.artifact.binary.sha256 == first_artifact.binary.sha256
    # Callgraph rebuilt
    assert sess.callgraph is not None


def test_unload_no_artifact_409(client: TestClient) -> None:
    r = client.get("/api/binary")
    assert r.status_code == 409
    r = client.get("/api/functions/0x1000")
    assert r.status_code == 409
    r = client.get("/api/imports")
    assert r.status_code == 409
    r = client.get("/api/graph")
    assert r.status_code == 409
    r = client.post("/api/rag/build")
    assert r.status_code == 409
    r = client.post("/api/refine", json={"addresses": ["0x1000"]})
    assert r.status_code == 409
    r = client.get("/api/refine/result/0x1000")
    assert r.status_code == 409
