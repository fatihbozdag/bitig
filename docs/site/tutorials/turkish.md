# Turkish stylometry walkthrough

A runnable Turkish example: set up a Turkish project, then explore a corpus of public-domain
Ömer Seyfettin short stories from Turkish Wikisource with MFW, PCA and Ward clustering.

## Setup

```bash
uv pip install 'bitig[turkish]'
python -c "import stanza; stanza.download('tr')"
bitig init seyfettin --language tr
cd seyfettin
```

This scaffolds a project directory with `study.yaml` pre-configured for Turkish
(`preprocess.language: tr`). Confirm with:

```bash
bitig info
```

The `language` row shows `tr`.

Stanza (through `spacy-stanza`) is only needed for `bitig ingest` and for spaCy-based
features in the Python API. The features that `bitig run` builds (MFW, n-grams, function
words, punctuation, lexical diversity, readability) work from the raw text and never load
Stanza.

## Corpus

Place your Turkish texts in `corpus/` as UTF-8 `.txt` files. A good public-domain
source is [Ömer Seyfettin on Turkish
Wikisource](https://tr.wikisource.org/wiki/Yazar:%C3%96mer_Seyfettin) — dozens of early-20th-
century short stories are already transcribed there.

Add a `corpus/metadata.tsv` and uncomment the `metadata:` line in `study.yaml`:

```tsv
filename	author	year
bomba.txt	Omer_Seyfettin	1910
kesik_biyik.txt	Omer_Seyfettin	1911
forsa.txt	Omer_Seyfettin	1913
pembe_incili_kaftan.txt	Omer_Seyfettin	1917
```

The scaffolded study runs Burrows Delta grouped by `author`, which needs documents from
**at least two** `author` values. With a single author the Delta method fails and
`bitig run` exits with status 1. Either add texts by a second author, or replace the Delta
method with `reduce` / `cluster` methods as in the worked example below.

## Running the study

```bash
bitig ingest corpus/ --language tr --metadata corpus/metadata.tsv   # optional
bitig run study.yaml --name first-run
```

`bitig ingest` runs Stanza through `spacy-stanza` and caches the parses as DocBins.
`bitig run` does not read that cache, so the ingest step is optional for this study.

## What you get

The scaffolded Turkish study builds **MFW** (top 1 000 words, z-scored) and runs **Burrows
Delta**. `bitig run` writes one folder per method plus the run configuration:

```
results/first-run/
├── resolved_config.json      # the fully resolved study configuration
└── burrows/
    ├── result.json           # predictions, resubstitution accuracy, provenance
    └── confusion_matrix.png
```

- `result.json` holds the method's values and a provenance block (bitig version, corpus
  hash, feature hash, seed, resolved config). There is no separate `provenance.json`.
- The Delta values are in-sample: `resubstitution_accuracy` is a separability check, and
  `attributions` lists documents that have no `author` value.
- Other methods write their own default figure: `scatter.png` and `pca_biplot.png` for
  `reduce`, `dendrogram.png` for `cluster`, `zeta.png` for `zeta`. Only methods that return
  tables (Zeta, rolling Delta, verification) also write `table_N.parquet` files.
- A failed method leaves an `error.txt` in its folder instead of `result.json`, and the run
  exits with status 1.

## Worked example: 28 short stories by Ömer Seyfettin

The `examples/turkish_seyfettin/` directory in the repository ships a complete,
end-to-end run against 28 short stories by Ömer Seyfettin (1884-1920; in the
Turkish public domain since 1991), scraped from
[tr.wikisource.org](https://tr.wikisource.org) by `fetch_corpus.py`. The corpus is
committed alongside the study, so you do not need to fetch it again:

```bash
bitig run examples/turkish_seyfettin/study.yaml --name seyfettin
# optional: re-download the stories (~30s, polite to Wikisource)
python examples/turkish_seyfettin/fetch_corpus.py --n 30
```

**Corpus.** 28 stories survive the 200-token cutoff; story lengths range from
326 to 4 455 tokens (median ≈ 1 560). Wikisource transcriptions are CC BY-SA 4.0;
attribution and source URLs live in `examples/turkish_seyfettin/manifest.json`.

**Study.** Five hundred most frequent words (z-scored, `min_df = 2`) → PCA + Ward
hierarchical clustering. The study also builds a Turkish function-word feature
(`tr_fwords`) that no method uses by default; point a method's `features:` at it to try it.
A single-author corpus admits no between-author attribution or verification (Delta,
Imposters, classify), so this is *exploratory within-author stylometry*, not authorship
attribution.

The run writes:

```
examples/turkish_seyfettin/results/seyfettin/
├── resolved_config.json
├── pca/
│   ├── result.json        # coordinates, loadings, explained variance
│   ├── scatter.png
│   └── pca_biplot.png
└── ward/
    ├── result.json        # cluster labels and linkage matrix
    └── dendrogram.png
```

### PCA on the MFW-500 lexical space

PC1 explains **8.0 %** of the variance, PC2 explains **6.9 %**. No single component
dominates: the lexical variance inside one author is spread across many small axes.

**Largest loadings — PC1**: `o`, `akşam`, `gül`, `bana`, `karşı`, `bakıyordu`, `nihayet`, `ki`.

**Largest loadings — PC2**: `durdu`, `idi`, `başını`, `hafif`, `değildi`, `üzerine`, `şeyler`, `tarafa`.

`pca/pca_biplot.png` overlays the top-15 loading vectors onto the same 2-D projection.

### Ward hierarchical clustering (k = 4)

Cutting the dendrogram (`ward/dendrogram.png`) at four flat clusters yields:

| Cluster | n  | Members | Story length (tokens) |
|--------:|---:|---|---|
| 0       | 17 | `and`, `antiseptik`, `elma`, `kasag`, … | median 1 152 (326–3 115) |
| 1       |  9 | `aleko`, `bomba`, `ferman`, `forsa`, … | median 2 418 (1 096–4 455) |
| 2       |  1 | `keramet` | 508 |
| 3       |  1 | `hediye` | 454 |

Story length tracks the clusters: the two singletons are the second- and third-shortest
stories, and cluster 1 collects the longer ones. z-scored MFW counts get noisy in short
texts, so short stories drift away from the main cloud regardless of topic. This is not a
bug in the method — it is the natural consequence of MFW estimation variance at small *N*:

> If you are running stylometry on Turkish short prose, raise the per-document
> token floor to at least 1 000 — or move to character n-grams, which are far
> more length-tolerant — before drawing topic / period conclusions from the
> sub-cluster structure.

### Caveats and what is *not* shown here

A genuine **authorship-attribution** demonstration needs at least one
additional PD-old Turkish prose author with comparable Wikisource coverage,
which Wikisource:tr does not currently have for the early-republican period
(Refik Halit Karay's transcriptions are present but the underlying texts
will not enter the Turkish public domain until 2036). For attribution work we
recommend pairing Seyfettin with a different-genre control corpus
(e.g. parliamentary speeches, Türkçe Wikipedia featured articles by topic,
or your own institutional corpus) rather than a contemporaneous literary author.

## Customising

Edit `study.yaml` to swap features or methods. `bitig run` builds the feature types `mfw`,
`word_ngram`, `char_ngram`, `function_word`, `punctuation`, `lexical_diversity` and
`readability`, and rejects any other type when it loads the study. For example, character
n-grams are more robust on short texts:

```yaml
features:
  - id: char3
    type: char_ngram
    n: 3
    scale: zscore
```

Contextual embeddings are not a `bitig run` feature type. Use them from Python with
`bitig.features.ContextualEmbeddingExtractor`; with `language="tr"` the model resolves to
`dbmdz/bert-base-turkish-cased`, and `model=` accepts any HuggingFace checkpoint (e.g.
`stefan-it/bert5urk`). This requires the `bitig[embeddings]` extra.

## Notes on Turkish specifics

- **Morphology.** Turkish is agglutinative; a token like `evlerinizden` packs
  `ev+ler+iniz+den` into one form. Stanza's Turkish BOUN model lemmatises and tags these
  correctly, which matters for POS-ngram and dependency-based features.
- **Syllable counting.** Both Ateşman and Bezirci-Yılmaz count syllables using a
  vowel-counter specialised for Turkish orthography (including `ı`, `ğ`, `ş`, `ç`, `ü`,
  `ö`).
- **Function words.** The bundled list leans on Turkish's closed-class postpositions,
  conjunctions, and discourse particles (e.g. `ile`, `ancak`, `fakat`, `çünkü`, `ki`,
  `ise`).

## Troubleshooting

- **`ModuleNotFoundError: No module named 'spacy_stanza'`** — run
  `uv pip install 'bitig[turkish]'`.
- **`FileNotFoundError: ... stanza_resources/tr/default.zip`** — run
  `python -c "import stanza; stanza.download('tr')"`. The model is about 600 MB.
- **Very slow first ingest on MPS.** Stanza's Turkish model does not yet support Apple
  Silicon MPS. Expect CPU parse rates on first run; subsequent runs are cache hits.
