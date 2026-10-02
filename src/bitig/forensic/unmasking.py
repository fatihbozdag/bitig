"""Authorship verification via Koppel & Schler's Unmasking method (2004).

Unmasking is a distribution-free, long-text verification method complementing the General
Impostors (GI) approach. The intuition:

1. Chunk the questioned and known documents into equally-sized windows.
2. Train a binary classifier to distinguish Q-chunks from K-chunks.
3. Iteratively (a) measure CV accuracy, (b) remove the most discriminative features,
   (c) retrain. Track accuracy across rounds.
4. **Same-author** documents are stylistically similar: once a few surface-level differences
   are removed, the classifier collapses quickly. **Different-author** documents keep
   handing the classifier new discriminating features, so accuracy degrades slowly.

The accuracy-degradation curve is the signal. A large drop = same author; a slow drop =
different author. For forensic reporting, the curve itself is the scientifically-interpretable
output; a scalar summary (``accuracy_drop``) is provided for convenience.

Designed for long texts. Practical minimum: ~3 chunks per document after chunking — for a
chunk_size of 500 words, that requires ~1500 word documents on each side.

References
----------
Koppel, M., & Schler, J. (2004). Authorship verification as a one-class classification
    problem. Proceedings of ICML 2004, 489-495.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score

from bitig.corpus import Corpus, Document
from bitig.features.base import BaseFeatureExtractor
from bitig.result import Result


def _chunk_text(text: str, *, chunk_size: int, id_prefix: str) -> list[Document]:
    """Split ``text`` into Documents of ``chunk_size`` whitespace-separated words each.

    A trailing remainder of at least half a chunk becomes its own (shorter) chunk.
    A shorter remainder is merged into the previous chunk: kept on its own, a
    1-word tail counted as a full sample toward ``min_chunks_per_class`` and was
    trivially separable, distorting the accuracy curve (audit 2026-09-26 P2).
    """
    words = text.split()
    groups = [words[i : i + chunk_size] for i in range(0, len(words), chunk_size)]
    if len(groups) > 1 and len(groups[-1]) < chunk_size / 2:
        tail = groups.pop()
        groups[-1] = groups[-1] + tail
    return [
        Document(
            id=f"{id_prefix}_{i}",
            text=" ".join(chunk_words),
            metadata={"source_prefix": id_prefix},
        )
        for i, chunk_words in enumerate(groups)
        if chunk_words
    ]


def _normalise_to_corpus(
    obj: Corpus | Document | str, *, id_prefix: str, chunk_size: int
) -> list[Document]:
    """Convert any of the accepted input types into a list of chunk Documents."""
    if isinstance(obj, Corpus):
        all_chunks = []
        for i, doc in enumerate(obj.documents):
            all_chunks.extend(
                _chunk_text(doc.text, chunk_size=chunk_size, id_prefix=f"{id_prefix}_d{i}")
            )
        return all_chunks
    if isinstance(obj, Document):
        return _chunk_text(obj.text, chunk_size=chunk_size, id_prefix=id_prefix)
    if isinstance(obj, str):
        return _chunk_text(obj, chunk_size=chunk_size, id_prefix=id_prefix)
    raise TypeError(f"questioned/known must be Corpus, Document, or str; got {type(obj).__name__}")


class Unmasking:
    """Koppel & Schler (2004) Unmasking for authorship verification.

    Parameters
    ----------
    chunk_size : int
        Words per chunk. 500 is the common default in the literature.
    n_rounds : int
        Number of iteration rounds (each round eliminates ``n_eliminate`` features and
        retrains). 10 is the standard setting.
    n_eliminate : int
        Per-class top-N features to remove each round, following Koppel & Schler 2004:
        the N most Q-discriminating (top positive coefficients) *and* the N most
        K-discriminating (top negative coefficients), so up to 2 * N features drop per
        round. Default 3 (6 features per round), matching the classical literature setup.
    n_folds : int
        CV folds for accuracy estimation per round. Must be >= 2 and <= min(#Q chunks,
        #K chunks).
    min_chunks_per_class : int
        Minimum chunks required on each side before Unmasking is meaningful. Raises
        ValueError if either side falls below this threshold.
    seed : int
        Seed for the CV split's random state.

    Examples
    --------
    >>> from bitig.features import MFWExtractor
    >>> from bitig.forensic import Unmasking
    >>> unmasking = Unmasking(chunk_size=500, n_rounds=10, seed=42)
    >>> result = unmasking.verify(
    ...     questioned=questioned_text,
    ...     known=known_text,
    ...     extractor=MFWExtractor(n=200, scale="zscore", lowercase=True),
    ... )
    >>> result.values["accuracy_curve"]
    [0.82, 0.79, 0.70, 0.58, 0.55, ...]
    >>> result.values["accuracy_drop"]
    0.27  # large drop = same author; small drop = different author
    """

    def __init__(
        self,
        *,
        chunk_size: int = 500,
        n_rounds: int = 10,
        n_eliminate: int = 3,
        n_folds: int = 10,
        min_chunks_per_class: int = 3,
        seed: int = 42,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if n_rounds < 1:
            raise ValueError("n_rounds must be >= 1")
        if n_eliminate < 1:
            raise ValueError("n_eliminate must be >= 1")
        if n_folds < 2:
            raise ValueError("n_folds must be >= 2")
        if min_chunks_per_class < 2:
            raise ValueError("min_chunks_per_class must be >= 2")
        self.chunk_size = chunk_size
        self.n_rounds = n_rounds
        self.n_eliminate = n_eliminate
        self.n_folds = n_folds
        self.min_chunks_per_class = min_chunks_per_class
        self.seed = seed

    def verify(
        self,
        *,
        questioned: Corpus | Document | str,
        known: Corpus | Document | str,
        extractor: BaseFeatureExtractor,
    ) -> Result:
        """Run Unmasking and return the accuracy-degradation curve plus summary stats.

        Parameters
        ----------
        questioned : Corpus, Document, or str
            The questioned text.
        known : Corpus, Document, or str
            The candidate author's known text.
        extractor : BaseFeatureExtractor
            Any bitig feature extractor. Fit on the combined chunks, so the feature space
            is the union of terms seen in Q and K.

        Returns
        -------
        Result
            ``values["accuracy_curve"]`` (list of CV accuracies per round, length
            ``n_rounds``), ``values["accuracy_drop"]`` (accuracy at round 0 minus accuracy
            at final round), ``values["n_q_chunks"]``, ``values["n_k_chunks"]``.
        """
        q_chunks = _normalise_to_corpus(questioned, id_prefix="Q", chunk_size=self.chunk_size)
        k_chunks = _normalise_to_corpus(known, id_prefix="K", chunk_size=self.chunk_size)

        if len(q_chunks) < self.min_chunks_per_class:
            raise ValueError(
                f"questioned yielded only {len(q_chunks)} chunk(s); Unmasking needs at "
                f"least min_chunks_per_class={self.min_chunks_per_class}. Reduce "
                "chunk_size or supply a longer document."
            )
        if len(k_chunks) < self.min_chunks_per_class:
            raise ValueError(
                f"known yielded only {len(k_chunks)} chunk(s); Unmasking needs at least "
                f"min_chunks_per_class={self.min_chunks_per_class}. Reduce chunk_size or "
                "supply a longer document."
            )

        combined = Corpus(documents=q_chunks + k_chunks)
        fm = extractor.fit_transform(combined)
        y = np.array([1] * len(q_chunks) + [0] * len(k_chunks))
        X = fm.X.copy()  # noqa: N806 — will be mutated across rounds
        feature_names = list(fm.feature_names)

        folds = min(self.n_folds, len(q_chunks), len(k_chunks))
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=self.seed)

        # Majority-class baseline once features are exhausted. For imbalanced Q/K chunks
        # the "random" floor is not 0.5 but max(n_q, n_k) / (n_q + n_k).
        majority_baseline = max(len(q_chunks), len(k_chunks)) / (len(q_chunks) + len(k_chunks))

        accuracies: list[float] = []
        eliminated_per_round: list[list[str]] = []

        for round_idx in range(self.n_rounds):
            if X.shape[1] == 0:
                # No features left — classifier collapses to majority-class prediction.
                accuracies.extend([majority_baseline] * (self.n_rounds - round_idx))
                eliminated_per_round.extend([[]] * (self.n_rounds - round_idx))
                break
            clf = LogisticRegression(solver="lbfgs", max_iter=2000)
            scores = cross_val_score(clf, X, y, cv=cv, scoring="accuracy")
            accuracies.append(float(scores.mean()))

            # Refit on all data to pick features to eliminate this round.
            # Per Koppel & Schler 2004: eliminate top-N features most discriminative for EACH
            # class — the N features with the most-positive coefficients (most "Q-like") and
            # the N with the most-negative ("K-like"), giving up to 2N eliminations per round.
            clf.fit(X, y)
            coefs = clf.coef_.ravel()
            half = min(self.n_eliminate, X.shape[1])
            top_positive = np.argsort(coefs)[-half:]  # most Q-discriminating
            top_negative = np.argsort(coefs)[:half]  # most K-discriminating
            drop_idx = np.unique(np.concatenate([top_positive, top_negative]))
            eliminated = [feature_names[i] for i in drop_idx]
            keep = np.ones(X.shape[1], dtype=bool)
            keep[drop_idx] = False
            X = X[:, keep]  # noqa: N806
            feature_names = [f for f, k in zip(feature_names, keep, strict=True) if k]
            eliminated_per_round.append(eliminated)

        accuracy_drop = accuracies[0] - accuracies[-1]

        return Result(
            method_name="unmasking",
            params={
                "chunk_size": self.chunk_size,
                "n_rounds": self.n_rounds,
                "n_eliminate": self.n_eliminate,
                "n_folds": folds,
                "seed": self.seed,
                "extractor": type(extractor).__name__,
                "n_features_initial": fm.X.shape[1],
            },
            values={
                "accuracy_curve": accuracies,
                "accuracy_drop": float(accuracy_drop),
                "accuracy_initial": accuracies[0],
                "accuracy_final": accuracies[-1],
                "n_q_chunks": len(q_chunks),
                "n_k_chunks": len(k_chunks),
                "eliminated_per_round": eliminated_per_round,
            },
        )
