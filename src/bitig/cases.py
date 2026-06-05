"""Case data model for the Forensic Lab UI (spec §2).

A *Case* is a single investigation on disk: one directory holding the
evidence, the resolved study config, every run that has executed against
that study, and the report draft. It is the persistent unit the GUI builds
its five-step workflow around (spec §5).

The on-disk layout is exactly as spec §2 describes::

    <root>/<slug>/
    ├── case.json
    ├── evidence/{questioned,known,control}/
    ├── study.yaml
    ├── runs/<iso-timestamp>/
    └── report/

The class hierarchy here mirrors the JSON schema:

* ``EvidenceEntry``     — one registered file (path, hash, token count, role)
* ``ControlCorpusRef``  — a reference to an external impostor pool
* ``CaseEvidence``      — the three buckets above grouped together
* ``CaseRecord``        — the full ``case.json`` shape
* ``Case``              — the live object you act on: load/save, register
                          evidence, verify chain of custody, sign, etc.

The CLI (spec §7 step 3, not in this file) and the GUI both interact with
Cases exclusively through ``Case``. ``case.json`` is never hand-edited.

This module is deliberately UI-agnostic and side-effect-light: it touches
the filesystem only when explicitly asked (``save``, ``add_evidence``,
``regenerate_study_yaml``, ``mark_signed``). It does NOT execute analyses
— that is the runner's job (step 3 of the Forensic Lab build sequence).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from bitig._version import __version__
from bitig.config.schema import StudyConfig
from bitig.recipes import (
    Mode,
    derive_mode,
    is_custom,
    recipe_mode,
    resolve_recipe,
)

EvidenceRole = Literal["questioned", "known", "control"]
_ROLES: tuple[EvidenceRole, ...] = ("questioned", "known", "control")

DEFAULT_CASES_DIR: Path = Path.home() / ".bitig" / "cases"
"""Default cases root (spec §9 open-followup). Override per-invocation with the
``--cases-dir`` CLI flag or by passing an explicit root to ``Case.create``."""

_CASE_JSON = "case.json"
_STUDY_YAML = "study.yaml"
_EVIDENCE_DIR = "evidence"
_RUNS_DIR = "runs"
_RUNS_LATEST = "latest"
_REPORT_DIR = "report"
_REPORT_DRAFT = "draft.html"
_REPORT_SIGNED = "signed.json"
_REPORT_SIGNED_HTML = "signed.html"  # immutable snapshot of the report at sign time


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class EvidenceEntry:
    """One file registered as evidence in a Case.

    ``path`` is stored *relative* to the case root so cases are portable
    across machines. ``sha256`` is the canonical content hash captured at
    registration time — chain-of-custody breaks the moment a re-hash on
    disk disagrees (see ``Case.verify_custody``).

    ``tokens`` is a display-only whitespace count, not the spaCy token
    count used by the runner. It is cheap to compute on registration and
    good enough for the Evidence step's metadata strip; the analyst gets
    the precise count after Run.
    """

    path: str
    sha256: str
    tokens: int
    role: EvidenceRole
    author: str | None = None
    year: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {
            k: v for k, v in d.items() if v is not None or k in {"path", "sha256", "tokens", "role"}
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceEntry:
        return cls(
            path=data["path"],
            sha256=data["sha256"],
            tokens=int(data["tokens"]),
            role=data["role"],
            author=data.get("author"),
            year=data.get("year"),
        )


@dataclass
class ControlCorpusRef:
    """Pointer to an external impostor pool (forensic mode only).

    Cases reference control corpora by id rather than copying them in.
    The runner is responsible for resolving the id at execution time
    (e.g., to a bundled corpus shipped with bitig, or one registered in
    ``~/.bitig/config.toml``).
    """

    corpus_id: str
    n_docs: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlCorpusRef:
        return cls(corpus_id=data["corpus_id"], n_docs=int(data["n_docs"]))


@dataclass
class CaseEvidence:
    questioned: list[EvidenceEntry] = field(default_factory=list)
    known: list[EvidenceEntry] = field(default_factory=list)
    control: ControlCorpusRef | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "questioned": [e.to_dict() for e in self.questioned],
            "known": [e.to_dict() for e in self.known],
        }
        if self.control is not None:
            out["control"] = self.control.to_dict()
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaseEvidence:
        return cls(
            questioned=[EvidenceEntry.from_dict(d) for d in data.get("questioned", [])],
            known=[EvidenceEntry.from_dict(d) for d in data.get("known", [])],
            control=ControlCorpusRef.from_dict(data["control"]) if data.get("control") else None,
        )

    def all_files(self) -> list[EvidenceEntry]:
        return [*self.questioned, *self.known]


@dataclass
class CaseRecord:
    """Exact on-disk shape of ``case.json`` (spec §2)."""

    id: str
    title: str
    created_at: str  # ISO 8601 UTC, e.g. "2026-05-17T11:42:08Z"
    examiner: str
    recipe: str
    mode: Mode
    evidence: CaseEvidence = field(default_factory=CaseEvidence)
    overrides: dict[str, Any] = field(default_factory=dict)
    study_hash: str = ""
    corpus_hash: str = ""
    runs: list[str] = field(default_factory=list)
    latest_run: str | None = None
    signed: bool = False
    signed_at: str | None = None
    signed_by: str | None = None
    signature_plugin_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "examiner": self.examiner,
            "recipe": self.recipe,
            "mode": self.mode,
            "evidence": self.evidence.to_dict(),
            "overrides": self.overrides,
            "study_hash": self.study_hash,
            "corpus_hash": self.corpus_hash,
            "runs": list(self.runs),
            "latest_run": self.latest_run,
            "signed": self.signed,
            "signed_at": self.signed_at,
            "signed_by": self.signed_by,
            "signature_plugin_id": self.signature_plugin_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaseRecord:
        return cls(
            id=data["id"],
            title=data["title"],
            created_at=data["created_at"],
            examiner=data["examiner"],
            recipe=data["recipe"],
            mode=data["mode"],
            evidence=CaseEvidence.from_dict(data.get("evidence", {})),
            overrides=dict(data.get("overrides", {})),
            study_hash=data.get("study_hash", ""),
            corpus_hash=data.get("corpus_hash", ""),
            runs=list(data.get("runs", [])),
            latest_run=data.get("latest_run"),
            signed=bool(data.get("signed", False)),
            signed_at=data.get("signed_at"),
            signed_by=data.get("signed_by"),
            signature_plugin_id=data.get("signature_plugin_id"),
        )


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def hash_file(path: Path, *, chunk_size: int = 65536) -> str:
    """SHA-256 of a file's bytes, streamed (constant memory)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _short_hash(h: str | None, n: int = 12) -> str:
    return f"{h[:n]}…" if h else "—"


# ---------------------------------------------------------------------------
# Path-safety helpers (audit P1.2/P1.3/P1.4)
#
# Cases are designed to be portable and shareable, so a case id, a dest_name,
# and the paths inside a case.json are all UNTRUSTED boundaries. A crafted
# value must not be able to read, write, or copy files outside the case dir.
# ---------------------------------------------------------------------------

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_case_id(case_id: str) -> str:
    """Reject case ids that aren't a single safe path component (P1.3)."""
    if not isinstance(case_id, str) or case_id in {"", ".", ".."} or not _SAFE_ID_RE.match(case_id):
        raise CaseError(
            f"Invalid case id {case_id!r}: must match [A-Za-z0-9._-]+ and not be '.' or '..' "
            "(no path separators, no parent-directory traversal, not absolute)."
        )
    return case_id


def _safe_component(name: str) -> str:
    """Return ``name`` iff it is a single safe filename component (P1.2)."""
    if (
        not isinstance(name, str)
        or name in {"", ".", ".."}
        or "/" in name
        or "\\" in name
        or os.path.isabs(name)
    ):
        raise CaseError(
            f"Invalid filename {name!r}: must be a single path component "
            "(no separators, no '..', not absolute)."
        )
    return name


def _ensure_within(path: Path, root: Path) -> Path:
    """Resolve ``path`` and assert it stays within ``root`` (P1.2/P1.4)."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise CaseError(f"Path {path!r} escapes the case directory {root}.")
    return resolved


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically (write temp + os.replace) so an
    interrupted write can't truncate an integrity-root file (audit P2)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Seal verification result (audit P1.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SealCheck:
    """One line of a :class:`SealVerification` — a single integrity check."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class SealVerification:
    """Result of :meth:`Case.verify_seal`.

    ``signed`` is False for an unsigned case (nothing to verify). ``ok`` is
    True only when the case is signed and *every* check passed.
    """

    signed: bool
    checks: list[SealCheck]

    @property
    def ok(self) -> bool:
        return self.signed and all(c.ok for c in self.checks)


def _count_tokens(path: Path) -> int:
    """Display-only whitespace token count. The runner uses spaCy."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    return len(text.split())


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_corpus_hash(evidence: CaseEvidence) -> str:
    """Stable hash over registered evidence.

    Distinct from the *runtime* corpus_hash captured in ``Provenance`` —
    this one is purely a function of what was registered in case.json, so
    it changes the moment a file is added, removed, or its registered hash
    changes. It is the chain-of-custody anchor for the Case itself.
    """
    parts: list[str] = []
    for e in sorted(evidence.questioned + evidence.known, key=lambda e: (e.role, e.path)):
        parts.append(f"{e.role}:{e.path}:{e.sha256}")
    if evidence.control is not None:
        parts.append(f"control:{evidence.control.corpus_id}:{evidence.control.n_docs}")
    return hash_text("\n".join(parts))


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------


class CaseError(RuntimeError):
    """Raised for any Case-level invariant violation (signed, custody, etc.)."""


class Case:
    """Live handle on a Case directory.

    Always construct via :meth:`Case.create` (new) or :meth:`Case.load`
    (existing). Mutating methods write to disk on completion; ``save()``
    forces a flush of ``case.json`` when you mutate the record directly.
    """

    def __init__(self, root: Path, record: CaseRecord) -> None:
        self.root: Path = Path(root)
        self.record: CaseRecord = record

    # -- construction -------------------------------------------------------

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        id: str,
        title: str,
        examiner: str,
        recipe: str,
        overrides: dict[str, Any] | None = None,
    ) -> Case:
        """Lay out a new Case directory and return a handle.

        ``root`` is the *parent* directory (e.g. ``~/.bitig/cases/``); the
        case dir itself is ``root / id``. Raises :class:`CaseError` if the
        case directory already exists, to prevent silent overwrites.
        """
        root = Path(root)
        _validate_case_id(id)  # reject traversal ids before touching the filesystem (P1.3)
        case_dir = root / id
        if case_dir.exists():
            raise CaseError(f"Case directory already exists: {case_dir}")

        # Determine mode up-front. For named recipes, ``recipe_mode`` is
        # purely declarative; for ``custom`` it has to derive from the
        # resolved study (which the caller supplies via ``overrides``).
        overrides = overrides or {}
        if is_custom(recipe):
            resolved = resolve_recipe(recipe, overrides)
            mode = recipe_mode(recipe, study=resolved)
        else:
            mode = recipe_mode(recipe)

        for sub in (
            _EVIDENCE_DIR,
            f"{_EVIDENCE_DIR}/questioned",
            f"{_EVIDENCE_DIR}/known",
            f"{_EVIDENCE_DIR}/control",
            _RUNS_DIR,
            _REPORT_DIR,
        ):
            (case_dir / sub).mkdir(parents=True, exist_ok=True)

        record = CaseRecord(
            id=id,
            title=title,
            created_at=_utcnow_iso(),
            examiner=examiner,
            recipe=recipe,
            mode=mode,
            overrides=dict(overrides),
        )
        case = cls(case_dir, record)
        case.regenerate_study_yaml()
        case.save()
        return case

    @classmethod
    def load(cls, case_dir: Path) -> Case:
        case_dir = Path(case_dir)
        case_json = case_dir / _CASE_JSON
        if not case_json.is_file():
            raise CaseError(f"Not a Case directory (missing {_CASE_JSON}): {case_dir}")
        data = json.loads(case_json.read_text(encoding="utf-8"))
        record = CaseRecord.from_dict(data)
        # case.json is untrusted (cases are shareable). Reject any evidence path
        # that is absolute or escapes the case dir BEFORE anything hashes or
        # copies it — otherwise a crafted entry is an arbitrary-file read (via
        # verify_custody) and a copy-out primitive (via fork_case). Audit P1.4.
        for entry in record.evidence.all_files():
            if os.path.isabs(entry.path):
                raise CaseError(f"Evidence path is absolute (rejected): {entry.path!r}")
            _ensure_within(case_dir / entry.path, case_dir)
        return cls(case_dir, record)

    # -- paths --------------------------------------------------------------

    @property
    def case_json_path(self) -> Path:
        return self.root / _CASE_JSON

    @property
    def study_yaml_path(self) -> Path:
        return self.root / _STUDY_YAML

    @property
    def evidence_dir(self) -> Path:
        return self.root / _EVIDENCE_DIR

    def evidence_role_dir(self, role: EvidenceRole) -> Path:
        if role not in _ROLES:
            raise ValueError(f"Unknown evidence role: {role!r}. Expected one of {_ROLES}.")
        return self.evidence_dir / role

    @property
    def runs_dir(self) -> Path:
        return self.root / _RUNS_DIR

    @property
    def report_dir(self) -> Path:
        return self.root / _REPORT_DIR

    # -- persistence --------------------------------------------------------

    def save(self) -> None:
        """Recompute derived hashes and flush ``case.json``."""
        # study_hash is refreshed lazily off the on-disk study.yaml so a
        # hand-edit through the Custom slide-over still produces a fresh
        # hash next save.
        if self.study_yaml_path.is_file():
            self.record.study_hash = hash_file(self.study_yaml_path)
        self.record.corpus_hash = compute_corpus_hash(self.record.evidence)
        payload = json.dumps(self.record.to_dict(), indent=2)
        _atomic_write_text(self.case_json_path, payload)

    # -- evidence -----------------------------------------------------------

    def add_evidence(
        self,
        src: Path,
        *,
        role: EvidenceRole,
        author: str | None = None,
        year: int | None = None,
        dest_name: str | None = None,
    ) -> EvidenceEntry:
        """Copy ``src`` into the role dir, hash it, register it, save.

        Refuses to overwrite an existing file with the same destination
        name — analysts can pass ``dest_name`` to disambiguate, or rename
        the source. Raises :class:`CaseError` if the Case is signed.
        """
        self._require_unsigned("add evidence")
        # Reject the control role before any filesystem mutation, so a failed
        # call leaves the evidence tree byte-for-byte unchanged (audit P1.6).
        if role == "control":
            raise CaseError(
                "Use set_control_corpus() for control-corpus references, not add_evidence()."
            )
        src = Path(src)
        if not src.is_file():
            raise FileNotFoundError(src)

        # dest_name (public API) and the src.name fallback are untrusted: a
        # crafted '../../report/forged.html' must not escape the role dir (P1.2).
        name = _safe_component(dest_name) if dest_name is not None else _safe_component(src.name)
        role_dir = self.evidence_role_dir(role)
        role_dir.mkdir(parents=True, exist_ok=True)
        dest = role_dir / name
        _ensure_within(dest, role_dir)
        if dest.exists():
            raise CaseError(f"Destination already exists: {dest}. Pass dest_name= to disambiguate.")
        shutil.copy2(src, dest)

        entry = EvidenceEntry(
            path=str(dest.relative_to(self.root)),
            sha256=hash_file(dest),
            tokens=_count_tokens(dest),
            role=role,
            author=author,
            year=year,
        )
        bucket = getattr(self.record.evidence, role)
        bucket.append(entry)
        self.save()
        return entry

    def set_control_corpus(self, corpus_id: str, n_docs: int) -> ControlCorpusRef:
        """Set the impostor pool reference (forensic-mode Cases)."""
        self._require_unsigned("set control corpus")
        ref = ControlCorpusRef(corpus_id=corpus_id, n_docs=int(n_docs))
        self.record.evidence.control = ref
        self.save()
        return ref

    def verify_custody(self) -> list[EvidenceEntry]:
        """Return registered entries whose on-disk SHA-256 no longer matches.

        Empty list means the chain of custody is intact (spec §5.1: the
        Evidence step uses this to flip cards red and block step 4+).
        Missing files also count as a mismatch — the entry is returned.
        """
        mismatches: list[EvidenceEntry] = []
        for entry in self.record.evidence.all_files():
            abs_path = self.root / entry.path
            if not abs_path.is_file():
                mismatches.append(entry)
                continue
            if hash_file(abs_path) != entry.sha256:
                mismatches.append(entry)
        return mismatches

    # -- study --------------------------------------------------------------

    def resolved_study_dict(self) -> dict[str, Any]:
        """The study.yaml-shaped dict for this Case's recipe + overrides.

        ``corpus.path`` is filled in to point at the Case's evidence dir
        so ``bitig run study.yaml`` from inside the Case works.
        """
        return resolve_recipe(
            self.record.recipe,
            self.record.overrides,
            corpus_path=str(self.evidence_dir),
            name=self.record.id,
        )

    def resolved_study(self) -> StudyConfig:
        return StudyConfig.model_validate(self.resolved_study_dict())

    def regenerate_study_yaml(self) -> Path:
        """Write the resolved study to ``study.yaml`` and refresh study_hash."""
        self._require_unsigned("regenerate study.yaml")
        resolved = self.resolved_study_dict()
        # Validate before writing so we never persist a broken study.
        StudyConfig.model_validate(resolved)
        text = yaml.safe_dump(resolved, sort_keys=False)
        _atomic_write_text(self.study_yaml_path, text)
        self.record.study_hash = hash_file(self.study_yaml_path)
        return self.study_yaml_path

    def set_param(self, target: str, value: Any) -> None:
        """Apply a ParamField override (spec §5.2 drawer save).

        ``target`` follows :func:`bitig.recipes.apply_param_target` syntax
        (e.g. ``"features[mfw].top_n"``). The override lives in
        ``record.overrides`` so it survives recipe-mode re-derivation, and
        ``study.yaml`` is regenerated against the new resolved study.

        Raises :class:`CaseError` if the Case is signed.
        """
        from bitig.recipes import apply_param_target

        self._require_unsigned("set param")
        resolved = apply_param_target(self.resolved_study_dict(), target, value)

        # Persist the override as a flat top-level patch over the recipe
        # defaults. We strip ``corpus`` / ``name`` because those are filled
        # in by :meth:`resolved_study_dict` from the Case itself.
        resolved.pop("corpus", None)
        resolved.pop("name", None)
        self.record.overrides = resolved
        self.regenerate_study_yaml()
        self.save()

    def change_recipe(
        self,
        new_recipe: str,
        overrides: dict[str, Any] | None = None,
    ) -> None:
        """Switch recipes (spec §3 confirmation dialog lives in the GUI).

        Resets ``overrides``, re-derives ``mode``, regenerates study.yaml.
        Raises if the Case is signed.
        """
        self._require_unsigned("change recipe")
        self.record.recipe = new_recipe
        self.record.overrides = dict(overrides or {})
        if is_custom(new_recipe):
            self.record.mode = recipe_mode(new_recipe, study=self.resolved_study_dict())
        else:
            self.record.mode = recipe_mode(new_recipe)
        self.regenerate_study_yaml()
        self.save()

    # -- runs ---------------------------------------------------------------

    def register_run(self, run_id: str) -> Path:
        """Record a completed run. The runner creates ``runs/<run_id>/``
        and writes its artefacts; this method just updates ``case.json``
        and refreshes the ``runs/latest`` symlink.
        """
        run_dir = self.runs_dir / run_id
        if not run_dir.is_dir():
            raise CaseError(f"Run directory does not exist: {run_dir}")
        if run_id not in self.record.runs:
            self.record.runs.append(run_id)
        self.record.latest_run = run_id

        # Update `runs/latest` symlink. Filesystems that don't support
        # symlinks (e.g. Windows without dev mode) silently skip — the
        # `latest_run` field in case.json is the source of truth either way.
        latest_link = self.runs_dir / _RUNS_LATEST
        try:
            if latest_link.is_symlink() or latest_link.exists():
                latest_link.unlink()
            latest_link.symlink_to(run_id, target_is_directory=True)
        except (OSError, NotImplementedError):
            pass

        self.save()
        return run_dir

    # -- sign & lock --------------------------------------------------------

    @property
    def is_signed(self) -> bool:
        return self.record.signed

    def mark_signed(
        self,
        *,
        signed_by: str | None = None,
        signature_plugin: Any = None,
    ) -> dict[str, Any]:
        """Freeze the Case and write ``report/signed.json`` (spec §6).

        ``signature_plugin`` is an optional :class:`~bitig.signatures
        .SignaturePlugin` that wraps the base chain-of-custody payload
        with an additional cryptographic binding (e.g. an HMAC or an
        HSM-backed signature). The default (``None``) keeps the
        chain-of-custody-only behaviour.

        Returns the (possibly plugin-augmented) ``signed.json`` payload
        as a dict. Raises :class:`CaseError` if the Case is already
        signed — `bitig case fork` produces a fresh unsigned descendant.
        """
        # Lazy import so bitig.cases stays importable without the new
        # signatures module (e.g. minimal embedded use).
        from bitig.signatures import DEFAULT_SIGNATURE_PLUGIN

        if self.record.signed:
            raise CaseError("Case is already signed.")

        plugin = signature_plugin if signature_plugin is not None else DEFAULT_SIGNATURE_PLUGIN
        signed_at = _utcnow_iso()
        signed_by = signed_by or self.record.examiner

        # Set the signing state BEFORE rendering so the sealed report shows the
        # SIGNED banner + signer/timestamp (the document that gets sealed must
        # reflect that it is signed). save() persists it; on any failure below
        # we roll the record back so a half-signed state can't be left behind.
        prev = (
            self.record.signed,
            self.record.signed_at,
            self.record.signed_by,
            self.record.signature_plugin_id,
        )
        self.record.signed = True
        self.record.signed_at = signed_at
        self.record.signed_by = signed_by
        self.record.signature_plugin_id = plugin.id
        self.save()

        try:
            # Render the final (signed-context) report and freeze it as an
            # immutable signed.html. Export-to-PDF and any later render serve
            # this frozen copy, so the locked artefact can never be silently
            # rewritten out from under its sealed hash (audit P1.5, P1.7).
            # Lazy import: bitig.report imports bitig.cases, so importing it at
            # module scope would cycle — but at call time the cycle is resolved.
            from bitig.report.case_report import build_case_report

            build_case_report(self, format="html")  # writes draft.html (signed banner)
            draft = self.report_dir / _REPORT_DRAFT
            if not draft.is_file():  # pragma: no cover - renderer always writes it
                raise CaseError("Report rendering produced no draft.html; cannot seal.")
            shutil.copy2(draft, self.report_dir / _REPORT_SIGNED_HTML)

            # case_state_hash is sign-invariant (see _case_state_hash) so it is
            # reproducible after the save() above. report_html_hash binds the
            # frozen report as a SEPARATE sealed field — folding it into
            # case_state_hash would be circular, since the report footer
            # displays case_state_hash itself. verify_seal() checks both.
            payload: dict[str, Any] = {
                "signed_at": signed_at,
                "signed_by": signed_by,
                "case_state_hash": self._case_state_hash(),
                "report_html_hash": self._report_html_hash(),
                "bitig_version": __version__,
                "signature_plugin_id": plugin.id,
            }
            signed_payload = plugin.sign(payload, case=self)
            _atomic_write_text(
                self.report_dir / _REPORT_SIGNED, json.dumps(signed_payload, indent=2)
            )
        except Exception:
            # Roll back so the case is not left in a half-signed state.
            (
                self.record.signed,
                self.record.signed_at,
                self.record.signed_by,
                self.record.signature_plugin_id,
            ) = prev
            self.save()
            raise

        return signed_payload

    # -- internals ----------------------------------------------------------

    def _require_unsigned(self, action: str) -> None:
        if self.record.signed:
            raise CaseError(f"Case is signed; cannot {action}. Fork it for further work.")

    def _canonical_state(self) -> dict[str, Any]:
        """Sign-invariant projection of the case — the chain-of-custody anchor.

        Deliberately EXCLUDES the signing fields (signed / signed_at /
        signed_by / signature_plugin_id) and the mutable run bookkeeping
        (runs / latest_run), so this projection — and therefore
        :meth:`_case_state_hash` — is byte-identical before and after
        ``mark_signed``'s own ``save()``. That is what makes the sealed
        ``case_state_hash`` reproducible on a reloaded signed case (audit P0.1).

        It also excludes the report hash: the report is bound separately via
        ``signed.json``'s ``report_html_hash`` field, because the rendered
        report footer *displays* ``case_state_hash`` and folding the report
        hash in here would be circular.

        It covers everything that defines *what was analysed*: identity,
        examiner, recipe + overrides, the resolved ``study.yaml``, and every
        evidence file's registered hash. Tampering with any of these changes
        the hash.
        """
        r = self.record
        evidence = [
            {
                "role": e.role,
                "path": e.path,
                "sha256": e.sha256,
                "tokens": e.tokens,
                "author": e.author,
                "year": e.year,
            }
            for e in sorted(r.evidence.all_files(), key=lambda e: (e.role, e.path))
        ]
        control = (
            {"corpus_id": r.evidence.control.corpus_id, "n_docs": r.evidence.control.n_docs}
            if r.evidence.control is not None
            else None
        )
        return {
            "schema": 1,
            "id": r.id,
            "title": r.title,
            "examiner": r.examiner,
            "created_at": r.created_at,
            "recipe": r.recipe,
            "mode": r.mode,
            "overrides": r.overrides,
            "study_yaml_sha256": (
                hash_file(self.study_yaml_path) if self.study_yaml_path.is_file() else None
            ),
            "evidence": evidence,
            "control": control,
        }

    def _case_state_hash(self) -> str:
        """SHA-256 over the sign-invariant canonical state (spec §6, audit P0.1).

        Stable across ``mark_signed``'s own ``save()`` — recomputing on a
        reloaded signed case yields the identical hash, so ``signed.json`` is
        independently verifiable (see :meth:`verify_seal`).
        """
        canonical = json.dumps(self._canonical_state(), sort_keys=True, ensure_ascii=False)
        return hash_text(canonical)

    def _report_html_hash(self) -> str | None:
        """Hash of the report of record.

        For a signed case this is the immutable ``signed.html`` snapshot; for
        an unsigned case it is the working ``draft.html``. Returns ``None``
        when no report has been rendered yet.
        """
        signed_html = self.report_dir / _REPORT_SIGNED_HTML
        if signed_html.is_file():
            return hash_file(signed_html)
        draft = self.report_dir / _REPORT_DRAFT
        if draft.is_file():
            return hash_file(draft)
        return None

    def verify_seal(self, *, signature_key: bytes | str | None = None) -> SealVerification:
        """Independently verify a signed case's chain-of-custody seal (audit P1.1).

        Recomputes every sealed quantity from the current on-disk state and
        compares it to ``report/signed.json``: the canonical state hash, the
        report hash, evidence custody, and — when a non-Null signature plugin
        was used — the cryptographic signature (HMAC needs ``signature_key`` or
        ``$BITIG_SIGNATURE_KEY``). Returns a structured result; the overall
        ``.ok`` is True only if *every* check passes. Pure read-only.
        """
        from bitig.signatures import verify_hmac_signature

        if not self.record.signed:
            return SealVerification(
                signed=False,
                checks=[SealCheck("signed", False, "Case is not signed; nothing to verify.")],
            )

        signed_path = self.report_dir / _REPORT_SIGNED
        if not signed_path.is_file():
            return SealVerification(
                signed=True,
                checks=[
                    SealCheck("signed_json", False, f"signed=true but {_REPORT_SIGNED} is missing")
                ],
            )
        try:
            payload = json.loads(signed_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return SealVerification(
                signed=True,
                checks=[SealCheck("signed_json", False, f"cannot read {_REPORT_SIGNED}: {exc}")],
            )

        checks: list[SealCheck] = []

        recomputed = self._case_state_hash()
        sealed = payload.get("case_state_hash")
        checks.append(
            SealCheck(
                "case_state_hash",
                recomputed == sealed,
                "matches sealed value"
                if recomputed == sealed
                else f"MISMATCH sealed={_short_hash(sealed)} recomputed={_short_hash(recomputed)}",
            )
        )

        rep = self._report_html_hash()
        sealed_rep = payload.get("report_html_hash")
        checks.append(
            SealCheck(
                "report_html_hash",
                rep == sealed_rep,
                "report matches sealed value"
                if rep == sealed_rep
                else f"MISMATCH sealed={_short_hash(sealed_rep)} recomputed={_short_hash(rep)}",
            )
        )

        mismatches = self.verify_custody()
        checks.append(
            SealCheck(
                "evidence_custody",
                not mismatches,
                "all evidence files match registered hashes"
                if not mismatches
                else f"{len(mismatches)} file(s) altered/missing: "
                + ", ".join(m.path for m in mismatches),
            )
        )

        plugin_id = payload.get("signature_plugin_id", "null")
        sig = payload.get("signature")
        if plugin_id == "null" or sig is None:
            checks.append(
                SealCheck(
                    "signature",
                    True,
                    "no cryptographic signature (Null plugin) — chain-of-custody hashes only",
                )
            )
        elif plugin_id == "hmac":
            key = signature_key or os.environ.get("BITIG_SIGNATURE_KEY")
            if not key:
                checks.append(
                    SealCheck(
                        "signature",
                        False,
                        "HMAC signature present but no key provided "
                        "(pass signature_key= or set BITIG_SIGNATURE_KEY)",
                    )
                )
            else:
                ok = verify_hmac_signature(payload, key=key)
                checks.append(
                    SealCheck(
                        "signature",
                        ok,
                        "HMAC signature valid"
                        if ok
                        else "HMAC signature INVALID (wrong key or tampered payload)",
                    )
                )
        else:
            checks.append(SealCheck("signature", False, f"unknown signature plugin {plugin_id!r}"))

        return SealVerification(signed=True, checks=checks)

    # -- convenience --------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"Case(id={self.record.id!r}, mode={self.record.mode!r}, "
            f"recipe={self.record.recipe!r}, signed={self.record.signed})"
        )


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def fork_case(
    src_dir: Path,
    new_id: str,
    *,
    cases_root: Path | None = None,
    title: str | None = None,
    examiner: str | None = None,
) -> Case:
    """Clone an existing Case into an unsigned descendant (spec §6).

    Evidence files and the control-corpus reference carry over, as do the
    recipe and overrides. Runs, report draft, and the signed state do not.
    The new Case is created under ``cases_root`` (defaults to the parent of
    ``src_dir``, mirroring the source layout) and is freshly hashed.

    Raises :class:`CaseError` if the destination already exists.
    """
    source = Case.load(src_dir)
    if cases_root is None:
        cases_root = source.root.parent

    forked = Case.create(
        cases_root,
        id=new_id,
        title=title if title is not None else f"{source.record.title} (fork of {source.record.id})",
        examiner=examiner if examiner is not None else source.record.examiner,
        recipe=source.record.recipe,
        overrides=dict(source.record.overrides),
    )

    for entry in source.record.evidence.questioned:
        forked.add_evidence(
            source.root / entry.path,
            role="questioned",
            author=entry.author,
            year=entry.year,
            dest_name=Path(entry.path).name,
        )
    for entry in source.record.evidence.known:
        forked.add_evidence(
            source.root / entry.path,
            role="known",
            author=entry.author,
            year=entry.year,
            dest_name=Path(entry.path).name,
        )
    if source.record.evidence.control is not None:
        c = source.record.evidence.control
        forked.set_control_corpus(c.corpus_id, n_docs=c.n_docs)

    return forked


def list_cases(root: Path) -> list[Case]:
    """Return every Case under ``root`` (one level deep).

    Skips entries that don't contain a ``case.json``. Returned in
    alphabetical order by id; the GUI's Case-list landing page can re-sort
    by created_at / signed status as needed.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    out: list[Case] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if not (child / _CASE_JSON).is_file():
            continue
        out.append(Case.load(child))
    return out


__all__ = [
    "DEFAULT_CASES_DIR",
    "Case",
    "CaseError",
    "CaseEvidence",
    "CaseRecord",
    "ControlCorpusRef",
    "EvidenceEntry",
    "EvidenceRole",
    "SealCheck",
    "SealVerification",
    "compute_corpus_hash",
    "derive_mode",  # re-export for callers that already import from cases
    "fork_case",
    "hash_file",
    "hash_text",
    "list_cases",
]
