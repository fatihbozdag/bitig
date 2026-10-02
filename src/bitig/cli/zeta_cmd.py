"""`bitig zeta <corpus>` — contrastive vocabulary between two metadata groups."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from bitig.io import load_corpus
from bitig.methods.zeta import ZetaClassic, ZetaEder

console = Console()


def zeta_command(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),  # noqa: B008
    metadata: Path = typer.Option(..., "--metadata", "-m", exists=True, dir_okay=False),  # noqa: B008
    group_by: str = typer.Option("author", "--group-by"),
    variant: str = typer.Option("classic", "--variant", help="classic | eder"),
    top_k: int = typer.Option(20, "--top-k"),
    group_a: str | None = typer.Option(
        None, "--group-a", help="First group label (default: the two largest groups are used)"
    ),
    group_b: str | None = typer.Option(
        None, "--group-b", help="Second group label (default: the two largest groups are used)"
    ),
) -> None:
    """Extract contrastive vocabulary between two groups via Craig's Zeta."""
    cls = {"classic": ZetaClassic, "eder": ZetaEder}.get(variant)
    if cls is None:
        console.print(f"[red]error:[/red] unknown variant {variant!r}")
        raise typer.Exit(code=1)
    corpus = load_corpus(path, metadata=metadata)
    result = cls(group_by=group_by, top_k=top_k, group_a=group_a, group_b=group_b).fit_transform(
        corpus
    )

    label_a = result.values["group_a"]
    label_b = result.values["group_b"]
    for df, label in [(result.tables[0], label_a), (result.tables[1], label_b)]:
        table = Table(title=f"preferred in {label}")
        table.add_column("word", style="cyan")
        table.add_column("zeta")
        table.add_column(f"prop_{label_a}")
        table.add_column(f"prop_{label_b}")
        for _, row in df.iterrows():
            table.add_row(
                row["word"], f"{row['zeta']:.3f}", f"{row['prop_a']:.3f}", f"{row['prop_b']:.3f}"
            )
        console.print(table)
