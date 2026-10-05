# Calibration & LR output

*Use when:* your verifier outputs raw scores (distances, fractions, probabilities)
that need to be turned into calibrated log-likelihood ratios before an evidential
report.
*Don't use when:* your scorer is already a well-calibrated LR — skip straight to
evaluation.
*Expect:* a fitted calibrator whose `predict_proba` / `predict_log_lr` outputs are
calibrated against a labelled development set.

Raw scores from a verifier are rarely honest probabilities out-of-the-box. This page
covers the two standard post-hoc calibration methods and the conversion of a calibrated
posterior into a log-LR; the chain-of-custody fields and the report itself are covered in
[Reporting](reporting.md).

Verification systems produce raw scores. Forensic reporting expects **calibrated
posteriors** converted to **likelihood ratios** — the evidential semantics courts
understand. `bitig.forensic` provides both steps.

## The workflow

```mermaid
flowchart LR
  S["raw score<br>(GI, Delta, SVM, ...)"] --> C["CalibratedScorer<br>fit on (cal_scores, cal_labels)"]
  C --> P["calibrated p(H1|E)"]
  P --> L["log<sub>10</sub>(LR)"]

  style C fill:#FBF3DE,stroke:#C9A34A
  style L fill:#FBF3DE,stroke:#C9A34A
```

The calibration fold must be **separate** from the test fold. Overfitting the calibrator
on the test set gives optimistic C_llr and ECE.

## CalibratedScorer

*Use when:* you have raw scores from any verifier (`GeneralImpostors`, `Unmasking`, a
custom Delta classifier) and want calibrated probabilities and log-LRs for them.
*Don't use when:* your upstream scorer already emits calibrated output.
*Expect:* `fit(scores, y)` learns the mapping from labelled calibration trials;
`predict_proba(scores)` returns calibrated p(H1 | score); `predict_log_lr(scores)`
returns the evidential quantity. It operates on score arrays, not on the verifier itself.

Fits a 1-D monotone calibrator, either Platt (logistic) or isotonic.

```python
from bitig.forensic import CalibratedScorer

scorer = CalibratedScorer(method="platt").fit(calibration_scores, calibration_labels)
probs   = scorer.predict_proba(test_scores)
log_lrs = scorer.predict_log_lr(test_scores, base=10.0)
```

### Choosing the method

| Method | When |
|---|---|
| `"platt"` | Small calibration sets (< 100 / class). Parametric; assumes sigmoidal mapping. Robust. |
| `"isotonic"` | Larger calibration sets (≥ 100 / class advisable; ≥ 20 / class enforced). Non-parametric; flexible. |

Platt is strictly monotone, so it preserves rank order and AUC. Isotonic is only
non-decreasing: it merges scores into tied steps, which can lower AUC slightly.

### Platt calibration

*Use when:* your scorer's decision boundary is approximately linear in log-odds —
logistic-regression-like shape. Fewer parameters than isotonic; needs fewer labelled
trials.
*Don't use when:* your score-to-probability relationship is non-monotonic or sharply
bent — Platt's sigmoid will underfit.
*Expect:* a scalar-parameter sigmoid fit; `predict_proba` outputs calibrated
probabilities via `1 / (1 + exp(a*score + b))`.

### Isotonic calibration

*Use when:* your scorer's decision boundary is non-linear and you have enough
labelled trials (≥ 100 per class advisable) to fit a non-parametric curve.
*Don't use when:* your dev set is small — fewer than 20 trials per class is refused.
*Expect:* a piecewise-constant calibration function; `predict_proba` outputs the
monotone non-decreasing step function.

Safeguards: one pseudo-trial per class is added at the opposite extreme, so the
calibrated probability never reaches exactly 0 or 1, and `|log₁₀ LR|` is capped at
`log₁₀(n)` for a calibration set of `n` trials (`scorer.log_lr_cap_`); `predict_log_lr`
warns when an output hits the cap. Without these, a small separable calibration set
produced log₁₀ LR = ±12 ("extremely strong support"). Expect isotonic LRs to be
conservative at the extremes.

## Log-LR conversion

Under flat priors ($p(H_1) = p(H_0) = 0.5$), log-LR is just the logit of the calibrated
posterior:

$$
\log_{10}(\text{LR}) = \log_{10}\left(\frac{p(H_1 \mid E)}{1 - p(H_1 \mid E)}\right)
$$

```python
from bitig.forensic import log_lr_from_probs, log_lr_from_probs_with_priors

log_lrs = log_lr_from_probs(probs)                                # flat priors
log_lrs = log_lr_from_probs_with_priors(probs, prior_target=0.3)  # non-flat
```

`CalibratedScorer.predict_log_lr` does this for you: `fit` records the calibration set's
share of target trials (`scorer.prior_target_`) and the LR divides out its prior odds, so
it does not depend on how many trials of each class you calibrated on. Call the two
functions above directly only when you have posteriors from elsewhere.

## Verbal scale

Report log-LR magnitudes alongside the six-band Nordgaard et al. (2012) / ENFSI (2015)
scale:

| \|log₁₀(LR)\| | Verbal support |
|---|---|
| 0 – 1 | weak |
| 1 – 2 | moderate |
| 2 – 3 | moderately strong |
| 3 – 4 | strong |
| 4 – 6 | very strong |
| ≥ 6 | extremely strong |

LR > 1 supports the same-author proposition, LR < 1 the different-author proposition;
the strength is the same for an LR and its reciprocal (`bitig.forensic.verbal_scale`).

The `build_forensic_report` template renders the verbal statement beside each LR passed
in `lr_summaries`. See [Reporting](reporting.md).

## Reference

::: bitig.forensic.lr.CalibratedScorer
    options:
      show_root_full_path: false

::: bitig.forensic.lr.log_lr_from_probs

::: bitig.forensic.lr.log_lr_from_probs_with_priors
