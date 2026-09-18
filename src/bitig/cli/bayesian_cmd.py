"""`bitig bayesian <corpus>` — Bayesian authorship attribution."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import typer
from rich.console import Console
from rich.table import Table

from bitig.features import MFWExtractor
from bitig.io import load_corpus

console = Console()


def bayesian_command(
    path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),  # noqa: B008
    metadata: Path = typer.Option(  # noqa: B008
        ..., "--metadata", "-m", exists=True, dir_okay=False
    ),
    group_by: str = typer.Option("author", "--group-by"),
    test_filter: str | None = typer.Option(
        None, "--test-filter", help="key=value selecting held-out documents"
    ),
    mfw: int = typer.Option(500, "--mfw"),
    prior_alpha: float = typer.Option(1.0, "--prior-alpha"),
) -> None:
    """Wallace-Mosteller Bayesian authorship attribution."""
    try:
        from bitig.methods.bayesian import BayesianAuthorshipAttributor
    except ImportError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    corpus = load_corpus(path, metadata=metadata)
    if test_filter:
        key, separator, value = test_filter.partition("=")
        if not separator or not key or not value:
            raise typer.BadParameter("test-filter must be key=value")
        test = corpus.filter(**{key: value})
        train_docs = [d for d in corpus.documents if d not in test.documents]
        from bitig.corpus import Corpus

        train = Corpus(documents=train_docs, language=corpus.language)
        if not train.documents or not test.documents:
            raise typer.BadParameter("test-filter must select a nonempty proper subset")
    else:
        train = corpus
        test = corpus

    ex = MFWExtractor(n=mfw, min_df=2, scale="none", lowercase=True)
    train_fm = ex.fit_transform(train)
    test_fm = ex.transform(test)

    clf = BayesianAuthorshipAttributor(prior_alpha=prior_alpha).fit(
        train_fm, np.array(train.metadata_column(group_by))
    )
    preds = clf.predict(test_fm)
    probs = clf.predict_proba(test_fm)

    evaluation = "held-out" if test_filter else "in-sample (not a generalization estimate)"
    table = Table(
        title=f"Bayesian attribution — {evaluation}; prior_alpha={prior_alpha}, mfw={mfw}"
    )
    table.add_column("doc_id", style="cyan")
    table.add_column(f"{group_by} (observed)")
    table.add_column("predicted")
    table.add_column("max p(author)")
    for doc, pred, prob in zip(test.documents, preds, probs, strict=True):
        observed = doc.metadata.get(group_by, "<unknown>")
        table.add_row(doc.id, str(observed), str(pred), f"{prob.max():.3f}")
    console.print(table)
