"""Tests for PAN-style evaluation metrics: auc, c@1, f0.5u, and compute_pan_report."""

from __future__ import annotations

import numpy as np
import pytest

from bitig.forensic.metrics import (
    PANReport,
    auc,
    c_at_1,
    compute_pan_report,
    f05u,
)


class TestAuc:
    def test_perfect_ranking_gives_one(self) -> None:
        scores = np.array([0.9, 0.8, 0.2, 0.1])
        y = np.array([1, 1, 0, 0])
        assert auc(scores, y) == pytest.approx(1.0)

    def test_random_ranking_gives_half(self) -> None:
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, size=1000)
        scores = rng.uniform(size=1000)  # unrelated to y
        assert abs(auc(scores, y) - 0.5) < 0.08  # Monte Carlo slack

    def test_inverse_ranking_gives_zero(self) -> None:
        scores = np.array([0.1, 0.2, 0.8, 0.9])
        y = np.array([1, 1, 0, 0])
        assert auc(scores, y) == pytest.approx(0.0)

    def test_ties_contribute_half(self) -> None:
        scores = np.array([0.5, 0.5, 0.5, 0.5])
        y = np.array([1, 1, 0, 0])
        assert auc(scores, y) == pytest.approx(0.5)

    def test_auc_requires_both_classes(self) -> None:
        with pytest.raises(ValueError, match="target and one non-target"):
            auc(np.array([0.1, 0.9]), np.array([1, 1]))

    def test_auc_rejects_shape_mismatch(self) -> None:
        with pytest.raises(ValueError, match="same shape"):
            auc(np.array([0.1, 0.2, 0.3]), np.array([1, 0]))


class TestCAt1:
    def test_c_at_1_with_no_margin_equals_accuracy(self) -> None:
        """unanswered_margin=0 → c@1 is plain accuracy."""
        probs = np.array([0.9, 0.9, 0.1, 0.1])
        y = np.array([1, 1, 0, 0])
        assert c_at_1(probs, y) == pytest.approx(1.0)

        # With a flipped prediction, c@1 = 3/4 (3 correct out of 4).
        probs2 = np.array([0.9, 0.9, 0.1, 0.9])
        assert c_at_1(probs2, y) == pytest.approx(0.75)

    def test_unanswered_trials_get_proportional_credit(self) -> None:
        """Peñas & Rodrigo (2011) eq. 1: c@1 = (1/n) * (n_correct + n_unanswered * n_correct/n).

        3 correct answered + 1 unanswered out of 4:
          c@1 = (1/4) * (3 + 1 * 3/4) = (1/4) * 3.75 = 0.9375

        A high-accuracy system gains a credit for abstaining that scales with its overall
        accuracy — not with its answered-only accuracy, which would reward systems that
        abstain a lot but are also inaccurate on the answers they do give.
        """
        probs = np.array([0.9, 0.9, 0.1, 0.5])
        y = np.array([1, 1, 0, 1])  # the last trial is unanswered (prob exactly 0.5)
        assert c_at_1(probs, y, unanswered_margin=0.001) == pytest.approx(0.9375)

    def test_unanswered_bonus_scales_with_overall_accuracy(self) -> None:
        """A system with 2 correct + 1 unanswered + 1 wrong (n=4): overall accuracy is 0.5
        (2/4). Paper formula: c@1 = (1/4) * (2 + 1 * 2/4) = (1/4) * 2.5 = 0.625.

        This is strictly less than under the pre-fix (wrong) denominator (n_answered=3),
        which would have given (1/4)(2 + 1 * 2/3) = 0.667. The test locks in the paper's
        version of the metric so the fix doesn't silently regress.
        """
        probs = np.array([0.9, 0.9, 0.9, 0.5])
        y = np.array([1, 1, 0, 1])  # 2 correct (idx 0, 1), 1 wrong (idx 2), 1 unanswered
        assert c_at_1(probs, y, unanswered_margin=0.001) == pytest.approx(0.625)

    def test_c_at_1_requires_valid_probs(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            c_at_1(np.array([0.5, 1.1]), np.array([1, 0]))

    def test_c_at_1_rejects_negative_margin(self) -> None:
        with pytest.raises(ValueError, match="unanswered_margin"):
            c_at_1(np.array([0.5]), np.array([1]), unanswered_margin=-0.1)

    def test_c_at_1_margin_zero_answers_exact_half(self) -> None:
        """At margin 0 an exact p==0.5 is ANSWERED (predicted class 1), so c@1
        equals plain accuracy — it must not be silently treated as an abstention
        (audit P2; the old `<=` band marked p==0.5 unanswered and diverged)."""
        probs = np.array([0.5, 0.9, 0.2])  # predictions at >=0.5 → [1, 1, 0]
        assert c_at_1(probs, np.array([1, 1, 0]), unanswered_margin=0.0) == pytest.approx(1.0)
        # p=0.5 predicts 1; with truth 0 it's simply wrong → 2/3 accuracy, no abstention credit.
        assert c_at_1(probs, np.array([0, 1, 0]), unanswered_margin=0.0) == pytest.approx(2 / 3)

    def test_c_at_1_all_unanswered_returns_zero(self) -> None:
        probs = np.full(4, 0.5)
        y = np.array([1, 1, 0, 0])
        assert c_at_1(probs, y, unanswered_margin=0.1) == 0.0


class TestF05u:
    def test_perfect_classifier_gives_one(self) -> None:
        probs = np.array([0.95, 0.9, 0.05, 0.1])
        y = np.array([1, 1, 0, 0])
        assert f05u(probs, y) == pytest.approx(1.0)

    def test_confident_wrong_gives_zero(self) -> None:
        """All predictions flipped: no true positives → F0.5u = 0."""
        probs = np.array([0.05, 0.1, 0.95, 0.9])
        y = np.array([1, 1, 0, 0])
        assert f05u(probs, y) == 0.0

    def test_unanswered_trials_lower_recall(self) -> None:
        """A target trial landing in the non-decision band is a pseudo-false-negative for F0.5u."""
        # Two targets confidently predicted, two abstained.
        probs = np.array([0.95, 0.9, 0.5, 0.55])
        y = np.array([1, 1, 1, 1])  # all target
        # tp=2, fp=0, fn=2 (from the unanswered targets).
        # precision = 2/(2+0) = 1.0
        # recall = 2/(2+2) = 0.5
        # F0.5 = (1.25 * 1.0 * 0.5) / (0.25 * 1.0 + 0.5) = 0.625 / 0.75 ≈ 0.833
        assert f05u(probs, y) == pytest.approx(0.833, abs=0.01)


class TestComputePanReport:
    def test_returns_PANReport_with_all_metrics(self) -> None:
        rng = np.random.default_rng(42)
        n = 200
        y = rng.integers(0, 2, size=n)
        probs = np.where(y == 1, rng.uniform(0.5, 1.0, size=n), rng.uniform(0.0, 0.5, size=n))
        log_lrs = np.where(y == 1, rng.uniform(0.5, 3.0, size=n), rng.uniform(-3.0, -0.5, size=n))

        report = compute_pan_report(probs, y, log_lrs=log_lrs)
        assert isinstance(report, PANReport)
        assert 0.0 <= report.auc <= 1.0
        assert 0.0 <= report.c_at_1 <= 1.0
        assert 0.0 <= report.f05u <= 1.0
        assert 0.0 <= report.brier <= 1.0
        assert 0.0 <= report.ece <= 1.0
        assert report.cllr_bits is not None and report.cllr_bits >= 0.0
        assert report.n_target + report.n_nontarget == n

    def test_cllr_none_when_log_lrs_not_provided(self) -> None:
        probs = np.array([0.9, 0.1, 0.8, 0.2])
        y = np.array([1, 0, 1, 0])
        report = compute_pan_report(probs, y)
        assert report.cllr_bits is None
        assert report.auc == pytest.approx(1.0)

    def test_to_dict_exposes_all_fields(self) -> None:
        probs = np.array([0.9, 0.1, 0.8, 0.2])
        y = np.array([1, 0, 1, 0])
        report = compute_pan_report(probs, y)
        data = report.to_dict()
        for key in (
            "auc",
            "c_at_1",
            "f05u",
            "brier",
            "ece",
            "cllr_bits",
            "n_target",
            "n_nontarget",
        ):
            assert key in data
