---
hide:
  - navigation
---

# bitig

<p align="center">
  <img src="assets/bitig-banner.svg" alt="bitig — computational stylometry" style="max-width: 100%;">
</p>

**Computational stylometry for authorship attribution, author-group comparison, and forensic-linguistic analysis.** A Python alternative to R's `Stylo`, with a modern NLP pipeline (spaCy, transformer embeddings), a Bayesian layer (PyMC), and a full forensic-evidential toolkit on top.

> Named after the **bitig** — the Turkic word for *writing* / *inscription*, the kind
> chiselled into the 8th-century Orkhon stelae. A bitig was a recorded text bearing a
> writer's hand; this package looks for that hand.

## Architecture

<p align="center">
  <img src="assets/bitig-architecture.svg" alt="corpus → features → methods → forensic → output" style="max-width: 100%;">
</p>

Every layer is `sklearn`-compatible; every `Result` carries full provenance (corpus hash,
feature hash, seed, spaCy version, timestamp, resolved config) so a study written as a
`study.yaml` re-runs to the same values given the same seed and library versions
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

    General Impostors verification, Unmasking, LR output + calibration, PAN evaluation.

    [:octicons-arrow-right-24: Forensic toolkit](forensic/index.md)

-   :material-school:{ .lg .middle } **Tutorials**

    ---

    Reproduce Mosteller & Wallace on the Federalist Papers; run PAN-style forensic verification end-to-end.

    [:octicons-arrow-right-24: Tutorials](tutorials/index.md)

</div>

## What's in the box

| Layer | Highlights |
|---|---|
| **Corpus** | `.txt` + TSV metadata ingestion, filter / groupby, content-addressed hashing |
| **Languages** | EN / TR / DE / ES / FR first-class — per-language function words, readability formulas, contextual/sentence embedding defaults. Turkish via Stanford Stanza (BOUN) through `spacy-stanza` |
| **Features** | MFW, char / word / POS n-grams, dependency bigrams, function words, punctuation, readability (EN + TR/DE/ES/FR native formulas), sentence length, lexical diversity, sentence + contextual embeddings |
| **Methods** | Burrows / Eder / Argamon / Cosine / Quadratic Delta; Zeta; PCA / UMAP / t-SNE / MDS; Ward / k-means / HDBSCAN; bootstrap consensus; sklearn classify + CV; Wallace–Mosteller Bayesian |
| **Forensic** | General Impostors, Unmasking, Stamatatos distortion, Sapkota n-gram categories, Platt / isotonic calibration, log-LR + C_llr + AUC + c@1 + F0.5u + ECE + Brier + Tippett, PANReport, chain-of-custody Provenance, LR-framed HTML report |

## Status

**Phase 5 landed** — visualisation, Jinja2 reports, declarative runner (`bitig run`), and a
Rich-based interactive `bitig shell`.

**Forensic phase landed** — six additions (General Impostors, LR + calibration + evaluation
metrics, Sapkota categories + Stamatatos distortion, Unmasking, chain-of-custody + forensic
report template, PAN harness).

**Multi-language phase landed** — first-class support for English, Turkish, German, Spanish,
French behind a `bitig.languages` registry. Turkish parses through Stanford Stanza (BOUN
treebank) via `spacy-stanza`, returning native spaCy `Doc` objects so every feature extractor
works unchanged. Native readability formulas per language (Ateşman + Bezirci–Yılmaz for Turkish,
Flesch-Amstad + Wiener Sachtextformel for German, Fernández-Huerta + Szigriszt-Pazos for
Spanish, Kandel–Moles + LIX for French). Function-word lists generated reproducibly from
UD closed-class tokens.

**Docs site landed** — this MkDocs Material site with Concepts, Forensic toolkit, Federalist +
PAN-CLEF + Turkish tutorials, and CLI/API reference.

**Docs site is multilingual** — English (default) and Turkish (`/tr/`) launched via
`mkdocs-static-i18n`; DE/ES/FR infrastructure ready, translation content deferred.

**Forensic Lab** — the case workflow (evidence custody, recipe runs, sealed reports) is documented in [Forensic Lab (cases)](forensic/case-workflow.md).

**Released on PyPI** — `pip install bitig`.

## License & citation

BSD-3-Clause. See [`LICENSE`](https://github.com/fatihbozdag/bitig/blob/main/LICENSE).

If you use bitig in published work, please cite it via
[`CITATION.cff`](https://github.com/fatihbozdag/bitig/blob/main/CITATION.cff).
