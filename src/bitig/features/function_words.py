"""Function-word frequency extractor with per-language bundled word lists."""

from __future__ import annotations

import re
from importlib import resources
from typing import Literal

import numpy as np

from bitig.corpus import Corpus
from bitig.features.base import BaseFeatureExtractor
from bitig.languages import LANGUAGES

Scale = Literal["none", "zscore", "l1", "l2"]

# Words with internal apostrophes stay whole (don't, l'homme); the bundled lists
# contain contractions (en) and elided forms ending in an apostrophe (fr: l', qu').
_RSQUO = "\u2019"  # typographic apostrophe, normalised to "'"
_WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*'?", flags=re.UNICODE)


def _tokens(text: str, index: dict[str, int]) -> list[str]:
    """Lower-cased tokens to match against the word list.

    A token like ``l'homme`` yields its elided prefix ``l'`` when that is a
    listed function word, plus ``homme``; ``don't`` stays one token.
    """
    out: list[str] = []
    for raw in _WORD_RE.findall(text.lower().replace(_RSQUO, "'")):
        if raw in index or "'" not in raw:
            out.append(raw)
            continue
        head, _, rest = raw.partition("'")
        if head + "'" in index:
            out.append(head + "'")
            if rest:
                out.extend(_tokens(rest, index))
        else:
            out.append(raw)
    return out


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
        self.wordlist = wordlist
        self.language = language
        self.scale = scale
        self._words: list[str] = []
        self._column_means: np.ndarray | None = None
        self._column_stds: np.ndarray | None = None

    def _fit(self, corpus: Corpus) -> None:
        if self.wordlist is not None:
            self._words = [w.lower().replace(_RSQUO, "'") for w in self.wordlist]
        else:
            lang = self.language or corpus.language
            self._words = _load_bundled_list(lang)
        if self.scale == "zscore":
            # z-score relative frequencies (count / document tokens), as MFW does;
            # 'zscore' used to be accepted and silently return raw counts.
            rel = self._relative_frequencies(corpus)
            self._column_means = rel.mean(axis=0)
            stds = rel.std(axis=0, ddof=0)
            stds[stds == 0] = 1.0
            self._column_stds = stds

    def _counts(self, corpus: Corpus) -> tuple[np.ndarray, np.ndarray]:
        """(function-word counts, total word tokens) per document."""
        index = {w: i for i, w in enumerate(self._words)}
        X = np.zeros((len(corpus), len(self._words)), dtype=float)  # noqa: N806
        lengths = np.zeros(len(corpus), dtype=float)
        for row, doc in enumerate(corpus.documents):
            toks = _tokens(doc.text, index)
            lengths[row] = len(toks)
            for tok in toks:
                j = index.get(tok)
                if j is not None:
                    X[row, j] += 1
        return X, lengths

    def _relative_frequencies(self, corpus: Corpus) -> np.ndarray:
        X, lengths = self._counts(corpus)  # noqa: N806
        lengths[lengths == 0] = 1.0
        return X / lengths[:, None]  # type: ignore[no-any-return]

    def _transform(self, corpus: Corpus) -> tuple[np.ndarray, list[str]]:
        if self.scale == "zscore":
            assert self._column_means is not None and self._column_stds is not None
            rel = self._relative_frequencies(corpus)
            return (rel - self._column_means) / self._column_stds, list(self._words)
        X, _ = self._counts(corpus)  # noqa: N806
        if self.scale == "l1":
            row_sums = X.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1.0
            X = X / row_sums  # noqa: N806
        elif self.scale == "l2":
            row_norms = np.linalg.norm(X, axis=1, keepdims=True)
            row_norms[row_norms == 0] = 1.0
            X = X / row_norms  # noqa: N806
        return X, list(self._words)
