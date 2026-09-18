"""End-to-end: load corpus → MFW → reduce → cluster → zeta → classify, all within one script."""

from __future__ import annotations

import numpy as np
import pytest

from bitig.features import MFWExtractor
from bitig.io import load_corpus
from bitig.methods.classify import build_classifier, cross_validate_bitig
from bitig.methods.cluster import HierarchicalCluster
from bitig.methods.reduce import PCAReducer
from bitig.methods.zeta import ZetaClassic

pytestmark = pytest.mark.integration

FED = "tests/fixtures/federalist"


def test_phase3_end_to_end_workflow() -> None:
    corpus = load_corpus(FED, metadata=f"{FED}/metadata.tsv").filter(role="train")
    y = np.array(corpus.metadata_column("author"))

    fm = MFWExtractor(n=200, min_df=2, scale="zscore", lowercase=True).fit_transform(corpus)

    pca = PCAReducer(n_components=2).fit_transform(fm)
    assert pca.values["coordinates"].shape == (len(corpus), 2)

    clusters = HierarchicalCluster(n_clusters=3, linkage="ward").fit_transform(fm)
    assert len(clusters.values["labels"]) == len(corpus)

    zeta = ZetaClassic(
        group_by="author", top_k=5, group_a="Hamilton", group_b="Madison"
    ).fit_transform(corpus)
    assert len(zeta.tables) == 2

    report = cross_validate_bitig(
        build_classifier("logreg", random_state=42),
        corpus,
        y,
        extractor=MFWExtractor(n=200, min_df=2, scale="zscore", lowercase=True),
        cv_kind="stratified",
        folds=2,
    )
    assert 0.0 <= report["accuracy"] <= 1.0
