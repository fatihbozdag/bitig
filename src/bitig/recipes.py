"""Recipe registry for the Forensic Lab UI (spec §5.2, §3).

A *recipe* is a named investigative goal — "did this person write this?",
"which of N authors?", "how is this corpus structured?" — bundled with the
feature + method skeleton that answers it. Recipes are user-visible (the
brass-tile method picker in `method-picker.html`); the spec calls out five
named recipes plus a ``custom`` escape hatch that bypasses the gallery and
opens the raw YAML editor.

The Case data model (``bitig.cases``) stores a recipe id and a small
``overrides`` dict. ``resolve_recipe`` materialises both into a study.yaml-
shaped dict that ``bitig.config.StudyConfig`` validates. Mode is *derived*
from the resolved study, never set by the user — a study containing any
``verify`` method is forensic; everything else is research (spec §3).

The recipe definitions here are intentionally minimal: defaults that pass
``StudyConfig`` validation and exercise the right code path. Real-world
parameter tuning happens through the param drawer (spec §5.2), which writes
into ``overrides``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from bitig.config.schema import StudyConfig

Mode = Literal["forensic", "research"]


@dataclass(frozen=True)
class ParamField:
    """One user-facing param surfaced in the recipe drawer (spec §5.2).

    ``target`` is a dotted path describing where the value lands in the
    resolved study dict — e.g. ``"features[mfw].top_n"`` means "find the
    feature with id 'mfw' and set its ``top_n`` param". The drawer widget
    layer (built later, step 4 of the build sequence) consumes this.
    """

    label: str
    kind: Literal["int", "float", "str", "select", "bool"]
    default: Any
    target: str
    options: tuple[str, ...] | None = None
    help: str | None = None


@dataclass(frozen=True)
class Recipe:
    """One investigative goal.

    The five non-custom recipes are user-visible. ``custom`` is the absence
    of a recipe: Case.load() may return a Case whose ``recipe == "custom"``
    and whose study.yaml was hand-edited via the Custom tile.
    """

    id: str
    title: str
    question: str
    mode: Mode
    default_features: tuple[dict[str, Any], ...]
    default_methods: tuple[dict[str, Any], ...]
    param_schema: tuple[ParamField, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Recipe definitions (spec §3 table)
# ---------------------------------------------------------------------------

_MFW_FEATURE: dict[str, Any] = {
    "id": "mfw",
    "type": "mfw",
    "top_n": 500,
}

_CHAR_NGRAM_FEATURE: dict[str, Any] = {
    "id": "char3",
    "type": "char_ngram",
    "n": 3,
    "top_n": 1500,
}


_IMPOSTERS_LR = Recipe(
    id="imposters_lr",
    title="Authorship verification",
    question="Did this person write this?",
    mode="forensic",
    default_features=(_MFW_FEATURE,),
    default_methods=(
        {
            "id": "verify",
            "kind": "verify",
            "features": "mfw",
            "delta": "cosine",
            "iterations": 100,
            "subset_fraction": 0.5,
        },
    ),
    param_schema=(
        ParamField(
            "MFW size",
            "int",
            500,
            "features[mfw].top_n",
            help="Number of most-frequent words to retain.",
        ),
        ParamField(
            "Iterations", "int", 100, "methods[verify].iterations", help="Impostor projections."
        ),
        ParamField(
            "Delta",
            "select",
            "cosine",
            "methods[verify].delta",
            options=("burrows", "cosine", "eder", "eder_simple", "argamon", "quadratic"),
        ),
        ParamField("Seed", "int", 42, "seed"),
    ),
)


_DELTA_ATTRIBUTION = Recipe(
    id="delta_attribution",
    title="Delta attribution",
    question="Which author, out of N?",
    mode="research",
    default_features=(_MFW_FEATURE,),
    default_methods=(
        {
            "id": "delta",
            "kind": "delta",
            "features": "mfw",
            "variant": "burrows",
        },
    ),
    param_schema=(
        ParamField("MFW size", "int", 500, "features[mfw].top_n"),
        ParamField(
            "Variant",
            "select",
            "burrows",
            "methods[delta].variant",
            options=("burrows", "cosine", "eder", "eder_simple", "argamon", "quadratic"),
        ),
        ParamField(
            "Group by",
            "str",
            "author",
            "methods[delta].group_by",
            help="Metadata column to attribute on.",
        ),
        ParamField("Seed", "int", 42, "seed"),
    ),
)


_EXPLORATION = Recipe(
    id="exploration",
    title="Corpus exploration",
    question="How is this corpus structured?",
    mode="research",
    default_features=(_MFW_FEATURE,),
    default_methods=(
        {
            "id": "pca",
            "kind": "reduce",
            "features": "mfw",
            "algorithm": "pca",
            "n_components": 2,
        },
        {
            "id": "hierarchical",
            "kind": "cluster",
            "features": "mfw",
            "algorithm": "hierarchical",
        },
    ),
    param_schema=(
        ParamField("MFW size", "int", 500, "features[mfw].top_n"),
        ParamField(
            "Reduction",
            "select",
            "pca",
            "methods[pca].algorithm",
            options=("pca", "umap"),
        ),
        ParamField("Group by", "str", "author", "methods[pca].group_by"),
        ParamField("Seed", "int", 42, "seed"),
    ),
)


_ZETA_CONTRAST = Recipe(
    id="zeta_contrast",
    title="Group contrast (Zeta)",
    question="What distinguishes group A from group B?",
    mode="research",
    default_features=({"id": "tokens", "type": "word_ngram", "n": 1, "top_n": 5000},),
    default_methods=(
        {
            "id": "zeta",
            "kind": "zeta",
            "features": "tokens",
            "variant": "craig",
        },
    ),
    param_schema=(
        ParamField(
            "Variant",
            "select",
            "craig",
            "methods[zeta].variant",
            options=("craig", "eder"),
        ),
        ParamField(
            "Group by",
            "str",
            "group",
            "methods[zeta].group_by",
            help="Metadata column splitting A vs B.",
        ),
        ParamField("Seed", "int", 42, "seed"),
    ),
)


_BAYESIAN = Recipe(
    id="bayesian",
    title="Bayesian posterior",
    question="Bayesian author posterior over N candidates",
    mode="research",
    default_features=({"id": "function_words", "type": "function_word"},),
    default_methods=(
        {
            "id": "bayes",
            "kind": "bayesian",
            "features": "function_words",
        },
    ),
    param_schema=(
        ParamField("Group by", "str", "author", "methods[bayes].group_by"),
        ParamField("Seed", "int", 42, "seed"),
    ),
)


RECIPES: dict[str, Recipe] = {
    r.id: r for r in (_IMPOSTERS_LR, _DELTA_ATTRIBUTION, _EXPLORATION, _ZETA_CONTRAST, _BAYESIAN)
}
"""Public registry. ``"custom"`` is intentionally absent — it signals the
*absence* of a recipe (study.yaml was hand-edited) rather than another row
here. Use ``is_custom(recipe_id)`` for the check."""


CUSTOM_RECIPE_ID = "custom"


def is_custom(recipe_id: str) -> bool:
    return recipe_id == CUSTOM_RECIPE_ID


# ---------------------------------------------------------------------------
# Resolution: recipe + overrides → study.yaml-shaped dict
# ---------------------------------------------------------------------------


def resolve_recipe(
    recipe_id: str,
    overrides: dict[str, Any] | None = None,
    *,
    corpus_path: str = "",
    name: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Materialise ``recipe_id`` + ``overrides`` into a study.yaml dict.

    The returned dict is shaped for ``StudyConfig.model_validate``. It does
    NOT include a corpus path by default — Case.regenerate_study_yaml()
    fills that in from the Case's evidence directory.

    ``overrides`` is a shallow study.yaml-shaped dict; its keys deep-merge
    on top of the recipe defaults. Lists (``features``, ``methods``) are
    replaced wholesale if present in overrides — there is no semantic merge
    on list items here, because the YAML editor under the Custom tile
    already produces complete lists.

    Raises ``KeyError`` if ``recipe_id`` is unknown and not ``"custom"``.
    Calling with ``recipe_id == "custom"`` returns ``overrides`` verbatim
    (with ``name`` / ``seed`` / ``corpus`` filled in if missing).
    """
    overrides = overrides or {}

    if is_custom(recipe_id):
        base: dict[str, Any] = dict(overrides)
    else:
        if recipe_id not in RECIPES:
            raise KeyError(
                f"Unknown recipe {recipe_id!r}. Known: {sorted(RECIPES)} or {CUSTOM_RECIPE_ID!r}."
            )
        recipe = RECIPES[recipe_id]
        base = {
            "features": [dict(f) for f in recipe.default_features],
            "methods": [dict(m) for m in recipe.default_methods],
        }
        for key, value in overrides.items():
            base[key] = value

    base.setdefault("corpus", {"path": corpus_path})
    if name is not None:
        base["name"] = name
    elif "name" not in base:
        base["name"] = recipe_id if not is_custom(recipe_id) else "custom-study"
    if seed is not None:
        base["seed"] = seed

    return base


def derive_mode(study: StudyConfig | dict[str, Any]) -> Mode:
    """Forensic iff any method kind is ``verify``; research otherwise (spec §3).

    Accepts a ``StudyConfig`` or its dict form. The dict form is consulted
    leniently so callers can derive mode before the config is fully
    validated.
    """
    methods: list[Any]
    if isinstance(study, StudyConfig):
        methods = list(study.methods)
        for m in methods:
            if m.kind == "verify":
                return "forensic"
        return "research"

    methods = list(study.get("methods") or [])
    for m in methods:
        if isinstance(m, dict) and m.get("kind") == "verify":
            return "forensic"
    return "research"


_BRACKET_RE = __import__("re").compile(r"^(?P<list>features|methods)\[(?P<id>[^\]]+)\]$")


def _walk_target(study: dict[str, Any], target: str) -> tuple[dict[str, Any], str]:
    """Walk ``target`` into ``study`` and return ``(parent, leaf_key)``.

    Supports two shapes:
    * ``seed`` — a top-level scalar; returns ``(study, "seed")``.
    * ``features[id].field`` / ``methods[id].field`` — looks up the list
      entry with matching ``id``, then descends into ``params`` for any
      field outside the entry's declared slots (the same extras-collection
      behaviour that ``FeatureConfig`` / ``MethodConfig`` use).

    Raises :class:`KeyError` if the target can't be resolved (unknown
    list id, malformed path, etc.).
    """
    parts = target.split(".")
    if len(parts) == 1:
        return study, parts[0]
    if len(parts) != 2:
        raise KeyError(f"unsupported ParamField target shape: {target!r}")

    head, tail = parts
    m = _BRACKET_RE.match(head)
    if m is None:
        raise KeyError(f"unsupported ParamField target shape: {target!r}")
    bucket, item_id = m.group("list"), m.group("id")

    items: list[dict[str, Any]] = study.get(bucket) or []
    for entry in items:
        if isinstance(entry, dict) and entry.get("id") == item_id:
            # At the recipe layer the study is flat, so the field is a
            # top-level key of the entry. But if the entry is in the validated
            # *nested* form (Pydantic folds extras into ``params``) and the
            # field isn't a top-level key, target the ``params`` sub-dict —
            # otherwise a write would create entry[field] alongside the real
            # params[field], leaving the study inconsistent (audit P2).
            if tail not in entry and isinstance(entry.get("params"), dict):
                return entry["params"], tail
            return entry, tail
    raise KeyError(f"no {bucket[:-1]} with id={item_id!r} in study")


def read_param_target(study: dict[str, Any], target: str) -> Any:
    """Read the value at ``target`` from a resolved study dict (or None)."""
    try:
        parent, leaf = _walk_target(study, target)
    except KeyError:
        return None
    return parent.get(leaf)


def apply_param_target(study: dict[str, Any], target: str, value: Any) -> dict[str, Any]:
    """Return a new study dict with ``target`` set to ``value``.

    The input is not mutated. ``target`` follows the same syntax as
    :func:`read_param_target`. Raises :class:`KeyError` if the target is
    malformed or references an item id that isn't in ``study``.
    """
    out = _deepcopy_dict(study)
    parent, leaf = _walk_target(out, target)
    parent[leaf] = value
    return out


def _deepcopy_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Cheap deep-copy specialised to recipe/study dicts (no exotic types)."""
    import copy

    return copy.deepcopy(d)


def recipe_mode(recipe_id: str, study: StudyConfig | dict[str, Any] | None = None) -> Mode:
    """Mode for a recipe. For known recipes the declared mode wins. For
    ``"custom"`` the mode is derived from the resolved study (spec §3).
    """
    if is_custom(recipe_id):
        if study is None:
            raise ValueError("custom recipe requires a resolved study to derive mode")
        return derive_mode(study)
    if recipe_id not in RECIPES:
        raise KeyError(f"Unknown recipe {recipe_id!r}.")
    return RECIPES[recipe_id].mode


__all__ = [
    "CUSTOM_RECIPE_ID",
    "RECIPES",
    "Mode",
    "ParamField",
    "Recipe",
    "apply_param_target",
    "derive_mode",
    "is_custom",
    "read_param_target",
    "recipe_mode",
    "resolve_recipe",
]
