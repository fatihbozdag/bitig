# Troubleshooting

Common install and runtime issues, and how to resolve them.

## Python version

bitig requires **Python 3.11+**. On an older interpreter, `pip install bitig` will refuse to
install (the wheel declares `requires-python >=3.11`). Use [uv](https://docs.astral.sh/uv/) or
`pyenv` to get a 3.11+ interpreter:

```bash
uv venv --python 3.11
```

## spaCy model not found

```
OSError: [E050] Can't find model 'en_core_web_trf'.
```

bitig parses text with spaCy but does **not** bundle a model, so download one after install:

```bash
python -m spacy download en_core_web_trf      # transformer pipeline (best accuracy)
python -m spacy download en_core_web_sm        # small pipeline (much faster, lower accuracy)
```

Then point your study at it with `preprocess.spacy.model`, or pass `--spacy-model` to
`bitig ingest`. For non-English languages, download the matching pipeline
(`de_dep_news_trf`, `es_dep_news_trf`, `fr_dep_news_trf`); Turkish is handled differently
(see below).

## `ImportError: requires the optional ... extra`

Several capabilities live behind optional extras to keep the base install light. If you hit an
import error, install the relevant extra:

| Extra | Enables | Install |
|---|---|---|
| `cluster` | UMAP reduction, HDBSCAN clustering | `uv pip install "bitig[cluster]"` |
| `bayesian` | PyMC hierarchical group comparison (the NumPy Wallace–Mosteller attributor needs **no** extra) | `uv pip install "bitig[bayesian]"` |
| `embeddings` | sentence-transformers + contextual BERT extractors | `uv pip install "bitig[embeddings]"` |
| `viz` | Plotly / kaleido / ete3 interactive + tree figures | `uv pip install "bitig[viz]"` |
| `interactive` | Plotly only, for interactive figures | `uv pip install "bitig[interactive]"` |
| `reports` | WeasyPrint PDF export | `uv pip install "bitig[reports]"` |
| `gui` | NiceGUI + pywebview desktop shell | `uv pip install "bitig[gui]"` |
| `turkish` | Turkish parsing via Stanza (`multilang` is an alias) | `uv pip install "bitig[turkish]"` |
| `docs` | MkDocs Material, to build this site | `uv pip install "bitig[docs]"` |

## Turkish setup and the version pins

Turkish parsing goes through Stanford Stanza (BOUN treebank) wrapped by `spacy-stanza`. The
`bitig[turkish]` extra deliberately **pins** its dependencies, because the upstream stack only
works inside a narrow window:

- `spacy-stanza` 1.0.4 (its last release) caps `stanza` at `<1.7`, so Stanza must stay in the
  `1.6.x` range.
- Stanza 1.6.x calls `torch.load` without `weights_only=False`, which breaks under `torch>=2.6`
  (where `weights_only` defaults to `True`), so `torch` is capped at `<2.6`.
- With torch held below 2.6, `transformers` is capped at `<5.19`: 5.19 needs torch 2.6 to
  build a model, and 5.20 fails at import. This matters when `turkish` is combined with
  `embeddings`.

After installing the extra, download the Stanza Turkish model once:

```bash
uv pip install "bitig[turkish]"
python -c "import stanza; stanza.download('tr')"
```

Notes:

- The Turkish model set takes about 700 MB on disk after the first download.
- You do **not** need to set `preprocess.spacy.backend` for Turkish; bitig resolves the
  `spacy_stanza` backend automatically from the corpus language.

## PDF export fails (WeasyPrint)

`bitig[reports]` installs WeasyPrint, which needs system libraries (Pango, HarfBuzz). On
Debian/Ubuntu:

```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
```

On macOS, install them with Homebrew (`brew install pango`). HTML and Markdown reports have no
such system dependency; only PDF export does.

## `bitig plot` prints a stub message

`bitig plot` is not yet wired to a renderer. To produce figures today, either:

- run the study with `bitig run`, which writes each method's default figure (the `viz` block in
  `study.yaml` is accepted but not read yet), or
- call the `bitig.viz.plot_*` functions directly from Python.

## Still stuck?

Open an issue at <https://github.com/fatihbozdag/bitig/issues> with the full traceback, your
Python version (`bitig info`), and the command you ran.
