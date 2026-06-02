"""``bitig case [new|open|list|status|fork|sign]`` — manage Forensic Lab Cases.

Each subcommand is a thin wrapper over ``bitig.cases``. See
``design/forensic-lab.md`` §7 step 3 for where this sits in the build
sequence; the GUI step 4 will share the same ``bitig.cases`` API, so any
behaviour exposed here also lives in the GUI.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from bitig.cases import (
    DEFAULT_CASES_DIR,
    Case,
    CaseError,
    fork_case,
    list_cases,
)
from bitig.recipes import RECIPES
from bitig.signatures import SIGNATURE_PLUGINS, get_signature_plugin

console = Console()

case_app = typer.Typer(
    name="case",
    help="Manage Forensic Lab Cases (evidence, recipe, runs, signed report).",
    no_args_is_help=True,
)


def _cases_dir_option() -> Path:
    """``--cases-dir`` default. Wrapped in a function so the home dir is
    looked up at invocation time (matters in tests that monkeypatch HOME).
    """
    return DEFAULT_CASES_DIR


def _resolve_case(cases_dir: Path, case_id: str) -> Case:
    """Load ``<cases_dir>/<case_id>`` or exit with a helpful message."""
    case_dir = cases_dir / case_id
    try:
        return Case.load(case_dir)
    except CaseError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


@case_app.command("new")
def case_new(
    id: str = typer.Argument(..., help="Case slug (used as directory name)."),
    title: str = typer.Option(..., "--title", help="Human-readable case title."),
    examiner: str = typer.Option(
        ..., "--examiner", help="Examiner name (recorded on the signed report)."
    ),
    recipe: str = typer.Option(
        "imposters_lr",
        "--recipe",
        help=f"Recipe id. One of: {', '.join(sorted(RECIPES))}, or 'custom'.",
    ),
    cases_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_CASES_DIR,
        "--cases-dir",
        help="Root directory holding all cases (default: ~/.bitig/cases/).",
    ),
) -> None:
    """Create a new Case directory under ``--cases-dir``."""
    try:
        case = Case.create(
            cases_dir,
            id=id,
            title=title,
            examiner=examiner,
            recipe=recipe,
        )
    except (CaseError, KeyError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]created case[/green] {case.record.id} "
        f"([cyan]{case.record.mode}[/cyan] / recipe={case.record.recipe}) at {case.root}"
    )
    console.print("  next:")
    console.print(f"    bitig case status {case.record.id}")
    if case.record.mode == "forensic":
        console.print("  drop questioned/known files into:")
        console.print(f"    {case.evidence_dir}/")
    console.print(f"  resolved study config: {case.study_yaml_path}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@case_app.command("list")
def case_list(
    cases_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_CASES_DIR, "--cases-dir", help="Cases root (default: ~/.bitig/cases/)."
    ),
) -> None:
    """List every Case under ``--cases-dir`` in a Rich table."""
    cases = list_cases(cases_dir)
    if not cases:
        console.print(f"[yellow]no cases found under[/yellow] {cases_dir}")
        return

    table = Table(title=f"Cases under {cases_dir}")
    table.add_column("id", style="bold")
    table.add_column("mode")
    table.add_column("recipe")
    table.add_column("evidence", justify="right")
    table.add_column("runs", justify="right")
    table.add_column("signed")
    table.add_column("title")

    for c in cases:
        r = c.record
        n_evidence = len(r.evidence.questioned) + len(r.evidence.known)
        signed_marker = "[green]✓[/green]" if r.signed else ""
        mode_style = "[bold yellow]forensic[/bold yellow]" if r.mode == "forensic" else "research"
        table.add_row(
            r.id,
            mode_style,
            r.recipe,
            str(n_evidence),
            str(len(r.runs)),
            signed_marker,
            r.title,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# open
# ---------------------------------------------------------------------------


@case_app.command("open")
def case_open(
    id: str = typer.Argument(..., help="Case id to open."),
    cases_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_CASES_DIR, "--cases-dir"
    ),
) -> None:
    """Print the case path + one-line summary.

    Intended as the shell-side "enter the Case" hook; the GUI build will
    use the same Case.load() under the hood, so behaviour stays consistent.
    """
    case = _resolve_case(cases_dir, id)
    r = case.record
    console.print(f"[bold]{r.id}[/bold] — {r.title}")
    console.print(f"  path:     {case.root}")
    console.print(f"  mode:     {r.mode}")
    console.print(f"  recipe:   {r.recipe}")
    console.print(f"  examiner: {r.examiner}")
    console.print(f"  signed:   {'yes' if r.signed else 'no'}")
    if r.latest_run:
        console.print(f"  latest run: {r.latest_run}")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@case_app.command("status")
def case_status(
    id: str = typer.Argument(..., help="Case id."),
    cases_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_CASES_DIR, "--cases-dir"
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Run a chain-of-custody check against the evidence files on disk.",
    ),
) -> None:
    """Full Case status: record fields, evidence inventory, custody check.

    Exits with code 2 if a custody mismatch is found (so CI / scripts can
    treat tampered cases as a hard failure).
    """
    case = _resolve_case(cases_dir, id)
    r = case.record

    console.print(f"[bold]{r.id}[/bold] — {r.title}")
    console.print(f"  created:   {r.created_at}")
    console.print(f"  examiner:  {r.examiner}")
    console.print(f"  mode:      [cyan]{r.mode}[/cyan]")
    console.print(f"  recipe:    {r.recipe}")
    console.print(f"  signed:    {'[green]yes[/green]' if r.signed else 'no'}")
    if r.signed:
        console.print(f"    signed_at: {r.signed_at}")
        console.print(f"    signed_by: {r.signed_by}")
    console.print(f"  hashes:    study={r.study_hash[:12]}…  corpus={r.corpus_hash[:12]}…")
    console.print(
        f"  evidence:  questioned={len(r.evidence.questioned)}, "
        f"known={len(r.evidence.known)}, "
        f"control={'set' if r.evidence.control else 'none'}"
    )
    if r.evidence.control is not None:
        console.print(
            f"    control: id={r.evidence.control.corpus_id}, n_docs={r.evidence.control.n_docs}"
        )
    console.print(
        f"  runs:      {len(r.runs)}" + (f" (latest={r.latest_run})" if r.latest_run else "")
    )

    if r.signed:
        # Warn if the sealed state can no longer be reproduced (audit P1.1).
        seal = case.verify_seal()
        broken = [c for c in seal.checks if not c.ok and c.name != "signature"]
        if broken:
            console.print(
                "  [red]⚠ seal cannot be reproduced — run `bitig case verify` for detail:[/red]"
            )
            for c in broken:
                console.print(f"    [red]✗ {c.name}: {c.detail}[/red]")

    if verify:
        mismatches = case.verify_custody()
        if mismatches:
            console.print(
                "[red]custody mismatch — the following files no longer match their registered hash:[/red]"
            )
            for m in mismatches:
                console.print(f"  - {m.path}  ([yellow]role={m.role}[/yellow])")
            raise typer.Exit(code=2)
        console.print("  [green]custody: OK[/green]")


# ---------------------------------------------------------------------------
# fork
# ---------------------------------------------------------------------------


@case_app.command("fork")
def case_fork(
    id: str = typer.Argument(..., help="Source case id."),
    new_id: str = typer.Argument(..., help="New case id (must not already exist)."),
    cases_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_CASES_DIR, "--cases-dir"
    ),
    title: str | None = typer.Option(
        None,
        "--title",
        help="Title for the forked case (default: '<source title> (fork of <id>)').",
    ),
    examiner: str | None = typer.Option(
        None,
        "--examiner",
        help="Examiner for the forked case (default: copy from source).",
    ),
) -> None:
    """Clone a Case into an unsigned descendant for further iteration (spec §6)."""
    src_dir = cases_dir / id
    try:
        forked = fork_case(src_dir, new_id, title=title, examiner=examiner)
    except (CaseError, FileNotFoundError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[green]forked[/green] {id} → {forked.record.id} at {forked.root} (signed=no, runs=0)"
    )


# ---------------------------------------------------------------------------
# sign
# ---------------------------------------------------------------------------


@case_app.command("sign")
def case_sign(
    id: str = typer.Argument(..., help="Case id to sign."),
    signed_by: str | None = typer.Option(
        None, "--signed-by", help="Override signer name (default: case examiner)."
    ),
    signature_plugin: str | None = typer.Option(
        None,
        "--signature-plugin",
        help=(
            "Optional cryptographic signature plugin to wrap signed.json. "
            f"Available: {', '.join(sorted(SIGNATURE_PLUGINS))}. "
            "Default is chain-of-custody only (no cryptographic signature)."
        ),
    ),
    cases_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_CASES_DIR, "--cases-dir"
    ),
) -> None:
    """Sign & lock a Case (spec §6). The Case becomes read-only after this."""
    case = _resolve_case(cases_dir, id)
    try:
        plugin = get_signature_plugin(signature_plugin)
    except (KeyError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    try:
        payload = case.mark_signed(signed_by=signed_by, signature_plugin=plugin)
    except CaseError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[green]signed[/green] {case.record.id} "
        f"at {payload['signed_at']} by {payload['signed_by']}"
    )
    console.print(f"  signature plugin: {payload.get('signature_plugin_id', 'null')}")
    console.print(f"  case_state_hash:  {payload['case_state_hash']}")
    if "signature" in payload:
        sig = payload["signature"]
        console.print(
            f"  signature:        {sig['algorithm']} key_fp={sig.get('key_fingerprint', '?')}"
        )
    console.print(f"  bitig_version:    {payload['bitig_version']}")
    console.print(f"  signed.json:      {case.report_dir / 'signed.json'}")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


@case_app.command("verify")
def case_verify(
    id: str = typer.Argument(..., help="Case id to verify."),
    key: str | None = typer.Option(
        None,
        "--key",
        help="Signature key for cryptographic plugins (HMAC). Falls back to $BITIG_SIGNATURE_KEY.",
    ),
    cases_dir: Path = typer.Option(  # noqa: B008
        DEFAULT_CASES_DIR, "--cases-dir"
    ),
) -> None:
    """Verify a signed Case's chain-of-custody seal (audit P1.1).

    Recomputes every sealed quantity from disk and compares it to signed.json.
    Exit codes: 0 = seal intact, 1 = case is not signed (nothing to verify),
    2 = seal broken (tamper / mismatch). Scriptable in CI.
    """
    case = _resolve_case(cases_dir, id)
    result = case.verify_seal(signature_key=key)

    if not result.signed:
        console.print(f"[yellow]{id} is not signed — nothing to verify.[/yellow]")
        raise typer.Exit(code=1)

    for c in result.checks:
        mark = "[green]✓[/green]" if c.ok else "[red]✗[/red]"
        console.print(f"  {mark} {c.name}: {c.detail}")

    if result.ok:
        console.print(f"[green]seal verified[/green] — {case.record.id} is intact")
    else:
        console.print(f"[red]SEAL BROKEN[/red] — {case.record.id} failed verification")
        raise typer.Exit(code=2)
