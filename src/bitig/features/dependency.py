"""Dependency bigram feature extractor — (head_lemma, dep_label, child_lemma) triples."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from bitig.corpus import Corpus
from bitig.features.base import BaseFeatureExtractor
from bitig.plumbing.textnorm import fold_lower
from bitig.preprocess.pipeline import SpacyPipeline


class DependencyBigramExtractor(BaseFeatureExtractor):
    feature_type = "dependency_bigram"

    def __init__(
        self,
        *,
        spacy_model: str = "en_core_web_trf",
        cache_dir: str | Path = ".bitig/cache/docbin",
        lowercase: bool = True,
    ) -> None:
        self.spacy_model = spacy_model
        # Stored as str so that sklearn `get_params()` yields a JSON-serialisable config
        # (used by the FeatureMatrix provenance hash).
        self.cache_dir = str(cache_dir)
        self.lowercase = lowercase
        self._vocabulary: list[str] = []
        self._pipeline: SpacyPipeline | None = None

    def _pipe(self) -> SpacyPipeline:
        if self._pipeline is None:
            self._pipeline = SpacyPipeline(model=self.spacy_model, cache_dir=self.cache_dir)
        return self._pipeline

    def _triples(self, spacy_doc: object) -> list[str]:
        out = []
        for tok in spacy_doc:  # type: ignore[attr-defined]
            if tok.is_space or tok.head is tok:  # skip whitespace tokens and root-self-loops
                continue
            head_lemma = fold_lower(tok.head.lemma_) if self.lowercase else tok.head.lemma_
            child_lemma = fold_lower(tok.lemma_) if self.lowercase else tok.lemma_
            out.append(f"{head_lemma}|{tok.dep_}|{child_lemma}")
        return out

    def _fit(self, corpus: Corpus) -> None:
        parsed = self._pipe().parse(corpus)
        counter: Counter[str] = Counter()
        for spacy_doc in parsed.spacy_docs():
            counter.update(self._triples(spacy_doc))
        self._vocabulary = sorted(counter.keys())

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        index = {t: i for i, t in enumerate(self._vocabulary)}
        parsed = self._pipe().parse(corpus)
        X = np.zeros((len(corpus), len(self._vocabulary)), dtype=float)  # noqa: N806
        for row, spacy_doc in enumerate(parsed.spacy_docs()):
            for triple in self._triples(spacy_doc):
                if triple in index:
                    X[row, index[triple]] += 1
        return X, list(self._vocabulary)
