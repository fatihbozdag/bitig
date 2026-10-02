# CLI reference

Every bitig CLI command, installed as `bitig`. Run `bitig --help` or `bitig <command> --help`
for the authoritative option list; `bitig --version` prints the version.

Most analysis commands take a corpus directory of `.txt` files as their first argument and a
metadata TSV through `--metadata/-m` (a `filename` column plus any fields, e.g. `author`).
Options differ per command — they are listed below.

## Project scaffolding

### `bitig init <name>`

Scaffold a new project directory.

```bash
bitig init my-study [--target DIR] [--language en|tr|de|es|fr] [--force]
```

Creates:

```
my-study/
├── corpus/          # drop .txt files here (and, optionally, metadata.tsv)
├── results/         # bitig run writes one folder per run here
├── reports/         # for reports you build with bitig report
├── .bitig/cache/    # spaCy DocBin cache
├── .gitignore
├── README.md        # short pointer
└── study.yaml       # declarative study config (Burrows Delta on 1000 MFW)
```

- `--target, -t` — directory to create (default `./<name>`)
- `--language, -l` — project language, written to `study.yaml` (default `en`)
- `--force` — fill in missing files even if the directory is not empty

No `metadata.tsv` is created; the `metadata:` line in `study.yaml` is commented out until you
provide one.

## Ingestion

### `bitig ingest <path>`

Parse a corpus directory with spaCy and cache the parses as DocBins.

```bash
bitig ingest corpus/ --metadata corpus/metadata.tsv [--no-strict] [--spacy-model en_core_web_sm]
```

- `--metadata, -m` — TSV mapping filename to metadata fields
- `--strict` (default) / `--no-strict` — require / do not require a metadata row for every file
- `--cache-dir` — cache location (default `.bitig/cache`)
- `--spacy-model` — spaCy model to load (default: `en_core_web_trf`)
- `--exclude` — spaCy pipeline component to skip (repeatable)
- `--language, -l` — corpus language code (default `en`)

`bitig run` does not need an ingest step: the feature types it supports work on raw text.

### `bitig info`

Print the environment: bitig, Python, platform and spaCy versions. When a `study.yaml` is in
the current directory, its configured language is shown too. It does not inspect a corpus.

## Features

### `bitig features <path>`

Build a feature matrix and save it to parquet.

```bash
bitig features corpus/ --metadata corpus/metadata.tsv --type mfw --n 500 [--output features.parquet]
```

- `--type` — `mfw` (default), `word_ngram`, `char_ngram`, `function_word`, `punctuation`
- `--n` — top-N for `mfw`, or the n-gram order (default 1000)
- `--min-df` (mfw only), `--scale` (`none`, `zscore`, `l1`, `l2`), `--lowercase` (mfw only)
- `--output, -o` — parquet path (default `features.parquet`)

Other extractors (`lexical_diversity`, `readability`, POS and dependency features, embeddings)
are available from `study.yaml` or the Python API, not from this command.

## Methods

Each method command builds its own MFW matrix from the corpus. Options are per command;
only `cluster`, `consensus` and `classify` take `--seed` (default 42).

| Command | Does | Main options |
|---|---|---|
| `bitig delta <path>` | Fit Delta, print per-document attributions | `-m` (required), `--method {burrows,argamon,eder,eder_simple,cosine,quadratic}`, `--mfw 1000`, `--mfw-min 2`, `--group-by author`, `--test-filter role=test` |
| `bitig zeta <path>` | Craig's Zeta contrast between two groups | `-m` (required), `--group-by author`, `--variant {classic,eder}`, `--top-k 20`, `--group-a X --group-b Y` (default: the two largest groups) |
| `bitig reduce <path>` | Dimensionality reduction → parquet | `--method {pca,mds,tsne,umap}`, `--n-components 2`, `--mfw 500`, `-o reduce.parquet` |
| `bitig cluster <path>` | Clustering → parquet + summary | `--method {hierarchical,kmeans,hdbscan}`, `--n-clusters 2`, `--linkage ward`, `--mfw 500`, `--seed`, `-o cluster.parquet` |
| `bitig consensus <path>` | Bootstrap consensus tree → Newick | `--bands 100,200,300,400,500`, `--replicates 100`, `--subsample 0.8`, `--support-threshold 0.5`, `--seed`, `-o consensus.nwk` |
| `bitig classify <path>` | sklearn classifier + stylometry-aware CV, per-author metrics | `-m` (required), `--estimator {logreg,svm_linear,svm_rbf,rf,hgbm}`, `--cv-kind {stratified,loao,leave_one_text_out}`, `--groups-by COL` (for `loao`), `--folds 5`, `--group-by author`, `--mfw 500`, `--seed` |
| `bitig embed <path>` | Sentence-transformer embeddings → parquet (extra: `bitig[embeddings]`) | `--model`, `--pool {mean,cls,max}`, `-o embeddings.parquet` |
| `bitig bayesian <path>` | Wallace–Mosteller attribution (extra: `bitig[bayesian]`) | `-m` (required), `--group-by author`, `--test-filter role=test`, `--mfw 500`, `--prior-alpha 1.0` |

`umap` and `hdbscan` need the `bitig[cluster]` extra.

## Orchestration

### `bitig run <study.yaml>`

Execute a full declarative study end-to-end (see the [study.yaml schema](config.md)).

```bash
bitig run study.yaml --name demo [--output results/] [--overwrite]
```

Writes every method's `Result` to its own subdirectory plus a `resolved_config.json`.
A run directory that already holds a previous run is refused; `--overwrite` replaces that
run's outputs (and nothing else). Exits with code 1 if any method failed — each failed
method's folder has an `error.txt` with the traceback.

- `--output, -o` — base directory (default: `output.dir` from `study.yaml`)
- `--name` — run-directory name (default: a timestamp, or none when `output.timestamp` is false)

### `bitig report <run-dir>`

Render a Jinja2 HTML or Markdown report from a run directory.

```bash
bitig report results/demo --output results/demo/report.html [--format html|md] [--title "My study"]
```

### `bitig plot <result-dir>`

Takes a single method's result directory (the folder holding `result.json`). Not yet
implemented: it prints a notice and renders nothing. `bitig run` already writes a default
figure into each method folder; for custom figures use the `bitig.viz` functions from Python.

### `bitig shell [<corpus>]`

Minimal interactive menu: loads a corpus (optionally with `--metadata`), can list its document
count and metadata fields, and points you to the CLI command for each method.

### `bitig gui`

Launch the desktop GUI (extra: `bitig[gui]`).

```bash
bitig gui [--no-native] [--host 127.0.0.1] [--port 8080] [--width 1200] [--height 800]
```

- `--no-native` — open in the default browser instead of a native window
- `--dev` — hot reload, for GUI development

## Cache

### `bitig cache <cmd>`

Manage the spaCy DocBin cache produced by `bitig ingest`. Each subcommand takes
`--cache-dir` (default `.bitig/cache`).

- `bitig cache size` — total bytes and number of entries
- `bitig cache list` — list cache keys
- `bitig cache clear` — delete every entry

## Forensic Lab cases

### `bitig case <cmd>`

Manage Forensic Lab Cases: evidence with chain of custody, a recipe, runs and a signed
report. Every subcommand takes `--cases-dir` (default `~/.bitig/cases/`). See the
[case workflow](../forensic/case-workflow.md) for the full procedure.

| Command | Does |
|---|---|
| `bitig case new <id> --title T --examiner E [--recipe R]` | Create a case; recipes: `imposters_lr` (default), `delta_attribution`, `bayesian`, `zeta_contrast`, `exploration`, or `custom` |
| `bitig case add-evidence <id> <files…> --role questioned` / `--role known --author A` | Copy files into the case, hash and register them (only registered evidence is analysed and sealed) |
| `bitig case list` | Table of all cases |
| `bitig case open <id>` | Path and a short summary |
| `bitig case status <id> [--no-verify]` | Full status with a chain-of-custody check; exit code 2 on a custody mismatch |
| `bitig case reacknowledge <id> <evidence-path> --reason R [--by NAME]` | Accept a changed evidence file's new hash (logged); the case must be re-run before signing |
| `bitig case run <id>` | Run the case's analysis on its registered evidence, with the same guards as the GUI Run step; prints ✓/✗ per method and the run directory. Exit 0 = all methods succeeded, 1 = partial or failed, 2 = blocked |
| `bitig case fork <id> <new-id> [--title] [--examiner] [--acknowledge-mismatch REASON]` | Clone into an unsigned descendant |
| `bitig case sign <id> [--signed-by NAME] [--signature-plugin hmac\|null]` | Sign and lock the case; needs a successful run |
| `bitig case verify <id> [--key KEY]` | Recompute the seal; exit 0 = verified (valid HMAC), 1 = not signed, 2 = broken, 3 = hashes intact but Null seal (UNSIGNED), 4 = hashes intact but HMAC not checkable without a key (CANNOT VERIFY). The HMAC key falls back to `$BITIG_SIGNATURE_KEY` |

Case parameters have no CLI command; set them in the GUI's Method step or with
`Case.set_param` in Python.

## Getting help

Every command supports `--help`:

```bash
bitig --help
bitig run --help
bitig case --help
```
