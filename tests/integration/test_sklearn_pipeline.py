"""Integration test — bitig extractors and delta classifiers compose cleanly in sklearn.Pipeline
with cross_validate + LeaveOneGroupOut CV.

This is the load-bearing demonstration that our architectural promise of sklearn compatibility
holds end-to-end.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.model_selection import LeaveOneGroupOut, cross_val_score
from sklearn.pipeline import Pipeline

from bitig.features import MFWExtractor
from bitig.io import load_corpus
from bitig.methods.delta import BurrowsDelta

pytestmark = pytest.mark.integration


FED = "tests/fixtures/federalist"


def test_pipeline_with_mfw_and_burrows_classifies() -> None:
    corpus = load_corpus(FED, metadata=f"{FED}/metadata.tsv")
    train = corpus.filter(role="train")
    y = np.array(train.metadata_column("author"))

    pipe = Pipeline(
        [
            ("feat", MFWExtractor(n=300, min_df=2, scale="zscore", lowercase=True)),
            ("clf", BurrowsDelta()),
        ]
    )

    pipe.fit(train, y)
    preds = pipe.predict(train)
    assert preds.shape == (len(train),)


def test_cross_val_score_with_leave_one_group_out() -> None:
    corpus = load_corpus(FED, metadata=f"{FED}/metadata.tsv")
    train = corpus.filter(role="train")
    y = np.array(train.metadata_column("author"))

    pipe = Pipeline(
        [
            ("feat", MFWExtractor(n=300, min_df=2, scale="zscore", lowercase=True)),
            ("clf", BurrowsDelta()),
        ]
    )

    groups = np.empty(len(y), dtype=int)
    for label in np.unique(y):
        positions = np.flatnonzero(y == label)
        groups[positions] = np.arange(len(positions)) % 2
    scores = cross_val_score(
        pipe, train, y, cv=LeaveOneGroupOut(), groups=groups, scoring="accuracy"
    )
    assert scores.shape[0] == 2
    assert np.isfinite(scores).all()
