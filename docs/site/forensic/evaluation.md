# Evaluation (PAN suite)

Forensic publications and courts expect more than raw accuracy. bitig ships the standard
PAN verification-task metric menu behind one call.

## One-call evaluation

```python
from bitig.forensic import compute_pan_report

report = compute_pan_report(
    probs=calibrated_probs,     # from CalibratedScorer
    y=ground_truth_labels,
    log_lrs=log_lr_values,      # optional; enables cllr_bits
)
report.to_dict()
# {
#   "auc": 0.94, "c_at_1": 0.88, "f05u": 0.87,
#   "brier": 0.11, "ece": 0.042, "cllr_bits": 0.31,
#   "n_target": 80, "n_nontarget": 120,
# }
```

## The metrics

| Metric | Measures | Use for | Range | Reference |
|---|---|---|---|---|
| `auc` | Ranking quality | **Choosing between systems.** Higher AUC → the system ranks same-author pairs above different-author pairs more reliably. | 0 (perfectly inverted) – 1 (perfect); 0.5 is random | — |
| `c_at_1` | Accuracy with abstention credit | **Operational decisions** where "don't know" is safer than a wrong answer. | 0 – 1 | Peñas & Rodrigo 2011 |
| `f05u` | Precision-weighted F with non-answer penalty | **PAN-style evaluation.** Penalises over-confident wrong answers. | 0 – 1 | Bevendorff et al. 2019/2020 |
| `brier` | Posterior calibration | **Probabilistic output quality.** Lower = better-calibrated probabilities. | 0 (perfect) – 1 (worst) | Brier 1950 |
| `ece` | Expected calibration error | **Is `predict_proba` honest?** Bins predictions by confidence; compares claimed vs. actual accuracy. | 0 (perfect) – 1 | — |
| `cllr` | Log-likelihood-ratio cost | **Forensic LR quality.** The strict proper scoring rule for evidential output. | 0 (perfect) – ∞ | Brümmer & du Preez 2006 |
| `tippett` | LR distribution plot | **Sanity-checking calibration visually.** Cumulative target vs. non-target LR curves should separate. | — | — |

### c@1

$$
\text{c@1} = \frac{1}{n}\!\left( n_\text{correct} + n_\text{unanswered} \cdot \frac{n_\text{correct}}{n} \right)
$$

where *unanswered* trials are those with `|p − 0.5| ≤ margin`. With the default margin 0
exactly `p = 0.5` is a non-answer, as in the PAN evaluator; with no such outputs c@1
equals accuracy. A positive margin widens the abstention band but is not PAN-comparable.

The PAN verification shared task has used c@1 as its primary metric since 2013 because it
rewards systems that know when to abstain — directly aligned with the forensic notion
of "insufficient evidence".

### C_llr

$$
C_\text{llr} = \frac{1}{2}\!\left[
  \frac{1}{|T|}\!\sum_{i \in T} \log_2\!\left(1 + \tfrac{1}{\text{LR}_i}\right)
  +
  \frac{1}{|N|}\!\sum_{i \in N} \log_2\!\left(1 + \text{LR}_i\right)
\right]
$$

where $T$ = target trials, $N$ = non-target. Interpreted as average information loss (in
bits) per trial relative to an optimally-calibrated reference system.

- **Prior-only system** (every log-LR = 0) → C_llr = **1.0** exactly.
- **Perfect, confident system** → C_llr ≈ 0.
- **Misleading system** (wrong sign) → C_llr > 1.

A system with C_llr < 1 beats prior-only. Forensic publications routinely report C_llr
alongside AUC because C_llr captures both discrimination *and* calibration in one scalar.

## Tippett plots

`tippett(log_lrs, y)` returns per-class cumulative distributions you can plot directly:

```python
import matplotlib.pyplot as plt
from bitig.forensic import tippett

data = tippett(log_lrs, y)
plt.step(data["thresholds"], data["target_cdf"], label="same-author")
plt.step(data["thresholds"], data["nontarget_cdf"], label="different-author")
plt.xlabel("log₁₀(LR) threshold")
plt.ylabel("P(log-LR ≥ threshold | class)")
plt.legend()
```

A well-discriminating system shows the target CDF accumulating on the right (high
log-LRs are predominantly target) and the non-target CDF on the left.

## Reference

### compute_pan_report

*Use when:* you have a labelled batch of verification trials and want every standard
metric in one call — AUC, c@1, F0.5u, Brier, ECE, (optionally) C_llr.
*Don't use when:* you only need one metric; each metric function is callable directly.
*Expect:* a `PANReport` dataclass with every field populated.

::: bitig.forensic.metrics.compute_pan_report

::: bitig.forensic.metrics.PANReport

### AUC

*Use when:* comparing two verification systems on the same benchmark — AUC is
threshold-independent.
*Don't use when:* you need an operational decision — AUC says nothing about where to
set the threshold.
*Expect:* a single number in `[0, 1]`, where 0.5 is a random ranking and values below
0.5 indicate an inverted ranking. Does not depend on predicted probabilities being
calibrated.

::: bitig.forensic.metrics.auc

### c@1

*Use when:* your system can abstain ("don't know") and you want to credit that
honestly — accuracy plus a partial-credit bonus for abstention.
*Don't use when:* your system never outputs exactly 0.5 (its abstention signal); `c@1` then equals accuracy.
*Expect:* a single number in `[0, 1]`. Dominates accuracy only when abstention rate > 0.

::: bitig.forensic.metrics.c_at_1

### F0.5u

*Use when:* you're scoring a PAN-CLEF verification track — PAN's precision-weighted
F-measure, `1.25·TP / (1.25·TP + 0.25·(FN + N_u) + FP)`, where `N_u` counts every
non-answer (`p = 0.5`) whatever its label (Bevendorff et al. 2019/2020).
*Don't use when:* you're reporting to a non-PAN audience; it's a specialist metric.
*Expect:* a single number in `[0, 1]`.

::: bitig.forensic.metrics.f05u

### C_llr

*Use when:* you need to quantify **how good your LR output is** in forensic terms —
this is the strict proper scoring rule the speaker-recognition community settled on.
*Don't use when:* your scorer outputs accuracy-style probabilities; `C_llr` expects
log-likelihood ratios.
*Expect:* a single non-negative number; 0 is perfect; 1 is uninformative (matches a
coin flip).

::: bitig.forensic.metrics.cllr

### ECE

*Use when:* you want to audit probabilistic honesty — ECE bins predictions by
claimed confidence and checks whether actual accuracy matches.
*Don't use when:* your dev set is small (<200 trials); ECE's bin estimates become
noisy.
*Expect:* a single number in `[0, 1]`; 0 is perfect calibration.

::: bitig.forensic.metrics.ece

### Brier

*Use when:* you want a proper scoring rule for probabilistic classifiers (not LR
outputs) — classic squared-error between predicted probability and ground truth.
*Don't use when:* you need a forensic LR-specific metric — use `C_llr`.
*Expect:* a single number in `[0, 1]`; 0 is perfect.

::: bitig.forensic.metrics.brier

### Tippett

*Use when:* you want a visual calibration check — plot target-trial vs. non-target
log-LRs as cumulative distributions.
*Don't use when:* you need a single-number summary (use `C_llr`).
*Expect:* a dict with `thresholds` (sorted unique log-LRs) and `target_cdf` /
`nontarget_cdf`, the proportion of each class at or above each threshold, ready for a
matplotlib plot.

::: bitig.forensic.metrics.tippett
