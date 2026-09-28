"""Study page — choose a feature + method and write a minimal study.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from nicegui import ui

from bitig.gui.filepicker import is_native_available, pick_save_path
from bitig.gui.layout import page_shell
from bitig.gui.state import get_state

_METHODS = {
    "delta": "Burrows Delta — nearest-author-centroid (small, known-author corpora)",
    "zeta": "Zeta — Craig distinctive-words contrast",
    "reduce": "PCA reduce — low-dim projection of a feature matrix",
    "cluster": "Hierarchical cluster — unsupervised grouping",
    "consensus": "Bootstrap consensus — stability across many MFW bands",
    "classify": "Classify (logreg) — cross-validated supervised",
    "bayesian": "Bayesian — Wallace-Mosteller-style authorship attribution",
}
_FEATURES = {
    "mfw": "Most-frequent words",
    "char_ngram": "Character n-grams",
    "word_ngram": "Word n-grams",
    "function_word": "Function words",
    "punctuation": "Punctuation rates",
    "lexical_diversity": "Lexical diversity (TTR, MATTR, MTLD)",
    "readability": "Readability indices (Flesch, Gunning-Fog, …)",
}
_METHODS_NEEDING_GROUP_BY = ("delta", "zeta", "classify", "bayesian")
_METHODS_NOT_USING_FEATURE = ("consensus",)

# Method-kind → {variant_id: label}. Consensus / classify / bayesian have no
# user-facing variants in the runner today, so they map to {} and the variant
# select is hidden.
_VARIANTS: dict[str, dict[str, str]] = {
    "delta": {
        "burrows": "Burrows (classic)",
        "cosine": "Cosine",
        "argamon_linear": "Argamon Linear (L2)",
        "quadratic": "Quadratic (L2²)",
        "eder": "Eder (rank-weighted)",
        "eder_simple": "Eder Simple (L1)",
    },
    "reduce": {
        "pca": "PCA",
        "mds": "MDS",
        "tsne": "t-SNE",
        "umap": "UMAP",
    },
    "cluster": {
        "hierarchical": "Hierarchical (Ward)",
        "kmeans": "KMeans",
        "hdbscan": "HDBSCAN",
    },
    "zeta": {
        "classic": "Classic (Craig)",
        "eder": "Eder",
    },
    "consensus": {},
    "classify": {},
    "bayesian": {},
}


@ui.page("/study")
def study_page() -> None:
    state = get_state()

    with page_shell("Study"):
        if state.corpus_path is None:
            ui.markdown("_No corpus loaded yet._ Go to **Ingest** and load a corpus first.")
            ui.button("← Ingest", on_click=lambda: ui.navigate.to("/ingest")).props("flat")
            return

        ui.markdown(
            f"**Corpus:** `{state.corpus_path}` ({state.corpus_doc_count} documents, "
            f"language: {state.language})"
        )

        ui.markdown("### 2. Configure a study")
        method_select = ui.select(options=_METHODS, value="delta", label="Method").classes("w-full")

        variant_options = _VARIANTS["delta"]
        variant_select = ui.select(
            options=variant_options,
            value=next(iter(variant_options)),
            label="Variant",
        ).classes("w-full")

        def _refresh_variant_options() -> None:
            opts = _VARIANTS.get(method_select.value, {})
            variant_select.options = opts
            variant_select.value = next(iter(opts), None)
            variant_select.set_visibility(bool(opts))
            variant_select.update()

        method_select.on_value_change(lambda _e: _refresh_variant_options())

        feature_select = ui.select(options=_FEATURES, value="mfw", label="Feature").classes(
            "w-full"
        )

        with ui.row().classes("gap-4 flex-wrap"):
            top_n_input = ui.number(label="MFW n (top words)", value=200, min=10, max=5000).classes(
                "w-40"
            )
            ngram_n_input = ui.number(label="n (n-gram length)", value=3, min=1, max=6).classes(
                "w-32"
            )
            n_clusters_input = ui.number(
                label="n_clusters (cluster)", value=2, min=2, max=20
            ).classes("w-40")
            n_components_input = ui.number(
                label="n_components (reduce)", value=2, min=2, max=10
            ).classes("w-40")
            top_k_input = ui.number(label="top_k (zeta)", value=20, min=5, max=200).classes("w-32")

        group_by_input = ui.input(
            label="Group-by metadata column (for delta / zeta / classify / bayesian)",
            value="author" if "author" in state.corpus_metadata_cols else "",
        ).classes("w-64")

        default_path = (
            (state.corpus_path.parent / "study.yaml") if state.corpus_path else Path("study.yaml")
        )
        with ui.row().classes("w-full items-end gap-2"):
            out_path_input = ui.input(
                label="Save study.yaml to",
                value=str(state.study_path or default_path),
            ).classes("flex-1")

            async def browse_save() -> None:
                chosen = await pick_save_path(
                    "Save study.yaml",
                    default_filename="study.yaml",
                    file_types=("YAML files (*.yaml;*.yml)", "All files (*.*)"),
                )
                if chosen:
                    out_path_input.value = chosen

            save_as_btn = ui.button("Save as…", icon="save", on_click=browse_save).props("outline")
            native_study = is_native_available()
            save_as_btn.set_enabled(native_study)
            if not native_study:
                save_as_btn.tooltip(
                    "Save-as dialog works only in native mode; type the path instead."
                )

        status = ui.markdown("")

        def save() -> None:
            feat_id = feature_select.value
            feat_type = feat_id
            feat_params: dict[str, object] = {}
            # MFW's "n" is top-n-words; n-grams' "n" is the gram length.
            # Other extractors (function_word, punctuation, lexical_diversity,
            # readability) run fine with their defaults.
            if feat_type == "mfw":
                feat_params["n"] = int(top_n_input.value)
            elif feat_type in ("char_ngram", "word_ngram"):
                feat_params["n"] = int(ngram_n_input.value)

            method_kind = method_select.value
            method_params: dict[str, object] = {}
            if _VARIANTS.get(method_kind) and variant_select.value:
                method_params["variant"] = variant_select.value
            method_cfg: dict[str, object] = {
                "id": f"{method_kind}_1",
                "kind": method_kind,
                "params": method_params,
            }
            if method_kind not in _METHODS_NOT_USING_FEATURE:
                method_cfg["features"] = feat_id
            if method_kind in _METHODS_NEEDING_GROUP_BY:
                if not group_by_input.value.strip():
                    status.set_content(
                        "**error:** `group_by` is required for delta / zeta / classify / bayesian."
                    )
                    return
                method_cfg["group_by"] = group_by_input.value.strip()
            if method_kind == "classify":
                method_params["estimator"] = "logreg"
            if method_kind == "cluster":
                # Only the params each clusterer accepts: the runner now rejects
                # unknown ones (k-means has no linkage; HDBSCAN no n_clusters).
                cluster_variant = method_params.get("variant", "hierarchical")
                if cluster_variant in {"hierarchical", "kmeans"}:
                    method_params["n_clusters"] = int(n_clusters_input.value)
                if cluster_variant == "hierarchical":
                    method_params["linkage"] = "ward"
            if method_kind == "reduce":
                method_params["n_components"] = int(n_components_input.value)
            if method_kind == "zeta":
                method_params["top_k"] = int(top_k_input.value)

            study = {
                "seed": 42,
                "preprocess": {"language": state.language, "spacy": {}},
                "corpus": {
                    "path": str(state.corpus_path),
                    **({"metadata": str(state.metadata_path)} if state.metadata_path else {}),
                },
                "features": [{"id": feat_id, "type": feat_type, "params": feat_params}],
                "methods": [method_cfg],
                "output": {"dir": "runs", "timestamp": True},
            }

            out_path = Path(out_path_input.value.strip()).expanduser()
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(yaml.safe_dump(study, sort_keys=False))
            except OSError as exc:
                status.set_content(f"**error:** {exc}")
                return
            state.study_path = out_path
            status.set_content(f"**saved:** `{out_path}`")

        with ui.row().classes("gap-2 mt-2"):
            ui.button("Save study.yaml", on_click=save).props("color=primary")
            ui.button(
                "Next: Run →",
                on_click=lambda: ui.navigate.to("/run"),
            ).props("flat")
