# Verification

Authorship *verification* is a one-class decision: **did this specific candidate produce
this questioned document?** Real case-work rarely offers a closed candidate set, so
verification — not attribution — is the forensically canonical task.

bitig ships two complementary verifiers.

## General Impostors

*Use when:* you have one questioned document, one candidate's known documents, and a
pool of ~100+ impostor documents from other authors — the forensically canonical
same-author-or-not question with a closed candidate.
*Don't use when:* you have no impostor pool available, or your candidate's known
writings are less than ~1000 words total (the test becomes sample-size-bound).
*Expect:* a score in `[0, 1]`; calibrate with `CalibratedScorer` before reporting as
an LR.

Koppel & Winter (2014). For a questioned document Q, a candidate's known documents K,
and a pool of impostor documents I drawn from other authors, repeatedly:

1. Sample a random feature subspace.
2. Sample m impostors from the pool.
3. Check whether Q is closer to K than to any sampled impostor.

The fraction of winning iterations is the verification score in [0, 1].

```python
from bitig.features import MFWExtractor
from bitig.forensic import GeneralImpostors

# Build features over the pooled corpus so Q, K, and impostors share one vocabulary.
fm = MFWExtractor(n=200, scale="zscore", lowercase=True).fit_transform(pooled_corpus)
q_fm      = slice_by_ids(fm, ["questioned"])
known_fm  = slice_by_ids(fm, known_doc_ids)
impostors = slice_by_ids(fm, impostor_doc_ids)

gi = GeneralImpostors(n_iterations=100, feature_subsample_rate=0.5, seed=42)
result = gi.verify(questioned=q_fm, known=known_fm, impostors=impostors)
result.values["score"]       # in [0, 1]
result.values["wins"]        # raw winning-iteration count
```

### Knobs

| Parameter | Default | Purpose |
|---|---|---|
| `n_iterations` | 100 | Number of random subspace + impostor-sample iterations |
| `feature_subsample_rate` | 0.5 | Fraction of features sampled per iteration |
| `impostor_sample_size` | `ceil(sqrt(pool_size))` | Impostors per iteration — scales sub-linearly so large pools don't trivialise the test |
| `similarity` | `"cosine"` | `"cosine"` (real-valued) or `"minmax"` (non-negative features only) |
| `aggregate` | `"centroid"` | `"centroid"` (mean of K) or `"nearest"` (most-similar known; gives the candidate its best of k chances per iteration, so it biases scores toward same-author — calibrate under the same setting) |
| `seed` | 42 | RNG seed (feature + impostor sampling) |

### Ties

Ties break **toward the impostors** (strict `>`). If Q is equally close to K and an
impostor, the iteration counts as a loss — the forensically conservative choice.

### Two implementations

`bitig.forensic.GeneralImpostors` (this page) compares Q with individual impostor
**documents** in feature matrices you build. `bitig.methods.imposters.GeneralImposters`,
used by `bitig run` (`kind: verify`) and Forensic Lab Cases, fits its own MFW space and
compares Q with author **centroids**. Both sample `ceil(sqrt(pool))` impostors per
iteration by default and return an uncalibrated win fraction in [0, 1] — read it against
its chance level, never as a likelihood ratio. Their scores differ; a parity test checks
they reach the same verdict on unambiguous cases.

## Unmasking

*Use when:* you have long same-author prose candidates (novel chapters, long essays,
blog archives) and want a distribution-free verification — the accuracy-drop curve
itself is interpretable evidence.
*Don't use when:* your documents are short (<~1500 words per side) — Unmasking needs
enough chunks to run cross-validation meaningfully.
*Expect:* an accuracy curve across elimination rounds; same-author pairs show a steep
drop, different-author pairs stay near random or above.

Koppel & Schler (2004). A distribution-free, long-text verification method. Chunk Q
and K into word-windows, then iteratively:

1. Train a binary classifier to distinguish Q-chunks from K-chunks.
2. Measure CV accuracy.
3. Remove the **top-N most-Q-discriminating** and **top-N most-K-discriminating**
   features (2 × N per round per Koppel & Schler).
4. Repeat.

Same-author documents are stylistically similar: once a few surface differences are
removed, the classifier collapses quickly (large drop). Different-author documents keep
yielding discriminating features, so accuracy stays high (small drop).

```python
from bitig.features import MFWExtractor
from bitig.forensic import Unmasking

unmasking = Unmasking(chunk_size=500, n_rounds=10, n_eliminate=3, seed=42)
result = unmasking.verify(
    questioned=questioned_text,            # str, Document, or Corpus
    known=known_text,
    extractor=MFWExtractor(n=200, scale="zscore", lowercase=True),
)
result.values["accuracy_curve"]    # list[float], length n_rounds
result.values["accuracy_drop"]     # scalar summary (curve[0] - curve[-1])
result.values["eliminated_per_round"]   # auditable per-round feature removal
```

### When to pick which

| Situation | Pick |
|---|---|
| Short CMC / threat texts (< ~2000 words total) | `GeneralImpostors`. Unmasking needs more text per side to run CV meaningfully. |
| Long prose (novels, essays, blog archives) | `Unmasking` — the accuracy-drop curve is directly interpretable. Pair with GI as a second opinion. |
| Building an evidential report | Run both, calibrate both with `CalibratedScorer`. Agreement between the two is itself evidential signal (Juola-style multi-method verdict). |

## Reference

::: bitig.forensic.verify.GeneralImpostors
    options:
      show_root_full_path: false

::: bitig.forensic.unmasking.Unmasking
    options:
      show_root_full_path: false
