"""Tests for sklearn classifier wrappers and LOAO CV."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.base import is_classifier

from bitig.corpus import Corpus, Document
from bitig.features import FeatureMatrix, MFWExtractor
from bitig.methods.classify import build_classifier, cross_validate_bitig


def _corpus() -> Corpus:
    docs = []
    rng = np.random.default_rng(42)
    for i in range(20):
        author = "A" if i < 10 else "B"
        text = " ".join(rng.choice(["the", "of", "and", "to", "a"], size=100))
        docs.append(Document(id=f"d{i}", text=text, metadata={"author": author}))
    return Corpus(documents=docs)


def test_build_classifier_logreg() -> None:
    clf = build_classifier("logreg", random_state=42)
    assert is_classifier(clf)


def test_build_classifier_svm_linear() -> None:
    clf = build_classifier("svm_linear", random_state=42)
    assert is_classifier(clf)


def test_build_classifier_rejects_unknown() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown"):
        build_classifier("nonsense")


def test_cross_validate_bitig_loao() -> None:
    corpus = _corpus()
    y = np.array(corpus.metadata_column("author"))
    mfw = MFWExtractor(n=5, scale="zscore", lowercase=True)
    X_fm = mfw.fit_transform(corpus)
    # Use four interleaved groups (0..3), each spanning both classes, so every
    # LOAO fold still has both classes in the training set (required by LogisticRegression).
    groups = np.array([i % 4 for i in range(20)])
    report = cross_validate_bitig(
        build_classifier("logreg", random_state=42),
        X_fm,
        y,
        cv_kind="loao",
        groups_from=groups,
    )
    assert "accuracy" in report
    assert "per_class" in report


def test_cross_validate_bitig_stratified() -> None:
    corpus = _corpus()
    y = np.array(corpus.metadata_column("author"))
    mfw = MFWExtractor(n=5, scale="zscore", lowercase=True)
    X_fm = mfw.fit_transform(corpus)
    report = cross_validate_bitig(
        build_classifier("rf", random_state=42),
        X_fm,
        y,
        cv_kind="stratified",
        folds=5,
    )
    assert "accuracy" in report


def test_cross_validate_seed_controls_stratified_folds() -> None:
    """Different seeds must produce different stratified fold assignments.

    Regression test for the audit finding that classify.py hardcoded random_state=42
    regardless of study.seed, making CV non-reproducible under user-supplied seeds.
    """
    corpus = _corpus()
    y = np.array(corpus.metadata_column("author"))
    mfw = MFWExtractor(n=5, scale="zscore", lowercase=True)
    X_fm = mfw.fit_transform(corpus)

    report_a = cross_validate_bitig(
        build_classifier("rf", random_state=0),
        X_fm,
        y,
        cv_kind="stratified",
        folds=5,
        seed=1,
    )
    report_b = cross_validate_bitig(
        build_classifier("rf", random_state=0),
        X_fm,
        y,
        cv_kind="stratified",
        folds=5,
        seed=999,
    )
    # Same seed must reproduce exactly.
    report_a2 = cross_validate_bitig(
        build_classifier("rf", random_state=0),
        X_fm,
        y,
        cv_kind="stratified",
        folds=5,
        seed=1,
    )
    assert np.array_equal(report_a["predictions"], report_a2["predictions"])
    # Different seeds must produce different fold assignments (and thus different
    # cross_val_predict output on this dataset).
    assert not np.array_equal(report_a["predictions"], report_b["predictions"])


def test_extractor_is_refit_inside_each_fold() -> None:
    """Held-out documents must not shape the MFW vocabulary (audit 2026-09-26 P2)."""
    from bitig.corpus import Corpus, Document
    from bitig.features.mfw import MFWExtractor

    seen_fits: list[set[str]] = []

    class Spy(MFWExtractor):
        def _fit(self, corpus):  # type: ignore[no-untyped-def]
            seen_fits.append({d.id for d in corpus.documents})
            super()._fit(corpus)

    docs = [
        Document(id=f"{a}{i}", text=f"{a} " * 5 + "the of and " * 3)
        for a in ("x", "y")
        for i in range(4)
    ]
    y = np.array([d.id[0] for d in docs])
    cross_validate_bitig(
        build_classifier("logreg"),
        None,
        y,
        cv_kind="stratified",
        folds=4,
        extractor=Spy(n=5, scale="zscore"),
        corpus=Corpus(documents=docs),
    )
    assert seen_fits and all(len(ids) == 6 for ids in seen_fits)  # 8 docs, 4 folds


@pytest.mark.parametrize("groups", ["same", "relabelled"])
def test_loao_rejects_groups_that_relabel_the_target(groups: str) -> None:
    y = np.array(["a", "a", "b", "b", "c", "c"])
    g = y if groups == "same" else np.array(["1", "1", "2", "2", "3", "3"])
    fm = FeatureMatrix(
        X=np.eye(6), document_ids=list("123456"), feature_names=list("abcdef"), feature_type="t"
    )
    with pytest.raises(ValueError, match="relabelling"):
        cross_validate_bitig(build_classifier("logreg"), fm, y, cv_kind="loao", groups_from=g)
