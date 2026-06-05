"""Craig's Zeta — contrastive-vocabulary extraction between two author/group populations.

Classical Zeta (Burrows 2007; Craig & Kinney 2009):
    zeta(w) = proportion_A(w) - proportion_B(w)
where proportion_X(w) = (# documents in X containing w) / (# documents in X).

Eder's variant (Eder 2017) adds Laplace smoothing so zero-count words don't explode under the
logarithmic variants some authors use.
"""

from __future__ import annotations

import re
from collections import Counter

import pandas as pd

from bitig.corpus import Corpus
from bitig.result import Result

_WORD_RE = re.compile(r"[^\W\d_]+", flags=re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text)]


class _ZetaBase:
    def __init__(
        self,
        *,
        group_by: str,
        top_k: int = 100,
        min_df: int = 2,
        group_a: str | None = None,
        group_b: str | None = None,
    ) -> None:
        self.group_by = group_by
        self.top_k = top_k
        self.min_df = min_df
        self.group_a = group_a
        self.group_b = group_b

    def _score(
        self,
        count_in_a: Counter[str],
        count_in_b: Counter[str],
        n_a: int,
        n_b: int,
        vocabulary: set[str],
    ) -> dict[str, float]:
        """Return ``{word: zeta}`` from per-group document-occurrence counts.

        Subclasses receive the raw counts and group sizes (not pre-divided
        proportions) so smoothing variants can apply add-k to the counts.
        """
        raise NotImplementedError

    def fit_transform(self, corpus: Corpus) -> Result:
        grouped = corpus.groupby(self.group_by)
        if len(grouped) < 2:
            raise ValueError("Zeta requires at least two groups in corpus.groupby(group_by)")

        if self.group_a is None or self.group_b is None:
            # Take the two with most documents, deterministically.
            ordered = sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            label_a, docs_a = ordered[0]
            label_b, docs_b = ordered[1]
        else:
            label_a, label_b = self.group_a, self.group_b
            docs_a = grouped[label_a]
            docs_b = grouped[label_b]

        n_a = len(docs_a)
        n_b = len(docs_b)

        count_in_a: Counter[str] = Counter()
        count_in_b: Counter[str] = Counter()
        for d in docs_a.documents:
            count_in_a.update(set(_tokens(d.text)))
        for d in docs_b.documents:
            count_in_b.update(set(_tokens(d.text)))

        # Cap min_df at each group's size so singleton groups still contribute vocabulary.
        min_df_a = min(self.min_df, n_a)
        min_df_b = min(self.min_df, n_b)
        vocabulary = {w for w, c in count_in_a.items() if c >= min_df_a}
        vocabulary |= {w for w, c in count_in_b.items() if c >= min_df_b}

        # proportion_* are kept for the output tables (display columns); the
        # score itself is computed from raw counts so smoothing variants work.
        proportion_a = {w: count_in_a.get(w, 0) / n_a for w in vocabulary}
        proportion_b = {w: count_in_b.get(w, 0) / n_b for w in vocabulary}
        scores = self._score(count_in_a, count_in_b, n_a, n_b, vocabulary)

        scored = sorted(scores.items(), key=lambda kv: kv[1])
        # Only include words with a directional preference for the group:
        # positive score → A-preferred, negative → B-preferred. Zero-score words are excluded
        # from both tables to avoid them leaking cross-group when vocabulary is small.
        a_preferred = [kv for kv in reversed(scored) if kv[1] > 0]
        b_preferred = [kv for kv in scored if kv[1] < 0]
        top_a = a_preferred[: self.top_k]
        top_b = b_preferred[: self.top_k]

        df_a = pd.DataFrame(
            [
                {"word": w, "zeta": s, "prop_a": proportion_a[w], "prop_b": proportion_b[w]}
                for w, s in top_a
            ]
        )
        df_b = pd.DataFrame(
            [
                {"word": w, "zeta": s, "prop_a": proportion_a[w], "prop_b": proportion_b[w]}
                for w, s in top_b
            ]
        )
        df_a.attrs["group"] = label_a
        df_b.attrs["group"] = label_b

        return Result(
            method_name=type(self).__name__,
            params={
                "group_by": self.group_by,
                "top_k": self.top_k,
                "min_df": self.min_df,
                "group_a": label_a,
                "group_b": label_b,
            },
            values={"group_a": label_a, "group_b": label_b, "n_a": n_a, "n_b": n_b},
            tables=[df_a, df_b],
            figures=[],
            provenance=None,
        )


class ZetaClassic(_ZetaBase):
    def _score(
        self,
        count_in_a: Counter[str],
        count_in_b: Counter[str],
        n_a: int,
        n_b: int,
        vocabulary: set[str],
    ) -> dict[str, float]:
        return {w: count_in_a.get(w, 0) / n_a - count_in_b.get(w, 0) / n_b for w in vocabulary}


class ZetaEder(_ZetaBase):
    """Eder 2017 variant with add-k (Laplace) smoothing on the per-group
    document-occurrence counts:

        prop_X(w) = (count_X(w) + k) / (n_X + 2k),  k = 0.5

    The +2k in the denominator is what makes this differ from classic Zeta —
    smoothing the *counts* (not the already-divided proportions) shrinks rare
    words toward 0.5 and keeps zero-count words from dominating the
    logarithmic Zeta variants. With k applied to proportions and a unit
    denominator the +k cancels in the difference, which is why the previous
    implementation was silently identical to ``ZetaClassic``.
    """

    _K = 0.5

    def _score(
        self,
        count_in_a: Counter[str],
        count_in_b: Counter[str],
        n_a: int,
        n_b: int,
        vocabulary: set[str],
    ) -> dict[str, float]:
        k = self._K
        return {
            w: (count_in_a.get(w, 0) + k) / (n_a + 2 * k)
            - (count_in_b.get(w, 0) + k) / (n_b + 2 * k)
            for w in vocabulary
        }
