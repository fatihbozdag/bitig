# Tutorial: Federalist Papers

Reproducing Mosteller & Wallace's (1964) classical authorship attribution of the 85
Federalist Papers.

## Background

The Federalist Papers (1787–1788) were published under the pseudonym *Publius* to
argue for ratification of the US Constitution. Authorship of 73 papers is known
(Hamilton, Madison, Jay); 12 are disputed between Hamilton and Madison. Mosteller &
Wallace (1964) used word-frequency Bayesian inference to attribute all 12 disputed
papers to Madison — a result confirmed by every subsequent stylometric analysis.

This tutorial uses bitig to reproduce the essentials of their result: training Burrows
Delta on the known Hamilton / Madison papers, projecting the disputed papers onto the
learned space, and visualising the separation with PCA and a Ward dendrogram.

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
own `README.md` to build it from Project Gutenberg.

`metadata.tsv` has one row per paper with: `filename`, `author`, `number`, `role`
(`train` for known-author papers, `test` for disputed).

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

The `filter: role: [train]` line hides the disputed papers during training so Delta
has a clean Hamilton / Madison centroid; we project the disputed set back in at the
analysis step.

## 4. Run the study

```bash
bitig run study.yaml --name demo
```

Expect per-method directories under `results/demo/`:

```
results/demo/
├── resolved_config.json
├── burrows/
│   └── result.json
├── pca/
│   └── result.json
├── ward/
│   └── result.json
└── zeta_hamilton_madison/
    ├── result.json
    ├── table_0.parquet     # Hamilton-preferred vocabulary
    └── table_1.parquet     # Madison-preferred vocabulary
```

## 5. Render figures

Matplotlib rendering is a thin post-processing step (full integration lands in a later
phase). The example ships a `render_figures.py` you can invoke:

```bash
python examples/federalist/render_figures.py results/demo metadata.tsv
```

This produces `pca.png`, `ward.png`, and `zeta.png` inside each method directory.

## 6. Report

```bash
bitig report results/demo --output results/demo/report.html
```

Open the HTML in a browser — you get a single-page report with the method sections,
embedded figures, and the full provenance JSON.

## Expected outcome

On PCA the Hamilton and Madison papers form two tight clusters along the first two
components (together ~35 % variance), with Jay's five essays at the margin. Burrows
Delta at MFW=200 attributes every disputed paper to Madison — matching Mosteller &
Wallace's 1964 result.

The quickstart mini-version of this tutorial is at
[`examples/quickstart/`](https://github.com/fatihbozdag/bitig/tree/main/examples/quickstart)
if you want to run through the pipeline on just 9 papers first.
