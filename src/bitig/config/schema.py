"""Pydantic schema for `study.yaml`.

Only the shape of the config is validated here; semantic validation (e.g., that `features:`
references exist, that methods point at real extractors) happens at execution time against the
extractor/method registries — not at parse time.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bitig.languages import LANGUAGES

CvKind = Literal["stratified", "loao", "group_kfold", "leave_one_text_out"]
MethodKind = Literal[
    "delta",
    "rolling_delta",
    "verify",
    "zeta",
    "reduce",
    "cluster",
    "consensus",
    "classify",
    "bayesian",
]
FeatureType = Literal[
    "mfw",
    "word_ngram",
    "char_ngram",
    "pos_ngram",
    "dependency_bigram",
    "function_word",
    "punctuation",
    "lexical_diversity",
    "readability",
    "sentence_length",
    "sentence_embedding",
    "contextual_embedding",
]

_STRICT_MODEL = ConfigDict(extra="forbid")


def _collect_extras_into_params(values: Any, known: set[str]) -> Any:
    """model_validator(mode='before') helper: move unknown top-level keys into `params`.

    If the input already has an explicit `params` dict, it is respected as-is (no extras
    collection happens). Otherwise, any key outside `known` is treated as a parameter.
    """
    if not isinstance(values, dict):
        return values
    if "params" in values:
        return values
    extras = {k: v for k, v in values.items() if k not in known}
    kept = {k: v for k, v in values.items() if k in known}
    kept["params"] = extras
    return kept


class CorpusConfig(BaseModel):
    model_config = _STRICT_MODEL
    path: str
    metadata: str | None = None
    filter: dict[str, Any] = Field(default_factory=dict)


class SpacyConfig(BaseModel):
    model_config = _STRICT_MODEL
    model: str | None = None
    backend: Literal["spacy", "spacy_stanza"] | None = None
    device: Literal["auto", "cpu", "mps", "cuda"] = "auto"
    exclude: list[str] = Field(default_factory=list)


class NormalizeConfig(BaseModel):
    model_config = _STRICT_MODEL
    lowercase: bool = False
    strip_punct: bool = False
    collapse_numerals: bool = False
    expand_contractions: bool = False


class PreprocessConfig(BaseModel):
    model_config = _STRICT_MODEL
    language: str = "en"
    spacy: SpacyConfig = Field(default_factory=SpacyConfig)
    normalize: NormalizeConfig = Field(default_factory=NormalizeConfig)

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_and_validate(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError(f"language must be a string, got {type(v).__name__}")
        normalized = v.lower()
        if normalized not in LANGUAGES:
            supported = sorted(LANGUAGES)
            raise ValueError(f"Unknown language code: {v!r}. Supported: {supported}.")
        return normalized


class FeatureConfig(BaseModel):
    """A named feature extractor entry.

    `type` selects the extractor; `params` holds the remaining keys (everything except `id` and
    `type`). The extractor registry is responsible for validating `params` against the extractor's
    signature at execution time.
    """

    model_config = _STRICT_MODEL

    id: str
    type: FeatureType
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect_params(cls, values: Any) -> Any:
        return _collect_extras_into_params(values, known={"id", "type"})


class CvConfig(BaseModel):
    model_config = _STRICT_MODEL
    kind: CvKind = "stratified"
    groups_from: str | None = None
    folds: int | None = Field(default=None, ge=2)


class MethodConfig(BaseModel):
    """A named analysis step."""

    model_config = _STRICT_MODEL

    id: str
    kind: MethodKind
    features: str | list[str] | None = None
    group_by: str | None = None
    cv: CvConfig | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect_params(cls, values: Any) -> Any:
        return _collect_extras_into_params(
            values, known={"id", "kind", "features", "group_by", "cv"}
        )


VizFormat = Literal["pdf", "png", "svg", "eps", "tiff"]


class VizConfig(BaseModel):
    model_config = _STRICT_MODEL
    format: list[VizFormat] = Field(
        default_factory=lambda: ["pdf", "png"],  # type: ignore[arg-type]
    )
    dpi: int = Field(default=300, ge=1)
    style: str = "default"
    palette: str = "colorblind"


class ReportConfig(BaseModel):
    model_config = _STRICT_MODEL
    format: Literal["html", "md", "none"] = "none"
    offline: bool = False
    include: list[str] = Field(
        default_factory=lambda: ["corpus", "config", "provenance", "results"]
    )
    title: str | None = None


class CacheConfig(BaseModel):
    model_config = _STRICT_MODEL
    dir: str = ".bitig/cache"
    reuse: bool = True


class OutputConfig(BaseModel):
    model_config = _STRICT_MODEL
    dir: str = "results/"
    timestamp: bool = True


class StudyConfig(BaseModel):
    model_config = _STRICT_MODEL

    name: str = "unnamed-study"
    seed: int = 42

    corpus: CorpusConfig
    preprocess: PreprocessConfig = Field(default_factory=PreprocessConfig)
    features: list[FeatureConfig] = Field(default_factory=list)
    methods: list[MethodConfig] = Field(default_factory=list)
    viz: VizConfig = Field(default_factory=VizConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @field_validator("seed", mode="before")
    @classmethod
    def _default_seed(cls, v: Any) -> int:
        if v is None:
            return 42
        return int(v)
