"""In-memory backend state for the bAInary GUI.

A single :class:`ArtifactSession` lives per server process: it owns the
currently-loaded :class:`bainary.lift.artifact.BinaryArtifact`, the
:class:`bainary.graph.CallGraph` derived from it, an optional
:class:`bainary.rag.Index` (built on demand), a lazily-created
:class:`bainary.refine.Refiner`, raw binary bytes cached for the hex
view, a per-address cache of refined pseudo-C, and a registry of
background jobs (lift, refine, rag_build).

Asynchronous jobs run on ``loop.run_in_executor(None, ...)`` to keep
the FastAPI event loop responsive; their progress is tracked by the
:class:`JobStatus` records stored in ``ArtifactSession.jobs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from bainary.graph import CallGraph
from bainary.lift.artifact import BinaryArtifact
from bainary.rag import Index
from bainary.refine import Refiner

JobKind = Literal["lift", "refine", "rag_build"]
JobState = Literal["running", "done", "error", "cancelled"]


@dataclass
class JobStatus:
    """Status of a background job (lift, refine, rag_build)."""

    job_id: str
    kind: JobKind
    status: JobState = "running"
    progress: int = 0
    total: int = 0
    log_lines: list[str] = field(default_factory=list)

    def log(self, line: str) -> None:
        """Append a log line and keep the buffer bounded (last 500 lines)."""
        self.log_lines.append(line)
        if len(self.log_lines) > 500:
            del self.log_lines[: len(self.log_lines) - 500]


@dataclass
class ArtifactSession:
    """One process-wide session: artifact in memory + auxiliary state.

    Mutated by FastAPI route handlers and background jobs. Not thread-safe;
    FastAPI's event loop serialises mutations. Cross-thread access happens
    only inside ``loop.run_in_executor`` jobs that publish progress via
    the SSE broker rather than mutating this struct directly.
    """

    artifact: BinaryArtifact | None = None
    callgraph: CallGraph | None = None
    refiner: Refiner | None = None
    index: Index | None = None
    binary_bytes: bytes | None = None
    refined_cache: dict[str, str] = field(default_factory=dict)
    jobs: dict[str, JobStatus] = field(default_factory=dict)

    def reset(self) -> None:
        """Reset all artifact-derived state. Used when re-loading a binary."""
        self.artifact = None
        self.callgraph = None
        self.index = None
        self.binary_bytes = None
        self.refined_cache.clear()
        self.jobs.clear()

    def has_artifact(self) -> bool:
        return self.artifact is not None
