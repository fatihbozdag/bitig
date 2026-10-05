# Choosing a method

Not sure which bitig method fits your question? This page answers *"I want to do X —
what should I reach for?"* for the most common cases. The method names link to their
primary entries in [Methods](methods.md) and [Forensic toolkit](../forensic/index.md)
for the full detail.

## Attribution, comparison, exploration

| I want to… | Required data | Method | Headline metric | Tutorial |
|---|---|---|---|---|
| Attribute 1 questioned doc to N candidate authors | N authors × ~2k+ words known each; 1 questioned doc | [`CosineDelta`](methods.md#cosinedelta) (robust default) or [`BurrowsDelta`](methods.md#burrowsdelta) (classic) | nearest-author rank | [Federalist](../tutorials/federalist.md) |
| Cluster an unknown corpus by stylistic similarity | 20+ docs, labels optional | [`PCAReducer`](methods.md#pcareducer) + [`KMeansCluster`](methods.md#kmeanscluster) or [`HDBSCANCluster`](methods.md#hdbscancluster) | silhouette, visual inspection | — |
| Compare two pre-defined author groups | 10+ docs per group | [`ZetaClassic`](methods.md#zetaclassic) or [`ZetaEder`](methods.md#zetaeder) | per-word distinctiveness score | — |
| Classify docs into groups with ML | 20+ docs per class | [`build_classifier`](methods.md#classification-cv) + [`cross_validate_bitig`](methods.md#classification-cv) | CV accuracy / F1 | — |
| Reduce features for visualisation | any `FeatureMatrix` | [`PCAReducer`](methods.md#pcareducer) / [`UMAPReducer`](methods.md#umapreducer) / [`TSNEReducer`](methods.md#tsnereducer) / [`MDSReducer`](methods.md#mdsreducer) | visual inspection | — |
| Bayesian attribution among N candidates | N candidates × ≥1k words as raw counts (`MFWExtractor(scale="none")`); 1 questioned doc | [`BayesianAuthorshipAttributor`](methods.md#bayesianauthorshipattributor) | posterior probability per candidate | — |
| Bootstrap-consensus tree across MFW bands | 10+ docs, multiple MFW bands | [`BootstrapConsensus`](methods.md#bootstrapconsensus) | Newick tree with clade support | — |

## Forensic — one-case verification

| I want to… | Required data | Method | Headline metric | Tutorial |
|---|---|---|---|---|
| Verify "same author?" between 1 questioned doc and 1 candidate | 1 candidate's known writings + an impostor pool (~100 docs) | [`GeneralImpostors`](../forensic/verification.md#general-impostors) | verification score (a log-LR only after [`CalibratedScorer`](../forensic/calibration.md#calibratedscorer)) | [PAN-CLEF](../tutorials/pan-clef.md) |
| Verify same-author with topic-robustness | Q + K long prose + impostor pool | [`Unmasking`](../forensic/verification.md#unmasking) | accuracy-drop curve | [PAN-CLEF](../tutorials/pan-clef.md) |
| Minimise topic bias in verification features | any corpus | [`CategorizedCharNgramExtractor`](features.md#categorizedcharngramextractor) with `categories=("prefix","suffix","punct")`, or [`distort_corpus(mode="dv_ma")`](features.md#distort_corpus) | same as upstream verifier | [PAN-CLEF](../tutorials/pan-clef.md) |
| Turn raw verifier scores into evidential LR | verifier outputs on labelled dev trials | [`CalibratedScorer`](../forensic/calibration.md#calibratedscorer) + [`compute_pan_report`](../forensic/evaluation.md#compute_pan_report) | log-LR, `C_llr`, `ECE` | [PAN-CLEF](../tutorials/pan-clef.md) |
| Generate an LR-framed forensic report | `Result` with chain-of-custody fields | [`build_forensic_report`](../forensic/reporting.md) | two-sided ENFSI verbal scale | — |

## How to read this page

- **"Required data"** is a minimum — more is always better.
- **"Headline metric"** is the output you should quote in write-ups, not the only output
  the method produces.
- When two methods are listed for the same task, the first one is the recommended default
  and the second is a published alternative worth considering.

## Next

- [Methods](methods.md) — full catalogue with gloss + detail per method.
- [Features](features.md) — extractor catalogue with gloss + detail per extractor.
- [Forensic toolkit](../forensic/index.md) — calibration, evaluation, reporting.
