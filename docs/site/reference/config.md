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

## Top-level keys

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | str | yes | Study name; shows in reports |
| `seed` | int | no | Default seed (42). Passed to every stochastic method unless it sets its own (see [reproducibility](../concepts/results.md)). |
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
  strict: true                    # default: raise if any file lacks metadata
  filter:                         # optional: subset the corpus before running
    role: [train]
```

## features

Each feature extractor is a dict with an `id` (referenced by methods), a `type`, and
type-specific params.

### Supported types

| type | params |
|---|---|
| `mfw` | `n`, `min_df`, `max_df`, `scale` ({none, zscore, l1, l2}), `lowercase` |
| `word_ngram` | `n` (int or [min, max]), `lowercase`, `scale` |
| `char_ngram` | `n`, `include_boundaries`, `scale` |
| `function_word` | `wordlist` (optional list or path), `scale` |
| `punctuation` | (none) |
| `lexical_diversity` | (none) |
| `readability` | (none) |

## methods

Each method is a dict with an `id`, a `kind`, an optional `features` (feature id), plus
`params`.

### Supported kinds

| kind | Description |
|---|---|
| `delta` | Nearest-centroid attribution (`variant: burrows` by default; also `cosine`, `eder`, `eder_simple`, `argamon_linear`, `quadratic`) |
| `zeta` | Craig's Zeta; requires `group_by` and either inferred or specified `params.group_a` / `group_b` |
| `reduce` | Dim-reduction (default PCA); `params.n_components` |
| `cluster` | Hierarchical (default Ward); `params.n_clusters`, `params.linkage` |
| `consensus` | Bootstrap consensus tree; `params.mfw_bands`, `params.replicates` |
| `classify` | sklearn classifier; `params.estimator`, `cv.kind`, `cv.folds` |

`bitig run` checks every feature and method parameter against the constructor it is
passed to and refuses the study if any is unknown, so a typo or a stale key fails at load
time instead of being silently ignored. Feature types the runner does not implement
(`pos_ngram`, `dependency_bigram`, `sentence_length`, the embedding types) are refused
the same way. `method:` on a `delta` method is a deprecated alias for `variant:`.

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
```
