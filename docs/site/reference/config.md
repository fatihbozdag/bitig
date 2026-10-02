# study.yaml schema

The declarative study config consumed by `bitig run`. A minimal example:

```yaml
name: my-study
seed: 42

corpus:
  path: corpus
  metadata: corpus/metadata.tsv

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
```

The file is validated in two passes. Loading checks its shape: every section rejects keys it
does not know, so a misspelt top-level or section key is an error. `bitig run` then checks
every feature and method parameter against the constructor it is passed to and refuses the
study if any is unknown, so a typo or a stale key fails at load time instead of being
silently ignored.

!!! note "Accepted but currently not used"
    Some sections are part of the schema (so a `study.yaml` that sets them loads) but
    `bitig run` does not read them yet: **`viz`**, **`report`**, **`cache`**,
    **`preprocess.spacy`** (`model`, `backend`, `device`, `exclude`) and
    **`preprocess.normalize`**. They are marked below. Setting them has no effect on a run.

## Top-level keys

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | str | no | Study name (default `unnamed-study`); recorded in `resolved_config.json` |
| `seed` | int | no | Default seed (42). Passed to every stochastic method unless it sets its own (see [reproducibility](../concepts/results.md)). |
| `corpus` | object | yes | Corpus config (below) |
| `preprocess` | object | no | Corpus language; spaCy and normalisation settings (below) |
| `features` | list | no | Feature extractors referenced by methods (default: none) |
| `methods` | list | no | Methods to run (default: none) |
| `output` | object | no | Output directory / timestamping |
| `viz` | object | no | *Accepted but currently not used* |
| `report` | object | no | *Accepted but currently not used* |
| `cache` | object | no | *Accepted but currently not used* |

## corpus

```yaml
corpus:
  path: corpus                    # directory of .txt files
  metadata: corpus/metadata.tsv   # optional TSV with filename + arbitrary fields
  filter:                         # optional: subset the corpus before running
    role: [train]
```

| Key | Description |
|---|---|
| `path` | Directory of `.txt` files (required). |
| `metadata` | Optional TSV with a `filename` column plus any fields. When given, every text file must have a row — there is no `strict` switch in `study.yaml`. |
| `filter` | Keep only documents whose metadata matches every key: a scalar value is an exact match, a list is membership. |

## preprocess

```yaml
preprocess:
  language: en              # en, tr, de, es, fr
```

| Key | Description |
|---|---|
| `language` | Corpus language code (default `en`; case-insensitive). Selects function-word lists, readability formulas and similar language-specific resources. |
| `spacy.model`, `spacy.backend` (`spacy` \| `spacy_stanza`), `spacy.device` (`auto` \| `cpu` \| `mps` \| `cuda`), `spacy.exclude` | *Accepted but currently not used.* `bitig run` does no spaCy parsing; the extractors it supports work on raw text. To choose a spaCy model for `bitig ingest`, use its `--spacy-model` option. |
| `normalize.lowercase`, `normalize.strip_punct`, `normalize.collapse_numerals`, `normalize.expand_contractions` | *Accepted but currently not used.* Lower-casing is set per feature (`lowercase:`). |

## features

Each feature extractor is a dict with an `id` (referenced by methods), a `type`, and
type-specific params, written either inline or under a `params:` key.

### Supported types

| type | params |
|---|---|
| `mfw` | `n`, `min_df`, `max_df`, `scale` ({none, zscore, l1, l2}), `lowercase` |
| `word_ngram` | `n` (int or [min, max]), `lowercase`, `scale`, `max_features` |
| `char_ngram` | `n` (int or [min, max]), `include_boundaries`, `scale`, `max_features` |
| `function_word` | `wordlist` (optional list), `language`, `scale` |
| `punctuation` | (none) |
| `lexical_diversity` | `indices` (default `[ttr, yules_k]`) |
| `readability` | `indices`, `language` |

The schema also knows `pos_ngram`, `dependency_bigram`, `sentence_length`,
`sentence_embedding` and `contextual_embedding`, but `bitig run` does not implement them and
refuses a study that uses them. They are available from the Python API.

## methods

Each method is a dict with an `id`, a `kind`, an optional `features` (feature id), an
optional `group_by` (metadata column), an optional `cv` block (classify only), plus params —
written inline or under a `params:` key. When `features` is a list only its first entry is
used. `zeta`, `consensus`, `rolling_delta` and `verify` work on the corpus directly and do not
use `features`.

### Supported kinds

| kind | Description |
|---|---|
| `delta` | Nearest-centroid attribution; needs `features` and `group_by`. `variant:` is one of `burrows` (default), `cosine`, `eder`, `eder_simple`, `argamon_linear`, `quadratic`. `method:` is a deprecated alias for `variant:`. |
| `zeta` | Craig's Zeta; needs `group_by`. Params: `variant` (`classic` default, `eder`), `top_k` (default 20), `min_df`, `group_a`, `group_b` (default: the two largest groups). |
| `reduce` | Dimensionality reduction; needs `features`. `variant`: `pca` (default), `mds`, `tsne`, `umap` (extra `bitig[cluster]`); `n_components` (default 2) plus the underlying estimator's own keyword arguments. |
| `cluster` | Clustering; needs `features`. `variant`: `hierarchical` (default; `n_clusters`, `linkage`, `metric`), `kmeans` (`n_clusters`, `random_state`, `n_init`), `hdbscan` (`min_cluster_size`, `min_samples`, `metric`; extra `bitig[cluster]`). |
| `consensus` | Bootstrap consensus tree. Params: `mfw_bands` (default `[100, 200, 300]`), `replicates` (default 20), `subsample`, `support_threshold`, `seed`. |
| `classify` | sklearn classifier; needs `features` and `group_by`. `estimator`: `logreg` (default), `svm_linear`, `svm_rbf`, `rf`, `hgbm`. Cross-validation in a `cv:` block (below). |
| `bayesian` | Wallace–Mosteller attribution; needs `features` and `group_by`. Param: `prior_alpha` (default 1.0). Extra `bitig[bayesian]`. |
| `rolling_delta` | Rolling Delta over long texts; needs `group_by` and `target_ids`. Params: `window_size`, `step`, `base_delta`, `mfw_n`, `lowercase`. |
| `verify` | General Impostors verification; needs `group_by`, `target_ids` and `candidate`. Params: `n_iter`, `feature_frac`, `impostor_n`, `base_delta`, `mfw_n`, `lowercase`, `threshold`, `seed`. |

### cv (classify)

```yaml
cv:
  kind: stratified          # stratified | loao | leave_one_text_out
  folds: 5                  # number of folds (default 5)
  groups_from: work         # loao only: metadata column to group folds by
```

`loao` requires `groups_from`, and it must not be a one-to-one relabelling of `group_by`.

## output

```yaml
output:
  dir: results/         # default
  timestamp: true       # wrap runs in timestamped subdirectories
```

`bitig run --output` and `--name` override these.

## viz, report, cache

*Accepted but currently not used.* `bitig run` always writes each method's default figure
as PNG; build reports with [`bitig report`](cli.md#bitig-report-run-dir) and manage the
spaCy cache with [`bitig cache`](cli.md#cache).

```yaml
viz:
  format: [pdf, png]    # pdf | png | svg | eps | tiff
  dpi: 300
  style: default
  palette: colorblind

report:
  format: none          # html | md | none
  offline: false
  include: [corpus, config, provenance, results]
  title: null

cache:
  dir: .bitig/cache
  reuse: true
```

## A realistic multi-method example

```yaml
name: federalist
seed: 42
output: { dir: results, timestamp: false }

corpus:
  path: corpus
  metadata: corpus/metadata.tsv
  filter:
    role: [train]

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

  - id: zeta_h_m
    kind: zeta
    group_by: author
    params:
      top_k: 50
      group_a: Hamilton
      group_b: Madison

  - id: logreg
    kind: classify
    features: mfw200
    group_by: author
    estimator: logreg
    cv: { kind: stratified, folds: 3 }
```
