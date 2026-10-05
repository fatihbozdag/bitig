# Languages

bitig ships with first-class support for five languages: **English**, **Turkish**, **German**,
**Spanish**, and **French**. Each language has bundled function-word lists, native readability
formulas, and tested end-to-end pipelines.

## Supported languages

| Code | Name    | Backend         | Default model            | Readability                             |
|------|---------|-----------------|--------------------------|------------------------------------------|
| en   | English | native spaCy    | `en_core_web_trf`        | Flesch, Flesch-Kincaid, Gunning Fog, Coleman-Liau, ARI, SMOG |
| tr   | Turkish | `spacy-stanza`  | Stanza `tr` (BOUN)       | Ateşman, Bezirci-Yılmaz                  |
| de   | German  | native spaCy    | `de_dep_news_trf`        | Flesch-Amstad, Wiener Sachtextformel     |
| es   | Spanish | native spaCy    | `es_dep_news_trf`        | Fernández-Huerta, Szigriszt-Pazos        |
| fr   | French  | native spaCy    | `fr_dep_news_trf`        | Kandel-Moles, LIX                        |

## How the registry works

Every language-dependent site in bitig (preprocess pipeline, function-word loading, readability
index selection, embedding model defaults) reads from the central `LANGUAGES` registry. Unknown
codes fail fast with a helpful error listing the supported set.

```python
from bitig import LANGUAGES, get_language

spec = get_language("tr")
print(spec.backend)                       # 'spacy_stanza'
print(spec.default_model)                 # 'tr'
print(spec.readability_indices)           # ('atesman', 'bezirci_yilmaz')
print(spec.contextual_embedding_default)  # 'dbmdz/bert-base-turkish-cased'
```

`LanguageSpec` is a frozen dataclass, so specs are safe to share across threads and processes.

## Declaring language in a study

A study declares its language once in `study.yaml`. The value is validated at config-load time
against the registry; typos fail before any parsing happens.

```yaml
# study.yaml
preprocess:
  language: tr
  spacy:
    # model and backend are auto-resolved from `language`.
    # Override only if you know what you are doing:
    # model: my-custom-model
    # backend: spacy
```

From the CLI, pass `--language` to `bitig init` or `bitig ingest`:

```bash
bitig init mystudy --language tr
bitig ingest corpus/ --language tr --metadata corpus/metadata.tsv
```

`bitig info` prints the configured language when a `study.yaml` sits in the current
directory, so you can sanity-check the active pipeline at a glance.

## Turkish prerequisites

Turkish is the one language that does not currently ship as a native spaCy pipeline. bitig
routes it through [Stanza](https://stanfordnlp.github.io/stanza/) via
[`spacy-stanza`](https://github.com/explosion/spacy-stanza), which still returns native spaCy
`Doc` objects — everything downstream behaves identically.

```bash
uv pip install 'bitig[turkish]'
python -c "import stanza; stanza.download('tr')"
```

The Stanza Turkish model (about 600 MB) is downloaded on first use. After that,
`bitig ingest --language tr` works identically to the English path.

## Function words

Per-language function-word lists live under
`src/bitig/resources/languages/<code>/function_words.txt`. The non-English lists were derived
from Universal Dependencies closed-class tokens (ADP / CCONJ / DET / PRON / SCONJ / PART /
AUX), filtered to the most frequent forms. Regenerate them with:

```bash
python scripts/regenerate_function_words.py
```

## Readability formulas

Each non-English language ships at least two native readability indices, implemented in
`bitig.languages.readability_<code>`:

- **Turkish (tr):** Ateşman (1997), Bezirci-Yılmaz (2010)
- **German (de):** Flesch-Amstad (1978), Wiener Sachtextformel (Bamberger & Vanecek, 1984)
- **Spanish (es):** Fernández-Huerta (1959), Szigriszt-Pazos (1993)
- **French (fr):** Kandel-Moles (1958), LIX (Björnsson, 1968)

German and French syllables are counted as vowel nuclei (`bitig.languages._syllables`), not
as hyphenation points, which undercount words such as *Abend* or *école*. English indices
come from `textstat` and need NLTK's cmudict, which bitig never downloads on its own
(`python -m nltk.downloader cmudict`).

When a study declares `type: readability`, the extractor uses the language's default indices
(`LanguageSpec.readability_indices`) unless its `indices` argument names others. For English
the defaults are Flesch, Flesch-Kincaid and Gunning Fog.

## Adding a sixth language

1. Add a `LanguageSpec` entry to `bitig.languages.registry.REGISTRY`.
2. Create `src/bitig/resources/languages/<code>/function_words.txt` (run
   `scripts/regenerate_function_words.py` after extending the UD corpus list).
3. If native readability formulas exist for the language, write them in
   `bitig.languages.readability_<code>` and register them in
   `bitig.features.readability._INDEX_REGISTRY`.
4. Add unit tests under `tests/languages/` and at least one integration test.
5. Add a tutorial page under `docs/site/tutorials/`.

See the multi-language support spec under `docs/superpowers/specs/` for the full design
rationale.
