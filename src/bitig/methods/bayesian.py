"""Bayesian authorship attribution (Wallace-Mosteller-style) + hierarchical group comparison.

Wallace-Mosteller approach:
  For candidate author `a`, compute log P(tokens | a) = sum(count_w * log rate_w_a), where
  rate_w_a is the MAP estimate of word w's rate under author a's training texts, with a Beta
  (or Dirichlet) prior smoothing zero-count words.

Predicted author = argmax log posterior = log prior (uniform) + log likelihood.

This is a sklearn `ClassifierMixin` so it plugs into Pipeline / cross_validate.

HierarchicalGroupComparison requires PyMC; it builds a varying-intercept model with per-author
draws from a group-level hyperparameter — useful for testing whether two author populations
differ systematically in a stylistic feature (e.g., L2 vs. native function-word use).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin

from bitig.features import FeatureMatrix

try:
    import pymc  # noqa: F401

    _pymc_available = True
except ImportError:
    _pymc_available = False

_INSTALL_HINT_BAYESIAN = (
    "this method requires the optional `bitig[bayesian]` extra — "
    "install with `pip install bitig[bayesian]`"
)


def _as_array(X: FeatureMatrix | np.ndarray) -> np.ndarray:  # noqa: N803 (sklearn convention)
    return X.X if isinstance(X, FeatureMatrix) else np.asarray(X)


def _build_author_to_group_idx(
    y: np.ndarray,
    groups: np.ndarray,
    unique_authors: np.ndarray,
    unique_groups: np.ndarray,
) -> np.ndarray:
    """Map each unique author to its group index.

    An author is expected to belong to exactly one group across the corpus; if any author
    appears under conflicting group labels (which would make the hierarchical model
    ill-defined for that author), raise ValueError with the offending author name.
    """
    author_to_group: dict[Any, int] = {}
    group_label_to_idx = {g: i for i, g in enumerate(unique_groups)}
    for a, g in zip(y, groups, strict=True):
        gi = group_label_to_idx[g]
        existing = author_to_group.get(a)
        if existing is None:
            author_to_group[a] = gi
        elif existing != gi:
            raise ValueError(
                f"author {a!r} appears under multiple groups "
                f"({unique_groups[existing]!r} and {g!r}); hierarchical model requires each "
                "author to belong to exactly one group"
            )
    return np.array([author_to_group[a] for a in unique_authors])


class BayesianAuthorshipAttributor(ClassifierMixin, BaseEstimator):
    """Wallace-Mosteller-style Bayesian authorship attribution.

    Expects count-valued features (raw word counts or equivalent). If z-scored features are
    passed, predictions will still work but the "rate" interpretation breaks down — use
    `MFWExtractor(scale="none")` to produce the right input.
    """

    def __init__(self, *, prior_alpha: float = 1.0) -> None:
        self.prior_alpha = prior_alpha
        self.classes_: np.ndarray = np.empty(0, dtype=object)
        self.log_rates_: dict[str, np.ndarray] = {}

    def fit(
        self,
        X: FeatureMatrix | np.ndarray,  # noqa: N803 (sklearn convention)
        y: np.ndarray,
    ) -> BayesianAuthorshipAttributor:
        counts = _as_array(X)
        # The rate model is only meaningful for non-negative count features.
        # Reject z-scored / mean-centred input loudly rather than silently
        # clipping negatives to 1e-12 (which yields confident but invalid
        # attributions). Build the feature with scale='none' or scale='l1'.
        if np.any(counts < 0):
            raise ValueError(
                "BayesianAuthorshipAttributor requires non-negative count features, but the "
                "input contains negative values (it looks z-scored / mean-centred). Build the "
                "feature with scale='none' or scale='l1' — e.g. MFWExtractor(scale='none')."
            )
        y_arr = np.asarray(y)
        self.classes_ = np.unique(y_arr)

        self.log_rates_ = {}
        for cls in self.classes_:
            class_counts = counts[y_arr == cls].sum(axis=0)
            # Additive (Dirichlet / Beta for binary words) smoothing.
            smoothed = class_counts + self.prior_alpha
            denom = smoothed.sum()
            if denom <= 0:
                raise ValueError(
                    f"class {cls!r} has zero total smoothed count; cannot form a rate vector "
                    "(use prior_alpha > 0 or non-empty count features)."
                )
            rates = smoothed / denom
            # Clip for numerical stability on unseen-but-allowed words.
            rates = np.clip(rates, 1e-12, 1.0)
            self.log_rates_[str(cls)] = np.log(rates)
        return self

    def decision_function(self, X: FeatureMatrix | np.ndarray) -> np.ndarray:  # noqa: N803
        counts = _as_array(X)
        scores = np.column_stack([counts @ self.log_rates_[str(cls)] for cls in self.classes_])
        return scores

    def predict(self, X: FeatureMatrix | np.ndarray) -> np.ndarray:  # noqa: N803
        scores = self.decision_function(X)
        return self.classes_[np.argmax(scores, axis=1)]  # type: ignore[no-any-return]

    def predict_proba(self, X: FeatureMatrix | np.ndarray) -> np.ndarray:  # noqa: N803
        scores = self.decision_function(X)
        scores_shift = scores - scores.max(axis=1, keepdims=True)
        exp = np.exp(scores_shift)
        return exp / exp.sum(axis=1, keepdims=True)  # type: ignore[no-any-return]


class HierarchicalGroupComparison:
    """PyMC hierarchical model: per-author draws of a stylistic feature drawn from a group-level
    hyperparameter, enabling a test of whether two or more groups differ systematically.

    Simple form:
        mu_group    ~ Normal(0, 5)       # group-level mean
        sigma_group ~ HalfNormal(1)      # group-level SD
        theta_author ~ Normal(mu_group, sigma_group)   # per-author stylistic score
        observation[author, doc] ~ Normal(theta_author, obs_sigma)

    Requires bitig[bayesian] extra.
    """

    def __init__(
        self,
        *,
        group_by: str,
        chains: int = 2,
        samples: int = 500,
        tune: int = 500,
        seed: int = 42,
    ) -> None:
        if not _pymc_available:
            raise ImportError(_INSTALL_HINT_BAYESIAN)
        self.group_by = group_by
        self.chains = chains
        self.samples = samples
        self.tune = tune
        self.seed = seed

    def fit_transform(self, fm: FeatureMatrix, y: np.ndarray, groups: np.ndarray) -> dict[str, Any]:
        """Fit the hierarchical model and return a summary dict.

        Parameters
        ----------
        fm : FeatureMatrix
            A single-feature column (use e.g. a scalar index per document such as lexical-diversity).
            If fm has multiple columns, we fit one model per column.
        y : np.ndarray
            Per-document author labels.
        groups : np.ndarray
            Per-document group labels (e.g. L1 vs L2).
        """
        import arviz as az
        import pymc as pm

        X = fm.X  # noqa: N806 (sklearn convention)
        y_arr = np.asarray(y)
        groups_arr = np.asarray(groups)
        if len(y_arr) != len(groups_arr) or len(y_arr) != X.shape[0]:
            raise ValueError("y, groups, and fm must all have the same length along axis 0")

        unique_groups = np.unique(groups_arr)
        unique_authors = np.unique(y_arr)
        author_idx = np.array([list(unique_authors).index(a) for a in y_arr])
        author_to_group_idx = _build_author_to_group_idx(
            y_arr, groups_arr, unique_authors, unique_groups
        )

        results = []
        for col in range(X.shape[1]):
            observations = X[:, col]
            with pm.Model():
                mu_group = pm.Normal("mu_group", mu=0, sigma=5, shape=len(unique_groups))
                pm.HalfNormal("sigma_group", sigma=1, shape=len(unique_groups))
                theta_author = pm.Normal(
                    "theta_author",
                    mu=mu_group[author_to_group_idx],
                    sigma=1,
                    shape=len(unique_authors),
                )
                obs_sigma = pm.HalfNormal("obs_sigma", sigma=1)
                pm.Normal(
                    "obs",
                    mu=theta_author[author_idx],
                    sigma=obs_sigma,
                    observed=observations,
                )
                trace = pm.sample(
                    self.samples,
                    tune=self.tune,
                    chains=self.chains,
                    random_seed=self.seed + col,
                    progressbar=False,
                    return_inferencedata=True,
                )
            summary = az.summary(trace, var_names=["mu_group"])
            results.append(
                {
                    "feature": fm.feature_names[col],
                    "mu_group_summary": summary.to_dict(),
                    "groups": list(unique_groups),
                }
            )
        return {"results": results}
