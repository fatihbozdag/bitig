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
| `MFWExtractor(n=..., scale=..., lowercase=...)` | Corpus | top-n words: z-scored relative frequencies (default), L1 / L2 row-normalised counts, or raw counts |
| `CharNgramExtractor(n=..., include_boundaries=..., scale=...)` | Corpus | character n-gram counts (delegates to sklearn CountVectorizer) |
| `WordNgramExtractor(n=..., lowercase=..., scale=...)` | Corpus | word n-gram counts |
| `PosNgramExtractor(n=..., tagset=..., spacy_model=...)` | Corpus | spaCy POS n-gram counts |
| `DependencyBigramExtractor(spacy_model=..., lowercase=...)` | Corpus | (head_lemma, dep, child_lemma) triple counts |
| `FunctionWordExtractor(wordlist=..., language=..., scale=...)` | Corpus | counts of the bundled per-language function words |
| `PunctuationExtractor()` | Corpus | counts of the 32 ASCII punctuation characters |
| `ReadabilityExtractor(indices=..., language=...)` | Corpus | per-language readability indices (English default: Flesch, FK-grade, Gunning Fog) |
| `SentenceLengthExtractor(spacy_model=...)` | Corpus | mean, SD, skew of per-sentence tokens |
| `LexicalDiversityExtractor(indices=...)` | Corpus | TTR, MATTR, MTLD, HD-D, Yule's K/I, Herdan's C, Simpson's D |
| `SentenceEmbeddingExtractor(model=...)` | Corpus | sentence-transformers pooled embedding (extra: `bitig[embeddings]`) |
| `ContextualEmbeddingExtractor(model=..., layer=..., pool=...)` | Corpus | HF transformer hidden-state vectors (extra: `bitig[embeddings]`) |

### Extractor detail

Each extractor above is an sklearn-style object; `fit_transform(corpus)` returns a
`FeatureMatrix`.

#### MFWExtractor
`MFWExtractor(n=200, scale="zscore", lowercase=True)`

*Use when:* you want the canonical stylometric feature — relative frequencies of
the most-frequent words. Default choice for Delta-family attribution.
*Don't use when:* your corpus is very small (<200 unique tokens), or the question is
topic-invariant (MFW is topic-sensitive; see `CategorizedCharNgramExtractor`).
*Expect:* an `(n_docs, n)` float matrix. Defaults are `n=1000`, `scale="zscore"`,
`lowercase=False` (plus `min_df=1`, `max_df=1.0`). Under `scale="zscore"` each value is
the relative frequency `count / document token count`, z-scored with the fitted column
means and SDs; `"l1"` rows sum to 1 over the retained words; `"none"` is raw counts.

#### CharNgramExtractor
`CharNgramExtractor(n=3, include_boundaries=False, scale="none", max_features=None)`

*Use when:* you want features that capture sub-word style (prefixes, suffixes,
punctuation adjacency) and that cope with OOV words or misspellings.
*Don't use when:* your languages mix scripts (n-grams across scripts produce noise),
or you specifically need word-level semantic sensitivity.
*Expect:* a dense count matrix built with sklearn's `CountVectorizer` (no case folding).
`include_boundaries=True` uses its `char_wb` analyser (n-grams inside word boundaries).
`n` may be an int or a `(min_n, max_n)` tuple.

#### WordNgramExtractor
`WordNgramExtractor(n=1, lowercase=False, scale="none", max_features=None)`

*Use when:* unigrams (MFW equivalent) or short bigram phrases are what you need and
you don't want z-scoring. Bigrams useful for detecting fixed expressions.
*Don't use when:* n ≥ 3 in small corpora — sparsity dominates. Use `MFWExtractor`
for unigrams unless you need raw counts.
*Expect:* dense count matrix; vocabulary grows fast with n.

#### PosNgramExtractor
`PosNgramExtractor(n=2, tagset="coarse", spacy_model="en_core_web_trf")`

*Use when:* you want syntactic-style features (sequences of part-of-speech tags) —
insensitive to content words, sensitive to register and syntactic register.
*Don't use when:* your spaCy pipeline doesn't include a tagger (most `_trf` models
do), or your corpus is very small per-doc.
*Expect:* dense count matrix over POS n-grams. `tagset="coarse"` (default) uses the
Universal POS tags (`token.pos_`; fewer dimensions); `tagset="fine"` uses the model's
fine-grained tags (`token.tag_`).

#### DependencyBigramExtractor
`DependencyBigramExtractor(spacy_model="en_core_web_trf", lowercase=True)`

*Use when:* you want syntax-sensitive style features — specifically, the
(head-lemma, dependency-relation, child-lemma) triples parsed by spaCy.
*Don't use when:* your parser is a bottleneck; dependency parsing is the slowest
step in the spaCy pipeline and you may be able to substitute POS n-grams.
*Expect:* dense count matrix over `head|dep|child` lemma triples.

#### FunctionWordExtractor
`FunctionWordExtractor(wordlist=None, language=None, scale="none")`

*Use when:* you want the short, topic-insensitive function-word list (the classic
anti-topic signal for stylometry) for the document's language.
*Don't use when:* your corpus mixes languages without a per-doc language tag — the
per-language word list won't apply.
*Expect:* `(n_docs, |wordlist|)` matrix of raw counts by default; `scale="zscore"`
z-scores relative frequencies (`count / document token count`), `"l1"` / `"l2"`
normalise the rows. The word list comes from the bundled list for `language` (or the
corpus language) unless you pass `wordlist` (see [Languages](languages.md)).

#### PunctuationExtractor
`PunctuationExtractor()`

*Use when:* you want pure-style features that are nearly topic-invariant —
punctuation usage is remarkably author-specific and corpus-robust.
*Don't use when:* your source text has been normalised or stripped of punctuation
(e.g., OCR output without correction).
*Expect:* `(n_docs, 32)` matrix of raw counts, one column per character in Python's
`string.punctuation`. It takes no `scale` argument; normalise downstream if documents
differ in length.

#### ReadabilityExtractor
`ReadabilityExtractor(indices=None, language=None)`

*Use when:* you want readability-as-style — Flesch, FK-grade, Gunning Fog, etc. —
as a lightweight feature set to combine with MFW.
*Don't use when:* readability itself is the question (for that, read the metric
directly; don't bundle into a Delta). For non-English, use the per-language
native-formula variant — see `concepts/languages.md`.
*Expect:* `(n_docs, k)` matrix, one column per index. With `indices=None` the language
default is used — for English `flesch`, `flesch_kincaid`, `gunning_fog`; `coleman_liau`,
`ari` and `smog` are also available via `indices=`.

#### SentenceLengthExtractor
`SentenceLengthExtractor(spacy_model="en_core_web_trf")`

*Use when:* you want the sentence-rhythm signature — mean, SD, and skew of
per-sentence token counts. Small but strong stylistic signal.
*Don't use when:* your text has aggressive sentence-boundary errors (e.g., ALL
CAPS legal text breaks most sentencizers).
*Expect:* `(n_docs, 3)` matrix with columns `mean`, `sd`, `skew`.

#### LexicalDiversityExtractor
`LexicalDiversityExtractor(indices=("ttr", "yules_k"))`

*Use when:* you want vocabulary-richness features — TTR, MATTR, MTLD, HD-D, Yule's
K/I, Herdan's C, Simpson's D. Eight indices let you compare sensitivities.
*Don't use when:* your documents are very short (<200 tokens); most indices become
unstable.
*Expect:* `(n_docs, k)` matrix, one column per requested index (default
`indices=("ttr", "yules_k")`; pass e.g. `["ttr", "mattr", "mtld", "hdd"]`). Where a
measure is undefined it is NaN with a warning: HD-D below 42 tokens, MTLD when no full
factor completes, Yule's I (`V²/(M2 − V)`) when every token is unique. `bitig run`
refuses NaN features rather than passing them to a method. Not every short text gives
NaN: MATTR falls back to plain TTR below its 100-token window, and an empty document
gets 0.0 for TTR, MATTR, MTLD, Yule's K, Herdan's C and Simpson's D.

#### SentenceEmbeddingExtractor
`SentenceEmbeddingExtractor(model=None, language=None, pool="mean", device=None)`

*Use when:* you want a modern neural-embedding feature set — pooled
sentence-transformer output per document. Strong in classification + clustering;
fast enough for moderate corpora.
*Don't use when:* your hardware lacks GPU / MPS and your corpus is large (CPU
inference is slow), or when interpretability matters (these vectors are opaque).
*Expect:* `(n_docs, embedding_dim)` dense matrix. With `model=None` the model is chosen
per language at fit time (English: `sentence-transformers/all-mpnet-base-v2`). Requires
`bitig[embeddings]`.

#### ContextualEmbeddingExtractor
`ContextualEmbeddingExtractor(model=None, language=None, layer=-1, pool="mean", device=None, max_length=512)`

*Use when:* you want HuggingFace-model hidden states aggregated per document —
language-specific embeddings (e.g., `dbmdz/bert-base-turkish-cased` for Turkish)
with configurable pooling (`pool="mean"`, `"cls"` or `"max"`).
*Don't use when:* you don't need a specific model's representation — use
`SentenceEmbeddingExtractor` for a lighter, faster default.
*Expect:* `(n_docs, hidden_dim)` dense matrix. With `model=None` the model is chosen per
language (English: `bert-base-uncased`; Turkish: `dbmdz/bert-base-turkish-cased`).
Requires `bitig[embeddings]`.

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
`CategorizedCharNgramExtractor(n=3, categories=None, scale="none", lowercase=False)`

*Use when:* you want topic-invariant character-level features for forensic
verification — n-grams classified by position in the word so you can keep only
the style-carrying categories (affixes, punctuation) and drop the topic-sensitive
whole-word category.
*Don't use when:* topic robustness isn't the goal — a plain `CharNgramExtractor`
is faster and carries more signal per dimension.
*Expect:* dense count matrix restricted to the chosen n-gram categories. The default
`categories=None` keeps all seven categories, i.e. no filtering.

Sapkota et al. 2015 found affix + punctuation n-grams worked best across topics; pass
`categories=("prefix", "suffix", "punct")` explicitly to get that subset.

#### distort_corpus
`distort_corpus(corpus, mode="dv_ma")`

*Use when:* you want Stamatatos (2017) topic masking — replaces content words with
placeholders while keeping function words and punctuation. Pair with any
extractor for a topic-invariant pipeline.
*Don't use when:* your analysis needs content-word signal (e.g., Zeta looking for
distinctive vocabulary).
*Expect:* a new Corpus object you feed to any existing extractor. Both modes
mask every word not on the function-word list: `"dv_ma"` (default) keeps each masked
word's length, `"dv_sa"` collapses it to one `*`.

See [Topic-invariant features](../forensic/topic-invariance.md).

## Scaling

`MFWExtractor`, `CharNgramExtractor`, `WordNgramExtractor`, `FunctionWordExtractor` and
`CategorizedCharNgramExtractor` accept `scale ∈ {"none", "zscore", "l1", "l2"}`:

- `none` — raw counts. Use for Bayesian Wallace–Mosteller.
- `l1` — rows normalised to sum to 1 over the retained features. Use for Zeta-like contrast methods.
- `l2` — unit-norm rows. Use for cosine-based distances.
- `zscore` — per-column z-score on training means / SDs (Stylo convention). For MFW the
  z-scored values are relative frequencies, `count / document token count` (the same for
  `FunctionWordExtractor`); for character and word n-grams the denominator is the
  document's total number of n-grams. `CategorizedCharNgramExtractor` z-scores raw
  counts. **Required for Burrows Delta.**

The z-score mean / SD are learned at `fit` time and applied at `transform` — so scores on
unseen documents use the training distribution. `cross_validate_bitig(..., extractor=...,
corpus=...)` refits the extractor inside each training fold, so held-out documents do not
shape the vocabulary or these statistics (see [Methods](methods.md)).

## Next

- [Methods](methods.md) — take the FeatureMatrix and produce a Result.
