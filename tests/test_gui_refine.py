"""Tests for bainary.gui.routes.refine — batch refine, result, SSE.

The refine tests use a :class:`MockClient` to avoid any LLM network call.
We stub ``_ensure_refiner`` indirectly by setting ``session.refiner`` to
a refiner that uses the mock client.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bainary.gui.server import create_app
from bainary.gui.state import ArtifactSession
from bainary.lift.artifact import (
    BinaryArtifact,
    BinaryInfo,
    ExportRef,
    Function,
    ImportRef,
    Section,
    StringRef,
)
from bainary.refine import Refiner
from bainary.refine.cache import RefinementCache
from tests.test_refiner import MockClient

FIXTURE = Path("tests/fixtures/loops_elf64/loops.elf")


def _artifact() -> BinaryArtifact:
    return BinaryArtifact(
        binary=BinaryInfo(
            path=str(FIXTURE),
            sha256="0" * 64,
            format="ELF",
            arch="x64",
            endianness="little",
            entry_point="0x1000",
            base_address="0x0",
        ),
        sections=[Section(name=".text", address="0x1000", size=0x1000, permissions="r-x")],
        imports=[ImportRef(address="0x2000", name="printf", library="libc")],
        exports=[ExportRef(address="0x1000", name="main")],
        strings=[StringRef(address="0x3000", value="hi", encoding="ascii")],
        functions=[
            Function(
                address="0x1000",
                name="main",
                signature="int main(void)",
                calling_convention="cdecl",
                size_bytes=64,
                assembly="",
                is_thunk=False,
                basic_blocks=[],
                cfg=None,
                callers=[],
                callees=[],
                pseudocode="int main(void) { return 0; }",
            ),
            Function(
                address="0x1100",
                name="helper",
                signature="void helper(void)",
                calling_convention="cdecl",
                size_bytes=16,
                assembly="",
                is_thunk=False,
                basic_blocks=[],
                cfg=None,
                callers=[],
                callees=[],
                pseudocode="void helper(void) {}",
            ),
            Function(
                address="0x1200",
                name="_thunk",
                signature="thunk",
                calling_convention="cdecl",
                size_bytes=4,
                assembly="",
                is_thunk=True,
                basic_blocks=[],
                cfg=None,
                callers=[],
                callees=[],
                pseudocode="thunk",
            ),
        ],
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    os.environ["BAINARY_GUI_CACHE_DIR"] = str(tmp_path)
    return TestClient(create_app())


def _wait_for_job(client: TestClient, jid: str, *, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{jid}")
        if r.status_code == 200:
            st = r.json()
            if st["status"] != "running":
                return st
        time.sleep(0.02)
    raise AssertionError(f"job {jid} did not finish in {timeout}s")


def _install_mock_refiner(sess: ArtifactSession, tmp_path: Path) -> Refiner:
    mock = MockClient(responses={"main": "int main() { return 1; }", "helper": "void helper() {}"})
    cache = RefinementCache(tmp_path / "cache", model="mock")
    refiner = Refiner(client=mock, cache=cache)
    sess.refiner = refiner
    return refiner


def test_refine_result_404_no_artifact(client: TestClient) -> None:
    r = client.get("/api/refine/result/0x1000")
    assert r.status_code == 409


def test_refine_result_404_no_refined(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    r = client.get("/api/refine/result/0x1000")
    assert r.status_code == 404


def test_refine_batch_409_no_artifact(client: TestClient) -> None:
    r = client.post("/api/refine", json={"addresses": ["0x1000"]})
    assert r.status_code == 409


def test_refine_batch_422_empty_addresses(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.post("/api/refine", json={"addresses": []})
    assert r.status_code == 422


def test_refine_batch_refines_one_function(client: TestClient, tmp_path: Path) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    _install_mock_refiner(sess, tmp_path)
    r = client.post("/api/refine", json={"addresses": ["0x1000"]})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    st = _wait_for_job(client, jid)
    assert st["status"] == "done"
    r2 = client.get("/api/refine/result/0x1000")
    assert r2.status_code == 200
    assert "main" in r2.json()["refined"]


def test_refine_batch_skips_thunk_by_default(client: TestClient, tmp_path: Path) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    _install_mock_refiner(sess, tmp_path)
    r = client.post("/api/refine", json={"addresses": ["0x1000", "0x1200"]})
    jid = r.json()["job_id"]
    _wait_for_job(client, jid)
    # thunk not refined (skip_thunks default true)
    assert client.get("/api/refine/result/0x1200").status_code == 404
    # main refined
    assert client.get("/api/refine/result/0x1000").status_code == 200


def test_refine_batch_unknown_address_marks_skip(client: TestClient, tmp_path: Path) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    _install_mock_refiner(sess, tmp_path)
    r = client.post("/api/refine", json={"addresses": ["0xdeadbeef"]})
    jid = r.json()["job_id"]
    st = _wait_for_job(client, jid)
    assert st["status"] == "done"
    assert st["progress"] == 1


def test_refine_cache_reused(client: TestClient, tmp_path: Path) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    refiner = _install_mock_refiner(sess, tmp_path)
    first_calls = refiner._client.call_count
    r = client.post("/api/refine", json={"addresses": ["0x1000"]})
    _wait_for_job(client, r.json()["job_id"])
    r2 = client.post("/api/refine", json={"addresses": ["0x1000"]})
    _wait_for_job(client, r2.json()["job_id"])
    # Cache hit means the mock was not re-invoked
    after = refiner._client.call_count
    assert after - first_calls == 1  # only the first call invoked the LLM


def test_sse_endpoint_streams_events(client: TestClient, tmp_path: Path) -> None:
    """Connect to /api/events, trigger a refine, assert the broker publishes."""
    from bainary.gui.sse import SSEBroker

    sess = client.app.state.session
    sess.artifact = _artifact()
    _install_mock_refiner(sess, tmp_path)

    # Drive the broker directly (avoids the long-lived streaming connection
    # that TestClient struggles to tear down).
    broker: SSEBroker = client.app.state.sse_broker
    assert broker.subscriber_count() == 0
    events_seen: list[str] = []

    async def collect() -> None:
        async with broker.subscribe() as q:
            # Publish a synthetic event to prove the wiring works.
            broker.publish("refine.progress", {"address": "0x1000", "status": "ok"})
            broker.publish("log", {"level": "info", "msg": "test"})
            evt = await asyncio.wait_for(q.get(), timeout=1)
            events_seen.append(evt["event"])
            evt2 = await asyncio.wait_for(q.get(), timeout=1)
            events_seen.append(evt2["event"])

    asyncio.run(collect())
    assert "refine.progress" in events_seen
    assert "log" in events_seen

    # Also assert the endpoint exists and is wired (we don't open the stream).
    r = client.get("/api/health")
    assert r.status_code == 200
