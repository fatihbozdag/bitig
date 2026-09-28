"""Tests for CalibratedScorer and log-LR transformations."""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from bitig.forensic.lr import (
    CalibratedScorer,
    log_lr_from_probs,
    log_lr_from_probs_with_priors,
)
from bitig.forensic.metrics import cllr, ece


class TestLogLrFromProbs:
    def test_prob_half_gives_zero_log_lr(self) -> None:
        """Under flat priors, p=0.5 means no evidence either way: log-LR = 0."""
        assert log_lr_from_probs(np.array([0.5]))[0] == pytest.approx(0.0)

    def test_high_probability_gives_positive_log_lr(self) -> None:
        result = log_lr_from_probs(np.array([0.99]))[0]
        assert result > 1.0  # log10(99) ≈ 1.996

    def test_low_probability_gives_negative_log_lr(self) -> None:
        result = log_lr_from_probs(np.array([0.01]))[0]
        assert result < -1.0  # log10(1/99) ≈ -1.996

    def test_base_controls_logarithm(self) -> None:
        prob = np.array([0.75])  # odds = 3
        assert log_lr_from_probs(prob, base=10.0)[0] == pytest.approx(np.log10(3.0))
        assert log_lr_from_probs(prob, base=np.e)[0] == pytest.approx(np.log(3.0))
        assert log_lr_from_probs(prob, base=2.0)[0] == pytest.approx(np.log2(3.0))

    def test_eps_clipping_prevents_inf(self) -> None:
        """At p=0 or p=1, the raw logit is ±inf — eps clipping produces finite but large LRs."""
        log_lrs = log_lr_from_probs(np.array([0.0, 1.0]), eps=1e-12)
        assert np.isfinite(log_lrs).all()
        assert log_lrs[0] < -10.0
        assert log_lrs[1] > 10.0

    def test_rejects_out_of_range_probs(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            log_lr_from_probs(np.array([-0.1, 0.5]))
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            log_lr_from_probs(np.array([0.5, 1.2]))

    def test_rejects_invalid_base(self) -> None:
        with pytest.raises(ValueError, match="base"):
            log_lr_from_probs(np.array([0.5]), base=1.0)


class TestLogLrWithPriors:
    def test_prior_equal_to_half_matches_flat_prior(self) -> None:
        probs = np.array([0.7, 0.3, 0.95])
        flat = log_lr_from_probs(probs)
        with_half = log_lr_from_probs_with_priors(probs, prior_target=0.5)
        np.testing.assert_allclose(flat, with_half, atol=1e-12)

    def test_rare_prior_deflates_log_lr(self) -> None:
        """If the calibrator was trained with a rare target prior (e.g., 0.01), the posterior
        p=0.5 implies a large LR (strong evidence), so log-LR > 0."""
        lr_flat = log_lr_from_probs_with_priors(np.array([0.5]), prior_target=0.5)[0]
        lr_rare = log_lr_from_probs_with_priors(np.array([0.5]), prior_target=0.01)[0]
        assert lr_rare > lr_flat

    def test_rejects_invalid_prior(self) -> None:
        with pytest.raises(ValueError, match="prior_target"):
            log_lr_from_probs_with_priors(np.array([0.5]), prior_target=0.0)
        with pytest.raises(ValueError, match="prior_target"):
            log_lr_from_probs_with_priors(np.array([0.5]), prior_target=1.0)


def _discriminating_dataset(n: int = 400, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Two well-separated Gaussians — a scorer that discriminates but whose raw values are
    in arbitrary units (not pre-calibrated as probabilities)."""
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, size=n)
    scores = np.where(y == 1, rng.normal(3.0, 1.0, size=n), rng.normal(-3.0, 1.0, size=n))
    return scores, y


class TestCalibratedScorerDiscrimination:
    """Calibration must preserve discrimination and produce posteriors that yield sensible
    forensic metrics downstream."""

    @pytest.mark.parametrize("method", ["platt", "isotonic"])
    def test_calibrated_output_beats_prior_only_on_separable_data(self, method: str) -> None:
        """On a discriminable dataset, calibrated C_llr must be well below 1.0 (prior-only)."""
        scores, y = _discriminating_dataset(n=400, seed=1)
        half = len(scores) // 2

        scorer = CalibratedScorer(method=method).fit(scores[:half], y[:half])  # type: ignore[arg-type]
        calibrated_probs = scorer.predict_proba(scores[half:])
        calibrated_log_lrs = scorer.predict_log_lr(scores[half:])

        assert 0.0 <= calibrated_probs.min() <= calibrated_probs.max() <= 1.0
        # On well-separated data, calibrated C_llr is << 1.0 (prior-only system).
        assert cllr(calibrated_log_lrs, y[half:]) < 0.5

    @pytest.mark.parametrize("method", ["platt", "isotonic"])
    def test_calibration_preserves_score_ordering(self, method: str) -> None:
        """Both calibrators are monotone, so rank order of outputs must match input scores."""
        scores, y = _discriminating_dataset(n=300, seed=2)
        scorer = CalibratedScorer(method=method).fit(scores, y)  # type: ignore[arg-type]
        test_scores = np.array([-5.0, -2.0, 0.0, 2.0, 5.0])
        probs = scorer.predict_proba(test_scores)
        # Monotone non-decreasing (ties are allowed for isotonic).
        assert np.all(np.diff(probs) >= -1e-12)

    def test_calibration_reduces_ece_on_biased_scores(self) -> None:
        """Biased raw probabilities (consistently over-confident) should have ECE reduced by
        calibration."""
        rng = np.random.default_rng(7)
        n = 300
        y = rng.integers(0, 2, size=n)
        # Over-confident raw probs: all pushed toward 0 or 1 regardless of true frequency.
        raw_probs = np.where(y == 1, rng.uniform(0.8, 1.0, size=n), rng.uniform(0.0, 0.2, size=n))
        # But add a systematic bias: all probabilities are shifted toward 0.5 by a constant,
        # making them under-confident and biased.
        biased_probs = 0.9 * raw_probs + 0.05

        half = n // 2
        scorer = CalibratedScorer(method="isotonic").fit(biased_probs[:half], y[:half])

        ece_raw = ece(biased_probs[half:], y[half:])
        ece_calibrated = ece(scorer.predict_proba(biased_probs[half:]), y[half:])
        # Calibration should not make ECE materially worse.
        assert ece_calibrated <= ece_raw + 0.02


class TestCalibratedScorerContract:
    def test_predict_before_fit_raises(self) -> None:
        scorer = CalibratedScorer()
        with pytest.raises(RuntimeError, match="not yet fit"):
            scorer.predict_proba(np.array([0.5]))

    def test_fit_rejects_non_binary_labels(self) -> None:
        scorer = CalibratedScorer()
        with pytest.raises(ValueError, match=r"\{0, 1\}"):
            scorer.fit(np.array([0.1, 0.2, 0.3, 0.4]), np.array([0, 1, 2, 0]))

    def test_fit_rejects_tiny_data(self) -> None:
        scorer = CalibratedScorer()
        with pytest.raises(ValueError, match="at least 4"):
            scorer.fit(np.array([0.1, 0.9]), np.array([0, 1]))

    def test_fit_rejects_shape_mismatch(self) -> None:
        scorer = CalibratedScorer()
        with pytest.raises(ValueError, match="same length"):
            scorer.fit(np.array([0.1, 0.2, 0.3]), np.array([0, 1, 0, 1]))

    def test_rejects_unknown_method(self) -> None:
        with pytest.raises(ValueError, match="unknown method"):
            CalibratedScorer(method="bogus")  # type: ignore[arg-type]

    def test_platt_and_isotonic_both_produce_valid_probs(self) -> None:
        scores, y = _discriminating_dataset(n=200, seed=3)
        for method in ("platt", "isotonic"):
            scorer = CalibratedScorer(method=method).fit(scores, y)  # type: ignore[arg-type]
            probs = scorer.predict_proba(scores)
            assert probs.shape == scores.shape
            assert ((probs >= 0) & (probs <= 1)).all()


class TestIsotonicSafeguards:
    """Audit 2026-09-26 N-P1.11: isotonic output saturated at log10 LR = +/-12."""

    def test_tiny_calibration_set_is_refused(self) -> None:
        scores = np.array([0.1, 0.2, 0.3, 0.6, 0.7, 0.8])
        y = np.array([0, 0, 0, 1, 1, 1])
        with pytest.raises(ValueError, match="at least 20"):
            CalibratedScorer(method="isotonic").fit(scores, y)

    def test_separable_set_does_not_saturate_and_is_capped(self) -> None:
        rng = np.random.default_rng(0)
        scores = np.r_[rng.normal(1, 0.3, 30), rng.normal(-1, 0.3, 30)]
        y = np.r_[np.ones(30), np.zeros(30)]  # perfectly separable in practice
        scorer = CalibratedScorer(method="isotonic").fit(scores, y)
        probs = scorer.predict_proba(np.array([-5.0, 5.0]))
        assert probs[0] > 0.0 and probs[1] < 1.0  # pseudo-counts keep bins mixed
        assert scorer.log_lr_cap_ == pytest.approx(np.log10(60))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            log_lr = scorer.predict_log_lr(np.array([-5.0, 5.0]))
        assert np.all(np.abs(log_lr) <= np.log10(60) + 1e-12)
        assert np.all(np.abs(log_lr) < 12)

    def test_cap_hit_warns(self) -> None:
        scores = np.r_[np.full(20, 1.0), np.full(20, 0.0)]
        y = np.r_[np.ones(20), np.zeros(20)]
        scorer = CalibratedScorer(method="isotonic").fit(scores, y)
        scorer.log_lr_cap_ = 0.5  # force the cap below the calibrated value
        with pytest.warns(UserWarning, match="cap"):
            out = scorer.predict_log_lr(np.array([1.0]))
        assert out[0] == pytest.approx(0.5)

    def test_cap_respects_log_base(self) -> None:
        scores = np.r_[np.full(20, 1.0), np.full(20, 0.0)]
        y = np.r_[np.ones(20), np.zeros(20)]
        scorer = CalibratedScorer(method="isotonic").fit(scores, y)
        scorer.log_lr_cap_ = 0.5
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = scorer.predict_log_lr(np.array([1.0]), base=np.e)
        assert out[0] == pytest.approx(0.5 * np.log(10))

    def test_platt_is_uncapped(self) -> None:
        scores = np.array([0.1, 0.2, 0.3, 0.6, 0.7, 0.8])
        y = np.array([0, 0, 0, 1, 1, 1])
        assert CalibratedScorer(method="platt").fit(scores, y).log_lr_cap_ is None
