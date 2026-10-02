# Topic-invariant features

*Use when:* your questioned and known documents might be on different topics — you
need features that capture style without leaking topic.
*Don't use when:* topic is part of the question (for example, a plagiarism check
where the two documents *should* share content). Use regular features then.
*Expect:* feature extractors that discard most content-word signal while preserving
function-word, morphology, and punctuation patterns.

Two techniques live under `bitig.forensic`: Sapkota char-n-gram *categorisation* and
Stamatatos *distortion*. Both compose with any downstream verifier.

Cross-topic is the most common failure mode of classical stylometry on real forensic
data. A suspect's threat letter and personal email are typically on different topics but
presumably the same author; unfiltered character-n-gram and word-n-gram features
collapse into topic detection in that setting.

bitig ships two complementary tools.

## Sapkota character n-gram categories

*Use when:* you want char-n-gram features for verification but need to strip
topic-sensitive whole-word n-grams — keeping only affixes, punctuation-adjacent, and
space-adjacent categories.
*Don't use when:* your corpus is so small that further filtering collapses the
feature space below ~500 dimensions.
*Expect:* a dense count matrix (unscaled by default, `scale="none"`) with only the
chosen categories. The default `categories=None` keeps **all seven** categories, so it
filters nothing; pass `("prefix", "suffix", "punct")` explicitly for the cross-topic
subset.

`CategorizedCharNgramExtractor` classifies each character n-gram **occurrence** (not just
the string) by its position in the source text. Feature columns are named
`<ngram>|<category>`, so `the|whole_word` and `the|prefix` are separate channels —
explicit and auditable.

Seven categories:

| Category | Description |
|---|---|
| `prefix` | word-start + char-internal (e.g., "the" in "there") |
| `suffix` | char-internal + word-end (e.g., "ing" in "running") |
| `whole_word` | exactly one word, boundaries at both ends |
| `mid_word` | entirely internal to a single word |
| `multi_word` | spans whitespace between two words |
| `punct` | contains any punctuation character |
| `space` | contains whitespace but not enough for multi_word |

Sapkota et al. (2015) found that **affix (prefix + suffix) + punct** n-grams work best
in their cross-topic attribution experiments. This subset is not the default: you must
request it, as below.

```python
from bitig.forensic import CategorizedCharNgramExtractor

extractor = CategorizedCharNgramExtractor(
    n=3,
    categories=("prefix", "suffix", "punct"),  # topic-invariant subset
    scale="zscore",
    lowercase=True,
)
fm = extractor.fit_transform(corpus)
```

## Stamatatos distortion

*Use when:* you want aggressive topic removal via content-word masking — replaces
content words with placeholders while preserving function words, morphology, and
punctuation.
*Don't use when:* you need any content-word signal downstream (e.g., Zeta on
distinctive vocabulary).
*Expect:* a new `Corpus` object you pass to any existing extractor. Both modes
mask every word that is not on the function-word list; `"dv_ma"` (default) keeps each
masked word's length, `"dv_sa"` collapses it to one `*`. Neither mode looks at POS
tags.

`distort_corpus` pre-processes documents to mask **content** while preserving **style**:
function words, punctuation, digits, and whitespace remain verbatim; content-word
characters are replaced.

### Two modes

Both come from Stamatatos (2017). bitig deviates from the paper in two ways: digits are
left as they are (the paper masks them with `#`), and the words kept are a bundled
function-word list for the corpus language (`en`, `tr`, `de`, `es`, `fr`) rather than
the k most frequent words of a reference corpus.

**DV-MA** (*Distortion View — Multiple Asterisks*): each content-word character → `*`.
Length-preserving — morphological habits (typical word lengths) remain visible.

**DV-SA** (*Distortion View — Single Asterisk*): each content word → single `*`.
Aggressive; only function-word and punctuation pattern survives.

```python
from bitig.forensic import distort_corpus
from bitig import MFWExtractor

distorted = distort_corpus(corpus, mode="dv_ma")

# Downstream extractors see the distorted text — topic signal is masked out.
fm = MFWExtractor(n=200, scale="zscore").fit_transform(distorted)
```

### Contractions

Both `_TOKEN_RE` and the bundled function-word list preserve common English contractions
(`don't`, `it's`, `we'll`, `they've`, …) verbatim. `o'clock` and other apostrophised
content words are masked as a single contiguous string (e.g., `*******`) rather than
split into fragments.

### Custom function-word list

```python
distorted = distort_corpus(
    corpus,
    mode="dv_ma",
    function_words={"the", "a", "of", "to", "and"},   # minimal stoplist
)
```

Pass `frozenset()` to treat every word as content (DV-MA then masks every word; digits,
punctuation and whitespace still remain).

## Combining the two

Sapkota categories + Stamatatos distortion compose cleanly:

```python
distorted = distort_corpus(corpus, mode="dv_ma")
extractor = CategorizedCharNgramExtractor(
    n=3, categories=("prefix", "suffix", "punct"), lowercase=True
)
fm = extractor.fit_transform(distorted)
```

Note what this keeps. The `*` mask is a punctuation character for `classify_ngram`, so
every n-gram that touches a masked word falls in the `punct` category; `prefix` and
`suffix` n-grams then come only from the function words left in clear. On
`"The cat was running."` distorted with DV-MA and the code above, all seven kept
features are `punct` n-grams (`***|punct`, `* w|punct`, `s *|punct`, …).

## Reference

::: bitig.forensic.char_ngrams.CategorizedCharNgramExtractor
    options:
      show_root_full_path: false

::: bitig.forensic.char_ngrams.classify_ngram

::: bitig.forensic.distortion.distort_corpus

::: bitig.forensic.distortion.distort_text
