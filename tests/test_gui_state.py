"""Tests for bainary.gui.state — ArtifactSession + JobStatus dataclasses."""

from __future__ import annotations

from bainary.gui.errors import GuiError
from bainary.gui.state import ArtifactSession, JobStatus


def test_artifact_session_empty() -> None:
    s = ArtifactSession()
    assert s.artifact is None
    assert s.callgraph is None
    assert s.index is None
    assert s.refiner is None
    assert s.binary_bytes is None
    assert s.refined_cache == {}
    assert s.jobs == {}


def test_artifact_session_factory_no_shared_mutable() -> None:
    a = ArtifactSession()
    b = ArtifactSession()
    a.refined_cache["0x1000"] = "code"
    assert b.refined_cache == {}
    a.jobs["x"] = JobStatus(job_id="x", kind="lift")
    assert b.jobs == {}


def test_job_status_defaults() -> None:
    j = JobStatus(job_id="abc", kind="lift")
    assert j.job_id == "abc"
    assert j.kind == "lift"
    assert j.status == "running"
    assert j.progress == 0
    assert j.total == 0
    assert j.log_lines == []


def test_job_status_kind_constrains_to_known_literals() -> None:
    # Literal check: only "lift", "refine", "rag_build" accepted.
    # A type-incorrect literal at runtime still works since Python is dynamyic,
    # but we exercise the documented values to lock the contract.
    for kind in ("lift", "refine", "rag_build"):
        JobStatus(job_id="x", kind=kind)  # type: ignore[arg-type]


def test_job_status_progress_advances() -> None:
    j = JobStatus(job_id="abc", kind="refine", total=3)
    j.progress += 1
    assert j.progress == 1


def test_gui_error_is_bainary_error() -> None:
    from bainary.lift.errors import BainaryError

    assert issubclass(GuiError, BainaryError)


def test_gui_error_message_preserved() -> None:
    e = GuiError("boom")
    assert str(e) == "boom"
