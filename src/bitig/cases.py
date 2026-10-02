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
import logging
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

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

if TYPE_CHECKING:
    from bitig.corpus import Corpus
    from bitig.signatures import SignaturePlugin

_log = logging.getLogger(__name__)

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
    NOTE: no runner code resolves or analyses this corpus yet. Reports list
    it as "not used by the analysis" so the chain of custody does not
    suggest otherwise (audit 2026-09-26 P2).
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
    # _case_state_hash() at the moment latest_run was computed; signing
    # refuses when the case has changed since (audit 2026-09-26 N-P1.2).
    latest_run_state_hash: str | None = None
    # Append-only record of evidence re-acknowledged after a hash change.
    custody_log: list[dict[str, Any]] = field(default_factory=list)
    # Parent case, its registered hashes and any custody mismatch at fork time.
    forked_from: dict[str, Any] | None = None

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
            "latest_run_state_hash": self.latest_run_state_hash,
            "custody_log": [dict(e) for e in self.custody_log],
            "forked_from": self.forked_from,
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
            latest_run_state_hash=data.get("latest_run_state_hash"),
            custody_log=[dict(e) for e in data.get("custody_log", [])],
            forked_from=data.get("forked_from"),
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


def _evidence_doc_id(entry: EvidenceEntry) -> str:
    """Document id of a registered evidence file in the run corpus: its file stem."""
    return Path(entry.path).stem


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
    if (
        not isinstance(case_id, str)
        or case_id in {"", ".", ".."}
        or not _SAFE_ID_RE.fullmatch(case_id)
    ):
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


def _current_umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


# Read once at import: os.umask can only be queried by setting it.
_UMASK = _current_umask()


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically (write temp + os.replace) so an
    interrupted write can't truncate an integrity-root file (audit P2)."""
    path = Path(path)
    # Unique per call (mkstemp): a pid-only name collided between threads.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp-")
    tmp = Path(tmp_name)
    try:
        # mkstemp creates 0600; give the file the mode a plain open() would.
        os.chmod(tmp, 0o666 & ~_UMASK)
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
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
    # True when the check could not be carried out (an HMAC seal checked
    # without a key): not a pass, but not evidence of tampering either.
    unverifiable: bool = False


SealStatus = Literal["not_signed", "broken", "unverifiable", "unsigned", "verified"]


@dataclass(frozen=True)
class SealVerification:
    """Result of :meth:`Case.verify_seal`.

    ``signed`` is False for an unsigned case (nothing to verify). ``ok`` is
    True only when the case is signed and *every* check passed.
    """

    signed: bool
    checks: list[SealCheck]
    # Plugin recorded in signed.json; "null" means hashes only — consistent
    # hashes are then NOT evidence against tampering by anyone with write access.
    plugin_id: str = "null"

    @property
    def ok(self) -> bool:
        return self.signed and all(c.ok for c in self.checks)

    @property
    def tamper_evident(self) -> bool:
        """True only for a verified seal with a cryptographic signature."""
        return self.ok and self.plugin_id != "null"

    @property
    def status(self) -> SealStatus:
        """One-word outcome.

        ``broken`` if any check failed; ``unverifiable`` if every hash check
        passed but the signature could not be checked (no key); ``unsigned``
        for an intact Null seal (hashes only, not tamper-evident);
        ``verified`` for an intact seal with a valid signature.
        """
        if not self.signed:
            return "not_signed"
        if any(not c.ok and not c.unverifiable for c in self.checks):
            return "broken"
        if any(c.unverifiable for c in self.checks):
            return "unverifiable"
        return "verified" if self.tamper_evident else "unsigned"


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
        # SHA-256 of case.json as this handle last read or wrote it; save()
        # refuses to overwrite a newer version (see _check_not_stale).
        self._disk_sha: str | None = None

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
        raw = case_json.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        record = CaseRecord.from_dict(data)
        # case.json is untrusted (cases are shareable). Reject any evidence path
        # that is absolute or escapes the case dir BEFORE anything hashes or
        # copies it — otherwise a crafted entry is an arbitrary-file read (via
        # verify_custody) and a copy-out primitive (via fork_case). Audit P1.4.
        for entry in record.evidence.all_files():
            if os.path.isabs(entry.path):
                raise CaseError(f"Evidence path is absolute (rejected): {entry.path!r}")
            _ensure_within(case_dir / entry.path, case_dir)
        # Run ids are joined onto runs/ by the report and seal code; a crafted
        # '../../x' would read result.json / figures from anywhere (audit P2).
        for run_id in [*record.runs, *([record.latest_run] if record.latest_run else [])]:
            _validate_case_id(run_id)
        case = cls(case_dir, record)
        case._disk_sha = hashlib.sha256(raw).hexdigest()
        return case

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
        """Recompute derived hashes and flush ``case.json``.

        ``study_hash`` is deliberately NOT refreshed from disk here: it is set
        only by :meth:`regenerate_study_yaml`, so a hand edit of
        ``study.yaml`` is detected (:meth:`study_yaml_intact`) instead of being
        silently re-blessed by the next save (audit 2026-09-26 N-P1.1). The
        Custom editor goes through :meth:`change_recipe`, which regenerates.
        """
        self._check_not_stale()
        self.record.corpus_hash = compute_corpus_hash(self.record.evidence)
        payload = json.dumps(self.record.to_dict(), indent=2)
        _atomic_write_text(self.case_json_path, payload)
        self._disk_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _check_not_stale(self) -> None:
        """Refuse to save over a case.json another handle or process has changed.

        save() writes the whole in-memory record, so a handle loaded before
        another one signed the case (e.g. the GUI run page during a long run)
        would un-sign it, and evidence registered elsewhere would be dropped
        (audit 2026-09-26 P2).
        """
        if not self.case_json_path.is_file():
            return
        current = hashlib.sha256(self.case_json_path.read_bytes()).hexdigest()
        if self._disk_sha is not None and current != self._disk_sha:
            raise CaseError(
                "case.json was changed by another handle or process since this case was "
                "loaded; reload the case (Case.load) and retry."
            )

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
        # The file stem is the document id in the run corpus, so it must be
        # unique across roles (questioned/alice.txt vs known/alice.txt).
        doc_id = Path(name).stem
        if any(_evidence_doc_id(e) == doc_id for e in self._registered_entries()):
            raise CaseError(
                f"Evidence document id {doc_id!r} is already registered under another role. "
                "Pass dest_name= to disambiguate."
            )
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

    def unregistered_evidence_files(self) -> list[str]:
        """Files under ``evidence/`` that are not registered (never analysed or sealed)."""
        if not self.evidence_dir.is_dir():
            return []
        registered = {e.path for e in self._registered_entries()}
        return sorted(
            p.relative_to(self.root).as_posix()
            for p in self.evidence_dir.rglob("*")
            if p.is_file() and p.relative_to(self.root).as_posix() not in registered
        )

    def reacknowledge_evidence(
        self, path: str, *, reason: str, by: str | None = None
    ) -> dict[str, Any]:
        """Accept the current bytes of a changed evidence file, on the record.

        For a registered file whose hash no longer matches (e.g. a re-export
        with different line endings), the analyst states *why* the change is
        legitimate. The old and new hashes, the reason, who and when are
        appended to ``record.custody_log``. That log is part of the canonical
        case state, so it is sealed and printed in the report's chain of
        custody. It also changes the case state, so any earlier run must be
        re-run before the case can be signed.

        Missing files cannot be re-acknowledged: fork the case instead.
        Raises :class:`CaseError` on a signed case, an empty reason, an
        unregistered path, a missing file, or a file that has not changed.
        """
        self._require_unsigned("re-acknowledge evidence")
        reason = (reason or "").strip()
        if not reason:
            raise CaseError("A reason is required to re-acknowledge changed evidence.")
        entry = next((e for e in self._registered_entries() if e.path == path), None)
        if entry is None:
            raise CaseError(f"Not a registered evidence path: {path!r}")
        abs_path = self.root / entry.path
        _ensure_within(abs_path, self.evidence_dir)
        if not abs_path.is_file():
            raise CaseError(
                f"{entry.path} is missing; a missing file cannot be re-acknowledged. "
                "Fork the case instead."
            )
        new_sha = hash_file(abs_path)
        if new_sha == entry.sha256:
            raise CaseError(f"{entry.path} is unchanged; nothing to re-acknowledge.")
        log_entry = {
            "at": _utcnow_iso(),
            "by": by or self.record.examiner,
            "path": entry.path,
            "old_sha256": entry.sha256,
            "new_sha256": new_sha,
            "reason": reason,
        }
        self.record.custody_log.append(log_entry)
        entry.sha256 = new_sha
        entry.tokens = _count_tokens(abs_path)
        self.save()
        return log_entry

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

    def _registered_entries(self) -> list[EvidenceEntry]:
        return [*self.record.evidence.questioned, *self.record.evidence.known]

    def build_corpus(self, *, language: str = "en") -> Corpus:
        """Load the run corpus from the registered evidence only (audit 2026-09-26 N-P0.1).

        Every document is read from its registered path and its bytes are
        re-hashed at read time, so the texts analysed are exactly the texts
        in the chain of custody: unregistered files under ``evidence/`` are
        never loaded, and a file altered since registration aborts the load.
        Each document carries ``role`` and, when registered, ``author`` /
        ``year`` metadata. The document id is the file stem.
        """
        from bitig.corpus import Corpus, Document

        entries = self._registered_entries()
        if not entries:
            raise CaseError("No evidence registered; add questioned/known files before running.")
        ids = [_evidence_doc_id(e) for e in entries]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            # Registered before add_evidence enforced unique stems: two
            # documents with one id would be confused (e.g. as verify targets).
            raise CaseError(
                f"Evidence files share a document id (file stem): {duplicates}. "
                "Fork the case without one of them, or rename and re-register it."
            )
        documents: list[Document] = []
        for entry in entries:
            abs_path = self.root / entry.path
            _ensure_within(abs_path, self.evidence_dir)
            data = abs_path.read_bytes()
            if hashlib.sha256(data).hexdigest() != entry.sha256:
                raise CaseError(
                    f"Chain-of-custody mismatch on {entry.path}: file changed since registration."
                )
            metadata: dict[str, Any] = {"role": entry.role}
            if entry.author is not None:
                metadata["author"] = entry.author
            if entry.year is not None:
                metadata["year"] = entry.year
            documents.append(
                Document(
                    id=_evidence_doc_id(entry),
                    text=data.decode("utf-8"),
                    metadata=metadata,
                )
            )
        return Corpus(documents=documents, language=language.lower())

    def study_yaml_intact(self) -> bool:
        """True iff ``study.yaml`` still hashes to the value recorded when it was written."""
        if not self.study_yaml_path.is_file():
            return False
        return hash_file(self.study_yaml_path) == self.record.study_hash

    # -- study --------------------------------------------------------------

    def resolved_study_dict(self, *, fill_targets: bool = True) -> dict[str, Any]:
        """The study.yaml-shaped dict for this Case's recipe + overrides.

        ``corpus.path`` is the case-relative ``evidence`` dir, recorded for
        reference only: a Case run loads its corpus from the registered
        evidence (:meth:`build_corpus`), never by globbing a directory, so a
        copied or moved Case analyses its own evidence (audit N-P1.1).

        ``verify`` methods without explicit ``target_ids`` target every
        registered questioned document (unless ``fill_targets`` is false), so
        a questioned document added later is targeted too.
        """
        study = resolve_recipe(
            self.record.recipe,
            self.record.overrides,
            corpus_path=_EVIDENCE_DIR,
            name=self.record.id,
        )
        if not fill_targets:
            return study
        questioned = [_evidence_doc_id(e) for e in self.record.evidence.questioned]
        for method in study.get("methods") or []:
            if isinstance(method, dict) and method.get("kind") == "verify":
                fields = method["params"] if isinstance(method.get("params"), dict) else method
                if not fields.get("target_ids"):
                    fields["target_ids"] = questioned
        return study

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
        # Patch the study without the auto-filled ``target_ids``: storing them
        # would freeze today's questioned set into the overrides, and a
        # questioned document added later would silently go untargeted.
        resolved = apply_param_target(self.resolved_study_dict(fill_targets=False), target, value)

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

    def register_run(self, run_id: str, *, case_state_hash: str | None = None) -> Path:
        """Record a completed run. The runner creates ``runs/<run_id>/``
        and writes its artefacts; this method just updates ``case.json``
        and refreshes the ``runs/latest`` symlink.

        ``case_state_hash`` is the case state the run was computed on (taken
        before the run started). Signing refuses a run whose state differs
        from the current one (audit 2026-09-26 N-P1.2); a run registered
        without it can never be signed.
        """
        self._require_unsigned("register a run")
        run_id = _validate_case_id(run_id)
        run_dir = self.runs_dir / run_id
        if not run_dir.is_dir():
            raise CaseError(f"Run directory does not exist: {run_dir}")
        if run_id not in self.record.runs:
            self.record.runs.append(run_id)
        self.record.latest_run = run_id
        self.record.latest_run_state_hash = case_state_hash

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

    def sign_blockers(self) -> list[str]:
        """Why this case cannot be signed right now; empty when it can.

        Enforced by :meth:`mark_signed` itself, so every entry point (CLI,
        GUI, API) gets the same guarantees (audit 2026-09-26 N-P1.2, N-P1.7).
        """
        if self.record.signed:
            return ["Case is already signed."]
        blockers: list[str] = []
        if not self._registered_entries():
            blockers.append("No evidence is registered.")
        mismatches = self.verify_custody()
        if mismatches:
            blockers.append(
                "Chain-of-custody mismatch on: " + ", ".join(m.path for m in mismatches)
            )
        if not self.study_yaml_intact():
            blockers.append("study.yaml is missing or was modified outside bitig.")
        latest = self.record.latest_run
        if latest is None or not (self.runs_dir / latest).is_dir():
            blockers.append("No successful run to sign; run the analysis first.")
        elif self.record.latest_run_state_hash != self._case_state_hash():
            blockers.append(
                "The case changed after the latest run (evidence, settings or custody log); "
                "re-run the analysis before signing."
            )
        return blockers

    def mark_signed(
        self,
        *,
        signed_by: str | None = None,
        signature_plugin: SignaturePlugin | None = None,
    ) -> dict[str, Any]:
        """Freeze the Case and write ``report/signed.json`` (spec §6).

        ``signature_plugin`` is an optional :class:`~bitig.signatures
        .SignaturePlugin` that wraps the base chain-of-custody payload
        with an additional cryptographic binding (e.g. an HMAC or an
        HSM-backed signature). The default (``None``) keeps the
        chain-of-custody-only behaviour.

        Refuses (:class:`CaseError`) unless :meth:`sign_blockers` is empty.
        The seal binds the canonical case state, the frozen ``signed.html``
        and a hash manifest of every file in the latest run. ``signed.html``
        and ``signed.json`` are written to temporary names and moved into
        place only once everything has succeeded; any failure (including an
        interrupt) removes them and leaves the case unsigned.

        Returns the (possibly plugin-augmented) ``signed.json`` payload
        as a dict.
        """
        # Lazy import so bitig.cases stays importable without the new
        # signatures module (e.g. minimal embedded use).
        from bitig.signatures import DEFAULT_SIGNATURE_PLUGIN

        blockers = self.sign_blockers()
        if blockers:
            raise CaseError("Cannot sign: " + " ".join(blockers))

        plugin = signature_plugin if signature_plugin is not None else DEFAULT_SIGNATURE_PLUGIN
        signed_at = _utcnow_iso()
        signed_by = signed_by or self.record.examiner

        signed_html = self.report_dir / _REPORT_SIGNED_HTML
        signed_json = self.report_dir / _REPORT_SIGNED
        tmp_html = signed_html.with_name(f".{signed_html.name}.tmp-{uuid.uuid4().hex}")
        tmp_json = signed_json.with_name(f".{signed_json.name}.tmp-{uuid.uuid4().hex}")

        # The signing fields are set in memory only, so the rendered report
        # shows the SIGNED banner; case.json is not touched until the seal
        # files are in place (audit 2026-09-26 N-P1.3).
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
        moved: list[Path] = []
        try:
            # Lazy import: bitig.report imports bitig.cases.
            from bitig.report.case_report import render_case_report_html

            self.report_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(tmp_html, render_case_report_html(self))

            # case_state_hash is sign-invariant (see _case_state_hash).
            # report_html_hash binds the frozen report as a SEPARATE field —
            # folding it into case_state_hash would be circular, since the
            # report footer displays case_state_hash itself. run_manifest binds
            # result.json and the figures the report embeds by path.
            payload: dict[str, Any] = {
                "signed_at": signed_at,
                "signed_by": signed_by,
                "case_state_hash": self._case_state_hash(),
                "report_html_hash": hash_file(tmp_html),
                "latest_run": self.record.latest_run,
                "run_manifest": self._run_manifest(),
                "bitig_version": __version__,
                "signature_plugin_id": plugin.id,
            }
            signed_payload = plugin.sign(payload, case=self)
            _atomic_write_text(tmp_json, json.dumps(signed_payload, indent=2))

            # A handle loaded before another one signed the case must not
            # overwrite that seal: refuse before moving any file into place.
            self._check_not_stale()
            os.replace(tmp_html, signed_html)
            moved.append(signed_html)
            os.replace(tmp_json, signed_json)
            moved.append(signed_json)
            self.save()  # persist signed=True last
        except BaseException:
            (
                self.record.signed,
                self.record.signed_at,
                self.record.signed_by,
                self.record.signature_plugin_id,
            ) = prev
            for path in (tmp_html, tmp_json, *moved):
                path.unlink(missing_ok=True)
            raise

        return signed_payload

    def _run_manifest(self) -> dict[str, str]:
        """``{path relative to the case root: sha256}`` for every file in the latest run."""
        if self.record.latest_run is None:
            return {}
        run_dir = self.runs_dir / self.record.latest_run
        _ensure_within(run_dir, self.runs_dir)
        return {
            p.relative_to(self.root).as_posix(): hash_file(p)
            for p in sorted(run_dir.rglob("*"))
            if p.is_file()
        }

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
        state: dict[str, Any] = {
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
        # Added in 0.3.2; included only when present so seals made by earlier
        # versions keep reproducing their case_state_hash.
        if r.custody_log:
            state["custody_log"] = r.custody_log
        if r.forked_from is not None:
            state["forked_from"] = r.forked_from
        return state

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
        if self.record.signed:
            return hash_file(signed_html) if signed_html.is_file() else None
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

        checks.append(self._run_outputs_check(payload))

        # A file copied into evidence/ by hand is neither analysed nor sealed;
        # flag it so nobody mistakes it for covered evidence (N-P1.7).
        stray = self.unregistered_evidence_files()
        checks.append(
            SealCheck(
                "unregistered_files",
                not stray,
                "no unregistered files under evidence/"
                if not stray
                else "NOT covered by the seal (never registered): " + ", ".join(stray),
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

        checks.append(self._signer_check(payload))
        checks.append(self._signature_check(payload, signature_key))

        return SealVerification(
            signed=True,
            checks=checks,
            plugin_id=str(payload.get("signature_plugin_id") or "null"),
        )

    def _signer_check(self, payload: dict[str, Any]) -> SealCheck:
        """case.json's signer / time must match the sealed ones (shown by status and GUI)."""
        mismatched = [
            field_name
            for field_name in ("signed_by", "signed_at")
            if getattr(self.record, field_name) != payload.get(field_name)
        ]
        if mismatched:
            return SealCheck(
                "signer",
                False,
                f"case.json {', '.join(mismatched)} differ from {_REPORT_SIGNED}",
            )
        return SealCheck("signer", True, f"signed by {payload.get('signed_by')!r}")

    def _run_outputs_check(self, payload: dict[str, Any]) -> SealCheck:
        """Compare the sealed run-output manifest with the files on disk (N-P1.5)."""
        sealed = payload.get("run_manifest")
        sig = payload.get("signature")
        if isinstance(sig, dict) and int(sig.get("scheme", 1)) < 2:
            # A scheme-1 HMAC does not cover run_manifest, so a manifest in
            # such a seal could have been added after signing.
            sealed = None
        if not isinstance(sealed, dict):
            return SealCheck(
                "run_outputs",
                False,
                "legacy seal: run outputs (result.json, figures) are not covered; "
                "re-verify by forking and re-signing",
            )
        if payload.get("latest_run") != self.record.latest_run:
            return SealCheck(
                "run_outputs",
                False,
                f"latest run changed: sealed {payload.get('latest_run')!r}, "
                f"case.json {self.record.latest_run!r}",
            )
        current = self._run_manifest()
        changed = sorted(k for k in sealed if current.get(k) != sealed[k])
        added = sorted(set(current) - set(sealed))
        if changed or added:
            detail = []
            if changed:
                detail.append("altered/missing: " + ", ".join(changed))
            if added:
                detail.append("added: " + ", ".join(added))
            return SealCheck("run_outputs", False, "; ".join(detail))
        return SealCheck("run_outputs", True, f"{len(sealed)} run file(s) match sealed hashes")

    def _signature_check(
        self, payload: dict[str, Any], signature_key: bytes | str | None
    ) -> SealCheck:
        """Check the cryptographic signature without trusting ``signed.json`` (audit N-P0.2).

        ``signed.json`` and ``case.json`` are both editable by anyone with
        write access, so neither may downgrade the seal on its own:

        * the plugin ids recorded in the two files must agree;
        * a non-Null plugin id with a missing signature fails;
        * a verifier passing ``signature_key`` explicitly always requires a
          valid HMAC, whatever plugin id the files claim;
        * a key found only in ``$BITIG_SIGNATURE_KEY`` checks HMAC seals, but
          does not fail a Null seal: the result stays ``unsigned`` (never
          ``verified``) with a note that a removed signature looks the same.
        """
        from bitig.signatures import verify_hmac_signature

        payload_plugin = payload.get("signature_plugin_id") or "null"
        record_plugin = self.record.signature_plugin_id or "null"
        sig = payload.get("signature")
        env_key = os.environ.get("BITIG_SIGNATURE_KEY")
        key = signature_key or env_key

        if payload_plugin != record_plugin:
            return SealCheck(
                "signature",
                False,
                f"plugin mismatch: {_REPORT_SIGNED} says {payload_plugin!r}, "
                f"case.json says {record_plugin!r}",
            )
        null_seal = payload_plugin == "null" and sig is None
        if key and not (signature_key is None and null_seal):
            ok = verify_hmac_signature(payload, key=key)
            if ok:
                return SealCheck("signature", True, "HMAC signature valid")
            if sig is None:
                return SealCheck(
                    "signature",
                    False,
                    "a signature key was supplied but the seal carries no signature",
                )
            return SealCheck(
                "signature", False, "HMAC signature INVALID (wrong key or tampered payload)"
            )
        if payload_plugin == "null":
            if sig is not None:
                return SealCheck(
                    "signature", False, "Null plugin seal unexpectedly carries a signature"
                )
            detail = (
                "UNSIGNED (Null plugin): hashes only — anyone with write access can "
                "recompute them, so this seal is not tamper-evident"
            )
            if env_key:
                detail += (
                    "; $BITIG_SIGNATURE_KEY is set: if this case was signed with HMAC, "
                    "its signature has been removed"
                )
            return SealCheck("signature", True, detail)
        if sig is None:
            return SealCheck(
                "signature", False, f"plugin {payload_plugin!r} recorded but signature is missing"
            )
        if payload_plugin == "hmac":
            return SealCheck(
                "signature",
                False,
                "CANNOT VERIFY: HMAC signature present but no key provided "
                "(pass signature_key= or set BITIG_SIGNATURE_KEY)",
                unverifiable=True,
            )
        return SealCheck("signature", False, f"unknown signature plugin {payload_plugin!r}")

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
    acknowledge_mismatch: str | None = None,
) -> Case:
    """Clone an existing Case into an unsigned descendant (spec §6).

    Evidence files and the control-corpus reference carry over, as do the
    recipe and overrides. Runs, report draft, and the signed state do not.
    The new Case is created under ``cases_root`` (defaults to the parent of
    ``src_dir``, mirroring the source layout) and is freshly hashed.

    If the source's evidence no longer matches its registered hashes, the
    fork is refused: copying would re-hash altered files into a clean chain
    of custody (audit 2026-09-26 N-P1.4). Passing ``acknowledge_mismatch``
    (the reason) allows it. Every fork records ``forked_from`` — the parent
    id, its registered hashes and any mismatch with the acknowledgement —
    which is part of the sealed case state and printed in the report.

    Raises :class:`CaseError` if the destination already exists.
    """
    source = Case.load(src_dir)
    if cases_root is None:
        cases_root = source.root.parent

    mismatches = [m.path for m in source.verify_custody()]
    reason = (acknowledge_mismatch or "").strip()
    if mismatches and not reason:
        raise CaseError(
            f"Source case {source.record.id!r} has a chain-of-custody mismatch on "
            + ", ".join(mismatches)
            + ". Forking would register the altered files under fresh hashes; pass an "
            "acknowledgement reason to fork anyway (it is recorded in the fork)."
        )
    forked_from: dict[str, Any] = {
        "case_id": source.record.id,
        "at": _utcnow_iso(),
        "case_state_hash": source._case_state_hash(),
        "evidence": [
            {"role": e.role, "path": e.path, "sha256": e.sha256}
            for e in source.record.evidence.all_files()
        ],
        "custody_mismatches": mismatches,
    }
    if mismatches:
        forked_from["acknowledged_reason"] = reason

    forked = Case.create(
        cases_root,
        id=new_id,
        title=title if title is not None else f"{source.record.title} (fork of {source.record.id})",
        examiner=examiner if examiner is not None else source.record.examiner,
        recipe=source.record.recipe,
        overrides=dict(source.record.overrides),
    )

    omitted: list[str] = []
    for entry in source.record.evidence.all_files():
        src_file = source.root / entry.path
        if not src_file.is_file():
            # Only reachable with an acknowledged mismatch: a missing file
            # cannot be carried over, so the fork records it as omitted.
            omitted.append(entry.path)
            continue
        forked.add_evidence(
            src_file,
            role=entry.role,
            author=entry.author,
            year=entry.year,
            dest_name=Path(entry.path).name,
        )
    if omitted:
        forked_from["omitted_missing"] = omitted
    if source.record.evidence.control is not None:
        c = source.record.evidence.control
        forked.set_control_corpus(c.corpus_id, n_docs=c.n_docs)

    forked.record.forked_from = forked_from
    forked.save()
    return forked


def scan_cases(root: Path) -> tuple[list[Case], list[tuple[Path, str]]]:
    """Every readable Case under ``root`` (one level deep), and the unreadable ones.

    Returns ``(cases, problems)`` where ``problems`` lists ``(directory,
    reason)`` for case directories whose ``case.json`` is malformed or
    rejected by :meth:`Case.load`; one bad case no longer aborts the whole
    listing (audit 2026-09-26 P2). Directories without ``case.json`` are not
    cases and are skipped silently.
    """
    root = Path(root)
    if not root.is_dir():
        return [], []
    cases: list[Case] = []
    problems: list[tuple[Path, str]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / _CASE_JSON).is_file():
            continue
        try:
            cases.append(Case.load(child))
        except (CaseError, KeyError, TypeError, ValueError, OSError) as exc:
            problems.append((child, f"{type(exc).__name__}: {exc}"))
    return cases, problems


def list_cases(root: Path) -> list[Case]:
    """Every readable Case under ``root`` (one level deep), alphabetical by id.

    Unreadable case directories are skipped with a warning; use
    :func:`scan_cases` to get them.
    """
    cases, problems = scan_cases(root)
    for path, reason in problems:
        _log.warning("skipping unreadable case %s: %s", path, reason)
    return cases


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
    "scan_cases",
]
