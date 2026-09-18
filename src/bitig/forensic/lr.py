"""Likelihood-ratio output and score calibration for forensic evidential reporting.

Forensic journals (IJSLL, Language and Law) and courtroom gatekeeping expect evidence framed
as a likelihood ratio — the probability of the evidence under the "same author" hypothesis
divided by its probability under "different author" — and they expect the underlying scorer
to be *calibrated*. Raw classifier posteriors are rarely calibrated well enough to support
LR-based reporting, and classifier outputs are trivially abusable as "probability of guilt"
in ways that misrepresent forensic semantics.

This module provides:

- ``log_lr_from_probs``: convert a calibrated posterior probability p(H1 | E) to a
  log10 likelihood ratio, under the flat-prior assumption. For non-flat priors use
  ``log_lr_from_probs_with_priors``.
- ``CalibratedScorer``: fit a monotone calibrator (Platt / logistic or isotonic) on
  held-out scores and their binary labels, then apply it to new scores. Use this on the
  output of any bitig classifier (or ``GeneralImpostors.verify().values["score"]``) before
  passing to the metrics in ``bitig.forensic.metrics``.

References
----------
Platt, J. C. (1999). Probabilistic outputs for support vector machines and comparisons to
    regularized likelihood methods. Advances in Large Margin Classifiers, 61-74.
Niculescu-Mizil, A., & Caruana, R. (2005). Predicting good probabilities with supervised
    learning. Proceedings of ICML 2005, 625-632.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

CalibrationMethod = Literal["platt", "isotonic"]


def log_lr_from_probs(probs: np.ndarray, *, eps: float = 1e-12, base: float = 10.0) -> np.ndarray:
    """Convert calibrated posteriors p(H1 | E) to log-likelihood ratios, flat-prior case.

    Under flat priors (p(H1) = p(H0) = 0.5), log-LR = log(p / (1 - p)) (the logit). When
    calibrated on a balanced set, this is the forensically-appropriate evidential output.

    Parameters
    ----------
    probs : np.ndarray
        Calibrated probabilities of the target hypothesis, in [0, 1].
    eps : float
        Clip bound to avoid log(0). Defaults to 1e-12.
    base : float
        Logarithm base. Defaults to 10 (the standard forensic convention).

    Returns
    -------
    np.ndarray
        log_base(LR) for each trial.
    """
    probs = np.asarray(probs, dtype=float)
    if not np.all((probs >= 0) & (probs <= 1)):
        raise ValueError("probs must lie in [0, 1]")
    if base <= 1.0:
        raise ValueError("base must be > 1")
    clipped = np.clip(probs, eps, 1.0 - eps)
    logit = np.log(clipped / (1.0 - clipped))
    return logit / np.log(base)  # type: ignore[no-any-return]


def log_lr_from_probs_with_priors(
    probs: np.ndarray, *, prior_target: float, eps: float = 1e-12, base: float = 10.0
) -> np.ndarray:
    """Convert p(H1 | E) to log-LR with a user-specified prior.

    posterior-odds = LR * prior-odds, so LR = posterior-odds / prior-odds.

    Parameters
    ----------
    probs : np.ndarray
        Calibrated probabilities of the target hypothesis, in [0, 1].
    prior_target : float
        Prior probability of H1 used when training the calibrator, in (0, 1).
    """
    if not np.isfinite(base) or base <= 1.0:
        raise ValueError("base must be finite and > 1")
    if not 0.0 < eps < 0.5:
        raise ValueError("eps must lie in (0, 0.5)")
    if not 0.0 < prior_target < 1.0:
        raise ValueError("prior_target must lie in (0, 1)")
    probs = np.asarray(probs, dtype=float)
    if not np.all((probs >= 0) & (probs <= 1)):
        raise ValueError("probs must lie in [0, 1]")
    clipped = np.clip(probs, eps, 1.0 - eps)
    posterior_odds = clipped / (1.0 - clipped)
    prior_odds = prior_target / (1.0 - prior_target)
    lr = posterior_odds / prior_odds
    return np.log(lr) / np.log(base)  # type: ignore[no-any-return]


class CalibratedScorer:
    """Fit a monotone calibrator mapping raw scores to calibrated posteriors.

    Parameters
    ----------
    method : {"platt", "isotonic"}
        - ``platt``: one-dimensional LogisticRegression (Platt scaling). Parametric; assumes
          the score-to-probability mapping is sigmoidal. Robust on small calibration sets.
        - ``isotonic``: IsotonicRegression. Non-parametric, monotone. More flexible but
          requires more calibration data (rule of thumb: >= 100 trials per class).

    Attributes
    ----------
    method : str
    fitted : bool
    """

    def __init__(self, *, method: CalibrationMethod = "platt") -> None:
        if method not in ("platt", "isotonic"):
            raise ValueError(f"unknown method {method!r}")
        self.method: CalibrationMethod = method
        self._model: LogisticRegression | IsotonicRegression | None = None
        self.fitted = False
        self.prior_target_: float | None = None

    def fit(self, scores: np.ndarray, y: np.ndarray) -> CalibratedScorer:
        scores = np.asarray(scores, dtype=float).reshape(-1)
        y = np.asarray(y)
        if scores.shape[0] != y.shape[0]:
            raise ValueError("scores and y must have the same length")
        if scores.size < 4:
            raise ValueError("calibration requires at least 4 trials (2 per class)")
        unique_y = np.unique(y)
        if not (len(unique_y) == 2 and set(unique_y.tolist()) <= {0, 1}):
            raise ValueError(f"y must be binary with labels in {{0, 1}}; got {unique_y.tolist()}")

        if self.method == "platt":
            lr = LogisticRegression(solver="lbfgs", max_iter=1000)
            lr.fit(scores.reshape(-1, 1), y)
            self._model = lr
        else:
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(scores, y)
            self._model = iso
        self.prior_target_ = float(np.mean(y))
        self.fitted = True
        return self

    def predict_proba(self, scores: np.ndarray) -> np.ndarray:
        """Return calibrated p(H1 | score) for each input score."""
        if not self.fitted or self._model is None:
            raise RuntimeError("CalibratedScorer not yet fit; call fit(scores, y) first")
        scores = np.asarray(scores, dtype=float).reshape(-1)
        if self.method == "platt":
            assert isinstance(self._model, LogisticRegression)
            probs = self._model.predict_proba(scores.reshape(-1, 1))[:, 1]
        else:
            assert isinstance(self._model, IsotonicRegression)
            probs = self._model.predict(scores)
        return np.clip(probs, 0.0, 1.0)  # type: ignore[no-any-return]

    def predict_log_lr(self, scores: np.ndarray, *, base: float = 10.0) -> np.ndarray:
        """Convert posteriors to log-LR, removing the fitted calibration prior odds."""
        probs = self.predict_proba(scores)
        assert self.prior_target_ is not None
        return log_lr_from_probs_with_priors(probs, prior_target=self.prior_target_, base=base)
