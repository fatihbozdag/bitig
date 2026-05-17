"""Shared mutable state for the GUI (single-user desktop app)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from bitig.cases import DEFAULT_CASES_DIR

PlotFormat = Literal["static", "interactive"]


@dataclass
class GuiState:
    corpus_path: Path | None = None
    metadata_path: Path | None = None
    language: str = "en"
    corpus_doc_count: int = 0
    corpus_metadata_cols: list[str] = field(default_factory=list)
    study_path: Path | None = None
    run_dir: Path | None = None
    plot_format: PlotFormat = "static"
    # Forensic Lab (spec §2). The GUI carries the *currently-open* Case id
    # plus the cases-root path so deep links into a step page survive page
    # reloads. Both default to None on a fresh GUI session.
    current_case_id: str | None = None
    cases_dir: Path = field(default_factory=lambda: DEFAULT_CASES_DIR)


_STATE: GuiState | None = None


def get_state() -> GuiState:
    global _STATE
    if _STATE is None:
        _STATE = GuiState()
    return _STATE


def reset_state() -> None:
    """Only used from tests."""
    global _STATE
    _STATE = None
