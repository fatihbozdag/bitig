"""Forensic page — authorship verification (Unmasking / General Impostors),
topic-invariance distortion, and LR-framed reporting.

This page covers the clean subset of the ``bitig.forensic`` API that can be
driven end-to-end from directory paths and a single questioned file.
Calibration (``CalibratedScorer``) is not surfaced here because it requires
an external calibration trial set; use the Python API for that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nicegui import ui

from bitig.features import CharNgramExtractor, MFWExtractor
from bitig.forensic import GeneralImpostors, Unmasking, distort_corpus
from bitig.gui.background import io_bound
from bitig.gui.filepicker import is_native_available, pick_file, pick_folder
from bitig.gui.layout import page_shell
from bitig.gui.state import get_state
from bitig.io import load_corpus

_VERIFIERS = {
    "unmasking": "Unmasking (Koppel & Schler 2004) — accuracy-degradation curve",
    "impostors": "General Impostors (Koppel & Winter 2014) — needs an impostor-author pool",
}
_FEATURES_FOR_IMPOSTORS = {
    "mfw": "Most-frequent words (top 500)",
    "char_ngram": "Character 3-grams",
}
_DISTORTION_MODES = {
    "dv_ma": "DV-MA — preserve word length (mask each letter with *)",
    "dv_sa": "DV-SA — collapse each content word to a single *",
}


def _build_extractor(kind: str) -> Any:
    if kind == "mfw":
        return MFWExtractor(n=500)
    if kind == "char_ngram":
        return CharNgramExtractor(n=3)
    raise ValueError(f"unknown extractor kind {kind!r}")


@ui.page("/forensic")
def forensic_page() -> None:
    state = get_state()

    with page_shell("Forensic"):
        ui.markdown("### Authorship verification")
        ui.markdown(
            "Compare a **questioned** document against a candidate author's **known** "
            "documents and return a score. The questioned side is a single ``.txt`` file; "
            "the known side is a directory of the candidate's documents. Optionally apply "
            "Stamatatos distortion first to strip topic signal."
        )

        native = is_native_available()
        browse_hint = "Browse works only in native mode (without --no-native)."

        # --- Known (candidate author) corpus ---------------------------------
        with ui.row().classes("w-full items-end gap-2"):
            known_input = ui.input(
                label="Known-author corpus directory",
                placeholder="/path/to/known/",
            ).classes("flex-1")

            async def browse_known() -> None:
                chosen = await pick_folder("Select known-author corpus")
                if chosen:
                    known_input.value = chosen

            known_btn = ui.button("Browse folder", icon="folder_open", on_click=browse_known).props(
                "outline"
            )
            known_btn.set_enabled(native)
            if not native:
                known_btn.tooltip(browse_hint)

        # --- Questioned document file ----------------------------------------
        with ui.row().classes("w-full items-end gap-2"):
            questioned_input = ui.input(
                label="Questioned document (single .txt file)",
                placeholder="/path/to/questioned.txt",
            ).classes("flex-1")

            async def browse_questioned() -> None:
                chosen = await pick_file(
                    "Select questioned document",
                    file_types=("Text files (*.txt)", "All files (*.*)"),
                )
                if chosen:
                    questioned_input.value = chosen

            q_btn = ui.button("Browse file", icon="description", on_click=browse_questioned).props(
                "outline"
            )
            q_btn.set_enabled(native)
            if not native:
                q_btn.tooltip(browse_hint)

        # --- Optional: impostor pool (GI only) -------------------------------
        with ui.row().classes("w-full items-end gap-2"):
            impostors_input = ui.input(
                label="Impostor pool directory (only for General Impostors)",
                placeholder="/path/to/other-authors/",
            ).classes("flex-1")

            async def browse_impostors() -> None:
                chosen = await pick_folder("Select impostor-pool corpus")
                if chosen:
                    impostors_input.value = chosen

            imp_btn = ui.button(
                "Browse folder", icon="folder_open", on_click=browse_impostors
            ).props("outline")
            imp_btn.set_enabled(native)
            if not native:
                imp_btn.tooltip(browse_hint)

        # --- Distortion ------------------------------------------------------
        ui.markdown("### Topic-invariance distortion (optional)")
        distortion_switch = ui.switch("Apply Stamatatos distortion before verification")
        distortion_mode_select = ui.select(
            options=_DISTORTION_MODES, value="dv_ma", label="Distortion mode"
        ).classes("w-full")

        # --- Verifier --------------------------------------------------------
        ui.markdown("### Verifier")
        verifier_select = ui.select(options=_VERIFIERS, value="unmasking", label="Method").classes(
            "w-full"
        )
        feature_kind_select = ui.select(
            options=_FEATURES_FOR_IMPOSTORS,
            value="char_ngram",
            label="Feature space (for both verifiers)",
        ).classes("w-full")

        with ui.row().classes("gap-4 flex-wrap"):
            chunk_size_input = ui.number(
                label="Unmasking chunk_size (words)", value=500, min=100, max=5000
            ).classes("w-48")
            n_rounds_input = ui.number(label="Unmasking n_rounds", value=10, min=1, max=30).classes(
                "w-40"
            )
            gi_iter_input = ui.number(label="GI n_iterations", value=100, min=10, max=500).classes(
                "w-40"
            )

        # --- Run / output ----------------------------------------------------
        status = ui.markdown("")
        output = ui.markdown("")

        with ui.row().classes("gap-2 mt-2 items-center"):
            verify_btn = ui.button("Verify").props("color=primary")
            spinner = ui.spinner(size="lg").classes("hidden")

        async def do_verify() -> None:
            spinner.classes(remove="hidden")
            status.set_content("**running…**")
            output.set_content("")
            try:
                known_path = Path(known_input.value.strip()).expanduser()
                questioned_path = Path(questioned_input.value.strip()).expanduser()
                if not known_path.is_dir():
                    raise ValueError(f"known-author path {known_path} is not a directory")
                if not questioned_path.is_file():
                    raise ValueError(f"questioned path {questioned_path} is not a file")

                known = await io_bound(load_corpus, known_path, language=state.language)
                # Wrap the questioned .txt in a one-document corpus by staging
                # its parent dir is not safe; construct via load_corpus on the
                # parent and filter — simpler to just read the text and pass it.
                q_text = questioned_path.read_text(encoding="utf-8")

                if distortion_switch.value:
                    known = await io_bound(distort_corpus, known, mode=distortion_mode_select.value)
                    from bitig.forensic import distort_text

                    q_text = distort_text(q_text, mode=distortion_mode_select.value)

                verifier_kind = verifier_select.value
                if verifier_kind == "unmasking":
                    extractor = _build_extractor(feature_kind_select.value)
                    unmasking = Unmasking(
                        chunk_size=int(chunk_size_input.value),
                        n_rounds=int(n_rounds_input.value),
                        seed=42,
                    )
                    result = await io_bound(
                        unmasking.verify,
                        questioned=q_text,
                        known=known,
                        extractor=extractor,
                    )
                elif verifier_kind == "impostors":
                    impostors_path_str = impostors_input.value.strip()
                    if not impostors_path_str:
                        raise ValueError("General Impostors requires an impostor-pool directory")
                    impostors_path = Path(impostors_path_str).expanduser()
                    if not impostors_path.is_dir():
                        raise ValueError(f"impostor-pool path {impostors_path} is not a directory")
                    impostors_corpus = await io_bound(
                        load_corpus, impostors_path, language=state.language
                    )
                    if distortion_switch.value:
                        impostors_corpus = await io_bound(
                            distort_corpus,
                            impostors_corpus,
                            mode=distortion_mode_select.value,
                        )
                    extractor = _build_extractor(feature_kind_select.value)
                    # Build matrices: questioned needs to be a Corpus too.
                    from bitig.corpus import Corpus, Document

                    q_corpus = Corpus(
                        documents=[Document(id=questioned_path.stem, text=q_text)],
                        language=state.language,
                    )
                    fit_corpus = Corpus(
                        documents=[
                            *known.documents,
                            *impostors_corpus.documents,
                            *q_corpus.documents,
                        ],
                        language=state.language,
                    )
                    extractor.fit(fit_corpus)
                    q_fm = extractor.transform(q_corpus)
                    k_fm = extractor.transform(known)
                    i_fm = extractor.transform(impostors_corpus)
                    gi = GeneralImpostors(n_iterations=int(gi_iter_input.value), seed=42)
                    result = await io_bound(gi.verify, questioned=q_fm, known=k_fm, impostors=i_fm)
                else:  # pragma: no cover — select is bounded
                    raise ValueError(f"unknown verifier {verifier_kind!r}")
            except Exception as exc:
                spinner.classes(add="hidden")
                status.set_content(f"**failed:** {type(exc).__name__}: {exc}")
                return

            spinner.classes(add="hidden")
            status.set_content("**done.**")
            lines = [f"**method:** `{result.method_name}`"]
            scalars = {
                k: v
                for k, v in (result.values or {}).items()
                if isinstance(v, (int, float, str, bool))
            }
            for k, v in scalars.items():
                lines.append(f"- **{k}**: `{v}`")
            output.set_content("\n".join(lines) or "_(no scalar output)_")

        verify_btn.on_click(do_verify)

        ui.separator()
        ui.markdown(
            "_Calibration (Platt / isotonic via `CalibratedScorer`) requires an external "
            "calibration trial set and is not yet surfaced in the GUI — use the Python API "
            "for that workflow._"
        )
