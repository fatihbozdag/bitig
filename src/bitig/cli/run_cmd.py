"""`bitig run <study.yaml>` — execute a full declarative study."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from bitig.runner import failed_methods, run_study

console = Console()


def run_command(
    config: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),  # noqa: B008
    output: Path | None = typer.Option(None, "--output", "-o"),  # noqa: B008
    name: str | None = typer.Option(
        None, "--name", help="Override the default timestamp run-directory name"
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace the outputs of a previous run in the same run directory.",
    ),
) -> None:
    """Execute a full declarative study and save results to `results/<run>/`.

    Exits with code 1 if any method failed (see error.txt in its folder).
    """
    try:
        run_dir = run_study(config, output_dir=output, run_name=name, overwrite=overwrite)
    except (FileExistsError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    failed = failed_methods(run_dir)
    if failed:
        console.print(f"[red]run finished with {len(failed)} failed method(s)[/red] {run_dir}")
        for method_id, error in failed.items():
            console.print(f"  ✗ {method_id}: {error}")
        raise typer.Exit(code=1)
    console.print(f"[green]run complete[/green] {run_dir}")
