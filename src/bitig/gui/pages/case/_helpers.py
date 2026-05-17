"""Pure helpers for the Case GUI — no NiceGUI imports.

Kept separate from the page modules so the logic here is unit-testable
without spinning up the GUI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bitig.cases import Case, CaseError
from bitig.gui.state import get_state
from bitig.result import Result


def resolve_case(case_id: str, cases_dir: Path | None = None) -> Case | None:
    """Return the Case for ``case_id`` under the GUI's cases_dir, or None."""
    state = get_state()
    root = cases_dir if cases_dir is not None else state.cases_dir
    try:
        return Case.load(root / case_id)
    except (CaseError, FileNotFoundError):
        return None


def short_hash(h: str, n: int = 12) -> str:
    """First ``n`` characters of a hash, with an ellipsis suffix."""
    return f"{h[:n]}…" if h else "—"


def latest_result_path(case: Case) -> Path | None:
    """Path to the latest run's ``result.json`` (if any).

    ``bitig.runner`` writes one subdirectory per method under
    ``runs/<run_id>/<method_id>/result.json``. There is no top-level
    ``result.json``; this helper walks the first (alphabetically sorted)
    method dir that has a ``result.json`` so single-method runs — the
    common Forensic Lab case — surface cleanly. Multi-method runs land
    on the first method; the Findings step's run-summary panel exposes
    a method picker for the rest.
    """
    if case.record.latest_run is None:
        return None
    run_dir = case.runs_dir / case.record.latest_run
    if not run_dir.is_dir():
        return None
    for method_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        candidate = method_dir / "result.json"
        if candidate.is_file():
            return candidate
    return None


def load_latest_result(case: Case) -> Result | None:
    """Convenience wrapper: load the latest run's Result, or None."""
    path = latest_result_path(case)
    if path is None:
        return None
    try:
        return Result.from_json(path)
    except Exception:
        return None


def headline_scalars(case: Case, result: Result | None) -> list[tuple[str, str]]:
    """Headline scalar row for the Findings step (spec §5.4).

    Forensic-mode cases surface LR / AUC / c@1 / C_llr; research-mode cases
    surface method-appropriate scalars (PCA: explained variance + n_features
    / n_docs; classification: accuracy / macro-F1 / ECE; others: a generic
    'samples / features' pair). Always returns 1-4 (label, value) pairs.
    """
    if result is None:
        return [("status", "no run yet")]

    if case.record.mode == "forensic":
        v = result.values
        out: list[tuple[str, str]] = []
        if "lr" in v:
            out.append(("LR", _fmt(v["lr"])))
        elif "log_lr" in v:
            out.append(("log LR", _fmt(v["log_lr"])))
        for key, label in (("auc", "AUC"), ("c_at_1", "c@1"), ("cllr", "C_llr")):
            if key in v:
                out.append((label, _fmt(v[key])))
        return out or [("score", _fmt(next(iter(v.values()), "—")))]

    # Research mode
    v = result.values
    method = result.method_name
    if method == "pca":
        evr = v.get("explained_variance_ratio")
        scalars: list[tuple[str, str]] = []
        if evr is not None and hasattr(evr, "__len__") and len(evr) >= 1:
            scalars.append(("PC1 var", _fmt(evr[0])))
            if len(evr) >= 2:
                scalars.append(("PC2 var", _fmt(evr[1])))
                scalars.append(("cum.", _fmt(sum(evr[:2]))))
        return scalars or [("status", "see figures")]
    if method in {"classify", "classification"}:
        out = []
        for key, label in (("accuracy", "accuracy"), ("macro_f1", "macro-F1"), ("ece", "ECE")):
            if key in v:
                out.append((label, _fmt(v[key])))
        return out or [("status", "see figures")]
    if method in {"bayesian", "bayes"} and "posterior_mode" in v:
        return [("posterior mode", str(v["posterior_mode"]))]
    return [("method", method)]


def _fmt(value: Any) -> str:
    """Compact numeric formatter — 3 sig figs, scientific for huge LRs."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if x == 0:
        return "0"
    if abs(x) >= 1e4 or abs(x) < 1e-3:
        return f"{x:.2e}"
    return f"{x:.3g}"


# Verbal-scale ladder for LR (Marquis et al. ENFSI 2016 recommendation).
LR_LADDER: list[tuple[str, float, float]] = [
    ("no support", 0.0, 1.0),
    ("weak support", 1.0, 10.0),
    ("moderate support", 10.0, 100.0),
    ("strong support", 100.0, 1000.0),
    ("very strong support", 1000.0, 10000.0),
    ("extremely strong support", 10000.0, float("inf")),
]


def lr_verbal_rung(lr: float) -> str:
    """Map an LR to a verbal scale (spec §5.5a)."""
    if lr <= 0:
        return "no support"
    for label, lo, hi in LR_LADDER:
        if lo <= lr < hi:
            return label
    return "extremely strong support"
