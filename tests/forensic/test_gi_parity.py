"""The two General Impostors implementations agree on clear cases (audit 2026-09-26 P2).

methods.imposters.GeneralImposters (corpus-level, author centroids, used by the
runner / Cases) and forensic.verify.GeneralImpostors (document-level, feature
matrices) answer slightly different questions, so their scores differ; on texts
whose authorship is unambiguous they must reach the same verdict.
"""

from __future__ import annotations

import numpy as np
import pytest

from bitig.corpus import Corpus, Document
from bitig.features.mfw import MFWExtractor
from bitig.forensic.verify import GeneralImpostors
from bitig.methods.imposters import GeneralImposters

_VOCAB = {
    "A": ["the", "of", "and", "garden", "rabbit"],
    "B": ["but", "that", "with", "office", "memo"],
    "C": ["yet", "upon", "into", "studio", "paint"],
    "D": ["so", "when", "from", "harbour", "boat"],
    "E": ["or", "while", "about", "forest", "deer"],
}


def _text(author: str, seed: int) -> str:
    rng = np.random.default_rng(seed)
    common = ["it", "was", "a", "to", "in"]
    return " ".join(rng.choice(_VOCAB[author] + common, size=400).tolist())


def _corpus(questioned_author: str) -> Corpus:
    docs = [
        Document(id=f"{a}{i}", text=_text(a, 10 * ord(a) + i), metadata={"author": a})
        for a in _VOCAB
        for i in range(4)
    ]
    docs.append(Document(id="Q", text=_text(questioned_author, 999), metadata={}))
    return Corpus(documents=docs)


def _centroid_score(corpus: Corpus) -> tuple[float, float]:
    res = GeneralImposters(
        target_ids=["Q"], candidate="A", group_by="author", n_iter=60, mfw_n=40, seed=3
    ).fit_transform(corpus)
    return float(res.values["scores"]["Q"]), float(res.values["chance"])


def _document_score(corpus: Corpus) -> float:
    mfw = MFWExtractor(n=40, scale="zscore", lowercase=True).fit(corpus)

    def fm(ids: list[str]):  # type: ignore[no-untyped-def]
        return mfw.transform(Corpus(documents=[d for d in corpus.documents if d.id in ids]))

    known = [f"A{i}" for i in range(4)]
    impostors = [d.id for d in corpus.documents if d.id[0] in "BCDE"]
    res = GeneralImpostors(n_iterations=60, seed=3).verify(
        questioned=fm(["Q"]), known=fm(known), impostors=fm(impostors)
    )
    return float(res.values["score"])


@pytest.mark.parametrize(("author", "same"), [("A", True), ("B", False), ("D", False)])
def test_both_implementations_reach_the_same_verdict(author: str, same: bool) -> None:
    corpus = _corpus(author)
    centroid, chance = _centroid_score(corpus)
    document = _document_score(corpus)
    if same:
        assert centroid > 0.9 and document > 0.9
    else:
        assert centroid < chance and document < 0.2
