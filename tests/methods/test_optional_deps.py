"""The cluster-extra methods give a clear install hint when the lib is absent.

UMAP + HDBSCAN moved from base deps to the ``cluster`` extra (audit P1.17);
the lazy imports must raise a helpful ImportError rather than a bare
ModuleNotFoundError. We simulate "not installed" by pinning ``sys.modules``
entry to ``None`` so ``import umap`` / ``import hdbscan`` raise ImportError.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

from bitig.features import FeatureMatrix


def test_umap_missing_gives_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "umap", None)
    from bitig.methods.reduce import UMAPReducer

    with pytest.raises(ImportError, match=r"bitig\[cluster\]"):
        _ = UMAPReducer()._impl


def test_hdbscan_missing_gives_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "hdbscan", None)
    from bitig.methods.cluster import HDBSCANCluster

    fm = FeatureMatrix(
        X=np.zeros((3, 2)),
        document_ids=["a", "b", "c"],
        feature_names=["f0", "f1"],
        feature_type="t",
    )
    with pytest.raises(ImportError, match=r"bitig\[cluster\]"):
        HDBSCANCluster().fit_transform(fm)
