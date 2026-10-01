# Forensic Lab: the Case workflow

*Use when:* one investigation has to be kept together: the evidence files with their
hashes, the analysis settings, every run, and a report that is frozen and sealed at the
end.
*Don't use when:* you are exploring a corpus or comparing methods. Use `bitig run` with
a `study.yaml` ([Concepts](../concepts/index.md)) or the forensic API pages linked below.
*Expect:* one directory per case. bitig refuses to run or sign while evidence is changed,
missing or unregistered, and `bitig case verify` re-checks the sealed case later.

A **Case** is the unit of the Forensic Lab. The GUI (`bitig gui`, then *Forensic Lab →*)
leads you through five steps: Evidence, Method, Run, Findings and Report. The `bitig case`
commands work on the same directories, and so does the Python class `bitig.cases.Case`.

!!! warning "What the seal does and does not prove"
    By default a signed case is sealed with **hashes only** (the *Null* plugin). Anyone who
    can write to the case directory can change it and recompute every hash, so a Null seal
    is an integrity record, **not** evidence against tampering. You need the HMAC plugin,
    a secret key, and a verifier who holds that key for a tamper-evident seal (see
    [Null vs HMAC](#null-vs-hmac)).

## Case layout

Cases live under `~/.bitig/cases/` by default. Each CLI command takes `--cases-dir` to
use another root. The GUI always uses the default root.

```text
<cases-dir>/<case-id>/
├── case.json              # the case record (never edit by hand)
├── study.yaml             # resolved analysis config, generated from the recipe
├── evidence/
│   ├── questioned/        # disputed documents
│   ├── known/             # documents of known authorship
│   └── control/           # created empty; not used by the analysis
├── runs/
│   ├── <run-id>/          # one directory per run (UTC timestamp)
│   └── latest -> <run-id> # symlink, where the filesystem supports it
└── report/
    ├── draft.html         # working report of an unsigned case
    ├── signed.html        # frozen report, written at signing
    └── signed.json        # the seal
```

The case id has to be a single path component (`[A-Za-z0-9._-]+`). `case.json` holds:

- identity: `id`, `title`, `examiner`, `created_at`
- settings: `recipe`, `mode`, `overrides`
- the registered evidence (path, `sha256`, whitespace token count, role, author)
- `study_hash`, `corpus_hash`, `runs`, `latest_run` and `latest_run_state_hash`
- the signing fields
- the append-only `custody_log`
- `forked_from`

bitig loads `case.json` as untrusted input. Evidence paths and run ids that would point
outside the case directory are rejected. A case handle refuses to save over a
`case.json` that changed after it was loaded; reload the case in that situation.

## Recipes and mode

A case is created with a **recipe**, which is a named question with default features and
methods. `bitig case new` uses `imposters_lr` unless you pass `--recipe`.

| Recipe id | Question | Mode |
|---|---|---|
| `imposters_lr` | Did this person write this? (General Impostors verification) | forensic |
| `delta_attribution` | Which author, out of N? | research |
| `exploration` | How is this corpus structured? (PCA + hierarchical clustering) | research |
| `zeta_contrast` | What distinguishes group A from group B? | research |
| `bayesian` | Bayesian author posterior over N candidates | research |
| `custom` | Hand-edited study (GUI *Custom* tile) | derived |

The mode is derived, never chosen. A study with any `verify` method is **forensic**, and
every other study is **research**. The mode selects the report template.

You change parameters (for example *Candidate author*, MFW size, iterations, seed) in the
GUI's Method step or with `Case.set_param` in Python. There is no CLI command for them.
Either route regenerates `study.yaml` and records its hash. A `study.yaml` edited outside
bitig is detected: runs and signing refuse it.

## Walkthrough (CLI + Python)

These commands were run as shown on bitig's development version. Nothing goes into
`~/.bitig` because every command passes `--cases-dir cases`.

**1. Make a tiny synthetic corpus.** It has two known authors and one questioned letter.

```python title="make_texts.py"
import pathlib, random

random.seed(1)
common = "the of and to a in that it is was he for on as with his at by but not".split()
styles = {
    "alice": "garden morning light quiet window letter river softly perhaps indeed".split(),
    "bob": "engine market figures report quarterly deadline budget meeting numbers".split(),
}
out = pathlib.Path("texts")
out.mkdir(exist_ok=True)
for name, style in [("alice_1", "alice"), ("alice_2", "alice"),
                    ("bob_1", "bob"), ("bob_2", "bob"), ("letter", "alice")]:
    words = random.choices(common * 2 + styles[style], k=400)
    (out / f"{name}.txt").write_text(" ".join(words) + ".\n", encoding="utf-8")
```

**2. Create the case and register the evidence.**

```bash
python make_texts.py
bitig case new letter-2026 --title "Anonymous letter" --examiner "J. Doe" --cases-dir cases
bitig case add-evidence letter-2026 texts/letter.txt --role questioned --cases-dir cases
bitig case add-evidence letter-2026 texts/alice_1.txt texts/alice_2.txt \
    --role known --author Alice --cases-dir cases
bitig case add-evidence letter-2026 texts/bob_1.txt texts/bob_2.txt \
    --role known --author Bob --cases-dir cases
bitig case status letter-2026 --cases-dir cases
```

```text
registered evidence/questioned/letter.txt  sha256=5d57c5c6828e…
...
  evidence:  questioned=1, known=4, control=none
  runs:      0
  custody: OK
```

**3. Run the analysis.** The CLI has **no** `case run` command. Use the GUI's Run step, or
call `perform_run` from Python:

```python title="run_case.py"
from bitig.case_run import perform_run
from bitig.cases import Case

case = Case.load("cases/letter-2026")
case.set_param("methods[verify].candidate", "Alice")  # author label of the suspect
case.set_param("methods[verify].mfw_n", 50)           # tiny demo texts
outcome = perform_run(case)
print(outcome.status, "-", outcome.message)
```

```text
$ python run_case.py
succeeded - All 1 method(s) succeeded.
```

**4. Sign and verify.**

```bash
bitig case sign letter-2026 --cases-dir cases
bitig case verify letter-2026 --cases-dir cases
```

```text
  ✓ case_state_hash: matches sealed value
  ✓ report_html_hash: report matches sealed value
  ✓ run_outputs: 4 run file(s) match sealed hashes
  ✓ unregistered_files: no unregistered files under evidence/
  ✓ evidence_custody: all evidence files match registered hashes
  ✓ signer: signed by 'J. Doe'
  ✓ signature: UNSIGNED (Null plugin): hashes only — anyone with write access can
recompute them, so this seal is not tamper-evident
hashes consistent — but letter-2026 is UNSIGNED (Null plugin): this is not evidence
against tampering by anyone with write access. Sign with --signature-plugin hmac for a
tamper-evident seal.
```

**5. Continue in a fork.** The signed case is now read-only.

```bash
bitig case fork letter-2026 letter-2026-b --cases-dir cases
bitig case list --cases-dir cases
```

## Evidence and chain of custody

### Roles

| Role | How to add | Notes |
|---|---|---|
| `questioned` | `bitig case add-evidence <id> <files…> --role questioned` | Disputed documents. By default, verification targets every questioned document. |
| `known` | `bitig case add-evidence <id> <files…> --role known --author <label>` | The CLI and the GUI require an author label. Verification groups known texts by author. |
| `control` | GUI Evidence step, forensic cases only (`Case.set_control_corpus`) | Only a reference (`corpus_id`, `n_docs`). **No runner uses it.** Reports list it as "not used by the analysis". |

`add-evidence` copies each file into `evidence/<role>/`, hashes it with SHA-256 and
records it in `case.json`. It refuses:

- a destination file that already exists;
- a file stem that is already registered under the other role. The stem is the document
  id in the run, so `questioned/alice.txt` and `known/alice.txt` cannot both exist;
- any change to a signed case.

**Only registered files are analysed and sealed.** A run builds its corpus from the
registered entries and re-hashes each file as it reads it. It never globs `evidence/`.
A file copied into `evidence/` by hand is ignored. `bitig case status` lists such files
as unregistered, and `bitig case verify` fails its `unregistered_files` check.

### Custody checks and mismatches

bitig re-hashes every registered file and compares the result with the recorded
`sha256`. A missing file also counts as a mismatch. While any mismatch exists:

- `bitig case status` lists the files and exits with code **2**;
- a run is **blocked**;
- signing is refused;
- forking is refused unless you acknowledge the mismatch (see [Forking](#forking)).

What to do next depends on the cause.

**The file changed for a legitimate reason** (for example a re-export with different line
endings). Re-acknowledge it and give the reason:

```bash
bitig case reacknowledge letter-2026-b evidence/known/bob_1.txt \
    --reason "Re-exported by the client" --cases-dir cases
```

```text
re-acknowledged evidence/known/bob_1.txt: 5d9655fb4ba4… → f4b35d03c52f… by J. Doe
  Re-run the analysis before signing.
```

This adds an entry to `custody_log` with `at`, `by` (default: the examiner, or `--by`),
`path`, `old_sha256`, `new_sha256` and `reason`, and registers the new hash. The custody
log is part of the sealed case state and appears in the report under *Re-acknowledged
evidence changes*. It also changes the case state, so you must re-run before signing.
bitig refuses to re-acknowledge:

- without a reason;
- an unregistered path or an unchanged file;
- a signed case;
- a **missing** file. Fork the case instead.

The GUI Evidence step has a *Re-acknowledge* button on each mismatched card.

**The file is missing or should not have changed.** Fork the case and record your
reason (see [Forking](#forking)).

## Running the analysis

`bitig.case_run.perform_run(case)` drives the GUI's Run step. It checks these guards in
order and returns `blocked` with a message at the first one that fails:

1. the case is signed;
2. a custody mismatch exists;
3. `study.yaml` was modified outside bitig;
4. the study configuration is invalid;
5. for `verify` methods:
    - at least one questioned document is registered;
    - every known document has an author label;
    - the *Candidate author* parameter is set and matches a known author;
    - there is at least one other author, who serves as the impostors.

After the guards pass, bitig regenerates `study.yaml`, builds the corpus from registered
evidence and records the case-state hash the run is computed on. The run writes to
`runs/<UTC timestamp>/`. The outcome `status` is one of these:

| Status | Meaning |
|---|---|
| `succeeded` | Every method produced a result; the run becomes `latest_run`. |
| `partial` | Some methods wrote `error.txt`; the run is still recorded. |
| `failed` | No method succeeded; the run directory stays on disk but is **not** recorded. |
| `blocked` | A guard refused the run; nothing was executed. |

!!! note "Set verification parameters after registering all questioned documents"
    When `target_ids` is empty, the `verify` method targets every registered questioned
    document. But `Case.set_param` (and the GUI drawer) saves the whole resolved method
    into `overrides`, including the `target_ids` in effect at that moment. A questioned
    document registered later is then **not** a target, and it has no author label, so
    General Impostors fails with "some training documents lack metadata column 'author'".
    Register all questioned documents first, or set `methods[verify].target_ids`
    explicitly afterwards.

## Reports

`bitig.report.case_report.build_case_report(case)` renders `report/draft.html` for an
unsigned case. The GUI Report step shows it. The forensic or research template is chosen
by the case mode.

- **Forensic report**:
    - question, headline scalars, method paragraph and figures;
    - chain of custody (role, file, tokens, hash), re-acknowledged changes and the fork
      note;
    - provenance footer (corpus, feature and study hashes, seed, bitig version) and the
      case hash.

  For `imposters_lr` the report gives one **General Impostors score per questioned
  document**, next to the chance level. It labels the score as uncalibrated, **not a
  likelihood ratio**, with no ENFSI verbal scale. A likelihood ratio, Hp/Hd hypotheses
  and the verbal scale appear only when the result actually contains a calibrated `lr`
  or `log_lr`. See [Calibration](calibration.md) for how to obtain one.
- **Research report**: research question (the recipe), headline result, methods, figures,
  the registered evidence and the custody log.

`build_case_report(case, format="pdf")` writes `report/final.pdf` with WeasyPrint. This
needs `pip install "bitig[reports]"`, and the GUI has an *Export PDF* button for it. For
a signed case, both functions serve the frozen `signed.html` and never re-render it.
They **refuse** to export when the seal no longer reproduces. The HMAC signature itself
is not checked during export.

## Signing and sealing

```bash
bitig case sign <id> [--signed-by NAME] [--signature-plugin null|hmac] --cases-dir cases
```

Signing is refused (`Cannot sign: …`) unless all of these hold:

- evidence is registered;
- custody is intact;
- `study.yaml` is unedited;
- a successful run exists;
- that run was computed on the **current** case state. Re-acknowledging evidence or
  changing settings after the run means you must re-run first.

Signing renders the report with the SIGNED banner and freezes it as `report/signed.html`.
It also writes `report/signed.json`:

| Field | What it binds |
|---|---|
| `case_state_hash` | SHA-256 over identity, examiner, recipe, overrides, the `study.yaml` hash, every evidence entry (role, path, hash, tokens, author), the control reference, the custody log and `forked_from` |
| `report_html_hash` | the frozen `signed.html` |
| `latest_run`, `run_manifest` | the hash of every file in the **latest** run directory (results, tables, figures, resolved config) |
| `signed_at`, `signed_by`, `signature_plugin_id`, `bitig_version` | who signed, when and how |

Signing is atomic. The seal files are written under temporary names and moved into place
first, and `case.json` gets `signed: true` last. If anything fails, the case stays
unsigned. After signing, the case is **read-only**: adding evidence, changing parameters,
running and re-acknowledging are all refused with "Fork it for further work". Earlier
runs, `draft.html` and an exported `final.pdf` are not covered by the seal.

### Null vs HMAC

| | Null (default) | HMAC (`--signature-plugin hmac`) |
|---|---|---|
| What it adds | nothing: hashes only | an HMAC-SHA256 `signature` block (`scheme: 2`) over the whole `signed.json` payload, signer included, plus a key fingerprint |
| Key | none | a shared secret from `BITIG_SIGNATURE_KEY` (signing fails without it) |
| Tamper-evident? | **No.** Anyone with write access can edit the case and recompute every hash. | Yes, against anyone who does not hold the key. It is a shared-secret scheme, not a public-key or hardware-backed signature. |
| `verify` verdict when intact | `hashes consistent — but … is UNSIGNED (Null plugin)` (exit 0) | `seal verified — … is intact` (exit 0), only when the key is supplied |

```bash
export BITIG_SIGNATURE_KEY="change-me"      # keep the real key out of shell history
bitig case sign letter-2026-b --signature-plugin hmac --cases-dir cases
```

The GUI's *Sign & lock* button always uses the **Null** plugin. Use the CLI for an HMAC
seal.

### Verifying a seal

```bash
bitig case verify <id> [--key KEY] --cases-dir cases
```

`verify` recomputes every sealed quantity from disk. Each check prints `✓` or `✗`:

| Check | Fails when |
|---|---|
| `case_state_hash` | anything in the canonical case state changed |
| `report_html_hash` | `signed.html` changed or is missing |
| `run_outputs` | a file in the sealed run was altered, removed or added; `latest_run` changed; or the seal predates `run_manifest` ("legacy seal", bitig 0.3.1 and earlier) |
| `unregistered_files` | a file under `evidence/` was never registered (it is **not** covered by the seal) |
| `evidence_custody` | an evidence file no longer matches its registered hash, or is missing |
| `signer` | `signed_by` / `signed_at` in `case.json` differ from `signed.json` |
| `signature` | plugin ids in `case.json` and `signed.json` disagree; an HMAC signature is missing, invalid or cannot be checked without a key; or a key was supplied but the seal has no signature |

Exit codes: **0** when every check passes, **1** when the case is not signed, **2** when
any check fails. A **Null** seal passes with exit 0 and the "UNSIGNED … not
tamper-evident" warning shown in the walkthrough. Scripts that need tamper evidence must
not treat exit 0 alone as proof.

For an HMAC seal, pass `--key` or set `BITIG_SIGNATURE_KEY`. Without a key, verification
fails (`HMAC signature present but no key provided`). With the wrong key it fails with
`HMAC signature INVALID`. Whenever a key is supplied, a valid HMAC is **required**, so a
stripped or downgraded signature cannot pass. This also means that a Null-sealed case
fails verification while `BITIG_SIGNATURE_KEY` is set in your environment.

`bitig case status` on a signed case also warns when the seal no longer reproduces. That
warning skips the signature check. The GUI Report step has a *Verify seal* dialog, which
accepts an optional key for HMAC seals.

## Forking

```bash
bitig case fork <id> <new-id> [--title T] [--examiner E] \
    [--acknowledge-mismatch "reason"] --cases-dir cases
```

A fork is a new, unsigned case. It copies:

- the recipe and overrides;
- the control reference;
- every registered evidence file, which is re-registered.

Runs, reports and the signed state are not copied. Every fork records `forked_from`:

- the parent id, the time and the parent's `case_state_hash`;
- the parent's registered evidence hashes;
- any custody mismatches.

`forked_from` is part of the fork's sealed state, and the report prints a note about it.

If the source fails custody, the fork is **refused**: copying would give the altered
files fresh hashes in a clean case. `--acknowledge-mismatch "<reason>"` allows the fork
and stores the reason as `acknowledged_reason`. Files that are missing from the source
cannot be copied and are listed as `omitted_missing`.

```text
$ bitig case fork demo demo-2 --cases-dir cases
error: Source case 'demo' has a chain-of-custody mismatch on evidence/known/bob_2.txt.
Forking would register the altered files under fresh hashes; pass an acknowledgement
reason to fork anyway (it is recorded in the fork).
```

The GUI has no fork button. Its messages point to `bitig case fork`.

## Listing and inspecting cases

| Command | Shows |
|---|---|
| `bitig case list` | a table of every case under `--cases-dir` (id, mode, recipe, evidence count, runs, signed, title). Unreadable cases are reported and skipped. |
| `bitig case open <id>` | path, mode, recipe, examiner, signed state, latest run |
| `bitig case status <id>` | all record fields, hashes, the evidence inventory, a custody check (`--no-verify` skips it; exit 2 on mismatch) and unregistered files; a seal warning for signed cases |

## In the GUI

`bitig gui` requires `pip install "bitig[gui]"`. Open *Forensic Lab →* to reach the case
list (`/case`) and *New case*. The five steps are:

- **Evidence**: register questioned and known files (known files need an author label),
  set the control reference, see custody status and re-acknowledge changed files. *Add
  file* uses the native file picker, so it is disabled under `--no-native`.
- **Method**: choose a recipe tile, edit its parameters in the drawer, or open the
  *Custom* editor for `study.yaml`.
- **Run**: runs `perform_run` and lists the methods that succeeded or failed.
- **Findings**: shows the latest run's results.
- **Report**: shows the draft report and has *Export PDF*, *Sign & lock* (Null plugin
  only) and *Verify seal* (optional HMAC key).

## Read next

- [Verification](verification.md): the General Impostors method behind `imposters_lr`
- [Calibration & LR output](calibration.md): turning scores into likelihood ratios
- [Reporting](reporting.md): the standalone forensic report outside the Case workflow
