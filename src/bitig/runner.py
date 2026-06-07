"""Config-driven orchestrator — executes all methods declared in a `study.yaml`."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import spacy

from bitig.config import StudyConfig, load_config
from bitig.features import (
    CharNgramExtractor,
    FeatureMatrix,
    FunctionWordExtractor,
    LexicalDiversityExtractor,
    MFWExtractor,
    PunctuationExtractor,
    ReadabilityExtractor,
    WordNgramExtractor,
)
from bitig.io import load_corpus
from bitig.methods.bayesian import BayesianAuthorshipAttributor
from bitig.methods.classify import build_classifier, cross_validate_bitig
from bitig.methods.cluster import HDBSCANCluster, HierarchicalCluster, KMeansCluster
from bitig.methods.consensus import BootstrapConsensus
from bitig.methods.delta import (
    ArgamonLinearDelta,
    BurrowsDelta,
    CosineDelta,
    EderDelta,
    EderSimpleDelta,
    QuadraticDelta,
)
from bitig.methods.imposters import GeneralImposters
from bitig.methods.reduce import MDSReducer, PCAReducer, TSNEReducer, UMAPReducer
from bitig.methods.rolling_delta import RollingDelta
from bitig.methods.zeta import ZetaClassic, ZetaEder
from bitig.plumbing.logging import get_logger
from bitig.preprocess.pipeline import SpacyPipeline
from bitig.provenance import Provenance
from bitig.result import Result

_log = get_logger(__name__)

_FEATURE_BUILDERS = {
    "mfw": MFWExtractor,
    "word_ngram": WordNgramExtractor,
    "char_ngram": CharNgramExtractor,
    "function_word": FunctionWordExtractor,
    "punctuation": PunctuationExtractor,
    "lexical_diversity": LexicalDiversityExtractor,
    "readability": ReadabilityExtractor,
}

_DELTA_VARIANTS: dict[str, type] = {
    "burrows": BurrowsDelta,
    "cosine": CosineDelta,
    "argamon_linear": ArgamonLinearDelta,
    "quadratic": QuadraticDelta,
    "eder": EderDelta,
    "eder_simple": EderSimpleDelta,
}

_REDUCER_VARIANTS: dict[str, type] = {
    "pca": PCAReducer,
    "mds": MDSReducer,
    "tsne": TSNEReducer,
    "umap": UMAPReducer,
}

_CLUSTER_VARIANTS: dict[str, type] = {
    "hierarchical": HierarchicalCluster,
    "kmeans": KMeansCluster,
    "hdbscan": HDBSCANCluster,
}

_ZETA_VARIANTS: dict[str, type] = {
    "classic": ZetaClassic,
    "eder": ZetaEder,
}


def run_study(
    config_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    run_name: str | None = None,
) -> Path:
    """Execute a full study from a `study.yaml` file and save all results.

    Returns the path to the run directory (e.g., `results/2026-04-17T10-15-30/`).
    """
    cfg: StudyConfig = load_config(Path(config_path))
    run_dir = _make_run_dir(cfg, output_dir, run_name)
    _log.info("run directory: %s", run_dir)

    corpus = load_corpus(
        Path(cfg.corpus.path), metadata=Path(cfg.corpus.metadata) if cfg.corpus.metadata else None
    )
    if cfg.corpus.filter:
        corpus = corpus.filter(**cfg.corpus.filter)
    _log.info("loaded %d documents", len(corpus))

    # Build all feature matrices by id.
    features_by_id: dict[str, FeatureMatrix] = {}
    for feat_cfg in cfg.features:
        extractor_cls = _FEATURE_BUILDERS.get(feat_cfg.type)
        if extractor_cls is None:
            _log.warning(
                "skipping feature %s: type %s not yet supported by runner",
                feat_cfg.id,
                feat_cfg.type,
            )
            continue
        extractor = extractor_cls(**feat_cfg.params)
        features_by_id[feat_cfg.id] = extractor.fit_transform(corpus)
        _log.info("built features %s: %s", feat_cfg.id, features_by_id[feat_cfg.id].X.shape)

    # SpacyPipeline resolves `language` → default model/backend via the languages registry.
    # Explicit model/backend on SpacyConfig override the registry defaults.
    pipe = SpacyPipeline(
        language=cfg.preprocess.language,
        model=cfg.preprocess.spacy.model,
        backend=cfg.preprocess.spacy.backend,
        exclude=list(cfg.preprocess.spacy.exclude),
    )

    # Execute each method.
    for method_cfg in cfg.methods:
        method_dir = run_dir / method_cfg.id
        method_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = _dispatch_method(method_cfg, corpus, features_by_id, seed=cfg.seed)
            # Derive feature_hash from the primary feature id used by this method (if any).
            feat_hash: str | None = None
            features_attr = getattr(method_cfg, "features", None)
            if features_attr:
                primary_feat_id = (
                    features_attr if isinstance(features_attr, str) else features_attr[0]
                )
                fm_primary = features_by_id.get(primary_feat_id)
                if fm_primary is not None:
                    feat_hash = fm_primary.provenance_hash or None
            result.provenance = Provenance.current(
                spacy_model=pipe.model,
                spacy_version=spacy.__version__,
                corpus_hash=corpus.hash(),
                feature_hash=feat_hash,
                seed=cfg.seed,
                resolved_config=cfg.model_dump(),
            )
            result.save(method_dir)
            _log.info("wrote %s", method_dir)
            _emit_default_plot(
                method_cfg=method_cfg, method_dir=method_dir, result=result, corpus=corpus
            )
        except Exception as exc:
            _log.error("method %s failed: %s", method_cfg.id, exc)
            (method_dir / "error.txt").write_text(str(exc))

    (run_dir / "resolved_config.json").write_text(
        json.dumps(cfg.model_dump(), indent=2, default=str)
    )
    return run_dir


def _make_run_dir(cfg: StudyConfig, output_dir: str | Path | None, run_name: str | None) -> Path:
    base = Path(output_dir or cfg.output.dir)
    if run_name:
        run_dir = base / run_name
    elif cfg.output.timestamp:
        run_dir = base / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    else:
        run_dir = base
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _dispatch_method(
    method_cfg: Any,
    corpus: Any,
    features_by_id: dict[str, FeatureMatrix],
    *,
    seed: int,
) -> Result:
    kind = method_cfg.kind

    if kind == "delta":
        feat_id = (
            method_cfg.features if isinstance(method_cfg.features, str) else method_cfg.features[0]
        )
        fm = features_by_id[feat_id]
        y = np.array(corpus.metadata_column(method_cfg.group_by))
        variant = str(method_cfg.params.get("variant", "burrows"))
        cls = _DELTA_VARIANTS.get(variant)
        if cls is None:
            raise ValueError(
                f"unknown delta variant: {variant!r} (known: {sorted(_DELTA_VARIANTS)})"
            )
        clf = cls().fit(fm, y)
        preds = clf.predict(fm)
        # In-sample (train == test): the centroids were fit on these same
        # documents and `fm` was z-scored over the whole corpus, so this is
        # RESUBSTITUTION accuracy — a separability diagnostic, NOT a held-out
        # generalization estimate. Labelling it plain "accuracy" overstated it
        # (audit P2, diagnostic-vs-attribution). For an attribution accuracy
        # estimate use `bitig classify` (stratified / leave-one-out CV).
        return Result(
            method_name=f"delta_{variant}",
            params=dict(method_cfg.params),
            values={
                "predictions": preds,
                "resubstitution_accuracy": float((preds == y).mean()),
                "evaluation": "resubstitution (in-sample); use `bitig classify` for held-out CV",
            },
        )

    if kind == "rolling_delta":
        # Rolling delta owns its MFW fit because targets must be excluded from
        # vocabulary and z-score statistics; it ignores `features:` references.
        if not method_cfg.group_by:
            raise ValueError("rolling_delta requires group_by (e.g. 'author')")
        params = dict(method_cfg.params)
        target_ids = params.pop("target_ids", None)
        if not target_ids:
            raise ValueError(
                "rolling_delta requires params.target_ids (list of document ids to scan)"
            )
        rolling_result: Result = RollingDelta(
            target_ids=list(target_ids),
            group_by=method_cfg.group_by,
            **params,
        ).fit_transform(corpus)
        return rolling_result

    if kind == "verify":
        if not method_cfg.group_by:
            raise ValueError("verify requires group_by (e.g. 'author')")
        params = dict(method_cfg.params)
        target_ids = params.pop("target_ids", None)
        if not target_ids:
            raise ValueError("verify requires params.target_ids (list of document ids to verify)")
        candidate = params.pop("candidate", None)
        if not candidate:
            raise ValueError("verify requires params.candidate (the alleged author label)")
        params.setdefault("seed", seed)
        verify_result: Result = GeneralImposters(
            target_ids=list(target_ids),
            candidate=str(candidate),
            group_by=method_cfg.group_by,
            **params,
        ).fit_transform(corpus)
        return verify_result

    if kind == "zeta":
        variant = str(method_cfg.params.get("variant", "classic"))
        zeta_cls = _ZETA_VARIANTS.get(variant)
        if zeta_cls is None:
            raise ValueError(f"unknown zeta variant: {variant!r} (known: {sorted(_ZETA_VARIANTS)})")
        zeta_kwargs = {k: v for k, v in method_cfg.params.items() if k not in ("variant",)}
        zeta_kwargs.setdefault("top_k", 20)
        zeta_result: Result = zeta_cls(group_by=method_cfg.group_by, **zeta_kwargs).fit_transform(
            corpus
        )
        return zeta_result

    if kind == "reduce":
        feat_id = (
            method_cfg.features if isinstance(method_cfg.features, str) else method_cfg.features[0]
        )
        fm = features_by_id[feat_id]
        variant = str(method_cfg.params.get("variant", "pca"))
        cls = _REDUCER_VARIANTS.get(variant)
        if cls is None:
            raise ValueError(
                f"unknown reduce variant: {variant!r} (known: {sorted(_REDUCER_VARIANTS)})"
            )
        kwargs = {k: v for k, v in method_cfg.params.items() if k != "variant"}
        kwargs.setdefault("n_components", 2)
        result: Result = cls(**kwargs).fit_transform(fm)
        return result

    if kind == "cluster":
        feat_id = (
            method_cfg.features if isinstance(method_cfg.features, str) else method_cfg.features[0]
        )
        fm = features_by_id[feat_id]
        variant = str(method_cfg.params.get("variant", "hierarchical"))
        cluster_cls = _CLUSTER_VARIANTS.get(variant)
        if cluster_cls is None:
            raise ValueError(
                f"unknown cluster variant: {variant!r} (known: {sorted(_CLUSTER_VARIANTS)})"
            )
        kwargs = {k: v for k, v in method_cfg.params.items() if k != "variant"}
        cluster_result: Result = cluster_cls(**kwargs).fit_transform(fm)
        return cluster_result

    if kind == "consensus":
        return BootstrapConsensus(
            mfw_bands=method_cfg.params.get("mfw_bands", [100, 200, 300]),
            replicates=int(method_cfg.params.get("replicates", 20)),
        ).fit_transform(corpus)

    if kind == "bayesian":
        feat_id = (
            method_cfg.features if isinstance(method_cfg.features, str) else method_cfg.features[0]
        )
        fm = features_by_id[feat_id]
        y = np.array(corpus.metadata_column(method_cfg.group_by))
        clf = BayesianAuthorshipAttributor(
            prior_alpha=float(method_cfg.params.get("prior_alpha", 1.0))
        ).fit(fm, y)
        preds = clf.predict(fm)
        proba = clf.predict_proba(fm)
        return Result(
            method_name="bayesian_authorship",
            params=dict(method_cfg.params),
            values={
                "predictions": preds,
                "accuracy": float((preds == y).mean()),
                "proba": proba,
                "classes": clf.classes_,
                "document_ids": list(fm.document_ids),
            },
        )

    if kind == "classify":
        feat_id = (
            method_cfg.features if isinstance(method_cfg.features, str) else method_cfg.features[0]
        )
        fm = features_by_id[feat_id]
        y = np.array(corpus.metadata_column(method_cfg.group_by))
        cv_kind = method_cfg.cv.kind if method_cfg.cv else "stratified"
        groups: Any = None
        if cv_kind == "loao":
            groups_col = method_cfg.cv.groups_from if method_cfg.cv else None
            if not groups_col:
                raise ValueError(
                    f"method {method_cfg.id!r}: cv.kind='loao' requires cv.groups_from "
                    "(a metadata column naming the grouping unit, e.g. 'author')"
                )
            groups = np.array(corpus.metadata_column(groups_col))
        clf = build_classifier(method_cfg.params.get("estimator", "logreg"))
        report = cross_validate_bitig(
            clf,
            fm,
            y,
            cv_kind=cv_kind,
            groups_from=groups,
            seed=seed,
        )
        from bitig.metrics.calibration import brier_score, expected_calibration_error

        values: dict[str, Any] = {
            "accuracy": report["accuracy"],
            "predictions": report["predictions"],
            "y_true": y,
        }
        if report.get("proba") is not None and report.get("classes") is not None:
            values["proba"] = report["proba"]
            values["classes"] = report["classes"]
            try:
                values["ece"] = expected_calibration_error(
                    y, report["proba"], classes=report["classes"]
                )
                values["brier"] = brier_score(y, report["proba"], classes=report["classes"])
            except Exception as exc:
                _log.warning("calibration metrics failed: %s", exc)
        return Result(
            method_name=f"classify_{method_cfg.params.get('estimator', 'logreg')}",
            params=dict(method_cfg.params),
            values=values,
        )

    raise ValueError(f"runner does not support method kind: {kind!r}")


def _emit_default_plot(
    *,
    method_cfg: Any,
    method_dir: Path,
    result: Result,
    corpus: Any,
) -> None:
    """Render a sensible default figure for this method into method_dir."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from bitig.viz.mpl import (
            plot_bootstrap_consensus_tree,
            plot_confusion_matrix,
            plot_dendrogram,
            plot_feature_importance,
            plot_imposters_scores,
            plot_pca_biplot,
            plot_posterior_heatmap,
            plot_reliability_diagram,
            plot_rolling_delta,
            plot_scatter_2d,
            plot_zeta,
        )

        kind = method_cfg.kind
        groups: list[str] | None = None
        group_by = getattr(method_cfg, "group_by", None)
        if group_by:
            try:
                groups = [str(v) for v in corpus.metadata_column(group_by)]
            except Exception:
                groups = None

        fig = None
        png_name: str | None = None

        if kind == "reduce":
            coords = result.values.get("coordinates")
            doc_ids = result.values.get("document_ids")
            if coords is None:
                return
            arr = np.asarray(coords)
            if arr.ndim != 2 or arr.shape[1] < 2:
                return
            fig = plot_scatter_2d(
                arr,
                labels=list(doc_ids) if doc_ids else None,
                groups=groups,
                title=str(result.method_name),
            )
            png_name = "scatter.png"
            # Bonus: PCA biplot when loadings + feature_names are available.
            loadings = result.values.get("loadings")
            feature_names = result.values.get("feature_names")
            if loadings is not None and feature_names:
                try:
                    evr = result.values.get("explained_variance_ratio")
                    biplot_fig = plot_pca_biplot(
                        arr,
                        np.asarray(loadings),
                        list(feature_names),
                        labels=list(doc_ids) if doc_ids else None,
                        groups=groups,
                        explained_variance_ratio=np.asarray(evr) if evr is not None else None,
                        title=f"{result.method_name} biplot",
                    )
                    biplot_fig.savefig(method_dir / "pca_biplot.png", dpi=150, bbox_inches="tight")
                    plt.close(biplot_fig)
                except Exception as bp_exc:
                    _log.warning("PCA biplot failed for %s: %s", method_dir.name, bp_exc)

        elif kind == "cluster":
            linkage = result.values.get("linkage")
            doc_ids = result.values.get("document_ids")
            if linkage is None:
                return
            fig = plot_dendrogram(
                np.asarray(linkage),
                labels=list(doc_ids) if doc_ids else None,
                title=str(result.method_name),
            )
            png_name = "dendrogram.png"

        elif kind == "zeta" and len(result.tables) >= 2:
            fig = plot_zeta(
                result.tables[0],
                result.tables[1],
                label_a=str(result.values.get("group_a", "A")),
                label_b=str(result.values.get("group_b", "B")),
            )
            png_name = "zeta.png"

        elif kind == "rolling_delta" and result.tables:
            fig = plot_rolling_delta(result.tables[0], title=str(result.method_name))
            png_name = "rolling_delta.png"

        elif kind == "verify" and result.tables:
            fig = plot_imposters_scores(
                result.tables[0],
                threshold=float(result.values.get("threshold", 0.5)),
                title=str(result.method_name),
            )
            png_name = "imposters_scores.png"

        elif kind in ("delta", "bayesian"):
            preds = result.values.get("predictions")
            if preds is None or groups is None:
                return
            fig = plot_confusion_matrix(
                np.asarray(groups),
                np.asarray(preds),
                title=str(result.method_name),
            )
            png_name = "confusion_matrix.png"
            # Bonus for bayesian: posterior heatmap if the matrix is on values.
            if kind == "bayesian":
                proba = result.values.get("proba")
                classes = result.values.get("classes")
                doc_ids = result.values.get("document_ids")
                if proba is not None and classes is not None and doc_ids:
                    try:
                        post_fig = plot_posterior_heatmap(
                            np.asarray(proba),
                            [str(d) for d in doc_ids],
                            [str(c) for c in classes],
                            title=f"{result.method_name} posterior",
                        )
                        post_fig.savefig(
                            method_dir / "posterior_heatmap.png",
                            dpi=150,
                            bbox_inches="tight",
                        )
                        plt.close(post_fig)
                    except Exception as ph_exc:
                        _log.warning(
                            "posterior heatmap failed for %s: %s",
                            method_dir.name,
                            ph_exc,
                        )

        elif kind == "classify":
            preds = result.values.get("predictions")
            y_true = result.values.get("y_true")
            if preds is None or y_true is None:
                return
            fig = plot_confusion_matrix(
                np.asarray(y_true),
                np.asarray(preds),
                title=str(result.method_name),
            )
            png_name = "confusion_matrix.png"
            # Bonus: reliability diagram if y_proba is available.
            proba = result.values.get("proba")
            classes = result.values.get("classes")
            if proba is not None and classes is not None:
                try:
                    rel_fig = plot_reliability_diagram(
                        np.asarray(y_true),
                        np.asarray(proba),
                        classes=np.asarray(classes),
                        title=f"{result.method_name} reliability",
                    )
                    rel_fig.savefig(
                        method_dir / "reliability_diagram.png",
                        dpi=150,
                        bbox_inches="tight",
                    )
                    plt.close(rel_fig)
                except Exception as cal_exc:
                    _log.warning(
                        "reliability diagram failed for %s: %s",
                        method_dir.name,
                        cal_exc,
                    )

        elif kind == "consensus":
            support = result.values.get("support") or {}
            doc_ids = result.values.get("document_ids") or []
            if not support:
                return
            leaves = [str(d) for d in doc_ids]
            if len(leaves) >= 2:
                try:
                    fig = plot_bootstrap_consensus_tree(
                        {str(k): float(v) for k, v in support.items()},
                        leaves,
                    )
                    png_name = "consensus_tree.png"
                except Exception as bct_exc:
                    _log.warning(
                        "BCT plot failed for %s, falling back to clade-support bar chart: %s",
                        method_dir.name,
                        bct_exc,
                    )
            if fig is None:
                items = sorted(support.items(), key=lambda kv: kv[1], reverse=True)[:20]
                names = [k.replace(",", " · ") for k, _ in items]
                scores = np.asarray([v for _, v in items], dtype=float)
                fig = plot_feature_importance(
                    names,
                    scores,
                    top_n=len(names),
                    title="Bootstrap clade support",
                )
                png_name = "clade_support.png"

        if fig is not None and png_name is not None:
            fig.savefig(method_dir / png_name, dpi=150, bbox_inches="tight")
            plt.close(fig)
    except Exception as exc:
        _log.warning("could not emit default plot for %s: %s", method_dir.name, exc)
