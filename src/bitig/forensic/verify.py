"""Authorship verification — the General Impostors (GI) method.

Verification (one-class, same/different-author decision) is the forensically canonical task:
real case-work rarely offers a closed candidate set, so the question is not "which of N authors
wrote this?" but "did *this specific* candidate write it, or did someone else?".

The General Impostors method (Koppel & Winter 2014; Seidman 2013) answers this by repeatedly
sampling a random feature subspace and a random subset of "impostor" documents drawn from
authors other than the candidate, then asking: in that subspace, is the questioned document
closer to the candidate's known writing than to any of the impostors? The fraction of
iterations in which the candidate wins is the verification score.

References
----------
Koppel, M., & Winter, Y. (2014). Determining if two documents are written by the same author.
    Journal of the Association for Information Science and Technology, 65(1), 178-187.
Seidman, S. (2013). Authorship verification using the impostors method. CLEF 2013 Working
    Notes (PAN Lab).
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from bitig.features import FeatureMatrix
from bitig.result import Result

Similarity = Literal["cosine", "minmax"]
Aggregate = Literal["centroid", "nearest"]


class GeneralImpostors:
    """Authorship verification via the General Impostors method.

    This is the document-level variant: Q is compared with the candidate's known
    documents and with individual impostor *documents* in precomputed feature
    matrices. :class:`bitig.methods.imposters.GeneralImposters` (used by
    ``bitig run`` and Forensic Lab Cases) is the corpus-level variant: it fits its
    own MFW space and compares Q with author *centroids*. Both sample
    ``ceil(sqrt(pool))`` impostors per iteration by default and return a win
    fraction in [0, 1]; neither score is a likelihood ratio. A parity test
    (``tests/forensic/test_gi_parity.py``) checks they agree on clear cases.

    Parameters
    ----------
    n_iterations : int
        Number of random feature-subspace + impostor-subsample iterations (Koppel & Winter
        2014 used 100; PAN baselines typically use 50-200).
    feature_subsample_rate : float
        Fraction of feature columns sampled per iteration, in (0, 1]. 0.5 is the classical
        default; smaller values increase variance but decorrelate impostor rankings.
    impostor_sample_size : int or None
        Number of impostors to sample per iteration. If None, uses
        ``ceil(sqrt(n_impostors))`` (a defensible default that scales sub-linearly with the
        pool size, so a large pool does not make every iteration trivially win).
    similarity : {"cosine", "minmax"}
        Similarity function used to compare the questioned document to the candidate and to
        each impostor.

        - ``cosine``: dot(u, v) / (||u|| * ||v||); works for any real-valued features.
        - ``minmax``: sum(min(u, v)) / sum(max(u, v)); Koppel et al.'s MinMax similarity,
          which requires non-negative features (e.g., raw relative frequencies). Raises if
          any feature in Q/known/impostors is negative.
    aggregate : {"centroid", "nearest"}
        How to build a single comparison point from the candidate's known documents:

        - ``centroid``: compare Q to the mean vector of the known samples (simple, standard).
        - ``nearest``: compare Q to the nearest known sample in the projected subspace.
          This gives the candidate its best of k chances per iteration, so it biases the
          score toward same-author (anti-conservative); calibrate under the same setting.
    seed : int
        Seed for the numpy random generator used to sample features and impostors.

    Examples
    --------
    >>> from bitig.forensic import GeneralImpostors
    >>> gi = GeneralImpostors(n_iterations=100, seed=42)
    >>> result = gi.verify(questioned=q_fm, known=known_fm, impostors=pool_fm)
    >>> result.values["score"]    # fraction of iterations where known beat all impostors
    0.87
    """

    def __init__(
        self,
        *,
        n_iterations: int = 100,
        feature_subsample_rate: float = 0.5,
        impostor_sample_size: int | None = None,
        similarity: Similarity = "cosine",
        aggregate: Aggregate = "centroid",
        seed: int = 42,
    ) -> None:
        if n_iterations < 1:
            raise ValueError("n_iterations must be >= 1")
        if not 0.0 < feature_subsample_rate <= 1.0:
            raise ValueError("feature_subsample_rate must lie in (0, 1]")
        if impostor_sample_size is not None and impostor_sample_size < 1:
            raise ValueError("impostor_sample_size must be >= 1 (or None for default)")
        if similarity not in ("cosine", "minmax"):
            raise ValueError(f"unknown similarity {similarity!r}")
        if aggregate not in ("centroid", "nearest"):
            raise ValueError(f"unknown aggregate {aggregate!r}")

        self.n_iterations = int(n_iterations)
        self.feature_subsample_rate = float(feature_subsample_rate)
        self.impostor_sample_size = impostor_sample_size
        self.similarity: Similarity = similarity
        self.aggregate: Aggregate = aggregate
        self.seed = int(seed)

    def verify(
        self,
        *,
        questioned: FeatureMatrix,
        known: FeatureMatrix,
        impostors: FeatureMatrix,
    ) -> Result:
        """Run the GI algorithm for one questioned document against one candidate's known set.

        Parameters
        ----------
        questioned : FeatureMatrix
            Exactly one row (the Q document).
        known : FeatureMatrix
            The candidate author's known documents (>= 1 row).
        impostors : FeatureMatrix
            Pool of documents from other authors (>= 2 rows so each iteration can sample
            distinct impostors even with the smallest default ``impostor_sample_size``).

        Returns
        -------
        Result
            With ``values["score"]`` in [0, 1] (higher = more likely same author),
            ``values["wins"]`` raw iteration-win count, and sampling counts in ``params``.

        Notes
        -----
        All three FeatureMatrix inputs must share the same feature space — i.e., identical
        ``feature_names`` in the same order. Callers that build features independently should
        use a single ``fit_transform`` on the pooled corpus and then slice by document id.
        """
        self._validate_inputs(questioned, known, impostors)

        q = questioned.X[0]
        k = known.X
        i_pool = impostors.X

        n_features = q.shape[0]
        n_impostors = i_pool.shape[0]
        k_per_iter = max(1, round(self.feature_subsample_rate * n_features))
        m_per_iter = self.impostor_sample_size or max(1, int(np.ceil(np.sqrt(n_impostors))))
        m_per_iter = min(m_per_iter, n_impostors)

        rng = np.random.default_rng(self.seed)
        wins = 0
        for _ in range(self.n_iterations):
            feat_idx = rng.choice(n_features, size=k_per_iter, replace=False)
            imp_idx = rng.choice(n_impostors, size=m_per_iter, replace=False)

            q_proj = q[feat_idx]
            k_proj = k[:, feat_idx]
            i_proj = i_pool[imp_idx][:, feat_idx]

            sim_k = self._similarity_to_candidate(q_proj, k_proj)
            sims_i = self._similarity_to_many(q_proj, i_proj)
            # Ties broken toward impostors (strict >) — the forensically conservative choice:
            # if Q is equally close to the candidate and an impostor, do not count it as a win.
            if sim_k > sims_i.max(initial=-np.inf):
                wins += 1

        score = wins / self.n_iterations

        return Result(
            method_name="general_impostors",
            params={
                "n_iterations": self.n_iterations,
                "feature_subsample_rate": self.feature_subsample_rate,
                "feature_sample_size": k_per_iter,
                "impostor_sample_size": m_per_iter,
                "similarity": self.similarity,
                "aggregate": self.aggregate,
                "seed": self.seed,
                "n_features": n_features,
                "n_known": int(known.X.shape[0]),
                "n_impostors": n_impostors,
            },
            values={
                "score": float(score),
                "wins": int(wins),
                "total_iterations": self.n_iterations,
                "questioned_id": questioned.document_ids[0],
            },
        )

    def _validate_inputs(
        self, questioned: FeatureMatrix, known: FeatureMatrix, impostors: FeatureMatrix
    ) -> None:
        if questioned.X.shape[0] != 1:
            raise ValueError(
                f"questioned must contain exactly 1 row; got {questioned.X.shape[0]}. "
                "To verify several questioned documents against the same candidate, call "
                "verify() once per document."
            )
        if known.X.shape[0] < 1:
            raise ValueError("known must contain at least 1 document")
        if impostors.X.shape[0] < 2:
            raise ValueError(
                "impostors pool must contain at least 2 documents; GI's sampling loop is "
                "degenerate with fewer impostors than default sample size"
            )
        if questioned.feature_names != known.feature_names:
            raise ValueError("questioned and known must share the same feature_names")
        if questioned.feature_names != impostors.feature_names:
            raise ValueError("questioned and impostors must share the same feature_names")
        if self.similarity == "minmax":
            for name, fm in (
                ("questioned", questioned),
                ("known", known),
                ("impostors", impostors),
            ):
                if (fm.X < 0).any():
                    raise ValueError(
                        f"{name} contains negative values; similarity='minmax' requires "
                        "non-negative features (e.g., relative frequencies, not z-scores)"
                    )

    def _similarity_to_candidate(self, q: np.ndarray, k: np.ndarray) -> float:
        if self.aggregate == "centroid":
            return self._pairwise(q, k.mean(axis=0))
        # "nearest": the maximum similarity across known samples
        return float(self._similarity_to_many(q, k).max(initial=-np.inf))

    def _similarity_to_many(self, q: np.ndarray, others: np.ndarray) -> np.ndarray:
        """Pairwise similarity from q (1-D) to each row of others (2-D)."""
        if self.similarity == "cosine":
            denom_q = np.linalg.norm(q)
            denom_o = np.linalg.norm(others, axis=1)
            denom = denom_q * denom_o
            denom = np.where(denom == 0, 1.0, denom)
            return (others @ q) / denom  # type: ignore[no-any-return]
        # minmax
        mins = np.minimum(q, others).sum(axis=1)
        maxs = np.maximum(q, others).sum(axis=1)
        maxs = np.where(maxs == 0, 1.0, maxs)
        return mins / maxs  # type: ignore[no-any-return]

    def _pairwise(self, q: np.ndarray, v: np.ndarray) -> float:
        return float(self._similarity_to_many(q, v[np.newaxis, :])[0])
