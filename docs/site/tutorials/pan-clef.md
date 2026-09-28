# Tutorial: PAN-CLEF authorship verification

An end-to-end forensic authorship-verification pipeline on a PAN-CLEF-style setup. By
the end you will have: a **calibrated General Impostors scorer**, a full **PAN metric
suite**, a **Tippett plot**, and a **forensic HTML report** with LR framing and
chain-of-custody metadata.

!!! info "About PAN-CLEF"
    The [PAN @ CLEF](https://pan.webis.de) shared task has run authorship-verification
    evaluations annually since 2013. Each year's corpus is a collection of *trials*
    where each trial is a pair `(known_docs, questioned_doc)` labelled with a binary
    ground truth `same-author` / `different-author`. The standard metric menu is AUC +
    c@1 + F0.5u + Brier + cllr.

    This tutorial uses a **synthetic** PAN-style dataset so it runs end-to-end without
    requiring the real PAN corpus download. Swap the synthetic loader for
    `load_pan_trials("path/to/pan22/pairs.jsonl")` on real data.

## The task

Given:

- A **reference population** of documents by many authors (the *impostor pool*).
- A **set of verification trials**, each with:
    - `questioned_id` — a single questioned document
    - `known_ids` — one or more known-author documents
    - `is_target` — binary ground truth (1 = same author wrote Q and K; 0 = different)

Produce for each trial:

- A **calibrated posterior** p(same-author | evidence)
- A **log₁₀ likelihood ratio**
- An overall **PANReport** with AUC, c@1, F0.5u, Brier, ECE, C_llr

## 1. Build the synthetic corpus

```python
import numpy as np
from bitig.corpus import Corpus, Document

rng = np.random.default_rng(42)
VOCAB = [
    # Letter-only tokens so MFW's regex picks them up
    *[f"{a}{b}" for a in "abcdefgh" for b in "abcdefgh"]
]

def _author_profile():
    """Each author has an idiosyncratic Dirichlet profile over the shared vocabulary."""
    return rng.dirichlet(np.ones(len(VOCAB)) * 0.4)

def _sample_doc(profile, n_words=800):
    return " ".join(rng.choice(VOCAB, size=n_words, p=profile).tolist())

N_AUTHORS = 40
authors = {f"A{i:02d}": _author_profile() for i in range(N_AUTHORS)}

# Two docs per author: one goes to the known set, one is the candidate for questioning.
documents = []
for author, profile in authors.items():
    for sample_idx in range(2):
        doc_id = f"{author}_s{sample_idx}"
        documents.append(
            Document(
                id=doc_id,
                text=_sample_doc(profile),
                metadata={"author": author, "sample": sample_idx},
            )
        )
corpus = Corpus(documents=documents)
print(f"Corpus: {len(corpus)} documents from {N_AUTHORS} authors")
```

## 2. Define trials

A PAN trial has a known set K, a questioned doc Q, and a label. We build trials where
the label is balanced across same-author and different-author pairs.

```python
from dataclasses import dataclass

@dataclass
class Trial:
    trial_id: str
    known_ids: list[str]
    questioned_id: str
    is_target: int          # 1 = same author; 0 = different

trials: list[Trial] = []
author_list = sorted({d.metadata["author"] for d in documents})

for candidate in author_list:
    # Known set: the candidate's sample 0.
    k_id = f"{candidate}_s0"

    # Same-author trial: questioned = the candidate's sample 1.
    trials.append(Trial(
        trial_id=f"T_{candidate}_same",
        known_ids=[k_id],
        questioned_id=f"{candidate}_s1",
        is_target=1,
    ))

    # Different-author trial: questioned = sample 1 from a random OTHER author.
    other = rng.choice([a for a in author_list if a != candidate])
    trials.append(Trial(
        trial_id=f"T_{candidate}_diff_{other}",
        known_ids=[k_id],
        questioned_id=f"{other}_s1",
        is_target=0,
    ))

print(f"{len(trials)} trials ({sum(t.is_target for t in trials)} target / "
      f"{sum(1 - t.is_target for t in trials)} non-target)")
```

## 3. Extract a shared feature space

Build the feature matrix over the pooled corpus once, so Q, K, and impostors live in
the same vocabulary.

```python
from bitig import MFWExtractor

fm = MFWExtractor(n=500, scale="zscore", lowercase=True).fit_transform(corpus)

# Index by document id for easy slicing below.
id_to_row = {doc_id: i for i, doc_id in enumerate(fm.document_ids)}
```

## 4. Run General Impostors per trial

For each trial we assemble:

- Questioned document row
- Known-document rows
- Impostor pool = everyone except the candidate author

```python
from bitig.features import FeatureMatrix
from bitig.forensic import GeneralImpostors

def slice_fm(rows: list[int]) -> FeatureMatrix:
    return FeatureMatrix(
        X=fm.X[rows],
        document_ids=[fm.document_ids[i] for i in rows],
        feature_names=fm.feature_names,
        feature_type=fm.feature_type,
    )

gi = GeneralImpostors(n_iterations=100, feature_subsample_rate=0.5, seed=42)

scores, labels = [], []
for trial in trials:
    q_rows = [id_to_row[trial.questioned_id]]
    k_rows = [id_to_row[kid] for kid in trial.known_ids]
    candidate_author = corpus.documents[k_rows[0]].metadata["author"]

    # Impostor pool: all docs from OTHER authors except the questioned one itself.
    impostor_rows = [
        id_to_row[d.id]
        for d in corpus.documents
        if d.metadata["author"] != candidate_author and d.id != trial.questioned_id
    ]

    result = gi.verify(
        questioned=slice_fm(q_rows),
        known=slice_fm(k_rows),
        impostors=slice_fm(impostor_rows),
    )
    scores.append(result.values["score"])
    labels.append(trial.is_target)

scores = np.array(scores)
labels = np.array(labels)
print(f"mean score (target trials): {scores[labels == 1].mean():.3f}")
print(f"mean score (non-target):    {scores[labels == 0].mean():.3f}")
```

On this synthetic setup the two means should be clearly separated (≈ 0.8 vs ≈ 0.2).

## 5. Calibrate

Raw GI scores are discrimination-shaped but not probabilities. Calibrate on a held-out
split so the output is a defensible posterior.

```python
from bitig.forensic import CalibratedScorer, log_lr_from_probs

# 60/40 split — calibrate on the first 60%, evaluate on the rest.
n = len(scores)
cut = int(0.6 * n)
perm = rng.permutation(n)
cal_idx, test_idx = perm[:cut], perm[cut:]

scorer = CalibratedScorer(method="platt").fit(scores[cal_idx], labels[cal_idx])
test_probs = scorer.predict_proba(scores[test_idx])
test_log_lrs = scorer.predict_log_lr(scores[test_idx])
test_labels = labels[test_idx]

print(f"calibrated posterior range: [{test_probs.min():.2f}, {test_probs.max():.2f}]")
print(f"log-LR range:               [{test_log_lrs.min():.2f}, {test_log_lrs.max():.2f}]")
```

## 6. PAN evaluation

```python
from bitig.forensic import compute_pan_report

report = compute_pan_report(
    probs=test_probs,
    y=test_labels,
    log_lrs=test_log_lrs,
    c_at_1_margin=0.05,   # 5 % abstention band around 0.5
)
for k, v in report.to_dict().items():
    if isinstance(v, float):
        print(f"  {k:12s} {v:.3f}")
    else:
        print(f"  {k:12s} {v}")
```

Expected output on the synthetic setup (approximate):

```
  auc          0.97
  c_at_1       0.92
  f05u         0.91
  brier        0.10
  ece          0.04
  cllr_bits    0.24
  n_target     20
  n_nontarget  20
```

## 7. Tippett plot

```python
import matplotlib.pyplot as plt
from bitig.forensic import tippett

data = tippett(test_log_lrs, test_labels)

fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
ax.step(data["thresholds"], data["target_cdf"],
        where="post", label="same author", linewidth=2)
ax.step(data["thresholds"], data["nontarget_cdf"],
        where="post", label="different author", linewidth=2, linestyle="--")
ax.set_xlabel(r"log$_{10}$(LR) threshold")
ax.set_ylabel(r"P(log$_{10}$-LR ≥ threshold | class)")
ax.set_title("Tippett plot — GI + Platt calibration")
ax.legend()
fig.tight_layout()
fig.savefig("tippett.png", dpi=300, bbox_inches="tight")
```

A well-discriminating system shows the target CDF staying near 1.0 across positive
log-LRs while the non-target CDF drops quickly.

## 8. Forensic HTML report

Save the test-set results as a bitig `Result`, stamp chain-of-custody metadata on its
`Provenance`, and render the LR-framed forensic report.

```python
import json
import spacy
from pathlib import Path
from bitig.provenance import Provenance
from bitig.result import Result
from bitig.report import build_forensic_report

run_dir = Path("pan_demo")
(run_dir / "gi").mkdir(parents=True, exist_ok=True)

result = Result(
    method_name="general_impostors",
    params={"n_iterations": 100, "feature_subsample_rate": 0.5, "seed": 42},
    values={
        "score_mean_target":    float(test_probs[test_labels == 1].mean()),
        "score_mean_nontarget": float(test_probs[test_labels == 0].mean()),
        "n_trials": int(len(test_labels)),
    },
    provenance=Provenance.current(
        spacy_model="n/a",
        spacy_version=spacy.__version__,
        corpus_hash=corpus.hash(),
        feature_hash=fm.provenance_hash,
        seed=42,
        resolved_config={"method": "pan_tutorial"},
        questioned_description="PAN-style verification trials (synthetic corpus)",
        known_description="one known sample per candidate, 40 authors",
        hypothesis_pair="H1: candidate wrote Q; H0: different author wrote Q",
        acquisition_notes="synthetic Dirichlet-multinomial profiles, seed 42",
        custody_notes="reproducible from tutorial code above",
    ),
)
result.save(run_dir / "gi")

build_forensic_report(
    run_dir,
    output=run_dir / "report.html",
    title="PAN-style verification — demo",
    lr_summaries={"general_impostors": {
        "log_lr": f"{test_log_lrs.mean():.2f}",
        "lr":     f"{10 ** test_log_lrs.mean():.1f}",
    }},
)
print(f"report: {run_dir / 'report.html'}")
```

Open the HTML in a browser: you get a single-page forensic report with the hypothesis
block, chain-of-custody block, method-level LR summary with the ENFSI verbal scale
interpretation, and the reproducibility provenance.

## Moving to real PAN data

For real PAN corpora:

```python
import json

def load_pan_trials(jsonl_path):
    """PAN-style format: one JSON object per line with known-texts + unknown-text + truth."""
    trials = []
    with open(jsonl_path) as f:
        for line in f:
            obj = json.loads(line)
            trials.append(Trial(
                trial_id=obj["id"],
                known_ids=obj["known_ids"],
                questioned_id=obj["questioned_id"],
                is_target=int(obj["same_author"]),
            ))
    return trials
```

Download instructions and corpus licensing terms live at
[pan.webis.de](https://pan.webis.de). The PAN 2020 and 2022 authorship-verification
corpora are among the largest public same-author benchmarks.

## Reproducibility notes

- Every random choice in this tutorial is seeded (`rng = np.random.default_rng(42)` +
  `GeneralImpostors(seed=42)` + `scorer.method="platt"` which is deterministic).
- A rerun produces identical `Result.values` (up to floating-point rounding) under
  matching Python + numpy + scikit-learn versions.
- The `Provenance` record captures all versions; any drift is detectable.

See [Forensic toolkit](../forensic/index.md) for deeper documentation of each component.
