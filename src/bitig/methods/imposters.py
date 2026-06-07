"""General Imposters -- Koppel & Winter (2014) / Seidman (2013) verification.

Each iteration draws TWO independent random samples: a subset of MFW features
*and* a subset of impostor authors from the pool. In that random feature
subspace the target is assigned to the nearest of the candidate plus the
sampled impostors; the candidate "wins" the iteration if it is nearest. The
aggregate score is the win fraction in [0, 1].

Sampling the impostors per iteration (rather than always comparing against the
whole author set) is the defining feature of *General* Impostors and is what
keeps the score interpretable: with one impostor per iteration (the default,
``impostor_n=1``) the comparison is candidate-vs-one-impostor, so under no
signal the candidate wins half the time — ``chance == 0.5`` — and the default
0.5 threshold sits exactly at chance. Larger ``impostor_n`` approximates the
stricter "nearer than every impostor" test with ``chance == 1/(1+impostor_n)``;
``chance`` is reported on the Result so the score is always read against it.

The score is an uncalibrated similarity statistic, NOT a likelihood ratio —
turning it into an LR requires a calibration set (see the forensic-domain
pass). This is a *verification* method (one candidate per config), the
complement of the delta runner branch's *attribution*. Targets are excluded
from the MFW vocabulary and z-score statistics so frequencies do not leak.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bitig.corpus import Corpus
from bitig.features.mfw import MFWExtractor, _tokenise
from bitig.methods.delta import (
    ArgamonLinearDelta,
    BurrowsDelta,
    CosineDelta,
    EderDelta,
    EderSimpleDelta,
    QuadraticDelta,
)
from bitig.result import Result

_BASE_DELTA: dict[str, type] = {
    "burrows": BurrowsDelta,
    "cosine": CosineDelta,
    "argamon_linear": ArgamonLinearDelta,
    "quadratic": QuadraticDelta,
    "eder": EderDelta,
    "eder_simple": EderSimpleDelta,
}


class GeneralImposters:
    """Koppel & Winter (2014) General Imposters verification.

    Parameters
    ----------
    target_ids : list[str]
        Document ids to verify. Each is asked whether it could plausibly be
        written by `candidate`.
    candidate : str
        The alleged author. Must appear in the `group_by` column of the
        training portion of the corpus (i.e., among non-target documents).
    group_by : str
        Metadata column naming the author of each training document.
    n_iter : int
        Number of bootstrap iterations; each samples a feature subset and
        votes on whether the candidate or some imposter is closer.
    feature_frac : float
        Fraction of MFW columns sampled per iteration. The classical GI
        value is 0.5; lower values produce noisier per-iteration votes but
        stabilise the aggregate score.
    impostor_n : int
        Impostors sampled per iteration from the pool. Default 1 → pairwise
        candidate-vs-impostor comparison, so ``chance == 0.5`` and the 0.5
        threshold is principled. Larger values give a stricter test with
        ``chance == 1/(1+impostor_n)`` (reported on the Result).
    base_delta : str
        Distance kernel; one of `burrows`, `cosine`, `argamon_linear`,
        `quadratic`, `eder`, `eder_simple`.
    mfw_n : int
        Top-N MFW vocabulary size (fit on training only).
    lowercase : bool
        Case-fold during tokenisation.
    threshold : float
        Decision cutoff; targets whose score >= threshold are reported as
        verified. Stored on Result.values so downstream code can re-decide.
    seed : int
        Seed for the per-iteration feature subsample.
    """

    def __init__(
        self,
        *,
        target_ids: list[str],
        candidate: str,
        group_by: str,
        n_iter: int = 100,
        feature_frac: float = 0.5,
        impostor_n: int = 1,
        base_delta: str = "burrows",
        mfw_n: int = 200,
        lowercase: bool = True,
        threshold: float = 0.5,
        seed: int = 42,
    ) -> None:
        if base_delta not in _BASE_DELTA:
            raise ValueError(f"unknown base_delta {base_delta!r} (known: {sorted(_BASE_DELTA)})")
        if not target_ids:
            raise ValueError("general_imposters requires at least one target_id")
        if not (0.0 < feature_frac <= 1.0):
            raise ValueError("feature_frac must be in (0, 1]")
        if n_iter < 1:
            raise ValueError("n_iter must be >= 1")
        if impostor_n < 1:
            raise ValueError("impostor_n must be >= 1")
        self.target_ids = list(target_ids)
        self.candidate = candidate
        self.group_by = group_by
        self.n_iter = int(n_iter)
        self.feature_frac = float(feature_frac)
        self.impostor_n = int(impostor_n)
        self.base_delta = base_delta
        self.mfw_n = int(mfw_n)
        self.lowercase = lowercase
        self.threshold = float(threshold)
        self.seed = int(seed)

    def fit_transform(self, corpus: Corpus) -> Result:
        target_set = set(self.target_ids)
        train_docs = [d for d in corpus.documents if d.id not in target_set]
        target_docs = [d for d in corpus.documents if d.id in target_set]
        if not train_docs:
            raise ValueError(
                "general_imposters needs at least one training document outside target_ids"
            )
        if not target_docs:
            raise ValueError(
                f"none of target_ids {self.target_ids!r} match documents in the corpus"
            )

        train_corpus = Corpus(documents=train_docs, language=corpus.language)
        mfw = MFWExtractor(n=self.mfw_n, scale="zscore", lowercase=self.lowercase)
        train_fm = mfw.fit_transform(train_corpus)
        x_train = train_fm.X
        y_train = np.array(train_corpus.metadata_column(self.group_by))
        if any(v is None for v in y_train):
            raise ValueError(f"some training documents lack metadata column {self.group_by!r}")
        authors = sorted({str(a) for a in y_train.tolist()})
        if self.candidate not in authors:
            raise ValueError(f"candidate {self.candidate!r} not in training authors {authors!r}")
        if len(authors) < 2:
            raise ValueError(
                "general_imposters needs at least 2 distinct authors in the training corpus"
            )

        # Project each target into the same MFW space (counts -> l1 -> z-score).
        # Direct internal-state access is intentional -- both classes ship in this package.
        vocab_index = {tok: i for i, tok in enumerate(mfw._vocabulary)}
        means = mfw._column_means
        stds = mfw._column_stds
        if means is None or stds is None:
            raise RuntimeError("MFW fit did not produce z-score statistics")
        target_vectors: list[np.ndarray] = []
        for doc in target_docs:
            counts = np.zeros(len(vocab_index), dtype=float)
            for tok in _tokenise(doc.text, self.lowercase):
                j = vocab_index.get(tok)
                if j is not None:
                    counts[j] += 1
            row_sum = counts.sum() or 1.0
            rel = counts / row_sum
            target_vectors.append((rel - means) / stds)

        delta_cls = _BASE_DELTA[self.base_delta]
        rng = np.random.default_rng(self.seed)
        n_features = x_train.shape[1]
        k = max(1, round(n_features * self.feature_frac))

        impostors = [a for a in authors if a != self.candidate]
        # Impostors sampled per iteration. With m == 1 (default) each iteration
        # is a candidate-vs-one-random-impostor comparison, so under no signal
        # the candidate wins half the time and the 0.5 threshold sits exactly at
        # chance. Larger m approximates the stricter Koppel "nearer than all of
        # a sampled impostor set" test, with chance 1/(1 + m).
        m = min(self.impostor_n, len(impostors))
        chance = 1.0 / (1 + m)

        rows: list[dict[str, object]] = []
        for doc, tgt in zip(target_docs, target_vectors, strict=True):
            wins = 0
            for _ in range(self.n_iter):
                # Two independent randomisations per iteration: a feature
                # subspace AND a fresh impostor subset drawn from the pool
                # (Seidman 2013; Koppel & Winter 2014). Sampling impostors —
                # not always comparing against the whole author set — is what
                # makes this General Impostors and what calibrates the score.
                cols = rng.choice(n_features, size=k, replace=False)
                sampled = rng.choice(np.asarray(impostors, dtype=object), size=m, replace=False)
                keep = {self.candidate, *(str(a) for a in sampled)}
                mask = np.array([str(a) in keep for a in y_train])
                clf = delta_cls()
                clf.fit(x_train[mask][:, cols], y_train[mask])
                # decision_function returns -distance; argmax => nearest centroid.
                neg_dists = clf.decision_function(tgt[cols].reshape(1, -1))[0]
                if str(clf.classes_[int(np.argmax(neg_dists))]) == self.candidate:
                    wins += 1
            score = wins / self.n_iter
            rows.append(
                {
                    "target_id": doc.id,
                    "candidate": self.candidate,
                    "score": float(score),
                    "chance": float(chance),
                    "n_iter": self.n_iter,
                    "n_features_per_iter": int(k),
                    "impostors_per_iter": int(m),
                    "verified": bool(score >= self.threshold),
                }
            )

        table = pd.DataFrame(rows)
        return Result(
            method_name=f"general_imposters_{self.base_delta}",
            params={
                "target_ids": self.target_ids,
                "candidate": self.candidate,
                "group_by": self.group_by,
                "n_iter": self.n_iter,
                "feature_frac": self.feature_frac,
                "impostor_n": self.impostor_n,
                "base_delta": self.base_delta,
                "mfw_n": self.mfw_n,
                "lowercase": self.lowercase,
                "threshold": self.threshold,
                "seed": self.seed,
            },
            values={
                "candidate": self.candidate,
                "imposters": impostors,
                "threshold": self.threshold,
                "chance": float(chance),
                "scores": {row["target_id"]: row["score"] for row in rows},
            },
            tables=[table],
        )
