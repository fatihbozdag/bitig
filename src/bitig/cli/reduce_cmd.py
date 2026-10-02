"""`bitig reduce <corpus>` — dimensionality reduction of the MFW feature matrix."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import typer
from rich.console import Console

from bitig.features import MFWExtractor
from bitig.io import load_corpus
from bitig.methods.reduce import MDSReducer, PCAReducer, TSNEReducer, UMAPReducer

console = Console()

_REDUCERS = {
    "pca": PCAReducer,
    "mds": MDSReducer,
    "tsne": TSNEReducer,
    "umap": UMAPReducer,
}


def reduce_command(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),  # noqa: B008
    metadata: Path | None = typer.Option(None, "--metadata", "-m", exists=True, dir_okay=False),  # noqa: B008
    method: str = typer.Option("pca", "--method", help="pca | mds | tsne | umap"),
    n_components: int = typer.Option(2, "--n-components"),
    mfw: int = typer.Option(500, "--mfw"),
    output: Path = typer.Option(Path("reduce.parquet"), "--output", "-o"),  # noqa: B008
) -> None:
    """Reduce corpus MFW matrix via PCA/MDS/t-SNE/UMAP; save coordinates to parquet."""
    if method not in _REDUCERS:
        console.print(f"[red]error:[/red] unknown method {method!r}")
        raise typer.Exit(code=1)
    corpus = load_corpus(path, metadata=metadata)
    fm = MFWExtractor(n=mfw, min_df=2, scale="zscore", lowercase=True).fit_transform(corpus)
    reducer = _REDUCERS[method](n_components=n_components)
    result = reducer.fit_transform(fm)
    coords: np.ndarray = result.values["coordinates"]
    df = pd.DataFrame(
        coords, index=fm.document_ids, columns=[f"c{i}" for i in range(coords.shape[1])]
    )
    df.to_parquet(output)
    console.print(
        f"[green]wrote[/green] {output} ({coords.shape[0]} docs x {coords.shape[1]} components)"
    )
