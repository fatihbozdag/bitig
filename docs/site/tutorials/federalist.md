# Tutorial: Federalist Papers

Reproducing Mosteller & Wallace's (1964) classical authorship attribution of the 85
Federalist Papers.

## Background

The Federalist Papers (1787–1788) were published under the pseudonym *Publius* to
argue for ratification of the US Constitution. Authorship of 73 papers is known
(Hamilton, Madison, Jay); the rest are either joint work or disputed between Hamilton and
Madison. Mosteller & Wallace (1964) used word-frequency Bayesian inference to attribute the
disputed papers to Madison — a result later stylometric studies have broadly supported.

The literature usually counts 12 disputed papers (49–58, 62, 63). The corpus shipped with
bitig labels No. 58 as Madison, so it has **11 disputed papers** (49–57, 62, 63), plus 3 joint
Hamilton–Madison papers (18–20).

This tutorial uses bitig to reproduce the essentials of their result in two steps:

1. A declarative `study.yaml` that explores the 71 single-author papers with Burrows Delta,
   PCA, a Ward dendrogram and Craig's Zeta. The disputed papers are filtered out of this step:
   they are not projected into the PCA and do not appear in its figures.
2. A separate attribution step (`bitig delta` / `bitig bayesian` with `--test-filter`) that
   trains on the known papers and assigns each disputed paper to a candidate.

## What you'll build

By the end you will have:

- A project skeleton with the 85 Federalist Papers ingested.
- A `study.yaml` declaring four analyses: Burrows Delta, PCA, Ward cluster, Craig's
  Zeta contrast between Hamilton and Madison.
- A `results/demo/` directory containing per-method `Result` JSONs plus rendered
  figures.
- A single HTML report stitching everything together.

## 1. Initialise the project

```bash
bitig init federalist
cd federalist
```

This scaffolds a project directory with an empty `corpus/` and a starter `study.yaml`.

## 2. Drop in the papers

The repo's [`examples/federalist/`](https://github.com/fatihbozdag/bitig/tree/main/examples/federalist)
directory has all 85 papers as individual `.txt` files plus a ready-made
`metadata.tsv`. Copy `corpus/` and `metadata.tsv` over, or follow the example's
own `README.md` to build it from Project Gutenberg. Each file holds only the essay body,
from the salutation "To the People of the State of New York" on: the Project Gutenberg
header (paper number, title, newspaper and date, author byline) has been stripped, so the
author names in it cannot leak into the features.

`metadata.tsv` has one row per paper with: `filename`, `author`, `role`, `notes`.
`role` is `train` for the 71 single-author papers, `test` for the 11 disputed papers
(`author` = `Disputed`) and `excluded` for the 3 joint papers (`author` = `Joint_HM`).
The study below reads it from `corpus/metadata.tsv`, so copy it into `corpus/`.

## 3. Edit study.yaml

```yaml
name: federalist
seed: 42
output:
  dir: results
  timestamp: false

corpus:
  path: corpus
  metadata: corpus/metadata.tsv
  filter:
    role: [train]            # hold out the disputed papers from training

features:
  - id: mfw200
    type: mfw
    n: 200
    scale: zscore
    lowercase: true

methods:
  - id: burrows
    kind: delta
    variant: burrows
    features: mfw200
    group_by: author

  - id: pca
    kind: reduce
    features: mfw200
    params: { n_components: 2 }

  - id: ward
    kind: cluster
    features: mfw200
    params: { n_clusters: 3, linkage: ward }

  - id: zeta_hamilton_madison
    kind: zeta
    group_by: author
    params:
      top_k: 50
      group_a: Hamilton
      group_b: Madison
```

The `filter: role: [train]` line keeps only the 71 single-author papers (Hamilton, Madison,
Jay) for **every** method in the study. The disputed and joint papers are not loaded at all,
so nothing is projected back in: Delta here reports only in-sample (resubstitution) accuracy,
and the PCA and dendrogram show known-author papers only. Attribution of the disputed papers
is step 5.

## 4. Run the study

```bash
bitig run study.yaml --name demo
```

Expect per-method directories under `results/demo/`:

```
results/demo/
├── resolved_config.json
├── burrows/
│   ├── result.json
│   └── confusion_matrix.png
├── pca/
│   ├── result.json
│   ├── scatter.png
│   └── pca_biplot.png
├── ward/
│   ├── result.json
│   └── dendrogram.png
└── zeta_hamilton_madison/
    ├── result.json
    ├── table_0.parquet     # Hamilton-preferred vocabulary
    ├── table_1.parquet     # Madison-preferred vocabulary
    └── zeta.png
```

Each `result.json` carries its own provenance block (corpus hash, seed, resolved config).
If a method fails, its directory holds an `error.txt` instead and `bitig run` exits with
status 1.

## 5. Attribute the disputed papers

The declarative study cannot train on one subset and score another yet, so attribution uses
the `bitig delta` and `bitig bayesian` commands with `--test-filter`:

```bash
bitig delta corpus --method burrows --mfw 200 \
    --metadata corpus/metadata.tsv --group-by author --test-filter role=test

bitig bayesian corpus --mfw 200 \
    --metadata corpus/metadata.tsv --group-by author --test-filter role=test
```

Both commands train on **every paper not selected by `--test-filter`**: the 71
single-author papers *and* the 3 joint papers, which form a fourth `Joint_HM` class next to
Hamilton, Madison and Jay. Neither command can leave the joint papers out; to do that, drop
them from the corpus directory you pass in.

`bitig bayesian` prints a `max p(author)` column. These are Naive Bayes posteriors that treat
every word occurrence as independent, so they are pushed to 0 or 1 and are **not calibrated
probabilities**. Read them as a ranking of candidates, not as a measure of certainty.

## 6. Render figures

`bitig run` already writes the default figures listed above, but its PCA scatter is not
coloured by author. The example ships a `render_figures.py` that redraws the PCA scatter
coloured by author, plus the dendrogram and Zeta plot:

```bash
python examples/federalist/render_figures.py results/demo corpus/metadata.tsv
```

This produces `pca.png`, `ward.png`, and `zeta.png` inside the matching method directories.
The figure titles say "MFW=500" because the script was written for the example's own
`study.yaml`.

## 7. Report

```bash
bitig report results/demo --output results/demo/report.html
```

Open the HTML in a browser — you get a single-page report with the method sections,
embedded figures, and a provenance section.

## Expected outcome

These are the numbers from running the steps above on the shipped corpus:

- **PCA** (71 papers, MFW 200): the first two components explain 7.4 % and 5.9 % of the
  variance (13.3 % together). PC1 mainly separates Jay's five essays from everyone else.
  Hamilton and Madison overlap heavily: Madison papers sit higher on PC2 on average, but
  there is no clean split. With the example's own MFW 500 study the two components explain
  5.6 % and 4.5 %.
- **Ward** (3 clusters): the Madison papers do not form their own cluster. Nine of them
  share the largest cluster with 45 Hamilton papers and 2 Jay papers; the other six form a
  second cluster with 6 Hamilton papers. The remaining 3 Jay papers make up the third
  cluster.
- **Burrows Delta in the study**: resubstitution accuracy 1.0. This is an in-sample
  separability check, not an attribution result.
- **Zeta**: the Hamilton-preferred list is topped by `upon`, `kind`, `community`, `intended`
  and `men`; the Madison-preferred list by `few`, `consequently`, `whilst`, `proceedings` and
  `particularly`. `upon` and `whilst` are among the markers Mosteller & Wallace relied on.
- **Attribution (step 5)**: `bitig delta` (MFW 200) assigns all 11 disputed papers to Madison.
  `bitig bayesian` also picks Madison for all 11 and prints `max p(author)` = 1.000 for each.
  As explained above, that 1.000 is not a calibrated probability. With `--mfw 500` (the
  commands in the example's `README.md`), `bitig bayesian` still picks Madison for all 11,
  but `bitig delta` assigns No. 50 to the fourth `Joint_HM` class and the other 10 to
  Madison. No disputed paper goes to Hamilton at either setting.

The Madison attribution matches Mosteller & Wallace's 1964 result.

The quickstart mini-version of this tutorial is at
[`examples/quickstart/`](https://github.com/fatihbozdag/bitig/tree/main/examples/quickstart)
if you want to run through the pipeline on just 9 papers first.
