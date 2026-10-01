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

import warnings
from typing import Literal

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

CalibrationMethod = Literal["platt", "isotonic"]

ISOTONIC_MIN_PER_CLASS = 20
"""Minimum calibration trials per class for isotonic calibration."""


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
          requires more calibration data: at least ``ISOTONIC_MIN_PER_CLASS`` (20) trials
          per class are enforced; >= 100 per class is advisable.

    Isotonic safeguards (audit 2026-09-26 N-P1.11). Plain isotonic regression outputs
    exactly 0 or 1 wherever the extreme calibration bins are pure, which the log-LR
    clip then turned into log10 LR = +/-12 ("extremely strong support") from as few
    as six trials. Here:

    * one pseudo-trial per class is added at the opposite extreme (a target at the
      lowest score, a non-target at the highest), so no bin is pure and calibrated
      probabilities stay strictly inside (0, 1);
    * ``|log10 LR|`` is capped at ``log10(n)`` for a calibration set of ``n`` trials
      (a simple empirical bound in the spirit of Vergeer et al. 2016's ELUB: a set
      of ``n`` trials cannot support an LR beyond about ``n``). ``predict_log_lr``
      warns when any output hits the cap; ``log_lr_cap_`` holds it.

    Attributes
    ----------
    method : str
    fitted : bool
    log_lr_cap_ : float | None
        Cap on |log10 LR| (isotonic only; ``None`` for Platt).
    prior_target_ : float
        Share of target trials the calibrator was fitted on. The calibrated
        posteriors carry this prior, so ``predict_log_lr`` divides out its odds:
        the LR then does not depend on how many trials of each class were used
        (audit 2026-09-26 P2; a 1:9 uninformative set gave log10 LR ~ -0.9).
    """

    def __init__(self, *, method: CalibrationMethod = "platt") -> None:
        if method not in ("platt", "isotonic"):
            raise ValueError(f"unknown method {method!r}")
        self.method: CalibrationMethod = method
        self._model: LogisticRegression | IsotonicRegression | None = None
        self.fitted = False
        self.log_lr_cap_: float | None = None
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
            self.prior_target_ = float(np.mean(y.astype(int)))
        else:
            y_int = y.astype(int)
            n_target = int(y_int.sum())
            n_nontarget = int(y_int.size - n_target)
            if min(n_target, n_nontarget) < ISOTONIC_MIN_PER_CLASS:
                raise ValueError(
                    f"isotonic calibration needs at least {ISOTONIC_MIN_PER_CLASS} trials per "
                    f"class (got {n_target} target, {n_nontarget} non-target); use "
                    "method='platt' for small calibration sets"
                )
            # One pseudo-trial per class at the opposite extreme keeps the end bins
            # mixed, so calibrated probabilities never reach exactly 0 or 1.
            fit_scores = np.concatenate([scores, [scores.min(), scores.max()]])
            fit_y = np.concatenate([y_int, [1, 0]])
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(fit_scores, fit_y)
            self._model = iso
            self.prior_target_ = float(np.mean(fit_y))
            self.log_lr_cap_ = float(np.log10(scores.size))
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
        """Calibrated posteriors → log-LR, with the calibration set's prior odds divided out.

        For isotonic calibration the result is capped at ``±log_lr_cap_``
        (expressed in ``base``); a ``UserWarning`` names how many outputs hit it.
        """
        if self.prior_target_ is None:
            raise RuntimeError("CalibratedScorer not yet fit; call fit(scores, y) first")
        log_lr = log_lr_from_probs_with_priors(
            self.predict_proba(scores), prior_target=self.prior_target_, base=base
        )
        if self.log_lr_cap_ is None:
            return log_lr
        cap = self.log_lr_cap_ * np.log(10.0) / np.log(base)
        capped = np.abs(log_lr) >= cap
        if capped.any():
            warnings.warn(
                f"{int(capped.sum())} log-LR value(s) reached the calibration-size cap "
                f"(|log10 LR| <= {self.log_lr_cap_:.2f}); the calibration set cannot "
                "support stronger evidence",
                UserWarning,
                stacklevel=2,
            )
        return np.clip(log_lr, -cap, cap)  # type: ignore[no-any-return]
