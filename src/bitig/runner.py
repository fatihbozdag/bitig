"""Config-driven orchestrator — executes all methods declared in a `study.yaml`."""

from __future__ import annotations

import inspect
import json
import shutil
import traceback
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import spacy

from bitig.config import StudyConfig, load_config
from bitig.corpus import Corpus
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


def _accepted_kwargs(cls: Any) -> set[str] | None:
    """Keyword names ``cls`` accepts, or ``None`` if it takes ``**kwargs``."""
    params = inspect.signature(cls).parameters.values()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return None
    return {p.name for p in params if p.name != "self"}


def _reducer_impl(variant: str) -> Any:
    cls = _REDUCER_VARIANTS.get(variant)
    if cls is None:
        return None
    if variant == "umap":
        try:
            import umap
        except ImportError:
            return None  # the run itself reports the missing extra
        return umap.UMAP
    return getattr(cls, "_impl", None)


def validate_study_params(cfg: StudyConfig) -> None:
    """Reject feature/method params the runner would ignore or crash on.

    Checked against the constructor signatures the runner actually calls, so a
    typo or a stale key fails loudly at load time instead of being silently
    dropped (audit 2026-09-26 N-P1.14). ``method:`` on a delta method is a
    deprecated alias for ``variant:`` and is translated with a warning.
    Mutates ``cfg`` only for that alias.
    """
    errors: list[str] = []
    for feat in cfg.features:
        extractor_cls = _FEATURE_BUILDERS.get(feat.type)
        if extractor_cls is None:
            errors.append(
                f"feature {feat.id!r}: type {feat.type!r} is not supported by `bitig run` "
                f"(supported: {sorted(_FEATURE_BUILDERS)})"
            )
            continue
        _check_keys(errors, f"feature {feat.id!r}", feat.params, _accepted_kwargs(extractor_cls))

    for method in cfg.methods:
        params = method.params
        kind = method.kind
        where = f"method {method.id!r} ({kind})"
        if kind == "delta" and "method" in params:
            if "variant" in params:
                errors.append(
                    f"{where}: give either 'variant' or the deprecated 'method', not both"
                )
            else:
                warnings.warn(
                    f"{where}: 'method:' is deprecated; use 'variant: {params['method']}'",
                    DeprecationWarning,
                    stacklevel=2,
                )
                params["variant"] = params.pop("method")
        allowed: set[str] | None
        if kind == "delta":
            allowed = {"variant"}
        elif kind == "rolling_delta":
            allowed = (_accepted_kwargs(RollingDelta) or set()) - {"group_by"}
        elif kind == "verify":
            allowed = (_accepted_kwargs(GeneralImposters) or set()) - {"group_by"}
        elif kind == "zeta":
            zeta_cls = _ZETA_VARIANTS.get(str(params.get("variant", "classic")), ZetaClassic)
            allowed = {"variant"} | ((_accepted_kwargs(zeta_cls) or set()) - {"group_by"})
        elif kind == "reduce":
            impl = _reducer_impl(str(params.get("variant", "pca")))
            impl_kwargs = _accepted_kwargs(impl) if impl is not None else None
            allowed = None if impl_kwargs is None else {"variant"} | impl_kwargs
        elif kind == "cluster":
            cluster_cls = _CLUSTER_VARIANTS.get(str(params.get("variant", "hierarchical")))
            cluster_kwargs = _accepted_kwargs(cluster_cls) if cluster_cls is not None else None
            allowed = None if cluster_kwargs is None else {"variant"} | cluster_kwargs
        elif kind == "consensus":
            allowed = _accepted_kwargs(BootstrapConsensus)
        elif kind == "bayesian":
            allowed = {"prior_alpha"}
        elif kind == "classify":
            allowed = {"estimator"}
        else:  # pragma: no cover - MethodKind is a closed Literal
            allowed = None
        _check_keys(errors, where, params, allowed)

    if errors:
        raise ValueError("invalid study configuration:\n  - " + "\n  - ".join(errors))


def _check_keys(
    errors: list[str], where: str, params: dict[str, Any], allowed: set[str] | None
) -> None:
    if allowed is None:
        return
    unknown = sorted(set(params) - allowed)
    if unknown:
        errors.append(f"{where}: unknown parameter(s) {unknown} (accepted: {sorted(allowed)})")


def _labelled_mask(labels: np.ndarray, group_by: str | None) -> np.ndarray:
    """Boolean mask of documents carrying a ``group_by`` label; at least two classes required."""
    if not group_by:
        raise ValueError("this method requires group_by (e.g. 'author')")
    mask = np.array([label is not None for label in labels], dtype=bool)
    n_classes = len(set(labels[mask]))
    if n_classes < 2:
        raise ValueError(
            f"need labelled documents from at least two {group_by!r} values; found {n_classes}"
        )
    return mask


def run_study(
    config_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    run_name: str | None = None,
    corpus: Corpus | None = None,
    overwrite: bool = False,
) -> Path:
    """Execute a full study from a `study.yaml` file and save all results.

    ``overwrite`` lets a run reuse a folder that holds a previous run, removing
    only that run's own outputs first; otherwise such a folder is refused, so
    stale method outputs never mix with new ones (audit 2026-09-26 P2).

    ``corpus`` supplies the documents directly instead of loading
    ``cfg.corpus.path`` (a Forensic Lab Case passes its registered,
    hash-checked evidence this way). ``cfg.corpus.filter`` still applies.

    Returns the path to the run directory (e.g., `results/2026-04-17T10-15-30/`).
    """
    cfg: StudyConfig = load_config(Path(config_path))
    validate_study_params(cfg)
    run_dir = _make_run_dir(cfg, output_dir, run_name, overwrite=overwrite)
    _log.info("run directory: %s", run_dir)

    if corpus is None:
        # The study language selects function-word lists, readability formulas
        # etc.; it defaulted to English here (audit 2026-09-26 N-P1.13).
        corpus = load_corpus(
            Path(cfg.corpus.path),
            metadata=Path(cfg.corpus.metadata) if cfg.corpus.metadata else None,
            language=cfg.preprocess.language,
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
        fm = extractor.fit_transform(corpus)
        bad = np.isnan(fm.X)
        if bad.any():
            rows, cols = np.nonzero(bad)
            cells = ", ".join(
                f"{fm.document_ids[r]}:{fm.feature_names[c]}"
                for r, c in zip(rows, cols, strict=True)
            )
            raise ValueError(
                f"feature {feat_cfg.id!r} has undefined (NaN) values for {cells}; drop those "
                "measures or documents (e.g. lexical-diversity indices need longer texts)"
            )
        features_by_id[feat_cfg.id] = fm
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
            result = _dispatch_method(
                method_cfg,
                corpus,
                features_by_id,
                seed=cfg.seed,
                feature_cfgs={f.id: f for f in cfg.features},
            )
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
            _log.error("method %s failed: %s", method_cfg.id, exc, exc_info=True)
            # Full traceback; its last line is "ExcType: message" (read by case_run).
            (method_dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")

    (run_dir / _RESOLVED_CONFIG).write_text(json.dumps(cfg.model_dump(), indent=2, default=str))
    return run_dir


_RESOLVED_CONFIG = "resolved_config.json"


def failed_methods(run_dir: Path) -> dict[str, str]:
    """``{method id: last line of its error.txt}`` for every failed method in a run."""
    out: dict[str, str] = {}
    for err in sorted(Path(run_dir).glob("*/error.txt")):
        lines = err.read_text(encoding="utf-8").strip().splitlines()
        out[err.parent.name] = lines[-1] if lines else "error"
    return out


def _previous_run_outputs(run_dir: Path, cfg: StudyConfig) -> list[Path]:
    """Outputs of an earlier bitig run in ``run_dir`` (method dirs + its config file)."""
    found: list[Path] = []
    previous_cfg = run_dir / _RESOLVED_CONFIG
    method_ids = {m.id for m in cfg.methods}
    if previous_cfg.is_file():
        found.append(previous_cfg)
        try:
            data = json.loads(previous_cfg.read_text(encoding="utf-8"))
            method_ids |= {str(m.get("id")) for m in data.get("methods", []) if m.get("id")}
        except (OSError, ValueError, AttributeError):
            pass
    for method_id in sorted(method_ids):
        path = run_dir / method_id
        # Only plain names directly under run_dir, and only folders bitig wrote.
        if (
            path.parent == run_dir
            and path.is_dir()
            and ((path / "result.json").exists() or (path / "error.txt").exists())
        ):
            found.append(path)
    return found


def _make_run_dir(
    cfg: StudyConfig,
    output_dir: str | Path | None,
    run_name: str | None,
    *,
    overwrite: bool = False,
) -> Path:
    base = Path(output_dir or cfg.output.dir)
    if run_name:
        run_dir = base / run_name
    elif cfg.output.timestamp:
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        run_dir, n = base / stamp, 2
        while run_dir.exists():  # two runs in the same second
            run_dir, n = base / f"{stamp}-{n}", n + 1
    else:
        run_dir = base
    previous = _previous_run_outputs(run_dir, cfg) if run_dir.is_dir() else []
    if previous:
        if not overwrite:
            raise FileExistsError(
                f"{run_dir} already holds a previous run ({', '.join(p.name for p in previous)}); "
                "use a new --name / timestamped output, or pass overwrite=True "
                "(`bitig run --overwrite`) to replace that run's outputs"
            )
        for path in previous:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _dispatch_method(
    method_cfg: Any,
    corpus: Any,
    features_by_id: dict[str, FeatureMatrix],
    *,
    seed: int,
    feature_cfgs: dict[str, Any] | None = None,
) -> Result:
    kind = method_cfg.kind

    if kind == "delta":
        feat_id = (
            method_cfg.features if isinstance(method_cfg.features, str) else method_cfg.features[0]
        )
        fm = features_by_id[feat_id]
        y_all = np.array(corpus.metadata_column(method_cfg.group_by), dtype=object)
        labelled = _labelled_mask(y_all, method_cfg.group_by)
        y = y_all[labelled]
        variant = str(method_cfg.params.get("variant", "burrows"))
        cls = _DELTA_VARIANTS.get(variant)
        if cls is None:
            raise ValueError(
                f"unknown delta variant: {variant!r} (known: {sorted(_DELTA_VARIANTS)})"
            )
        # Centroids come from the labelled documents only; documents without
        # a label (e.g. questioned texts) are attributed, never trained on.
        clf = cls().fit(fm.X[labelled], y)
        all_preds = clf.predict(fm)
        preds = all_preds[labelled]
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
                "attributions": {
                    doc_id: str(pred)
                    for doc_id, pred, is_lab in zip(
                        fm.document_ids, all_preds, labelled, strict=True
                    )
                    if not is_lab
                },
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
        # Zeta contrasts labelled groups; unlabelled documents take no part.
        labelled_corpus = Corpus(
            documents=[
                d for d in corpus.documents if d.metadata.get(str(method_cfg.group_by)) is not None
            ],
            language=corpus.language,
        )
        zeta_result: Result = zeta_cls(group_by=method_cfg.group_by, **zeta_kwargs).fit_transform(
            labelled_corpus
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
        # Every reducer is stochastic or solver-seeded; thread the study seed
        # (audit 2026-09-26 N-P1.15).
        kwargs.setdefault("random_state", seed)
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
        if cluster_cls is KMeansCluster:
            kwargs.setdefault("random_state", seed)
        cluster_result: Result = cluster_cls(**kwargs).fit_transform(fm)
        return cluster_result

    if kind == "consensus":
        consensus_kwargs = dict(method_cfg.params)
        consensus_kwargs.setdefault("mfw_bands", [100, 200, 300])
        consensus_kwargs.setdefault("replicates", 20)
        consensus_kwargs.setdefault("seed", seed)
        return BootstrapConsensus(**consensus_kwargs).fit_transform(corpus)

    if kind == "bayesian":
        feat_id = (
            method_cfg.features if isinstance(method_cfg.features, str) else method_cfg.features[0]
        )
        fm = features_by_id[feat_id]
        y_all = np.array(corpus.metadata_column(method_cfg.group_by), dtype=object)
        labelled = _labelled_mask(y_all, method_cfg.group_by)
        y = y_all[labelled]
        clf = BayesianAuthorshipAttributor(
            prior_alpha=float(method_cfg.params.get("prior_alpha", 1.0))
        ).fit(fm.X[labelled], y)
        preds = clf.predict(fm)
        proba = clf.predict_proba(fm)
        return Result(
            method_name="bayesian_authorship",
            params=dict(method_cfg.params),
            values={
                "predictions": preds,
                # In-sample, like the delta branch: a separability diagnostic, not a
                # held-out estimate (audit 2026-09-26 P2).
                "resubstitution_accuracy": float((preds[labelled] == y).mean()),
                "evaluation": "resubstitution (in-sample); use kind: classify for held-out CV",
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
        clf = build_classifier(method_cfg.params.get("estimator", "logreg"), random_state=seed)
        # Refit the feature extractor inside each training fold so held-out
        # documents never shape the vocabulary or z-scores (audit 2026-09-26 P2).
        feat_cfg = (feature_cfgs or {}).get(feat_id)
        extractor = (
            _FEATURE_BUILDERS[feat_cfg.type](**feat_cfg.params) if feat_cfg is not None else None
        )
        report = cross_validate_bitig(
            clf,
            None if extractor is not None else fm,
            y,
            cv_kind=cv_kind,
            groups_from=groups,
            seed=seed,
            extractor=extractor,
            corpus=corpus if extractor is not None else None,
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
