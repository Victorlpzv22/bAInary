"""Command-line interface for the bAInary lifting subsystem."""

from __future__ import annotations

from pathlib import Path

import typer

from bainary.lift.api import lift
from bainary.lift.errors import BainaryError

app = typer.Typer(
    name="bainary-lift",
    help="Lift a PE/ELF x86/x64 binary into bAInary's JSON artifact format.",
    no_args_is_help=True,
)


@app.command()  # type: ignore[untyped-decorator]  # typer has no stubs
def main(
    binary: Path = typer.Argument(  # noqa: B008
        ..., exists=True, file_okay=True, dir_okay=False, readable=True
    ),
    output: Path = typer.Option(..., "-o", "--output", help="Path to write the JSON artifact."),  # noqa: B008
    backend: str | None = typer.Option(
        None, "--backend", help="Backend name (default: ghidra_headless)."
    ),  # noqa: B008
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip the cache; always re-lift."),  # noqa: B008
    timeout: int = typer.Option(600, "--timeout", help="Backend timeout in seconds."),  # noqa: B008
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),  # noqa: B008
) -> None:
    """Lift BINARY into a bAInary JSON artifact and write to OUTPUT."""
    import logging

    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    try:
        artifact = lift(
            binary,
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

    try:
        artifact.to_json(output)
    except OSError as e:
        typer.echo(f"Could not write {output}: {e}", err=True)
        raise typer.Exit(code=3) from e

    typer.echo(
        f"Wrote {output} ({artifact.binary.format} {artifact.binary.arch}, "
        f"{len(artifact.functions)} functions, decompiler={artifact.binary.decompiler_version})"
    )
