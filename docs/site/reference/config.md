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
    method: burrows
    features: mfw200
    group_by: author
```

## Top-level keys

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | str | yes | Study name; shows in reports |
| `seed` | int | no | Default seed (42). Threaded to every stochastic method. |
| `corpus` | object | yes | Corpus config (below) |
| `features` | list | yes | One or more feature extractors |
| `methods` | list | yes | One or more methods to run |
| `output` | object | no | Output directory / timestamping |
| `cache` | object | no | DocBin cache directory |
| `preprocess` | object | no | spaCy model selection |

## corpus

```yaml
corpus:
  path: corpus                    # directory of .txt files
  metadata: corpus/metadata.tsv   # optional TSV with filename + arbitrary fields
  filter:                         # optional: subset the corpus before running
    role: [train]
```

## features

Each feature extractor is a dict with an `id` (referenced by methods), a `type`, and
type-specific params.

### Supported types

| type | params |
|---|---|
| `mfw` | `n`, `min_df`, `max_df`, `scale` ({none, zscore, l1, l2}), `lowercase`, `frequency_basis` |
| `word_ngram` | `n` (int or [min, max]), `lowercase`, `scale` |
| `char_ngram` | `n`, `include_boundaries`, `scale` |
| `function_word` | `wordlist` (optional list), `language`, `scale` |
| `punctuation` | (none) |
| `lexical_diversity` | (none) |
| `readability` | (none) |

## methods

Each method is a dict with an `id`, a `kind`, an optional `features` (feature id), plus
`params`.

### Supported kinds

| kind | Description |
|---|---|
| `delta` | Nearest-centroid attribution (`method: burrows` by default) |
| `zeta` | Craig's Zeta; requires `group_by` and either inferred or specified `params.group_a` / `group_b` |
| `reduce` | Dim-reduction (default PCA); `params.n_components` |
| `cluster` | Hierarchical (default Ward); `params.n_clusters`, `params.linkage` |
| `consensus` | Bootstrap consensus tree; `params.mfw_bands`, `params.replicates` |
| `classify` | sklearn classifier; `params.estimator`, `cv.kind`, `cv.folds` |

## output

```yaml
output:
  dir: results          # default
  timestamp: true       # wrap runs in timestamped subdirectories
```

## cache

```yaml
cache:
  dir: .bitig/cache     # spaCy DocBin cache location
```

## preprocess

```yaml
preprocess:
  spacy:
    model: en_core_web_trf    # default; change to sm/md for speed
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
    method: burrows
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
```

## Execution and evaluation contracts

`bitig run` validates feature references, unique safe IDs, estimator parameters, and
supported settings before creating its output directory. Existing run directories
are never reused. `run_status.json` records each method's outcome; the CLI exits
with 0 for success, 1 for failure, and 2 for partial success. Reports include failed
methods. The Python `run_study()` API retains its Path return value;
`StudyRunStatus.load(path)` reads the structured outcome.

`preprocess.language` controls the corpus language and default function-word and
readability features. Lowercasing, punctuation removal, and numeral collapsing are
supported under `preprocess.normalize`; `expand_contractions` is rejected.
The runner supports spaCy `auto`/`cpu` device settings. POS, dependency, and
sentence-length extractors use the configured model/backend/exclusions and
`cache.dir` / `cache.reuse`. Embedding feature types currently require the Python
API or dedicated CLI; the study runner rejects them rather than skipping them.

Classification learns vocabulary and scaling separately in each training fold:

```yaml
methods:
  - id: classifier
    kind: classify
    features: mfw200
    group_by: author
    params: {estimator: rf, n_estimators: 200}
    cv: {kind: group_kfold, groups_from: source_text, folds: 3}
```

Supported CV kinds are `stratified`, `group_kfold`, `loao` (leave one group out),
and `leave_one_text_out`. Group by a unit independent of the target labels;
training folds missing a target class are rejected. Unspecified stratified folds
use `min(5, smallest_class_size)`, requiring at least two. Fold indices, document
IDs, training feature hashes, and effective estimator parameters are recorded.
Bayesian study methods also accept `cv`; without it, they report explicitly
labelled in-sample `resubstitution_accuracy`. The standalone Bayesian CLI requires
`--test-filter` for a held-out split and does not perform automatic CV.

`viz.format`, `viz.dpi`, `viz.style`, and `viz.palette` control plot export.
`report.format` (`html`, `md`, `none`) and `report.title` control report generation.
HTML figures are embedded, making reports offline by default. Customized
`report.include` lists are currently rejected. Multiple feature references per
method are rejected rather than silently selecting only the first.
Methods that extract their own features (`rolling_delta`, `verify`, `zeta`, and
`consensus`) reject `features` references. A report-generation failure is recorded
in `run_status.json` as `report_error` and produces a nonzero CLI exit while
preserving completed method results.
