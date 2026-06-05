"""Clustering methods — hierarchical (Ward/average/complete/single), k-means, HDBSCAN."""

from __future__ import annotations

from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.cluster import KMeans

from bitig.features import FeatureMatrix
from bitig.result import Result


class HierarchicalCluster:
    """scipy-based hierarchical clustering — returns both flat labels and the full linkage matrix
    (the latter is what the viz layer uses to render dendrograms).
    """

    def __init__(
        self,
        n_clusters: int = 2,
        *,
        linkage: str = "ward",
        metric: str = "euclidean",
    ) -> None:
        self.n_clusters = n_clusters
        self.linkage = linkage
        self.metric = metric

    def fit_transform(self, fm: FeatureMatrix) -> Result:
        # Ward requires Euclidean distances, scipy handles this internally when method="ward".
        Z = linkage(  # noqa: N806
            fm.X,
            method=self.linkage,
            metric=self.metric if self.linkage != "ward" else "euclidean",
        )
        labels = fcluster(Z, t=self.n_clusters, criterion="maxclust") - 1  # 0-indexed
        return Result(
            method_name="hierarchical",
            params={"n_clusters": self.n_clusters, "linkage": self.linkage, "metric": self.metric},
            values={
                "labels": labels,
                "linkage": Z,
                "document_ids": list(fm.document_ids),
            },
        )


class KMeansCluster:
    def __init__(
        self,
        n_clusters: int = 2,
        *,
        random_state: int | None = None,
        n_init: int | str = "auto",
    ) -> None:
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.n_init = n_init

    def fit_transform(self, fm: FeatureMatrix) -> Result:
        model = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init=self.n_init,
        )
        labels = model.fit_predict(fm.X)
        return Result(
            method_name="kmeans",
            params={"n_clusters": self.n_clusters, "random_state": self.random_state},
            values={
                "labels": labels,
                "centers": model.cluster_centers_,
                "inertia": float(model.inertia_),
                "document_ids": list(fm.document_ids),
            },
        )


class HDBSCANCluster:
    def __init__(
        self,
        min_cluster_size: int = 5,
        *,
        min_samples: int | None = None,
        metric: str = "euclidean",
    ) -> None:
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.metric = metric

    def fit_transform(self, fm: FeatureMatrix) -> Result:
        try:
            import hdbscan
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise ImportError(
                "HDBSCAN clustering requires the 'cluster' extra. "
                "Install with: uv pip install 'bitig[cluster]'"
            ) from exc

        model = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            metric=self.metric,
        )
        labels = model.fit_predict(fm.X)
        return Result(
            method_name="hdbscan",
            params={
                "min_cluster_size": self.min_cluster_size,
                "min_samples": self.min_samples,
                "metric": self.metric,
            },
            values={
                "labels": labels,
                "probabilities": getattr(model, "probabilities_", None),
                "document_ids": list(fm.document_ids),
            },
        )
