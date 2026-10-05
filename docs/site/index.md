---
hide:
  - navigation
---

# bitig

<p align="center">
  <img src="assets/bitig-banner.svg" alt="bitig — computational stylometry" style="max-width: 100%;">
</p>

`bitig` is a Python package and command-line tool for **authorship attribution**,
**author-group style comparison** and **forensic authorship analysis**. It covers the core
methods of R's `Stylo` (Delta, Zeta, PCA/MDS, clustering, bootstrap consensus trees,
classification) and adds a spaCy pipeline, transformer embeddings, a Bayesian layer (PyMC),
authorship verification with likelihood-ratio calibration, and a case workflow with
chain-of-custody hashing and sealed reports.

The name is the Old Turkic word for *writing* or *inscription*, the kind cut into the
8th-century Orkhon stelae.

## Architecture

<p align="center">
  <img src="assets/bitig-architecture.svg" alt="corpus → features → methods → forensic → output" style="max-width: 100%;">
</p>

Feature extractors, the Delta classifiers and the Bayesian attributor are scikit-learn
estimators. Every `Result` carries its provenance (corpus hash, feature hash, seed, library
versions, timestamp, resolved config), so a study written as a `study.yaml` re-runs to the
same values given the same seed and library versions
(see [Results & provenance](concepts/results.md)).

## Quick navigation

<div class="grid cards" markdown>

-   :fontawesome-solid-rocket:{ .lg .middle } **Getting started**

    ---

    Install bitig, build your first corpus, and run a Burrows Delta study from the CLI.

    [:octicons-arrow-right-24: Install & quickstart](getting-started.md)

-   :material-book-open-page-variant:{ .lg .middle } **Concepts**

    ---

    Corpus → Features → Methods → Results. The four layers of the pipeline, explained.

    [:octicons-arrow-right-24: Concepts](concepts/index.md)

-   :material-shield-search:{ .lg .middle } **Forensic toolkit**

    ---

    General Impostors and Unmasking verification, LR calibration, PAN evaluation, and the Forensic Lab case workflow.

    [:octicons-arrow-right-24: Forensic toolkit](forensic/index.md)

-   :material-school:{ .lg .middle } **Tutorials**

    ---

    Follow Mosteller & Wallace on the Federalist Papers, run PAN-style verification end to end, and analyse Turkish prose.

    [:octicons-arrow-right-24: Tutorials](tutorials/index.md)

</div>

## What's included

| Layer | Contents |
|---|---|
| **Corpus** | `.txt` + TSV metadata, filtering and grouping, a corpus hash that binds each text to its id and metadata |
| **Features** | most frequent words, character / word / POS n-grams, dependency bigrams, function words, punctuation, sentence length, readability (6 English indices plus native Turkish, German, Spanish and French formulas), 8 lexical-diversity indices, sentence and contextual embeddings |
| **Methods** | Burrows, Eder, Eder Simple, Argamon, Cosine and Quadratic Delta; Zeta (classic, Eder); PCA, MDS, t-SNE, UMAP; Ward, k-means, HDBSCAN; bootstrap consensus trees; sklearn classifiers with stylometry-aware cross-validation (stratified, leave-one-author-out, leave-one-text-out); Bayesian Wallace–Mosteller and hierarchical group comparison |
| **Forensic** | General Impostors and Unmasking verification; Sapkota character n-gram categories and Stamatatos text distortion for topic robustness; Platt / isotonic calibration to log-LRs; C_llr, AUC, c@1, F0.5u (PAN definitions), ECE, Brier, Tippett data; LR-framed HTML report with the two-sided verbal scale of Nordgaard et al. (2012), as adopted by ENFSI (2015); a case workflow with custody hashing and sealed reports ([Forensic Lab](forensic/case-workflow.md)) |
| **Languages** | English, Turkish, German, Spanish, French: per-language function words, readability and embedding defaults; Turkish parsing through Stanza (BOUN treebank) |
| **Output** | `result.json` + Parquet tables + figures per method; HTML / Markdown reports; PDF export of case reports (`bitig[reports]`) |

The documentation is in English and Turkish (`/tr/`).

## Status

The latest release on PyPI is **0.3.1** (`pip install bitig`). `main` carries unreleased
changes, several of which change results or behaviour (case seals, General Impostors
defaults, calibration, PAN metrics, feature scaling).
[`CHANGELOG.md`](https://github.com/fatihbozdag/bitig/blob/main/CHANGELOG.md) lists them,
marked **[results]** and **[breaking]**.

## License & citation

BSD-3-Clause. See [`LICENSE`](https://github.com/fatihbozdag/bitig/blob/main/LICENSE).

If you use bitig in published work, please cite it via
[`CITATION.cff`](https://github.com/fatihbozdag/bitig/blob/main/CITATION.cff).
