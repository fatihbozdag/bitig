"""`bitig embed <corpus>` — produce an embedding FeatureMatrix and save to parquet."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from bitig.io import load_corpus

console = Console()


def embed_command(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),  # noqa: B008
    metadata: Path | None = typer.Option(  # noqa: B008
        None, "--metadata", "-m", exists=True, dir_okay=False
    ),
    model: str = typer.Option("sentence-transformers/all-MiniLM-L6-v2", "--model"),
    pool: str = typer.Option("mean", "--pool", help="mean | cls | max"),
    output: Path = typer.Option(Path("embeddings.parquet"), "--output", "-o"),  # noqa: B008
) -> None:
    """Embed a corpus with a sentence-transformer model and save the matrix to parquet."""
    try:
        from bitig.features.embeddings import SentenceEmbeddingExtractor
    except ImportError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    corpus = load_corpus(path, metadata=metadata)
    ex = SentenceEmbeddingExtractor(model=model, pool=pool)  # type: ignore[arg-type]
    fm = ex.fit_transform(corpus)
    fm.as_dataframe().to_parquet(output)
    console.print(f"[green]wrote[/green] {output} ({fm.X.shape[0]} docs x {fm.n_features} dims)")
