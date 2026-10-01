"""Feature scaling / tokenisation regressions (audit 2026-09-26 P2)."""

from __future__ import annotations

import numpy as np

from bitig.corpus import Corpus, Document
from bitig.features.function_words import FunctionWordExtractor
from bitig.features.ngrams import CharNgramExtractor, WordNgramExtractor


def _corpus(*texts: str, language: str = "en") -> Corpus:
    return Corpus(
        documents=[Document(id=f"d{i}", text=t) for i, t in enumerate(texts)],
        language=language,
    )


def test_function_word_zscore_is_applied() -> None:
    corpus = _corpus("the cat and the dog", "a cat of the house and more words here", "the")
    fm = FunctionWordExtractor(wordlist=["the", "and"], scale="zscore").fit_transform(corpus)
    rel_the = np.array([2 / 5, 1 / 9, 1 / 1])
    np.testing.assert_allclose(fm.X[:, 0], (rel_the - rel_the.mean()) / rel_the.std())
    assert abs(fm.X.mean(axis=0)).max() < 1e-12  # centred, i.e. not raw counts


def test_english_contractions_are_counted() -> None:
    corpus = _corpus("I don't know and can\u2019t say", "nothing here")
    fm = FunctionWordExtractor(language="en").fit_transform(corpus)
    names = list(fm.feature_names)
    assert fm.X[0, names.index("don't")] == 1
    assert fm.X[0, names.index("can't")] == 1  # typographic apostrophe normalised


def test_french_elided_forms_are_counted() -> None:
    corpus = _corpus("l'homme et l'enfant qu'il voit", "rien", language="fr")
    fm = FunctionWordExtractor(language="fr").fit_transform(corpus)
    names = list(fm.feature_names)
    assert fm.X[0, names.index("l'")] == 2
    assert fm.X[0, names.index("qu'")] == 1


def test_ngram_zscore_uses_relative_frequencies() -> None:
    """A text and its doubled copy have the same relative frequencies, so the same
    z-scored row; with raw counts the doubled copy would differ."""
    word = WordNgramExtractor(scale="zscore").fit_transform(
        _corpus("abab cdcd", "abab cdcd abab cdcd", "efef abab")
    )
    np.testing.assert_allclose(word.X[0], word.X[1])
    char = CharNgramExtractor(n=1, scale="zscore").fit_transform(_corpus("aab", "aabaab", "abbb"))
    np.testing.assert_allclose(char.X[0], char.X[1])


def test_ngram_max_features_caps_vocabulary() -> None:
    corpus = _corpus("one two three four five", "one two six seven")
    fm = WordNgramExtractor(max_features=3).fit_transform(corpus)
    assert fm.X.shape[1] == 3
