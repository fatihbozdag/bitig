"""Pydantic ReportContext model — input to the case-report Jinja templates.

The two layouts (forensic vs research, spec §5.5) share most fields and
diverge in a few mode-specific ones. Keeping the model unified means
``build_case_report`` only varies the template path, not the rendering
pipeline. Optional fields stay ``None`` when the active layout doesn't
need them — templates check ``{% if field %}`` rather than introspecting
on ``mode``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

Mode = Literal["forensic", "research"]
EvidenceRole = Literal["questioned", "known", "control"]


class HeadlineScalar(BaseModel):
    """One row in the headline scalar strip (spec §5.4 / §5.5)."""

    model_config = _STRICT
    label: str
    value: str
    is_primary: bool = False


class ChainOfCustodyEntry(BaseModel):
    """One row of the chain-of-custody table."""

    model_config = _STRICT
    role: EvidenceRole
    label: str  # filename for questioned/known, corpus_id for control
    tokens: int | None = None
    sha256: str | None = None
    n_docs: int | None = None  # control corpus only


class ProvenanceFooter(BaseModel):
    """Provenance row at the bottom of every report (spec §5.5a footer)."""

    model_config = _STRICT
    corpus_hash: str
    feature_hash: str | None = None
    study_hash: str
    seed: int
    bitig_version: str
    spacy_model: str


class ReportContext(BaseModel):
    """Everything the forensic/research Jinja templates render."""

    model_config = _STRICT

    # ---- common ----
    mode: Mode
    title: str
    case_id: str
    examiner: str
    date_iso: str
    bitig_version: str
    case_state_hash: str

    headline_scalars: list[HeadlineScalar] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
    chain_of_custody: list[ChainOfCustodyEntry] = Field(default_factory=list)
    provenance: ProvenanceFooter | None = None

    signed: bool = False
    signed_at: str | None = None
    signed_by: str | None = None

    # ---- forensic-only ----
    hypothesis_p: str | None = None
    hypothesis_d: str | None = None
    lr_value: str | None = None  # formatted LR for display; None when no calibrated LR
    lr_verbal_rung: str | None = None  # classified from the RAW LR float, not lr_value
    lr_ladder_rows: list[tuple[str, str, str]] = Field(default_factory=list)
    method_paragraph: str | None = None

    # ---- research-only ----
    research_question: str | None = None
    hypothesis: str | None = None
    methods_paragraph: str | None = None
    data_availability: str | None = None


__all__ = [
    "ChainOfCustodyEntry",
    "HeadlineScalar",
    "Mode",
    "ProvenanceFooter",
    "ReportContext",
]
