"""Tests for bainary.gui.routes.meta — imports/exports/strings."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bainary.gui.server import create_app
from bainary.lift.artifact import (
    BinaryArtifact,
    BinaryInfo,
    ExportRef,
    ImportRef,
    Section,
    StringRef,
)

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
        imports=[
            ImportRef(address="0x2000", name="printf", library="libc"),
            ImportRef(address="0x2008", name="malloc", library="libc"),
            ImportRef(address="0x2010", name="xmlInitParser", library="libxml2"),
        ],
        exports=[
            ExportRef(address="0x1000", name="main"),
            ExportRef(address="0x1100", name="helper"),
        ],
        strings=[
            StringRef(address="0x3000", value="hello", encoding="ascii"),
            StringRef(address="0x3008", value="world", encoding="ascii"),
        ],
        functions=[],
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_imports_409_no_artifact(client: TestClient) -> None:
    r = client.get("/api/imports")
    assert r.status_code == 409


def test_imports_list_all(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/imports")
    assert r.status_code == 200
    j = r.json()
    assert len(j) == 3
    assert all("name" in e and "library" in e and "address" in e for e in j)


def test_imports_filter_by_name(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/imports?q=printf")
    assert r.status_code == 200
    j = r.json()
    assert len(j) == 1
    assert j[0]["name"] == "printf"


def test_imports_filter_by_library(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/imports?q=libxml2")
    assert r.status_code == 200
    j = r.json()
    assert len(j) == 1
    assert j[0]["name"] == "xmlInitParser"


def test_imports_filter_no_match(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/imports?q=zzz")
    assert r.status_code == 200
    assert r.json() == []


def test_exports_list(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/exports")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_exports_filter(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/exports?q=helper")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "helper"


def test_strings_list(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/strings")
    assert r.status_code == 200
    j = r.json()
    assert len(j) == 2
    assert all("value" in s and "address" in s and "encoding" in s for s in j)


def test_strings_filter(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/strings?q=hello")
    assert r.status_code == 200
    assert r.json()[0]["value"] == "hello"


def test_strings_409_no_artifact(client: TestClient) -> None:
    r = client.get("/api/strings")
    assert r.status_code == 409


def test_exports_409_no_artifact(client: TestClient) -> None:
    r = client.get("/api/exports")
    assert r.status_code == 409
