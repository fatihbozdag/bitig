"""`bitig classify <corpus>` — sklearn classifier + CV report."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import typer
from rich.console import Console
from rich.table import Table

from bitig.features import MFWExtractor
from bitig.io import load_corpus
from bitig.methods.classify import build_classifier, cross_validate_bitig

console = Console()


def classify_command(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),  # noqa: B008
    metadata: Path = typer.Option(..., "--metadata", "-m", exists=True, dir_okay=False),  # noqa: B008
    estimator: str = typer.Option("logreg", "--estimator"),
    group_by: str = typer.Option("author", "--group-by"),
    cv_kind: str = typer.Option("stratified", "--cv-kind"),
    groups_by: str | None = typer.Option(
        None,
        "--groups-by",
        help="Metadata column to GROUP folds by for cv-kind=loao (must differ from --group-by, "
        "so the held-out group isn't the classification target). Defaults to --group-by, which "
        "is rejected as degenerate.",
    ),
    folds: int = typer.Option(5, "--folds"),
    mfw: int = typer.Option(500, "--mfw"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    """Fit+cross-validate a classifier and print per-author metrics."""
    corpus = load_corpus(path, metadata=metadata)
    y = np.array(corpus.metadata_column(group_by))

    groups: np.ndarray | None = None
    if cv_kind == "loao":
        col = groups_by or group_by
        groups = np.array(corpus.metadata_column(col))
        # Grouping by the target holds out every instance of each class, so the
        # held-out class is never in training → ~0 accuracy. Refuse loudly
        # rather than reporting a meaningless score (audit P1.16).
        if np.array_equal(groups, y):
            console.print(
                f"[red]error:[/red] cv-kind=loao groups by {col!r}, which is identical to the "
                f"classification target ({group_by!r}). LeaveOneGroupOut would hold out every "
                f"target class and yield ~0 accuracy. Pass --groups-by <other-column> "
                f"(e.g. a topic/source column), or use --cv-kind stratified."
            )
            raise typer.Exit(code=1)

    fm = MFWExtractor(n=mfw, min_df=2, scale="zscore", lowercase=True).fit_transform(corpus)
    clf = build_classifier(estimator, random_state=seed)
    report = cross_validate_bitig(
        clf,
        fm,
        y,
        cv_kind=cv_kind,
        groups_from=groups,
        folds=folds,
        seed=seed,
    )
    table = Table(title=f"classify — {estimator} / {cv_kind}")
    table.add_column("metric")
    table.add_column("value")
    table.add_row("accuracy", f"{report['accuracy']:.3f}")
    per_class = report["per_class"]
    if "macro avg" in per_class:
        table.add_row("macro_f1", f"{per_class['macro avg']['f1-score']:.3f}")
    console.print(table)
