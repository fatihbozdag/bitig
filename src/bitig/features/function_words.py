"""Function-word frequency extractor with per-language bundled word lists."""

from __future__ import annotations

import re
from importlib import resources
from typing import Literal

import numpy as np

from bitig.corpus import Corpus
from bitig.features.base import BaseFeatureExtractor
from bitig.languages import LANGUAGES
from bitig.plumbing.textnorm import fold_lower

Scale = Literal["none", "zscore", "l1", "l2"]

_WORD_RE = re.compile(r"[^\W\d_]+", flags=re.UNICODE)


def _load_bundled_list(language: str) -> list[str]:
    """Load resources/languages/<lang>/function_words.txt.

    Raises FileNotFoundError with a helpful message listing supported languages if no list is
    bundled for `language`.
    """
    pkg = f"bitig.resources.languages.{language}"
    try:
        path = resources.files(pkg) / "function_words.txt"
    except (ModuleNotFoundError, FileNotFoundError) as e:
        supported = sorted(LANGUAGES)
        raise FileNotFoundError(
            f"No bundled function word list for language {language!r}. "
            f"Supported: {supported}. Pass wordlist=[...] to override."
        ) from e
    if not path.is_file():
        supported = sorted(LANGUAGES)
        raise FileNotFoundError(
            f"No bundled function word list for language {language!r} "
            f"(expected at {path}). Supported: {supported}. Pass wordlist=[...] to override."
        )
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class FunctionWordExtractor(BaseFeatureExtractor):
    feature_type = "function_word"

    def __init__(
        self,
        *,
        wordlist: list[str] | None = None,
        language: str | None = None,
        scale: Scale = "none",
    ) -> None:
        if scale not in ("none", "zscore", "l1", "l2"):
            raise ValueError(f"unknown scale {scale!r}")
        self._column_means: np.ndarray | None = None
        self._column_stds: np.ndarray | None = None
        self.wordlist = wordlist
        self.language = language
        self.scale = scale
        self._words: list[str] = []

    def _fit(self, corpus: Corpus) -> None:
        if self.wordlist is not None:
            self._words = list(self.wordlist)
        else:
            lang = self.language or corpus.language
            self._words = _load_bundled_list(lang)
        if self.scale == "zscore":
            counts = self._raw_counts(corpus)
            self._column_means = counts.mean(axis=0)
            self._column_stds = counts.std(axis=0)
            self._column_stds[self._column_stds == 0] = 1.0

    def _raw_counts(self, corpus: Corpus) -> np.ndarray:
        index = {fold_lower(w): i for i, w in enumerate(self._words)}
        X = np.zeros((len(corpus), len(self._words)), dtype=float)  # noqa: N806
        for row, doc in enumerate(corpus.documents):
            for tok in _WORD_RE.findall(fold_lower(doc.text)):
                if tok in index:
                    X[row, index[tok]] += 1
        return X

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        X = self._raw_counts(corpus)  # noqa: N806
        if self.scale == "zscore":
            assert self._column_means is not None and self._column_stds is not None
            X = (X - self._column_means) / self._column_stds  # noqa: N806
        elif self.scale == "l1":
            row_sums = X.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1.0
            X = X / row_sums  # noqa: N806
        elif self.scale == "l2":
            row_norms = np.linalg.norm(X, axis=1, keepdims=True)
            row_norms[row_norms == 0] = 1.0
            X = X / row_norms  # noqa: N806
        return X, list(self._words)
