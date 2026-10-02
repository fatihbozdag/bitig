"""Rolling Delta -- sliding-window authorship attribution.

For each target document, slide a fixed-size token window and project each
window through an MFW vocabulary fit on the *training* corpus only (target
documents are excluded from the fit so MFW frequencies and z-score statistics
do not leak target tokens into the training distribution). At each window we
compute the configured Delta variant against every candidate author centroid
and report the nearest author plus per-author distances.

This is the schema-stable companion to the regular delta runner branch:
training and targets share the same corpus, but the `target_ids` list flags
which documents are scanned and which contribute to the centroids.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bitig.corpus import Corpus
from bitig.features.mfw import MFWExtractor
from bitig.methods.delta import (
    ArgamonLinearDelta,
    BurrowsDelta,
    CosineDelta,
    EderDelta,
    EderSimpleDelta,
    QuadraticDelta,
)
from bitig.result import Result

_BASE_DELTA: dict[str, type] = {
    "burrows": BurrowsDelta,
    "cosine": CosineDelta,
    "argamon_linear": ArgamonLinearDelta,
    "quadratic": QuadraticDelta,
    "eder": EderDelta,
    "eder_simple": EderSimpleDelta,
}


class RollingDelta:
    """Sliding-window Delta authorship attributor.

    Parameters
    ----------
    target_ids : list[str]
        Document ids to scan. Every other document in the corpus is training.
    group_by : str
        Metadata column that names the candidate author for each training doc.
    window_size : int
        Window length in tokens. Default 5000 follows Eder (2016)'s "rolling
        classify" sweet spot for English prose; halve it for shorter corpora.
    step : int | None
        Stride between successive windows. `None` -> `max(1, window_size // 10)`.
    base_delta : str
        Distance kernel; one of `burrows`, `cosine`, `argamon_linear`,
        `quadratic`, `eder`, `eder_simple`.
    mfw_n : int
        Top-N MFW vocabulary size. Fit on the training corpus only.
    lowercase : bool
        Case-fold during tokenisation. Defaults to True for stylometric work.
    """

    def __init__(
        self,
        *,
        target_ids: list[str],
        group_by: str,
        window_size: int = 5000,
        step: int | None = None,
        base_delta: str = "burrows",
        mfw_n: int = 200,
        lowercase: bool = True,
    ) -> None:
        if base_delta not in _BASE_DELTA:
            raise ValueError(f"unknown base_delta {base_delta!r} (known: {sorted(_BASE_DELTA)})")
        if not target_ids:
            raise ValueError("rolling_delta requires at least one target_id")
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.target_ids = list(target_ids)
        self.group_by = group_by
        self.window_size = int(window_size)
        self.step = int(step) if step is not None else max(1, self.window_size // 10)
        self.base_delta = base_delta
        self.mfw_n = int(mfw_n)
        self.lowercase = lowercase

    def fit_transform(self, corpus: Corpus) -> Result:
        target_set = set(self.target_ids)
        train_docs = [d for d in corpus.documents if d.id not in target_set]
        target_docs = [d for d in corpus.documents if d.id in target_set]
        if not train_docs:
            raise ValueError(
                "rolling_delta needs at least one training document outside target_ids"
            )
        if not target_docs:
            raise ValueError(
                f"none of target_ids {self.target_ids!r} match documents in the corpus"
            )

        train_corpus = Corpus(documents=train_docs, language=corpus.language)
        mfw = MFWExtractor(n=self.mfw_n, scale="zscore", lowercase=self.lowercase)
        train_fm = mfw.fit_transform(train_corpus)

        y_train = np.array(train_corpus.metadata_column(self.group_by))
        if any(v is None for v in y_train):
            raise ValueError(f"some training documents lack metadata column {self.group_by!r}")
        clf = _BASE_DELTA[self.base_delta]().fit(train_fm, y_train)
        authors = [str(a) for a in clf.classes_]

        # Windows are projected with the training vocabulary and z-score statistics.

        rows: list[dict[str, object]] = []
        for doc in target_docs:
            tokens = mfw.tokenise(doc.text)
            n_tokens = len(tokens)
            if n_tokens < self.window_size:
                raise ValueError(
                    f"target {doc.id!r} has {n_tokens} tokens, "
                    f"less than window_size {self.window_size}"
                )
            for w_idx, start in enumerate(range(0, n_tokens - self.window_size + 1, self.step)):
                window = tokens[start : start + self.window_size]
                vec = mfw.project_tokens(window)
                # decision_function returns -distance; invert to recover the distance.
                neg_dists = clf.decision_function(vec.reshape(1, -1))[0]
                dists = -neg_dists
                row: dict[str, object] = {
                    "doc_id": doc.id,
                    "window_idx": int(w_idx),
                    "window_start_token": int(start),
                    "window_end_token": int(start + self.window_size),
                    "nearest_author": authors[int(np.argmin(dists))],
                }
                for a, d in zip(authors, dists, strict=True):
                    row[f"distance_{a}"] = float(d)
                rows.append(row)

        table = pd.DataFrame(rows)
        return Result(
            method_name=f"rolling_delta_{self.base_delta}",
            params={
                "target_ids": self.target_ids,
                "group_by": self.group_by,
                "window_size": self.window_size,
                "step": self.step,
                "base_delta": self.base_delta,
                "mfw_n": self.mfw_n,
                "lowercase": self.lowercase,
            },
            values={
                "authors": authors,
                "target_ids": self.target_ids,
                "n_windows": len(rows),
            },
            tables=[table],
        )
