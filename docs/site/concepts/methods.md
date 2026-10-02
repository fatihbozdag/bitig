# Methods

Methods turn a `FeatureMatrix` into a `Result`. Every method is `sklearn`-compatible
where it makes sense (`fit`, `predict`, `fit_transform`).

## Attribution — Delta variants

All Delta variants share `_DeltaBase`, work on z-scored features, and produce a
nearest-centroid classifier.

| Class | Distance | Reference |
|---|---|---|
| `BurrowsDelta` | mean absolute L1 | Burrows 2002 |
| `ArgamonLinearDelta` | L2 (Euclidean) | Argamon 2008 |
| `QuadraticDelta` | squared L2 | — |
| `CosineDelta` | 1 − cosine similarity | Smith & Aldridge 2011 |
| `EderDelta` | frequency-rank-weighted L1 | Eder 2015 |
| `EderSimpleDelta` | summed L1 (unweighted) | Eder 2017 |

```python
from bitig import MFWExtractor, BurrowsDelta
fm = MFWExtractor(n=200, scale="zscore", lowercase=True).fit_transform(corpus)
y = np.array(corpus.metadata_column("author"))
clf = BurrowsDelta().fit(fm, y)
predictions = clf.predict(fm)       # nearest-centroid labels
probs = clf.predict_proba(fm)       # softmax over negative distances
```

### BurrowsDelta
`BurrowsDelta()`

*Use when:* you have 2+ candidate authors with ~2000+ words of known writing each and
want to rank which one most likely wrote a questioned document.
*Don't use when:* you have only one candidate (use `GeneralImpostors` verification
instead), or when documents are shorter than ~500 words (signal gets noisy).
*Expect:* a distance score per candidate; lowest distance is the predicted author.

The classic Burrows (2002) method: z-score features, mean-absolute-difference (L1)
distance to each candidate's centroid. Good default for literary English.

### CosineDelta
`CosineDelta()`

*Use when:* you want a modern default for Delta-family attribution — cosine is robust
to document-length differences and less sensitive to outlier words than L1.
*Don't use when:* your corpus mixes wildly different genres without care; cosine is
less diagnostic when topic dominates style.
*Expect:* a distance score per candidate in `[0, 2]`; lowest distance wins.

Smith & Aldridge (2011). Standard choice in modern stylometry; often the best
single-method baseline before tuning.

### EderDelta / EderSimpleDelta
`EderDelta()`, `EderSimpleDelta()`

*Use when:* you want to dampen noisy low-frequency words in the MFW tail — `EderDelta`
weights each feature by its frequency rank, so less-frequent features contribute less.
*Don't use when:* your MFW list is already short (n < 100); there's little tail to down-
weight.
*Expect:* same shape as Burrows Delta; different ranking when tail-MFW contributions
would otherwise dominate.

`EderDelta` (Eder 2015) weights the i-th most frequent of n features by `(n - i) / n`;
the columns must be in frequency order, as `MFWExtractor` returns them.
`EderSimpleDelta` is the summed L1 distance with no weights. It differs from
`BurrowsDelta` (mean L1) only by the constant factor n, so it ranks candidates exactly
as Burrows does.

### ArgamonLinearDelta
`ArgamonLinearDelta()`

*Use when:* you specifically want Euclidean (L2) distance rather than L1 — appropriate
when features are approximately Gaussian after z-scoring.
*Don't use when:* the MFW distribution is skewed enough to produce outliers; L2
penalises outliers quadratically. Prefer `CosineDelta` or `BurrowsDelta`.
*Expect:* a distance score per candidate; same ranking shape as other Deltas with
different sensitivity to large per-feature deviations.

Argamon (2008). Probabilistic interpretation of Delta under a Gaussian generative
model.

### QuadraticDelta
`QuadraticDelta()`

*Use when:* you want to replicate experiments that use squared-L2 distance — equivalent
to Argamon Delta without the square root.
*Don't use when:* you need a calibrated distance for downstream combining; squared
distances aren't a proper metric.
*Expect:* a distance score per candidate; monotonic with Argamon Linear Delta so
ranking is identical.

## Contrast — Zeta

Craig's Zeta (`ZetaClassic`) and Eder's smoothed variant (`ZetaEder`) extract the
vocabulary most preferred by one author group versus another.

```python
from bitig.methods.zeta import ZetaClassic
result = ZetaClassic(group_by="author", top_k=50, group_a="Hamilton", group_b="Madison").fit_transform(corpus)
df_a, df_b = result.tables   # top-k A-preferred / B-preferred words with proportions
```

### ZetaClassic
`ZetaClassic(group_by=..., top_k=..., group_a=..., group_b=...)`

*Use when:* you have two pre-defined author groups (or authors) and want to know which
words each group prefers over the other — Craig's classic Zeta.
*Don't use when:* you only want to rank one unknown document against candidates (use a
Delta instead), or when your groups are very small (<10 docs each).
*Expect:* two tables of top-k words; each word has a proportion-in-A and
proportion-in-B; large differences are the distinctive vocabulary.

### ZetaEder
`ZetaEder(group_by=..., top_k=..., group_a=..., group_b=...)`

*Use when:* you want Zeta with the Eder (2017) smoothing — add-0.5 smoothing of the
per-group document counts, which shrinks very rare words toward the middle instead of
letting zero counts dominate.
*Don't use when:* you're reproducing Burrows/Craig-era results for comparison; use
`ZetaClassic` for historical parity.
*Expect:* same output shape as `ZetaClassic`; smoother ranking near the tails.

## Dimensionality reduction

All reducers accept a `FeatureMatrix` and return a `Result` with 2-D / n-D coordinates
in `values["coordinates"]`. Keyword arguments are passed unchanged to the underlying
scikit-learn (or `umap-learn`) estimator, so the parameters below are theirs.

### PCAReducer
`PCAReducer(n_components=2)`

*Use when:* you want a fast, interpretable 2-D or 3-D projection where axes are
orthogonal variance directions. Default choice for "plot my corpus" questions.
*Don't use when:* authorship differences are highly non-linear; PCA's linear axes will
miss curved manifolds.
*Expect:* `coordinates` (n_docs × n_components) + `explained_variance_ratio` per
component + `loadings` (n_components × n_features).

### UMAPReducer
`UMAPReducer(n_components=2, n_neighbors=15, min_dist=0.1)`

*Use when:* you want a non-linear projection that preserves local *and* global
structure — typically the best-looking 2-D visualisation of stylometric features.
*Don't use when:* you need reproducibility without pinning a seed — UMAP is
stochastic. Always set `random_state`.
*Expect:* `coordinates` (n_docs × n_components). Requires `bitig[cluster]`.

### TSNEReducer
`TSNEReducer(n_components=2, perplexity=30)`

*Use when:* you want a non-linear projection that emphasises local neighbourhood
structure — authors cluster tightly.
*Don't use when:* you need inter-cluster distances to be meaningful (t-SNE warps them),
or when you plan to use the coordinates as features for a downstream method.
*Expect:* `coordinates` (n_docs × n_components). Non-deterministic without
`random_state`. `perplexity` must be smaller than the number of documents.

### MDSReducer
`MDSReducer(n_components=2)`

*Use when:* you want a projection that tries to preserve the pairwise (Euclidean)
distances between feature vectors as literally as possible — good for interpreting dendrogram + scatter together.
*Don't use when:* you have a large corpus (>500 docs); MDS scales poorly.
*Expect:* `coordinates` (n_docs × n_components) + `stress` (lower = better fit).
Metric MDS is the default; with scikit-learn ≥ 1.8 pass `metric_mds=False` for
non-metric MDS (the old `metric=True/False` raises a `FutureWarning`).

## Clustering

Clusterers accept a `FeatureMatrix` and produce cluster labels; hierarchical clustering
also returns the linkage matrix for dendrograms.

### HierarchicalCluster
`HierarchicalCluster(n_clusters=2, linkage="ward", metric="euclidean")`

*Use when:* you want a dendrogram — the canonical stylometry visualisation — where
leaves are documents and branch heights are distances.
*Don't use when:* your corpus is large enough (>2000 docs) that dendrogram inspection
is no longer practical.
*Expect:* `labels` (n_docs,), cut at `n_clusters`, + `linkage` (the scipy linkage
matrix) usable with `scipy.cluster.hierarchy.dendrogram`. `metric` is ignored for
`"ward"`, which always uses Euclidean distance.

Supported linkages: `"ward"` (default, variance-minimising), `"average"`, `"complete"`,
`"single"`.

### KMeansCluster
`KMeansCluster(n_clusters=3, random_state=42)`

*Use when:* you have a rough expected cluster count and want spherical clusters of
comparable size — fastest clustering option.
*Don't use when:* cluster sizes are very unequal, cluster shapes are elongated, or you
don't know `n_clusters` ahead of time (use `HDBSCANCluster`).
*Expect:* `labels` (n_docs,) + `centers` (cluster centroids) + `inertia`. Set
`random_state` for reproducible labels (default `None`).

### HDBSCANCluster
`HDBSCANCluster(min_cluster_size=5)`

*Use when:* you don't know the cluster count ahead of time, expect variable cluster
density, or want "noise" points to be labelled as outliers (-1).
*Don't use when:* your corpus is small (<30 docs); HDBSCAN's density estimates get
unstable.
*Expect:* `labels` (n_docs,) with -1 for noise; `probabilities` (cluster-membership
confidence). Requires `bitig[cluster]`.

## Consensus trees

### BootstrapConsensus
`BootstrapConsensus(mfw_bands=[100, 200, 300], replicates=100)` (`mfw_bands` is required;
`replicates` defaults to 100). It takes a `Corpus` and fits its own MFW features.

*Use when:* you want robustness evidence for a dendrogram — repeatedly resample the
MFW feature set and see which clades survive.
*Don't use when:* you need one quick visualisation; bootstrap runs many Delta +
clustering cycles and is slow.
*Expect:* a Newick consensus tree with clade-support values. Each replicate also
subsamples documents (`subsample`, default 0.8), so a clade's support is the fraction of
trees **containing all of its members** in which it appears as a clade. Clades with
support strictly above `support_threshold` (default 0.5, majority rule) form the tree.

Eder (2017) bootstraps across MFW bands; bitig additionally subsamples documents, which
Eder's method does not.

## Classification + CV

Any sklearn classifier (`"logreg"`, `"svm_linear"`, `"svm_rbf"`, `"rf"`, `"hgbm"`) via
`build_classifier(name, **kwargs)`, plus
`cross_validate_bitig(clf, None, y, extractor=..., corpus=..., cv_kind=..., groups_from=...)`,
which refits the feature extractor inside each training fold so held-out documents never
shape the vocabulary or z-scores. (Passing a precomputed `fm` instead is allowed but
leaks test documents into the features if `fm` was fit on all of them.)

*Use when:* you have labelled documents (author or group) and want standard ML
performance numbers — accuracy, per-class precision / recall / F1.
*Don't use when:* you have fewer than ~20 documents per class; CV becomes statistically
meaningless. Also don't use for single-case verification (use `GeneralImpostors`).
*Expect:* a dict with `accuracy`, the out-of-fold `predictions`, a `per_class`
`classification_report` dict, and `proba` / `classes` when the classifier has
`predict_proba`.

Three CV strategies (`cv_kind`):

- `stratified` (default) — StratifiedKFold with `folds` splits (default 5); `seed`
  controls the shuffle. Documents by the same author can sit in both training and test
  folds, which is what attribution needs.
- `loao` — LeaveOneGroupOut over `groups_from`. Use it as *leave-one-author-out* when
  the target is **not** the author (e.g. period, genre, L1 group): pass the per-document
  author as `groups_from`, so every test document comes from an author the model never
  saw and the score cannot ride on author identity. For attribution (target = author),
  leave-one-author-out holds out a class absent from training; when `groups_from` is a
  one-to-one relabelling of `y` it raises `ValueError`.
- `leave_one_text_out` — LeaveOneOut

## Bayesian

### BayesianAuthorshipAttributor
`BayesianAuthorshipAttributor()`

*Use when:* you want posterior probabilities over N candidate authors with principled
Dirichlet smoothing — the Wallace–Mosteller Federalist approach.
*Don't use when:* your features are z-scored (it expects raw counts; use
`MFWExtractor(scale="none")`).
*Expect:* `predict_proba` returns per-document posterior probability vectors over
candidates. No need for `bitig[bayesian]` — this variant is pure NumPy.

### HierarchicalGroupComparison
`HierarchicalGroupComparison(group_by=..., chains=2, samples=500, tune=500, seed=42)`,
then `.fit_transform(fm, y, groups)`

*Use when:* you want to test whether two author populations differ systematically in a
stylistic feature, with full per-author uncertainty — a PyMC varying-intercept model.
*Don't use when:* you only have one author per group (no pooling signal) or need a
fast screening method (MCMC sampling is slow; use a frequentist Zeta first).
*Expect:* `fit_transform(fm, y, groups)` takes per-document author labels `y` and
group labels `groups` and fits one model per column of `fm` (two or more groups are
allowed). It returns a dict `{"results": [...]}`, one entry per feature, holding the
arviz summary of the group means (`mu_group`) and SDs (`sigma_group`) on the
standardised feature scale, plus the mean and SD to map back. Requires
`bitig[bayesian]`.

## Forensic methods

Under `bitig.forensic`:

*Use when:* you want bitig's one-case verification or calibration layer — see the
dedicated [Forensic toolkit](../forensic/index.md) pages for gloss-per-method detail.
*Don't use when:* you have a closed candidate set and just want attribution — use
Delta variants above.
*Expect:* verification scores in [0, 1] (not LRs) and, via `CalibratedScorer` fitted
on held-out trials, calibrated posteriors and per-trial log-LRs.

| Method | Task | Reference |
|---|---|---|
| `GeneralImpostors` | one-class verification | Koppel & Winter 2014 |
| `Unmasking` | long-text verification (accuracy-degradation curve) | Koppel & Schler 2004 |
| `CalibratedScorer` | Platt / isotonic calibration of any scorer | Platt 1999; Niculescu-Mizil & Caruana 2005 |

See [Forensic toolkit](../forensic/index.md).

## Next

- [Results & provenance](results.md) — what every method returns.
