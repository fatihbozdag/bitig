"""Forensic-evaluation metrics for authorship verification and attribution.

All functions here evaluate the *calibration and discrimination* of a scorer's output against
binary ground truth (1 = target / same-author trial, 0 = non-target / different-author trial).
These are the metrics forensic journals and courtroom gatekeeping (Daubert, *R v T*) expect
above and beyond raw accuracy.

``compute_pan_report`` bundles the full PAN-style evaluation suite (AUC, c@1, F0.5u,
Brier, ECE, optional C_llr) behind one call, matching the metric menu used in the PAN
shared-task overviews since Stamatatos et al. (2014).

References
----------
Brummer, N., & du Preez, J. (2006). Application-independent evaluation of speaker detection.
    Computer Speech & Language, 20(2-3), 230-275.
Penas, A., & Rodrigo, A. (2011). A simple measure to assess non-response. Proceedings of
    ACL-HLT 2011, 1415-1424.
Bevendorff, J., Chulvi, B., Fersini, E., Heini, A., Kestemont, M., Kredens, K., Mayerl, M.,
    Ortega-Bueno, R., Pezik, P., Potthast, M., Rangel, F., Rosso, P., Stamatatos, E., Stein,
    B., Wiegmann, M., Wolska, M., & Zangerle, E. (2022). Overview of PAN 2022: Authorship
    verification, profiling of irony and stereotype spreaders, and style change detection.
    CEUR Workshop Proceedings, 3180.
Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. Monthly
    Weather Review, 78(1), 1-3.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from scipy.stats import rankdata


def cllr(log_lrs: np.ndarray, y: np.ndarray) -> float:
    """Log-likelihood-ratio cost (Brümmer & du Preez 2006).

    A proper scoring rule for binary forensic LR output, capturing both calibration and
    discrimination in a single scalar. Interpreted as the average information loss (in bits)
    per trial relative to an optimally-calibrated reference system.

    C_llr = 0.5 * ( mean_{i: y=1} log2(1 + 1/LR_i)
                  + mean_{i: y=0} log2(1 + LR_i) )

    Zero is unattainable in practice; a prior-only (uninformative) system gives C_llr = 1.
    Values below 1 indicate the system is better than prior-only; values above 1 indicate the
    system's LRs are actively misleading.

    Parameters
    ----------
    log_lrs : np.ndarray of shape (n,)
        log10 likelihood ratios for each trial.
    y : np.ndarray of shape (n,)
        Binary labels: 1 = target (same-author trial), 0 = non-target.

    Returns
    -------
    float
        C_llr cost, in bits.
    """
    log_lrs = np.asarray(log_lrs, dtype=float)
    y = np.asarray(y)
    if log_lrs.shape != y.shape:
        raise ValueError("log_lrs and y must have the same shape")
    if log_lrs.size == 0:
        raise ValueError("log_lrs must not be empty")
    target = y == 1
    nontarget = y == 0
    if not target.any() or not nontarget.any():
        raise ValueError("C_llr requires at least one target and one non-target trial")

    # Convert log10-LR → natural-log-LR for log2(1 + exp(.)) computation.
    # log2(1 + 1/LR) = log2(1 + exp(-ln(LR))); log2(1 + LR) = log2(1 + exp(ln(LR))).
    ln_lr = log_lrs * np.log(10.0)
    # Use logaddexp for numerical stability: log2(1 + exp(x)) = log2(e) * np.logaddexp(0, x).
    log2e = 1.0 / np.log(2.0)
    target_cost = log2e * np.logaddexp(0.0, -ln_lr[target]).mean()
    nontarget_cost = log2e * np.logaddexp(0.0, ln_lr[nontarget]).mean()
    return 0.5 * (float(target_cost) + float(nontarget_cost))


def ece(probs: np.ndarray, y: np.ndarray, *, n_bins: int = 10) -> float:
    """Expected Calibration Error with equal-width binning.

    ECE = sum_{b=1..B} (|B_b|/n) * |accuracy(B_b) - confidence(B_b)|

    Zero indicates perfect calibration (empirical frequency matches predicted probability in
    every bin). Typical forensic thresholds: ECE < 0.05 is considered well-calibrated.

    Parameters
    ----------
    probs : np.ndarray of shape (n,)
        Predicted probability of the positive class for each trial, in [0, 1].
    y : np.ndarray of shape (n,)
        Binary labels (0 or 1).
    n_bins : int
        Number of equal-width probability bins. Default 10.
    """
    probs = np.asarray(probs, dtype=float)
    y = np.asarray(y, dtype=float)
    if probs.shape != y.shape:
        raise ValueError("probs and y must have the same shape")
    if not np.all((probs >= 0) & (probs <= 1)):
        raise ValueError("probs must lie in [0, 1]")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = float(probs.size)
    err = 0.0
    for lo, hi in pairwise(edges):
        # Include right edge on the final bin so p=1.0 is counted.
        in_bin = (probs >= lo) & (probs < hi) if hi < 1.0 else (probs >= lo) & (probs <= hi)
        if not in_bin.any():
            continue
        bin_acc = float(y[in_bin].mean())
        bin_conf = float(probs[in_bin].mean())
        err += (in_bin.sum() / total) * abs(bin_acc - bin_conf)
    return err


def brier(probs: np.ndarray, y: np.ndarray) -> float:
    """Brier score (mean squared error between predicted probability and binary label).

    Zero = perfect probabilistic prediction; 0.25 = uninformed (all probs = 0.5); 1.0 = worst
    possible (confident-wrong on every trial).
    """
    probs = np.asarray(probs, dtype=float)
    y = np.asarray(y, dtype=float)
    if probs.shape != y.shape:
        raise ValueError("probs and y must have the same shape")
    return float(np.mean((probs - y) ** 2))


def tippett(log_lrs: np.ndarray, y: np.ndarray) -> dict[str, np.ndarray]:
    """Tippett-plot data: cumulative proportion of target and non-target trials at or above
    each threshold.

    The classical forensic visualisation: plot both CDFs together on a log-LR x-axis.
    - The target CDF should accumulate at high log-LR (right of zero).
    - The non-target CDF should accumulate at low log-LR (left of zero).
    - Where they cross is an empirical equal-error threshold.

    Returns
    -------
    dict
        ``thresholds``: sorted unique log-LR values.
        ``target_cdf``: P(log-LR ≥ t | target) at each threshold.
        ``nontarget_cdf``: P(log-LR ≥ t | non-target) at each threshold.
    """
    log_lrs = np.asarray(log_lrs, dtype=float)
    y = np.asarray(y)
    if log_lrs.shape != y.shape:
        raise ValueError("log_lrs and y must have the same shape")
    target_mask = y == 1
    nontarget_mask = y == 0
    if not target_mask.any() or not nontarget_mask.any():
        raise ValueError("tippett requires at least one target and one non-target trial")

    thresholds = np.unique(log_lrs)
    target_lrs = log_lrs[target_mask]
    nontarget_lrs = log_lrs[nontarget_mask]
    target_cdf = np.array([(target_lrs >= t).mean() for t in thresholds])
    nontarget_cdf = np.array([(nontarget_lrs >= t).mean() for t in thresholds])
    return {
        "thresholds": thresholds,
        "target_cdf": target_cdf,
        "nontarget_cdf": nontarget_cdf,
    }


def auc(scores: np.ndarray, y: np.ndarray) -> float:
    """Area under the ROC curve — computed via the Mann-Whitney U statistic.

    Invariant to monotone transformations of ``scores``; 1.0 = perfect ranking, 0.5 = random,
    0.0 = perfectly inverse. Ties contribute 0.5 each (standard convention).

    Parameters
    ----------
    scores : np.ndarray of shape (n,)
        Higher scores should indicate the target (y=1) hypothesis.
    y : np.ndarray of shape (n,)
        Binary labels.
    """
    scores = np.asarray(scores, dtype=float)
    y = np.asarray(y)
    if scores.shape != y.shape:
        raise ValueError("scores and y must have the same shape")
    target = scores[y == 1]
    nontarget = scores[y == 0]
    if target.size == 0 or nontarget.size == 0:
        raise ValueError("auc requires at least one target and one non-target trial")
    # Mann-Whitney U via rankdata: sum-of-ranks for target minus target-self-rank lower bound.
    all_scores = np.concatenate([target, nontarget])
    ranks = rankdata(all_scores)
    r_target = ranks[: target.size].sum()
    n_t = target.size
    n_n = nontarget.size
    u = r_target - n_t * (n_t + 1) / 2
    return float(u / (n_t * n_n))


def c_at_1(probs: np.ndarray, y: np.ndarray, *, unanswered_margin: float = 0.0) -> float:
    """c@1 (Peñas & Rodrigo 2011): accuracy with a credit for non-answers.

    Canonical formula (Peñas & Rodrigo 2011, eq. 1):

        c@1 = (1 / n) * (n_correct + n_unanswered * (n_correct / n))

    where ``n`` is the total number of trials, ``n_correct`` is the number of correct
    answered trials, and ``n_unanswered`` is the number of abstentions. The bonus for
    abstention scales with the *overall* accuracy of the system (n_correct / n), not with
    its accuracy on the answered subset — so a system that abstains frequently but is
    also inaccurate on its answers does not get rewarded.

    Non-answers are defined as trials whose probability lies within
    ``[0.5 - unanswered_margin, 0.5 + unanswered_margin]``. If ``unanswered_margin = 0``,
    the default, there are no non-answers and c@1 reduces to raw accuracy.

    Forensically principled because it rewards a system that knows when to abstain (vs.
    forcing a coin-flip on ambiguous evidence). The PAN verification shared task has used
    c@1 as the primary metric since 2013.

    Parameters
    ----------
    probs : np.ndarray of shape (n,)
        Calibrated probabilities of the target hypothesis, in [0, 1]. Decisions are taken
        at threshold 0.5.
    y : np.ndarray of shape (n,)
        Binary labels.
    unanswered_margin : float
        Half-width of the non-decision band around 0.5. 0.0 = no abstention; common PAN
        settings use 0.0 or a small value like 0.05.
    """
    probs = np.asarray(probs, dtype=float)
    y = np.asarray(y)
    if probs.shape != y.shape:
        raise ValueError("probs and y must have the same shape")
    if probs.size == 0:
        raise ValueError("c@1 requires at least one trial")
    if not np.all((probs >= 0) & (probs <= 1)):
        raise ValueError("probs must lie in [0, 1]")
    if unanswered_margin < 0:
        raise ValueError("unanswered_margin must be >= 0")

    # Strict `<`: with unanswered_margin == 0 the band is empty, so NO trial is
    # an abstention (not even an exact p == 0.5, which the prediction path below
    # answers as class 1). This is what makes c@1 reduce exactly to accuracy at
    # margin 0, as the docstring promises (audit P2 — `<=` marked p == 0.5
    # unanswered and diverged from accuracy).
    unanswered = np.abs(probs - 0.5) < unanswered_margin
    predictions = (probs >= 0.5).astype(int)
    correct = (predictions == y) & ~unanswered
    n_correct = int(correct.sum())
    n_unanswered = int(unanswered.sum())
    n = probs.size
    if n - n_unanswered == 0:
        # All trials unanswered: by convention c@1 = 0 (prior-only).
        return 0.0
    return float((1.0 / n) * (n_correct + n_unanswered * (n_correct / n)))


def f05u(probs: np.ndarray, y: np.ndarray) -> float:
    """F0.5-unanswered (Bevendorff et al. PAN 2022) — a precision-weighted F-measure that
    penalises both wrong answers and (weakly) non-answers.

    F0.5u uses the classical F-beta with beta=0.5 (weighting precision over recall), but
    counts trials falling in the [0.4, 0.6] decision band as non-answers, which are neither
    true positives nor false positives (they lower recall).

    Parameters
    ----------
    probs : np.ndarray of shape (n,)
        Probabilities of the target hypothesis, in [0, 1].
    y : np.ndarray of shape (n,)
        Binary labels.
    """
    probs = np.asarray(probs, dtype=float)
    y = np.asarray(y)
    if probs.shape != y.shape:
        raise ValueError("probs and y must have the same shape")
    if probs.size == 0:
        raise ValueError("f0.5u requires at least one trial")
    if not np.all((probs >= 0) & (probs <= 1)):
        raise ValueError("probs must lie in [0, 1]")

    unanswered = (probs >= 0.4) & (probs <= 0.6)
    decision = np.where(probs > 0.6, 1, np.where(probs < 0.4, 0, -1))
    tp = int(((decision == 1) & (y == 1)).sum())
    fp = int(((decision == 1) & (y == 0)).sum())
    fn = int(((decision == 0) & (y == 1)).sum()) + int(((y == 1) & unanswered).sum())
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    beta2 = 0.25  # 0.5^2
    return float((1 + beta2) * precision * recall / (beta2 * precision + recall))


@dataclass
class PANReport:
    """Bundled PAN-style evaluation summary for a verification system.

    All metrics are computed over binary (same-author / different-author) trials. ``cllr_bits``
    requires log-LR inputs and so is optional — set when available. Fields match the metric
    menu reported in PAN verification-task overviews (Stamatatos et al. 2014 onward).
    """

    auc: float
    c_at_1: float
    f05u: float
    brier: float
    ece: float
    cllr_bits: float | None = None
    n_target: int = 0
    n_nontarget: int = 0

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "auc": self.auc,
            "c_at_1": self.c_at_1,
            "f05u": self.f05u,
            "brier": self.brier,
            "ece": self.ece,
            "cllr_bits": self.cllr_bits,
            "n_target": self.n_target,
            "n_nontarget": self.n_nontarget,
        }


def compute_pan_report(
    probs: np.ndarray,
    y: np.ndarray,
    *,
    log_lrs: np.ndarray | None = None,
    ece_bins: int = 10,
    c_at_1_margin: float = 0.0,
) -> PANReport:
    """Run the full PAN evaluation suite on one set of trials.

    Parameters
    ----------
    probs : np.ndarray of shape (n,)
        Calibrated probabilities of the target hypothesis.
    y : np.ndarray of shape (n,)
        Binary labels.
    log_lrs : np.ndarray, optional
        log10-LRs for each trial. If provided, ``cllr_bits`` is included in the report.
    ece_bins : int
    c_at_1_margin : float
    """
    probs = np.asarray(probs, dtype=float)
    y = np.asarray(y)
    return PANReport(
        auc=auc(probs, y),
        c_at_1=c_at_1(probs, y, unanswered_margin=c_at_1_margin),
        f05u=f05u(probs, y),
        brier=brier(probs, y),
        ece=ece(probs, y, n_bins=ece_bins),
        cllr_bits=cllr(np.asarray(log_lrs, dtype=float), y) if log_lrs is not None else None,
        n_target=int((y == 1).sum()),
        n_nontarget=int((y == 0).sum()),
    )
