"""`bitig run <study.yaml>` — execute a full declarative study."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from bitig.runner import StudyRunStatus, run_study

console = Console()


def run_command(
    config: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),  # noqa: B008
    output: Path | None = typer.Option(None, "--output", "-o"),  # noqa: B008
    name: str | None = typer.Option(
        None, "--name", help="Override the default timestamp run-directory name"
    ),
) -> None:
    """Execute a full declarative study and save results to `results/<run>/`."""
    try:
        run_dir = run_study(config, output_dir=output, run_name=name)
    except (ValueError, TypeError, OSError) as exc:
        console.print(f"[red]run failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    status = StudyRunStatus.load(run_dir)
    if status.status != "succeeded":
        console.print(f"[red]run {status.status}[/red] {run_dir}")
        for method, error in status.methods.items():
            if error:
                console.print(f"{method}: {error}")
        if status.report_error:
            console.print(f"report: {status.report_error}")
        raise typer.Exit(code=1 if status.status == "failed" else 2)
    console.print(f"[green]run complete[/green] {run_dir}")
