"""Shared Findings/report scalar derivation + run-result loading.

One implementation used by BOTH the GUI Findings step
(:mod:`bitig.gui.pages.case._helpers`) and the report renderer
(:mod:`bitig.report.case_report`). They previously carried divergent copies of
the latest-result loader and the headline-scalar logic; the copies drifted,
which is how the verbal-rung bug (audit P1.11) shipped. This module is the
single source. It has no GUI dependency, so the report layer can import it
without pulling in NiceGUI.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from bitig.cases import Case
from bitig.forensic.verbal_scale import lr_from_values
from bitig.result import Result


def fmt_scalar(value: Any) -> str:
    """Compact numeric formatter — 3 sig figs, scientific for huge/tiny LRs."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(x):
        return "—"
    if x == 0:
        return "0"
    if abs(x) >= 1e4 or abs(x) < 1e-3:
        return f"{x:.2e}"
    return f"{x:.3g}"


def latest_result_path(case: Case) -> Path | None:
    """Path to the latest run's headline ``result.json``.

    ``bitig.runner`` writes ``runs/<run_id>/<method_id>/result.json`` (no
    top-level result.json). A forensic case reports its ``verify`` method,
    chosen by kind from the study rather than by directory name (audit
    2026-09-26 N-P1.9); otherwise the first method dir (sorted) is used.
    """
    if case.record.latest_run is None:
        return None
    run_dir = case.runs_dir / case.record.latest_run
    if not run_dir.is_dir():
        return None
    if case.record.mode == "forensic":
        try:
            methods = case.resolved_study_dict().get("methods") or []
        except Exception:
            methods = []
        for method in methods:
            if isinstance(method, dict) and method.get("kind") == "verify":
                candidate = run_dir / str(method.get("id")) / "result.json"
                if candidate.is_file():
                    return candidate
    for method_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        candidate = method_dir / "result.json"
        if candidate.is_file():
            return candidate
    return None


def load_latest_result(case: Case) -> Result | None:
    """Load the latest run's Result, or ``None`` (malformed/mid-run → None)."""
    path = latest_result_path(case)
    if path is None:
        return None
    try:
        return Result.from_json(path)
    except Exception:
        return None


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def gi_scores(values: dict[str, Any]) -> list[tuple[str, float]]:
    """Per-questioned-document General Impostors scores as ``(doc_id, score)``.

    ``GeneralImposters`` keys ``scores`` by target document id. Each score is
    the candidate's win-fraction in [0, 1] — NOT a likelihood ratio; callers
    must label it honestly and never feed it to the LR verbal ladder (P1.10).
    """
    scores = values.get("scores")
    if not isinstance(scores, dict):
        return []
    return [(str(k), float(v)) for k, v in sorted(scores.items()) if _is_number(v)]


def gi_score(values: dict[str, Any]) -> float | None:
    """The single GI score when exactly one document was verified, else ``None``.

    Several questioned documents are never collapsed into one number: taking
    the maximum overstated the evidence (audit 2026-09-26 N-P1.9).
    """
    rows = gi_scores(values)
    return rows[0][1] if len(rows) == 1 else None


def headline_scalars(case: Case, result: Result | None) -> list[tuple[str, str, bool]]:
    """Headline scalar row as ``(label, value, is_primary)`` (spec §5.4).

    Forensic mode surfaces LR / AUC / c@1 / C_llr when a calibrated LR exists;
    otherwise the General Impostors verification score (labelled "GI score",
    never the candidate's name — audit P1.10a). Research mode surfaces
    method-appropriate scalars. Always returns at least one entry.
    """
    if result is None:
        return [("status", "no run yet", True)]

    v = result.values
    if case.record.mode == "forensic":
        return _forensic_scalars(v)
    return _research_scalars(result.method_name, v)


def _forensic_scalars(v: dict[str, Any]) -> list[tuple[str, str, bool]]:
    out: list[tuple[str, str, bool]] = []
    lr = lr_from_values(v)
    if lr is not None:
        out.append(("LR", fmt_scalar(lr), True))
    for key, label in (("auc", "AUC"), ("c_at_1", "c@1"), ("cllr", "C_llr")):
        if key in v:
            out.append((label, fmt_scalar(v[key]), False))
    if out:
        return out
    # No calibrated LR — surface the GI verification score, never a name/string,
    # and never an aggregate over several questioned documents.
    rows = gi_scores(v)
    if rows:
        chance = v.get("chance")
        chance_cell = [("chance level", fmt_scalar(chance), False)] if _is_number(chance) else []
        if len(rows) == 1:
            return [("GI score", fmt_scalar(rows[0][1]), True), *chance_cell]
        return [("GI score", f"{len(rows)} documents — see per-document table", True), *chance_cell]
    return [("status", "no scalar result", True)]


def _research_scalars(method: str, v: dict[str, Any]) -> list[tuple[str, str, bool]]:
    if method == "pca":
        evr = v.get("explained_variance_ratio")
        if evr is not None and hasattr(evr, "__len__") and len(evr) >= 1:
            scalars = [("PC1 var", fmt_scalar(evr[0]), True)]
            if len(evr) >= 2:
                scalars.append(("PC2 var", fmt_scalar(evr[1]), False))
                scalars.append(("cum.", fmt_scalar(sum(evr[:2])), False))
            return scalars
    # The runner names these classify_<estimator> and bayesian_authorship; exact
    # matching never fired (audit 2026-09-26 P3).
    if method.startswith("classify") or method == "classification":
        out: list[tuple[str, str, bool]] = []
        for key, label in (("accuracy", "CV accuracy"), ("macro_f1", "macro-F1"), ("ece", "ECE")):
            if key in v:
                out.append((label, fmt_scalar(v[key]), not out))
        if out:
            return out
    if method.startswith(("bayesian", "bayes")):
        if "resubstitution_accuracy" in v:
            return [("resubstitution accuracy", fmt_scalar(v["resubstitution_accuracy"]), True)]
        if "posterior_mode" in v:
            return [("posterior mode", str(v["posterior_mode"]), True)]
    return [("method", method, True)]


__all__ = [
    "fmt_scalar",
    "gi_score",
    "gi_scores",
    "headline_scalars",
    "latest_result_path",
    "load_latest_result",
]
