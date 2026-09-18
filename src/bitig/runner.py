"""Config-driven orchestrator — executes all methods declared in a `study.yaml`."""

from __future__ import annotations

import inspect
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import spacy

from bitig.config import StudyConfig, load_config
from bitig.corpus import Corpus, Document
from bitig.features import (
    CharNgramExtractor,
    DependencyBigramExtractor,
    FeatureMatrix,
    FunctionWordExtractor,
    LexicalDiversityExtractor,
    MFWExtractor,
    PosNgramExtractor,
    PunctuationExtractor,
    ReadabilityExtractor,
    SentenceLengthExtractor,
    WordNgramExtractor,
)
from bitig.features.base import BaseFeatureExtractor
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
    "pos_ngram": PosNgramExtractor,
    "dependency_bigram": DependencyBigramExtractor,
    "sentence_length": SentenceLengthExtractor,
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


@dataclass
class StudyRunStatus:
    directory: Path
    methods: dict[str, str | None]
    report_error: str | None = None

    @property
    def status(self) -> str:
        successes = sum(error is None for error in self.methods.values())
        return (
            "failed"
            if not successes
            else "succeeded"
            if successes == len(self.methods) and self.report_error is None
            else "partial"
        )

    @classmethod
    def load(cls, directory: Path) -> StudyRunStatus:
        data = json.loads((directory / "run_status.json").read_text())
        return cls(directory, data["methods"], data.get("report_error"))


def _prepare_config(cfg: StudyConfig) -> None:
    """Resolve supported aliases/defaults and reject ineffective settings before execution."""
    if cfg.preprocess.normalize.expand_contractions:
        raise ValueError("expand_contractions is not supported; supply pre-normalized text")
    if cfg.preprocess.spacy.device not in ("auto", "cpu"):
        raise ValueError("runner spaCy device supports auto/cpu only")
    for items in (cfg.features, cfg.methods):
        ids = [item.id for item in items]
        if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids):
            raise ValueError("feature/method IDs must be unique safe names (letters, digits, _, -)")
    feature_ids = {f.id for f in cfg.features}
    for feat in cfg.features:
        if feat.type not in _FEATURE_BUILDERS:
            raise ValueError(f"feature type {feat.type!r} is not supported by the runner")
        if "top_n" in feat.params:
            if feat.type != "mfw":
                raise ValueError(f"top_n is unsupported for {feat.type}; remove it")
            feat.params["n"] = feat.params.pop("top_n")
    for method in cfg.methods:
        refs = [method.features] if isinstance(method.features, str) else method.features or []
        if set(refs) - feature_ids:
            raise ValueError(f"method {method.id}: unknown feature references {refs}")
        if len(refs) > 1:
            raise ValueError(f"method {method.id}: multiple feature inputs are not supported")
        if refs and method.kind in ("rolling_delta", "verify", "zeta", "consensus"):
            raise ValueError(
                f"method {method.id}: {method.kind} extracts its own features; remove features"
            )
        if method.kind in ("delta", "reduce", "cluster", "bayesian", "classify") and not refs:
            raise ValueError(f"method {method.id}: a feature reference is required")
        if (
            method.kind in ("delta", "bayesian", "classify", "zeta", "verify", "rolling_delta")
            and not method.group_by
        ):
            raise ValueError(f"method {method.id}: group_by is required")
        if method.cv is not None and method.kind not in ("classify", "bayesian"):
            raise ValueError(f"method {method.id}: cv is only supported for classify/bayesian")
        if method.cv and method.cv.kind in ("loao", "group_kfold") and not method.cv.groups_from:
            raise ValueError(f"method {method.id}: grouped CV requires groups_from")
        if (
            method.cv
            and method.cv.kind in ("loao", "leave_one_text_out")
            and method.cv.folds is not None
        ):
            raise ValueError(f"method {method.id}: folds is not applicable to {method.cv.kind}")
        params = method.params
        if method.kind in ("delta", "reduce", "cluster", "zeta"):
            for alias in ("method", "algorithm"):
                if alias in params:
                    if "variant" in params and params["variant"] != params[alias]:
                        raise ValueError("conflicting method/algorithm and variant")
                    params["variant"] = params.pop(alias)
            if params.get("variant") == "craig":
                params["variant"] = "classic"
        if method.kind == "classify":
            name = params.get("estimator", "logreg")
            effective = {k: v for k, v in params.items() if k != "estimator"}
            if effective.get("random_state") is None:
                effective["random_state"] = cfg.seed
            clf = build_classifier(name, **effective)
            method.params = {"estimator": name, **clf.get_params()}
            # Kernel/probability are fixed by the named SVM factory.
            for key in ("kernel", "probability"):
                if name.startswith("svm_"):
                    method.params.pop(key, None)
        elif method.kind == "bayesian":
            inspect.signature(BayesianAuthorshipAttributor).bind(**params)
        elif method.kind == "delta":
            unknown = set(params) - {"variant"}
            if unknown or params.get("variant", "burrows") not in _DELTA_VARIANTS:
                raise ValueError(f"invalid delta parameters: {params}")
        elif method.kind in ("reduce", "cluster"):
            registry = _REDUCER_VARIANTS if method.kind == "reduce" else _CLUSTER_VARIANTS
            variant = params.get("variant", "pca" if method.kind == "reduce" else "hierarchical")
            if variant not in registry:
                raise ValueError(f"unsupported variant {variant!r}")
            if method.kind == "reduce" or variant == "kmeans":
                params.setdefault("random_state", cfg.seed)
            kwargs = {k: v for k, v in params.items() if k != "variant"}
            instance = registry[variant](**kwargs)
            if method.kind == "reduce":
                instance._impl(**kwargs)
        elif method.kind == "consensus":
            params.setdefault("mfw_bands", [100, 200, 300])
            params.setdefault("replicates", 20)
            params.setdefault("seed", cfg.seed)
            inspect.signature(BootstrapConsensus).bind(**params)
        elif method.kind in ("verify", "rolling_delta"):
            params.setdefault("seed", cfg.seed) if method.kind == "verify" else None
            cls = GeneralImposters if method.kind == "verify" else RollingDelta
            inspect.signature(cls).bind(group_by=method.group_by, **params)
        elif method.kind == "zeta":
            variant = params.get("variant", "classic")
            if variant not in _ZETA_VARIANTS:
                raise ValueError(f"unsupported zeta variant {variant!r}")
            inspect.signature(_ZETA_VARIANTS[variant]).bind(
                group_by=method.group_by, **{k: v for k, v in params.items() if k != "variant"}
            )
    if cfg.report.include != ["corpus", "config", "provenance", "results"]:
        raise ValueError("custom report.include is not supported")


def _normalize_corpus(corpus: Corpus, cfg: StudyConfig) -> Corpus:
    norm = cfg.preprocess.normalize
    docs = []
    for doc in corpus:
        text = doc.text
        if norm.lowercase:
            from bitig.plumbing.textnorm import fold_lower

            text = fold_lower(text)
        if norm.strip_punct:
            text = "".join(" " if unicodedata.category(c).startswith("P") else c for c in text)
        if norm.collapse_numerals:
            text = re.sub(r"\d+", "0", text)
        docs.append(Document(doc.id, text, dict(doc.metadata)))
    return Corpus(docs, language=corpus.language)


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
    _prepare_config(cfg)

    corpus = load_corpus(
        Path(cfg.corpus.path),
        metadata=Path(cfg.corpus.metadata) if cfg.corpus.metadata else None,
        language=cfg.preprocess.language,
    )
    if cfg.corpus.filter:
        corpus = corpus.filter(**cfg.corpus.filter)
    _log.info("loaded %d documents", len(corpus))

    corpus = _normalize_corpus(corpus, cfg)
    if cfg.preprocess.spacy.device == "cpu":
        spacy.require_cpu()
    pipe = SpacyPipeline(
        language=cfg.preprocess.language,
        model=cfg.preprocess.spacy.model,
        backend=cfg.preprocess.spacy.backend,
        exclude=list(cfg.preprocess.spacy.exclude),
        cache_dir=Path(cfg.cache.dir) / "docbin",
        reuse_cache=cfg.cache.reuse,
    )
    if pipe.backend == "spacy_stanza" and pipe.exclude:
        raise ValueError("spaCy component exclusions are not supported by the Stanza backend")
    extractors: dict[str, BaseFeatureExtractor] = {}
    for feat_cfg in cfg.features:
        extractor_cls = _FEATURE_BUILDERS[feat_cfg.type]
        params = dict(feat_cfg.params)
        if feat_cfg.type in ("pos_ngram", "dependency_bigram", "sentence_length"):
            params.setdefault("spacy_model", pipe.model)
            params.setdefault("cache_dir", str(Path(cfg.cache.dir) / "docbin"))
        extractor = extractor_cls(**params)
        if hasattr(extractor, "_pipeline"):
            extractor._pipeline = SpacyPipeline(
                language=cfg.preprocess.language,
                model=params["spacy_model"],
                backend=cfg.preprocess.spacy.backend,
                exclude=list(cfg.preprocess.spacy.exclude),
                cache_dir=params["cache_dir"],
                reuse_cache=cfg.cache.reuse,
            )
        feat_cfg.params = extractor.get_params()
        extractors[feat_cfg.id] = extractor
    run_dir = _make_run_dir(cfg, output_dir, run_name)
    _log.info("run directory: %s", run_dir)
    features_by_id: dict[str, FeatureMatrix] = {}
    outcomes: dict[str, str | None] = {}

    # Execute each method.
    for method_cfg in cfg.methods:
        method_dir = run_dir / method_cfg.id
        method_dir.mkdir(parents=True, exist_ok=True)
        try:
            refs = (
                [method_cfg.features]
                if isinstance(method_cfg.features, str)
                else method_cfg.features or []
            )
            uses_cv = method_cfg.kind == "classify" or (
                method_cfg.kind == "bayesian" and method_cfg.cv is not None
            )
            if not uses_cv:
                for ref in refs:
                    if ref not in features_by_id:
                        from copy import deepcopy

                        features_by_id[ref] = deepcopy(extractors[ref]).fit_transform(corpus)
            result = _dispatch_method(
                method_cfg, corpus, features_by_id, seed=cfg.seed, extractors=extractors
            )
            # Derive feature_hash from the primary feature id used by this method (if any).
            feat_hash: str | None = None
            features_attr = getattr(method_cfg, "features", None)
            if uses_cv:
                from bitig.plumbing.hashing import hash_mapping

                feat_hash = hash_mapping({"folds": result.values["folds"]})
            elif features_attr:
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
            import matplotlib.pyplot as plt

            from bitig.viz.style import apply_publication_style

            with plt.style.context(cfg.viz.style), plt.rc_context():
                apply_publication_style(dpi=cfg.viz.dpi, palette=cfg.viz.palette)
                _emit_default_plot(
                    method_cfg=method_cfg,
                    method_dir=method_dir,
                    result=result,
                    corpus=corpus,
                    viz=cfg.viz,
                )
            outcomes[method_cfg.id] = None
        except Exception as exc:
            _log.error("method %s failed: %s", method_cfg.id, exc)
            (method_dir / "error.txt").write_text(str(exc))
            outcomes[method_cfg.id] = f"{type(exc).__name__}: {exc}"

    (run_dir / "resolved_config.json").write_text(
        json.dumps(cfg.model_dump(), indent=2, default=str)
    )
    status = StudyRunStatus(run_dir, outcomes)
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": status.status, "methods": outcomes}, indent=2)
    )
    if cfg.report.format != "none":
        from bitig.report.render import build_report

        try:
            build_report(
                run_dir,
                output=run_dir / f"report.{cfg.report.format}",
                format=cfg.report.format,
                title=cfg.report.title or cfg.name,
                corpus_summary={"documents": len(corpus), "language": corpus.language},
            )
        except Exception as exc:
            status.report_error = f"{type(exc).__name__}: {exc}"
            _log.error("report failed: %s", exc)
            (run_dir / "run_status.json").write_text(
                json.dumps(
                    {
                        "status": status.status,
                        "methods": outcomes,
                        "report_error": status.report_error,
                    },
                    indent=2,
                )
            )
    return run_dir


def _make_run_dir(cfg: StudyConfig, output_dir: str | Path | None, run_name: str | None) -> Path:
    base = Path(output_dir or cfg.output.dir)
    if run_name:
        if Path(run_name).name != run_name or run_name in (".", ".."):
            raise ValueError("run_name must be a single directory name")
        run_dir = base / run_name
    elif cfg.output.timestamp:
        run_dir = base / datetime.now().strftime("%Y-%m-%dT%H-%M-%S-%f")
    else:
        run_dir = base
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _dispatch_method(
    method_cfg: Any,
    corpus: Any,
    features_by_id: dict[str, FeatureMatrix],
    *,
    seed: int,
    extractors: dict[str, BaseFeatureExtractor] | None = None,
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
        # vocabulary and z-score statistics; feature references are rejected.
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
        return BootstrapConsensus(**method_cfg.params).fit_transform(corpus)

    if kind == "bayesian" and method_cfg.cv is None:
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
                "resubstitution_accuracy": float((preds == y).mean()),
                "evaluation": "resubstitution (in-sample)",
                "proba": proba,
                "classes": clf.classes_,
                "document_ids": list(fm.document_ids),
            },
        )

    if kind in ("classify", "bayesian"):
        feat_id = (
            method_cfg.features if isinstance(method_cfg.features, str) else method_cfg.features[0]
        )
        y = np.array(corpus.metadata_column(method_cfg.group_by))
        cv_kind = method_cfg.cv.kind if method_cfg.cv else "stratified"
        groups: Any = None
        if cv_kind in ("loao", "group_kfold"):
            groups_col = method_cfg.cv.groups_from if method_cfg.cv else None
            if not groups_col:
                raise ValueError(
                    f"method {method_cfg.id!r}: cv.kind='loao' requires cv.groups_from "
                    "(a metadata column naming the grouping unit, e.g. 'author')"
                )
            groups = np.array(corpus.metadata_column(groups_col))
        params = dict(method_cfg.params)
        estimator_name = params.pop("estimator", "logreg")
        clf = (
            BayesianAuthorshipAttributor(**params)
            if kind == "bayesian"
            else build_classifier(estimator_name, **params)
        )
        if extractors is None:
            raise ValueError("classifier evaluation requires unfitted feature extractors")
        report = cross_validate_bitig(
            clf,
            corpus,
            y,
            extractor=extractors[feat_id],
            folds=method_cfg.cv.folds if method_cfg.cv else None,
            cv_kind=cv_kind,
            groups_from=groups,
            seed=seed,
        )
        from bitig.metrics.calibration import brier_score, expected_calibration_error

        values: dict[str, Any] = {
            "accuracy": report["accuracy"],
            "predictions": report["predictions"],
            "y_true": y,
            "document_ids": [d.id for d in corpus],
            "evaluation": report["evaluation"],
            "fold_ids": report["fold_ids"],
            "folds": report["folds"],
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
            method_name="bayesian_authorship_cv"
            if kind == "bayesian"
            else f"classify_{estimator_name}",
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
    viz: Any = None,
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

        def save_plot(figure: Any, name: str) -> None:
            formats = viz.format if viz is not None else ["png"]
            dpi = viz.dpi if viz is not None else 150
            for extension in formats:
                figure.savefig(
                    method_dir / f"{Path(name).stem}.{extension}", dpi=dpi, bbox_inches="tight"
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
                    save_plot(biplot_fig, "pca_biplot.png")
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
            if kind == "bayesian" and method_cfg.cv is None:
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
                        save_plot(post_fig, "posterior_heatmap.png")
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
                    save_plot(rel_fig, "reliability_diagram.png")
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
            save_plot(fig, png_name)
            plt.close(fig)
    except Exception as exc:
        _log.warning("could not emit default plot for %s: %s", method_dir.name, exc)
