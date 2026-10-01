"""`bitig cluster <corpus>` — hierarchical / k-means / HDBSCAN clustering of the MFW matrix."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from bitig.features import MFWExtractor
from bitig.io import load_corpus
from bitig.methods.cluster import HDBSCANCluster, HierarchicalCluster, KMeansCluster

console = Console()


def cluster_command(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),  # noqa: B008
    metadata: Path | None = typer.Option(None, "--metadata", "-m", exists=True, dir_okay=False),  # noqa: B008
    method: str = typer.Option("hierarchical", "--method", help="hierarchical | kmeans | hdbscan"),
    n_clusters: int = typer.Option(2, "--n-clusters"),
    linkage: str = typer.Option(
        "ward", "--linkage", help="For hierarchical: ward | average | complete | single"
    ),
    mfw: int = typer.Option(500, "--mfw"),
    seed: int = typer.Option(42, "--seed", help="Random seed for kmeans initialisation."),
    output: Path = typer.Option(Path("cluster.parquet"), "--output", "-o"),  # noqa: B008
) -> None:
    """Cluster corpus MFW matrix; save per-document labels to parquet + print a summary."""
    corpus = load_corpus(path, metadata=metadata)
    fm = MFWExtractor(n=mfw, min_df=2, scale="zscore", lowercase=True).fit_transform(corpus)
    if method == "hierarchical":
        result = HierarchicalCluster(n_clusters=n_clusters, linkage=linkage).fit_transform(fm)
    elif method == "kmeans":
        result = KMeansCluster(n_clusters=n_clusters, random_state=seed).fit_transform(fm)
    elif method == "hdbscan":
        result = HDBSCANCluster(min_cluster_size=max(2, n_clusters)).fit_transform(fm)
    else:
        console.print(f"[red]error:[/red] unknown method {method!r}")
        raise typer.Exit(code=1)
    labels = result.values["labels"]
    df = pd.DataFrame({"document_id": fm.document_ids, "cluster": labels})
    df.to_parquet(output)
    table = Table(title=f"clustering — {method}")
    table.add_column("cluster")
    table.add_column("documents")
    for cluster_id, grp in df.groupby("cluster"):
        table.add_row(str(cluster_id), ", ".join(grp["document_id"].tolist()))
    console.print(table)
    console.print(f"[green]wrote[/green] {output}")
