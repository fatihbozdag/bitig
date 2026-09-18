# Features

Every feature extractor returns a `FeatureMatrix` — the shared numeric envelope that
methods consume.

## The FeatureMatrix

```python
@dataclass
class FeatureMatrix:
    X: np.ndarray            # (n_docs, n_features)
    document_ids: list[str]
    feature_names: list[str]
    feature_type: str
    extractor_config: dict[str, Any]
    provenance_hash: str
```

Key properties:

- `fm.n_features`, `len(fm)` for `n_docs`
- `fm.as_dataframe()` — pandas `DataFrame` indexed by `document_ids`
- `fm.concat(other)` — column-concatenate two matrices with identical row ids

## Available extractors

Import from `bitig`:

| Extractor | Input | Output |
|---|---|---|
| `MFWExtractor(n=..., scale=..., lowercase=...)` | Corpus | top-n word relative frequencies (z-scored, L1, L2, or raw) |
| `CharNgramExtractor(n=..., include_boundaries=...)` | Corpus | character n-gram counts (delegates to sklearn CountVectorizer) |
| `WordNgramExtractor(n=..., lowercase=...)` | Corpus | word n-gram counts |
| `PosNgramExtractor(n=..., coarse=...)` | Corpus | spaCy POS n-grams |
| `DependencyBigramExtractor()` | Corpus | (head_lemma, dep, child_lemma) triples |
| `FunctionWordExtractor(wordlist=...)` | Corpus | bundled English function-word frequencies |
| `PunctuationExtractor()` | Corpus | ASCII punctuation frequencies |
| `ReadabilityExtractor()` | Corpus | six readability indices (Flesch, FK-grade, Gunning Fog, Coleman-Liau, ARI, SMOG) |
| `SentenceLengthExtractor()` | Corpus | mean, SD, skew of per-sentence tokens |
| `LexicalDiversityExtractor()` | Corpus | TTR, MATTR, MTLD, HD-D, Yule's K/I, Herdan's C, Simpson's D |
| `SentenceEmbeddingExtractor(model=...)` | Corpus | sentence-transformers pooled embedding (extra: `bitig[embeddings]`) |
| `ContextualEmbeddingExtractor(model=..., pooling=...)` | Corpus | HF transformer hidden-state vectors (extra: `bitig[embeddings]`) |

### Extractor detail

Each extractor above is a callable object; `fit_transform(corpus)` returns a
`FeatureMatrix`.

#### MFWExtractor
`MFWExtractor(n=200, scale="zscore", lowercase=True)`

*Use when:* you want the canonical stylometric feature — relative frequencies of
the most-frequent words. Default choice for Delta-family attribution.
*Don't use when:* your corpus is very small (<200 unique tokens), or the question is
topic-invariant (MFW is topic-sensitive; see `CategorizedCharNgramExtractor`).
*Expect:* an `(n_docs, n)` float matrix; rows sum to ~1 under `scale="l1"`,
zero-centred unit-variance under `scale="zscore"`.

**Numerical compatibility:** MFW z-scoring now divides word counts by the full
number of word tokens in each document before learning training means and
standard deviations. Earlier releases divided by counts in the selected
vocabulary. Set `frequency_basis="vocabulary"` explicitly to reproduce that
historical definition; the new default is `"document"`. L1/L2 row normalization
and raw counts retain their previous definitions. Record this setting when
comparing old and new results. Function-word `scale="zscore"` now uses training
count means/standard deviations; it previously returned raw counts.

#### CharNgramExtractor
`CharNgramExtractor(n=3, include_boundaries=True)`

*Use when:* you want features that capture sub-word style (prefixes, suffixes,
punctuation adjacency) and that cope with OOV words or misspellings.
*Don't use when:* your languages mix scripts (n-grams across scripts produce noise),
or you specifically need word-level semantic sensitivity.
*Expect:* sparse count matrix delegated to sklearn's `CountVectorizer`.

#### WordNgramExtractor
`WordNgramExtractor(n=1, lowercase=True)`

*Use when:* unigrams (MFW equivalent) or short bigram phrases are what you need and
you don't want z-scoring. Bigrams useful for detecting fixed expressions.
*Don't use when:* n ≥ 3 in small corpora — sparsity dominates. Use `MFWExtractor`
for unigrams unless you need raw counts.
*Expect:* sparse count matrix; vocabulary grows fast with n.

#### PosNgramExtractor
`PosNgramExtractor(n=2, coarse=False)`

*Use when:* you want syntactic-style features (sequences of part-of-speech tags) —
insensitive to content words, sensitive to register and syntactic register.
*Don't use when:* your spaCy pipeline doesn't include a tagger (most `_trf` models
do), or your corpus is very small per-doc.
*Expect:* sparse count matrix over POS n-grams. `coarse=True` uses UD coarse tags
(fewer dimensions, more robust).

#### DependencyBigramExtractor
`DependencyBigramExtractor()`

*Use when:* you want syntax-sensitive style features — specifically, the
(head-lemma, dependency-relation, child-lemma) triples parsed by spaCy.
*Don't use when:* your parser is a bottleneck; dependency parsing is the slowest
step in the spaCy pipeline and you may be able to substitute POS n-grams.
*Expect:* sparse count matrix over dependency triples.

#### FunctionWordExtractor
`FunctionWordExtractor(wordlist=None)`

*Use when:* you want the short, topic-insensitive function-word list (the classic
anti-topic signal for stylometry) for the document's language.
*Don't use when:* your corpus mixes languages without a per-doc language tag — the
per-language word list won't apply.
*Expect:* `(n_docs, |wordlist|)` relative-frequency matrix. Defaults come from the
bundled per-language list (see [Languages](languages.md)).

#### PunctuationExtractor
`PunctuationExtractor()`

*Use when:* you want pure-style features that are nearly topic-invariant —
punctuation usage is remarkably author-specific and corpus-robust.
*Don't use when:* your source text has been normalised or stripped of punctuation
(e.g., OCR output without correction).
*Expect:* `(n_docs, ~20)` matrix of ASCII punctuation relative frequencies.

#### ReadabilityExtractor
`ReadabilityExtractor()`

*Use when:* you want readability-as-style — Flesch, FK-grade, Gunning Fog, etc. —
as a lightweight feature set to combine with MFW.
*Don't use when:* readability itself is the question (for that, read the metric
directly; don't bundle into a Delta). For non-English, use the per-language
native-formula variant — see `concepts/languages.md`.
*Expect:* `(n_docs, 6)` matrix of readability indices (English defaults: Flesch,
FK-grade, Gunning Fog, Coleman-Liau, ARI, SMOG).

#### SentenceLengthExtractor
`SentenceLengthExtractor()`

*Use when:* you want the sentence-rhythm signature — mean, SD, and skew of
per-sentence token counts. Small but strong stylistic signal.
*Don't use when:* your text has aggressive sentence-boundary errors (e.g., ALL
CAPS legal text breaks most sentencizers).
*Expect:* `(n_docs, 3)` matrix: `[mean, std, skew]`.

#### LexicalDiversityExtractor
`LexicalDiversityExtractor()`

*Use when:* you want vocabulary-richness features — TTR, MATTR, MTLD, HD-D, Yule's
K/I, Herdan's C, Simpson's D. Eight indices let you compare sensitivities.
*Don't use when:* your documents are very short (<200 tokens); most indices become
unstable.
*Expect:* `(n_docs, 8)` matrix; columns are the 8 indices.

#### SentenceEmbeddingExtractor
`SentenceEmbeddingExtractor(model="paraphrase-MiniLM-L6-v2")`

*Use when:* you want a modern neural-embedding feature set — pooled
sentence-transformer output per document. Strong in classification + clustering;
fast enough for moderate corpora.
*Don't use when:* your hardware lacks GPU / MPS and your corpus is large (CPU
inference is slow), or when interpretability matters (these vectors are opaque).
*Expect:* `(n_docs, embedding_dim)` dense matrix. Requires `bitig[embeddings]`.

#### ContextualEmbeddingExtractor
`ContextualEmbeddingExtractor(model="bert-base-multilingual-cased", pooling="mean")`

*Use when:* you want HuggingFace-model hidden states aggregated per document —
language-specific embeddings (e.g., `dbmdz/bert-base-turkish-cased` for Turkish)
with configurable pooling.
*Don't use when:* you don't need a specific model's representation — use
`SentenceEmbeddingExtractor` for a lighter, faster default.
*Expect:* `(n_docs, hidden_dim)` dense matrix. Requires `bitig[embeddings]`.

## Composing features

Two ways to build a multi-feature matrix:

### Python

```python
from bitig import MFWExtractor, PunctuationExtractor

mfw = MFWExtractor(n=200, scale="zscore").fit_transform(corpus)
punct = PunctuationExtractor().fit_transform(corpus)
combined = mfw.concat(punct)  # (n_docs, n_mfw + n_punct)
```

### study.yaml

```yaml
features:
  - id: mfw
    type: mfw
    n: 200
    scale: zscore
  - id: punct
    type: punctuation
```

Methods can reference feature ids; the runner builds each matrix once and reuses it.

## Forensic feature extractors

Two topic-invariant extractors live under `bitig.forensic`:

#### CategorizedCharNgramExtractor
`CategorizedCharNgramExtractor(n=4, categories=("prefix","suffix","punct"))`

*Use when:* you want topic-invariant character-level features for forensic
verification — n-grams classified by position in the word so you can keep only
the style-carrying categories (affixes, punctuation) and drop the topic-sensitive
whole-word category.
*Don't use when:* topic robustness isn't the goal — a plain `CharNgramExtractor`
is faster and carries more signal per dimension.
*Expect:* sparse count matrix restricted to the chosen n-gram categories.

Sapkota et al. 2015; `categories=("prefix","suffix","punct")` is the affix-only
recipe that generalises best across topics.

#### distort_corpus
`distort_corpus(corpus, mode="dv_ma")`

*Use when:* you want Stamatatos (2013) topic masking — replaces content words with
placeholders while keeping function words and punctuation. Pair with any
extractor for a topic-invariant pipeline.
*Don't use when:* your analysis needs content-word signal (e.g., Zeta looking for
distinctive vocabulary).
*Expect:* a new Corpus object you feed to any existing extractor. Modes: `"dv_ma"`
masks all content words, `"dv_sa"` masks selectively.

See [Topic-invariant features](../forensic/topic-invariance.md).

## Scaling

Most extractors accept `scale ∈ {"none", "zscore", "l1", "l2"}`:

- `none` — raw counts. Use for Bayesian Wallace–Mosteller.
- `l1` — relative frequencies (row sums to 1). Use for Zeta-like contrast methods.
- `l2` — unit-norm rows. Use for cosine-based distances.
- `zscore` — per-column z-score on training means / SDs (Stylo convention). **Required for
  Burrows Delta.**

The z-score mean / SD are learned at `fit` time and applied at `transform` — so scores on
unseen documents use the training distribution.

## Next

- [Methods](methods.md) — take the FeatureMatrix and produce a Result.
