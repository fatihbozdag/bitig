# Concepts

## What bitig is for

bitig answers three questions about who wrote a text:

- **Attribution** — which of a set of candidate authors most likely wrote this document?
- **Verification** — was this document written by *this specific* person?
- **Group comparison** — how does one author's style differ from another's, or from a
  defined group?

On top of those core questions it ships a forensic layer: calibrated likelihood ratios,
chain-of-custody metadata, and evaluation metrics for likelihood-ratio systems.

Not sure which question you're asking? **[Start with the Choosing a method
guide](choosing.md).**

## The four layers

bitig is organised around four layers, each with one primary return type. Understanding
these four types lets you compose anything bitig can do:

| Layer | Type | Purpose |
|---|---|---|
| Corpus | `Corpus` (wraps `Document`s) | texts + metadata |
| Features | `FeatureMatrix` | numeric document-feature table |
| Methods | `Result` | outcome of an analysis |
| Reporting | report file | publication- or forensic-ready artifact |

## The pipeline

```mermaid
flowchart LR
  C["Corpus<br><code>.txt + metadata.tsv</code>"] --> F["FeatureMatrix<br>(n_docs × n_features)"]
  F --> M["Result<br>(method-specific)"]
  M --> R["Report<br>(HTML / Markdown)"]

  style C fill:#FBF3DE,stroke:#C9A34A
  style F fill:#FBF3DE,stroke:#C9A34A
  style M fill:#FBF3DE,stroke:#C9A34A
  style R fill:#FBF3DE,stroke:#C9A34A
```

Each arrow is a boundary where data serialises cleanly to disk:

- **Corpus → FeatureMatrix**: parsed documents are cached as spaCy `DocBin` blobs, keyed
  by document hash and pipeline configuration.
- **FeatureMatrix → Result**: every result directory contains `result.json` + optional
  `table_*.parquet` + figures.
- **Result → Report**: Jinja2 templates render the result directory to a single HTML or
  Markdown file.

## Provenance, everywhere

Every `Result` carries a `Provenance` record with:

- bitig version, Python version, spaCy version and model (`bitig run` records
  `"none (no spaCy parsing in this run)"`, since it parses nothing)
- versions of the result-shaping libraries, plus a checksum of NLTK's cmudict when present
- corpus hash (binds each text to its id and metadata) and the hashing scheme that
  produced it
- feature hash (extractor, config and corpus hash)
- seed used for the run
- timestamp
- resolved `study.yaml` config

Plus six optional forensic fields (questioned / known descriptions, hypothesis pair,
acquisition + custody notes, source-file SHA-256s) for chain-of-custody.

Two runs of the same `study.yaml` against the same corpus with matching seeds produce
identical result values (up to floating-point rounding). See [Results & provenance](results.md).

## Read next

- [Corpus](corpus.md) — ingestion, metadata, filtering
- [Features](features.md) — what's available, when to use each
- [Methods](methods.md) — Delta, Zeta, classify, Bayesian
- [Results & provenance](results.md) — the shared return type + reproducibility
