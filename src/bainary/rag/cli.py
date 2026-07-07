"""Command-line interface for the bAInary RAG subsystem."""

from __future__ import annotations

from pathlib import Path

import typer

from bainary.lift.api import lift as lift_binary
from bainary.lift.artifact import BinaryArtifact
from bainary.lift.errors import BainaryError
from bainary.rag.errors import RagError
from bainary.rag.index import Index
from bainary.rag.store import NumpyFileStore
from bainary.rag.vectorize import HashingTextVectorizer, TextualVectorizer

app = typer.Typer(
    name="bainary-rag",
    help="Cross-binary function search (subsystem C).",
    no_args_is_help=True,
)


def _default_store_root() -> Path:
    return Path.home() / ".cache" / "bainary" / "rag"


def _default_dim() -> int:
    return 1024


def _build_index(store_root: Path, dim: int) -> Index:
    """Build an Index with default settings (HashingTextVectorizer + NumpyFileStore)."""
    vec: TextualVectorizer = HashingTextVectorizer(dim=dim)
    store = NumpyFileStore(root=store_root, dim=dim)
    return Index(vectorizer=vec, store=store)


@app.command()
def index(
    binary: Path | None = typer.Argument(  # noqa: B008
        None,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Binary to lift and index. Omit if --from-artifact is used.",
    ),
    from_artifact: Path | None = typer.Option(  # noqa: B008
        None,
        "--from-artifact",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a JSON BinaryArtifact to index (skip the lift step).",
    ),
    store_root: Path = typer.Option(  # noqa: B008
        None,
        "--store-root",
        help="Where the vector store lives (default: ~/.cache/bainary/rag).",
    ),
    backend: str | None = typer.Option(
        None,
        "--backend",
        help="Lift backend (default: ghidra_headless, falls back to lief_capstone).",
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip lift cache."),
    timeout: int = typer.Option(600, "--timeout", help="Lift timeout in seconds."),
    dim: int = typer.Option(_default_dim(), "--dim", help="Vector dim."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Lift BINARY (or load --from-artifact) and add it to the corpus."""
    import logging

    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    if binary is None and from_artifact is None:
        typer.echo("ERROR: provide either a binary path or --from-artifact", err=True)
        raise typer.Exit(code=2)
    if binary is not None and from_artifact is not None:
        typer.echo("ERROR: pass either a binary or --from-artifact, not both", err=True)
        raise typer.Exit(code=2)

    if from_artifact is not None:
        try:
            artifact = BinaryArtifact.from_json(from_artifact)
        except (OSError, ValueError) as e:
            typer.echo(f"Could not read artifact {from_artifact}: {e}", err=True)
            raise typer.Exit(code=3) from e
    else:
        try:
            artifact = lift_binary(
                binary,  # type: ignore[arg-type]
                backend=backend,
                use_cache=not no_cache,
                timeout_s=timeout,
            )
        except BainaryError as e:
            typer.echo(f"bAInary error: {e}", err=True)
            raise typer.Exit(code=1) from e
        except ValueError as e:
            typer.echo(f"Invalid input: {e}", err=True)
            raise typer.Exit(code=2) from e

    root = store_root or _default_store_root()
    idx = _build_index(root, dim)
    try:
        idx.add_artifact(artifact)
    finally:
        idx.close()

    typer.echo(
        f"indexed {len(artifact.functions)} functions from {artifact.binary.sha256[:12]} "
        f"({artifact.binary.path})"
    )


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural-language query."),
    store_root: Path = typer.Option(  # noqa: B008
        None,
        "--store-root",
        help="Where the vector store lives (default: ~/.cache/bainary/rag).",
    ),
    k: int = typer.Option(5, "--top-k", "-k", help="Number of hits to return."),
    dim: int = typer.Option(_default_dim(), "--dim", help="Vector dim."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Search the corpus with a natural-language query."""
    import logging

    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    root = store_root or _default_store_root()
    idx = _build_index(root, dim)
    try:
        if len(idx) == 0:
            typer.echo(f"0 hits (empty corpus at {root})")
            return
        try:
            hits = idx.search(query, k=k)
        except RagError as e:
            typer.echo(f"bAInary error: {e}", err=True)
            raise typer.Exit(code=1) from e
    finally:
        idx.close()

    if not hits:
        typer.echo(f"0 hits for {query!r}")
        return
    typer.echo(f"top {len(hits)} hits for {query!r}:")
    for h in hits:
        typer.echo(
            f"{h.score:.4f}\t{h.binary_sha256[:12]}\t{h.function.name}\t{h.function.address}"
        )


@app.command()
def stats(
    store_root: Path = typer.Option(  # noqa: B008
        None,
        "--store-root",
        help="Where the vector store lives (default: ~/.cache/bainary/rag).",
    ),
    dim: int = typer.Option(_default_dim(), "--dim", help="Vector dim."),
) -> None:
    """Print corpus statistics: function count, distinct binaries, dim."""
    root = store_root or _default_store_root()
    store = NumpyFileStore(root=root, dim=dim)
    count = store.count()
    binaries = store.list_binaries()
    typer.echo(f"store: {root}")
    typer.echo(f"functions: {count}")
    typer.echo(f"binaries: {len(binaries)}")
    typer.echo(f"dim: {store.dim}")
