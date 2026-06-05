"""Dimensionality reducers — PCA, MDS, t-SNE, UMAP — with a shared Result interface."""

from __future__ import annotations

from sklearn.decomposition import PCA
from sklearn.manifold import MDS, TSNE

from bitig.features import FeatureMatrix
from bitig.result import Result


class _ReducerBase:
    _impl: type
    method_name: str

    def __init__(self, **kwargs: object) -> None:
        self._kwargs = kwargs

    def fit_transform(self, fm: FeatureMatrix) -> Result:
        model = self._impl(**self._kwargs)
        coords = model.fit_transform(fm.X)
        values: dict[str, object] = {
            "coordinates": coords,
            "document_ids": list(fm.document_ids),
            "feature_names": list(fm.feature_names),
        }
        # Attach implementation-specific artefacts.
        if hasattr(model, "explained_variance_ratio_"):
            values["explained_variance_ratio"] = model.explained_variance_ratio_
        if hasattr(model, "stress_"):
            values["stress"] = float(model.stress_)
        # PCA-only: components_ is the (n_components, n_features) loading matrix.
        # Manifold methods (MDS, t-SNE, UMAP) have no analogue, so we surface this only
        # when the underlying sklearn estimator exposes it.
        if hasattr(model, "components_"):
            values["loadings"] = model.components_
        return Result(
            method_name=self.method_name,
            params=dict(self._kwargs),
            values=values,
        )


class PCAReducer(_ReducerBase):
    _impl = PCA
    method_name = "pca"


class MDSReducer(_ReducerBase):
    _impl = MDS
    method_name = "mds"

    def __init__(self, **kwargs: object) -> None:
        # Pin defaults that sklearn will change in 1.9/1.10, preserving current behaviour
        # and silencing the transient FutureWarnings. Callers can override either.
        kwargs.setdefault("n_init", 4)
        kwargs.setdefault("init", "random")
        super().__init__(**kwargs)


class TSNEReducer(_ReducerBase):
    _impl = TSNE
    method_name = "tsne"


class UMAPReducer(_ReducerBase):
    method_name = "umap"

    def __init__(self, **kwargs: object) -> None:
        # UMAP overrides n_jobs to 1 when random_state is set; pass it explicitly to silence
        # the informational warning about deterministic reproducibility.
        if "random_state" in kwargs:
            kwargs.setdefault("n_jobs", 1)
        super().__init__(**kwargs)

    @property
    def _impl(self) -> type:  # type: ignore[override]
        try:
            import umap
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise ImportError(
                "UMAP reduction requires the 'cluster' extra. "
                "Install with: uv pip install 'bitig[cluster]'"
            ) from exc

        return umap.UMAP  # type: ignore[no-any-return]
