"""Pure helpers for the Case GUI — no NiceGUI imports.

The scalar derivation, result loading and LR verbal-scale logic now live in
shared, GUI-free modules (:mod:`bitig.report.scalars`,
:mod:`bitig.forensic.verbal_scale`) so the GUI Findings step and the report
renderer share ONE implementation (audit P1.11 + dedup). This module re-exports
them (plus a couple of GUI-only helpers) so existing imports keep working.
"""

from __future__ import annotations

from pathlib import Path

from bitig.cases import Case, CaseError
from bitig.forensic.verbal_scale import LR_LADDER, lr_verbal_rung
from bitig.gui.state import get_state
from bitig.report.scalars import headline_scalars as _headline_scalars
from bitig.report.scalars import latest_result_path, load_latest_result
from bitig.result import Result

__all__ = [
    "LR_LADDER",
    "headline_scalars",
    "latest_result_path",
    "load_latest_result",
    "lr_verbal_rung",
    "resolve_case",
    "short_hash",
]


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


def headline_scalars(case: Case, result: Result | None) -> list[tuple[str, str]]:
    """Findings headline row as ``(label, value)`` pairs (GUI view drops the
    is_primary flag the shared helper returns; the first entry is primary)."""
    return [(label, value) for label, value, _primary in _headline_scalars(case, result)]
