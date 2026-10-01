# Federalist Papers — full stylometric analysis

A complete, reproducible demonstration of `bitig` against the classical
stylometry benchmark: the 85 Federalist Papers (1787–1788, public domain),
with attribution of the 11 historically disputed essays (49–57, 62, 63).

## Corpus

85 texts — Hamilton (51), Madison (15), Jay (5), joint Hamilton+Madison (3),
disputed (11) — copied verbatim from Project Gutenberg ebook 1404 and
labelled in `metadata.tsv` following the canonical consensus (Mosteller &
Wallace 1964; subsequent scholarship).

| Author                | Count |
|-----------------------|-------|
| Hamilton              | 51    |
| Madison               | 15    |
| Jay                   | 5     |
| Hamilton + Madison    | 3     |
| Disputed              | 11    |

## Reproduce

```bash
# From the repository root
uv pip install -e ".[dev,embeddings,bayesian]"
python -m spacy download en_core_web_sm

# Run the full study (Delta / Zeta / PCA / Ward / Consensus)
bitig run examples/federalist/study.yaml --name demo

# Render the publication-quality figures
python examples/federalist/render_figures.py

# Generate the HTML report (figures included)
bitig report examples/federalist/results/demo \
    --output examples/federalist/results/demo/report.html \
    --title "Federalist Papers — full analysis"

# Disputed-paper attribution: test on the 11 role=test papers, train on all other 74
# (Hamilton, Madison, Jay, and the 3 joint papers as a fourth "Joint_HM" class)
bitig delta examples/federalist/corpus --method burrows --mfw 500 \
    --metadata examples/federalist/metadata.tsv --group-by author \
    --test-filter role=test

bitig bayesian examples/federalist/corpus --mfw 500 \
    --metadata examples/federalist/metadata.tsv --group-by author \
    --test-filter role=test
```

## Result

Both Burrows Delta and the Wallace–Mosteller-style Bayesian attribution
assign **every one of the 11 disputed papers to Madison** (at MFW 500 as
above, and at MFW 200), reproducing the classical Mosteller & Wallace (1964)
result. `bitig bayesian` prints `max p(author)` = 1.000 for every disputed
paper. That number is a Naive Bayes posterior (word occurrences treated as
independent), which is pushed to 0 or 1; it is **not a calibrated
probability** and should be read as a ranking of candidates only.

The commands train on every paper outside `role=test`, so the 3 joint papers
(18–20) enter training as their own `Joint_HM` class; there is no flag to
exclude them. Training on Hamilton and Madison only gives the same 11/11
Madison result.

**Caveat — author bylines.** Each text keeps its Project Gutenberg byline
(`HAMILTON`, `MADISON`, `JAY`), and the disputed papers carry `MADISON`. At
MFW 500 the token `hamilton` is one of the features, and the Zeta lists below
are topped by `hamilton` / `madison`. With the bylines stripped, Bayesian
attribution is still 11/11 Madison, and so is Delta trained on Hamilton and
Madison only; Delta trained as above (with the `Joint_HM` class) then assigns
No. 50 to `Joint_HM`. Strip the bylines before running your own experiments.

## What the study.yaml does

`examples/federalist/study.yaml` runs five methods on the 71 single-author
papers (Joint and Disputed excluded via `role: [train]`):

1. **Burrows Delta** — nearest-author-centroid on 500 most-frequent words (z-scored).
   Its accuracy (1.0) is resubstitution (in-sample) only: no disputed paper is in this study.
2. **PCA** — 2-D projection of the same feature matrix. The two components
   explain 5.6 % and 4.6 % of the variance. PC1 separates Jay from the rest;
   Hamilton and Madison overlap. The disputed papers are not in the plot. See
   `results/demo/pca/scatter.png` (written by `bitig run`) or the
   author-coloured `pca.png` written by `render_figures.py`.
3. **Hierarchical clustering (Ward)** — 3 clusters. Measured: all 15 Madison
   papers share a cluster with 38 Hamilton and 2 Jay papers; the other 13
   Hamilton papers form a second cluster and 3 Jay papers the third. Dendrogram in
   `results/demo/ward/dendrogram.png` (`ward.png` from `render_figures.py`).
4. **Craig's Zeta** — contrastive vocabulary between Hamilton and Madison.
   Shows the "upon" vs. "whilst" signature Mosteller & Wallace relied on
   (after the byline tokens `hamilton` / `madison`, see the caveat above).
   Preference plot in `results/demo/zeta_hamilton_madison/zeta.png`.
5. **Bootstrap consensus tree** — 5 MFW bands × 20 replicates = 100 Ward
   dendrograms, with majority-support clade extraction. Newick string in
   `results/demo/consensus/result.json`.

The disputed-paper attribution is a separate step (via `bitig delta` +
`bitig bayesian` with the `--test-filter role=test` flag) because it
requires a train/test split that the declarative `bitig run` workflow
does not yet expose.

## License

Federalist Papers texts are in the public domain. `metadata.tsv` and
`study.yaml` are BSD-3-Clause along with the rest of `bitig`.
