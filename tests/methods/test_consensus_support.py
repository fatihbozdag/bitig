"""Consensus clade-support semantics (audit 2026-09-26 P2); fast, unlike test_consensus."""

from __future__ import annotations

import pytest

from bitig.corpus import Corpus
from bitig.methods.consensus import BootstrapConsensus


def _tiny_corpus() -> Corpus:
    from bitig.corpus import Document

    a = "the cat sat on the mat and the cat ran " * 20
    b = "the cat sat on a mat and the cat ran off " * 20
    c = "of which upon whilst moreover hence thus " * 20
    d = "of which upon whilst moreover hence thus therefore " * 20
    return Corpus(
        documents=[
            Document(id="a", text=a),
            Document(id="b", text=b),
            Document(id="c", text=c),
            Document(id="d", text=d),
        ]
    )


def test_subsample_root_is_not_counted_as_a_clade() -> None:
    """A 2-document subsample's root is not evidence that those two form a clade
    (audit 2026-09-26 P2: it was counted, inflating support)."""
    from bitig.corpus import Document

    docs = _tiny_corpus().documents[:3]
    result = BootstrapConsensus(mfw_bands=[5], replicates=10, subsample=0.67, seed=1).fit_transform(
        Corpus(documents=[Document(id=d.id, text=d.text) for d in docs])
    )
    assert result.values["support"] == {}


def test_support_is_relative_to_trees_containing_the_clade() -> None:
    full = BootstrapConsensus(mfw_bands=[8], replicates=5, subsample=1.0, seed=1).fit_transform(
        _tiny_corpus()
    )
    assert full.values["support"]["a,b"] == 1.0
    assert full.values["support"]["c,d"] == 1.0
    sub = BootstrapConsensus(mfw_bands=[8], replicates=30, subsample=0.75, seed=2).fit_transform(
        _tiny_corpus()
    )
    # Only trees containing both a and b count; in all of them a and b group together.
    assert sub.values["support"].get("a,b") == 1.0


@pytest.mark.parametrize(
    "kwargs", [{"subsample": 0.0}, {"subsample": 1.5}, {"support_threshold": 1.0}]
)
def test_invalid_params_raise(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        BootstrapConsensus(mfw_bands=[5], **kwargs)
