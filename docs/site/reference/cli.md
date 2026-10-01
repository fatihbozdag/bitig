# CLI reference

Every bitig CLI command. Installed as `bitig` via the `bitig` entry point.

## Project scaffolding

### `bitig init <name>`

Scaffold a new project directory.

```bash
bitig init my-study
```

Creates:

```
my-study/
├── corpus/             # drop .txt files here
│   └── metadata.tsv    # one row per file
├── study.yaml          # declarative study config
└── README.md           # short pointer
```

## Ingestion

### `bitig ingest <path>`

Parse a corpus directory with optional metadata.

```bash
bitig ingest corpus/ --metadata corpus/metadata.tsv [--strict|--no-strict]
```

- `--strict` (default) — raise if any document lacks a metadata row
- `--no-strict` — allow partial coverage

Output is cached as a spaCy DocBin for subsequent commands.

### `bitig info`

Summarise an ingested corpus: document count, metadata fields + value distributions,
total tokens.

## Features

### `bitig features <path>`

Build a feature matrix and print a summary.

```bash
bitig features corpus/ --metadata corpus/metadata.tsv --type mfw --n 500
```

Types: `mfw`, `word_ngram`, `char_ngram`, `function_word`, `punctuation`,
`lexical_diversity`, `readability`.

## Methods

All method commands accept `--metadata`, `--group-by <field>`, `--seed <int>`.

| Command | Does |
|---|---|
| `bitig delta <path> --method {burrows,argamon,eder,cosine,quadratic}` | Fit Delta, print per-author predictions |
| `bitig zeta <path> --group-a X --group-b Y` | Craig's Zeta contrast between two author groups |
| `bitig reduce <path> --method {pca,mds,tsne,umap} --n-components 2` | Dimensionality reduction → parquet |
| `bitig cluster <path> --method {hierarchical,kmeans,hdbscan} --n-clusters N --seed S` | Clustering with `--seed` for k-means |
| `bitig consensus <path>` | Bootstrap consensus tree across MFW bands |
| `bitig classify <path> --estimator {logreg,svm_linear,svm_rbf,rf,hgbm} --cv-kind {stratified,loao,leave_one_text_out}` | sklearn classifier + stylometry-aware CV |
| `bitig embed <path>` | Sentence or contextual embeddings (extra: `bitig[embeddings]`) |
| `bitig bayesian <path>` | Wallace–Mosteller attribution + hierarchical group comparison (extra: `bitig[bayesian]`) |

## Orchestration

### `bitig run <study.yaml>`

Execute a full declarative study end-to-end.

```bash
bitig run study.yaml --name demo [--output results/] [--overwrite]
```

Writes every method's `Result` to its own subdirectory plus a `resolved_config.json`.
A run directory that already holds a previous run is refused; `--overwrite` replaces that
run's outputs (and nothing else). Exits with code 1 if any method failed — each failed
method's folder has an `error.txt` with the traceback.

### `bitig report <run-dir>`

Render a Jinja2 HTML or Markdown report from a run directory.

```bash
bitig report results/demo --output results/demo/report.html [--format html|md]
```

### `bitig plot <run-dir>`

Render per-method figures (PCA scatter, Ward dendrogram, Zeta preference plot, …) from
saved Results.

### `bitig shell`

Interactive Rich-based wizard that walks you through a study setup.

## Cache

### `bitig cache <cmd>`

Manage the spaCy DocBin cache produced by `bitig ingest`:

- `bitig cache info` — summarise
- `bitig cache clear` — remove

## Getting help

Every command supports `--help`:

```bash
bitig --help
bitig run --help
```
