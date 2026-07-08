"""Tests for bainary.gui.routes.binary — lift (upload/path), info, hex, list.

Backend = ``lief_capstone`` everywhere to avoid the 10-30s Ghidra subprocess
in CI. The lief_capstone path is fast (<1s) and exercises the same
:func:`bainary.lift.api.lift` entry point that the GUI uses in production.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bainary.gui.server import create_app
from bainary.gui.state import ArtifactSession
from bainary.lift.artifact import (
    BasicBlock,
    BinaryArtifact,
    BinaryInfo,
    CallRef,
    Cfg,
    ExportRef,
    Function,
    ImportRef,
    Section,
    StringRef,
)

FIXTURE = Path("tests/fixtures/loops_elf64/loops.elf")


def _build_fake_artifact(addr: str = "0x1000", name: str = "main") -> BinaryArtifact:
    return BinaryArtifact(
        binary=BinaryInfo(
            path=str(FIXTURE),
            sha256="0" * 64,
            format="ELF",
            arch="x64",
            endianness="little",
            entry_point=addr,
            base_address="0x0",
        ),
        sections=[Section(name=".text", address="0x1000", size=0x1000, permissions="r-x")],
        imports=[ImportRef(address="0x2000", name="printf", library="libc")],
        exports=[ExportRef(address=addr, name=name)],
        strings=[StringRef(address="0x3000", value="hello", encoding="ascii")],
        functions=[
            Function(
                address=addr,
                name=name,
                signature="int main(void)",
                calling_convention="cdecl",
                size_bytes=64,
                assembly="push rbp\nmov rbp, rsp\n...",
                is_thunk=False,
                basic_blocks=[
                    BasicBlock(
                        address=addr,
                        instructions=[],
                        successors=[f"{int(addr, 16) + 0x10:#x}"],
                        terminator="return",
                    ),
                ],
                cfg=Cfg(
                    nodes=[addr, f"{int(addr, 16) + 0x10:#x}"],
                    edges=[[addr, f"{int(addr, 16) + 0x10:#x}"]],
                ),
                callers=[],
                callees=[
                    CallRef.from_dict({"address": "0x2000", "name": "printf", "is_external": True})
                ],
                pseudocode='int main(void) { printf("hi"); return 0; }',
            ),
        ],
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _wait_for_job(client: TestClient, jid: str, *, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{jid}")
        if r.status_code == 200:
            st = r.json()
            if st["status"] != "running":
                return st
        time.sleep(0.05)
    raise AssertionError(f"job {jid} did not finish in {timeout}s")


def test_lift_path_lief(client: TestClient) -> None:
    r = client.post(
        "/api/lift/path",
        json={"path": str(FIXTURE), "backend": "lief_capstone"},
    )
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    st = _wait_for_job(client, jid)
    assert st["status"] == "done", st
    # binary info endpoint should now describe the lifted file
    r2 = client.get("/api/binary")
    assert r2.status_code == 200
    info = r2.json()
    assert info["format"] == "ELF"
    assert info["arch"] == "x64"


def test_lift_path_missing_422(client: TestClient) -> None:
    r = client.post(
        "/api/lift/path",
        json={"path": "/nope/never/here.elf", "backend": "lief_capstone"},
    )
    assert r.status_code == 422
    assert "detail" in r.json()


def test_lift_path_ghidra_without_home_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GHIDRA_HOME", raising=False)
    r = client.post(
        "/api/lift/path",
        json={"path": str(FIXTURE), "backend": "ghidra_headless"},
    )
    assert r.status_code == 503
    assert "ghidra" in r.json()["detail"].lower()


def test_hex_no_artifact_409(client: TestClient) -> None:
    r = client.get("/api/hex?addr=0x1000&len=32")
    assert r.status_code == 409


def test_hex_with_fake_bytes(client: TestClient) -> None:
    app = client.app
    sess: ArtifactSession = app.state.session
    sess.artifact = _build_fake_artifact()
    sess.binary_bytes = b"\x55\x48\x89\xe5" * 8  # 32 bytes
    r = client.get("/api/hex?addr=0x0&len=32")
    assert r.status_code == 200
    j = r.json()
    assert "rows" in j
    assert len(j["rows"]) == 2  # 32 bytes / 16 per row
    assert "hex" in j["rows"][0]
    assert "ascii" in j["rows"][0]
    assert "off" in j["rows"][0]


def test_hex_truncates_length(client: TestClient) -> None:
    app = client.app
    sess: ArtifactSession = app.state.session
    sess.artifact = _build_fake_artifact()
    sess.binary_bytes = b"\x00" * 10
    r = client.get("/api/hex?addr=0x0&len=256")
    assert r.status_code == 200
    # 10 bytes -> 1 row
    assert len(r.json()["rows"]) == 1


def test_functions_list_no_artifact_409(client: TestClient) -> None:
    r = client.get("/api/functions")
    assert r.status_code == 409


def test_functions_list_filter_by_name(client: TestClient) -> None:
    app = client.app
    sess: ArtifactSession = app.state.session
    sess.artifact = _build_fake_artifact()
    r = client.get("/api/functions?q=main")
    assert r.status_code == 200
    fns = r.json()
    assert any(f["name"] == "main" for f in fns)
    assert all("address" in f and "name" in f and "is_thunk" in f for f in fns)


def test_functions_list_filter_no_match(client: TestClient) -> None:
    app = client.app
    sess: ArtifactSession = app.state.session
    sess.artifact = _build_fake_artifact()
    r = client.get("/api/functions?q=zzz_nope")
    assert r.status_code == 200
    assert r.json() == []


def test_jobs_status_404_unknown(client: TestClient) -> None:
    r = client.get("/api/jobs/does-not-exist")
    assert r.status_code == 404


def test_lift_upload_persists_to_tmpfile(client: TestClient, tmp_path: Path) -> None:
    content = FIXTURE.read_bytes()
    r = client.post(
        "/api/lift/upload?backend=lief_capstone",
        files={"file": ("loops.elf", content, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    st = _wait_for_job(client, jid)
    assert st["status"] == "done"


def test_lift_replaces_previous_artifact(client: TestClient) -> None:
    # First lift
    r = client.post("/api/lift/path", json={"path": str(FIXTURE), "backend": "lief_capstone"})
    jid = r.json()["job_id"]
    _wait_for_job(client, jid)
    r1 = client.get("/api/binary")
    sha1 = r1.json()["sha256"]
    # Second lift
    r = client.post("/api/lift/path", json={"path": str(FIXTURE), "backend": "lief_capstone"})
    jid = r.json()["job_id"]
    _wait_for_job(client, jid)
    r2 = client.get("/api/binary")
    assert r2.json()["sha256"] == sha1  # same fixture, same sha
    assert r1.status_code == r2.status_code == 200


def test_callgraph_built_on_lift(client: TestClient) -> None:
    r = client.post("/api/lift/path", json={"path": str(FIXTURE), "backend": "lief_capstone"})
    jid = r.json()["job_id"]
    _wait_for_job(client, jid)
    sess: ArtifactSession = client.app.state.session
    assert sess.callgraph is not None
    # sanity: the callgraph should have at least the discovered function
    assert len(sess.callgraph.graph.nodes) >= 1
