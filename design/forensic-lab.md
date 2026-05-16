# bitig Forensic Lab — UI design spec

Status: locked from brainstorm session `50552-1778966027` (2026-05-17).
Mockups under `.superpowers/brainstorm/50552-1778966027/content/`:
`visual-direction.html`, `nav-ia.html`, `method-picker.html`, `findings-and-report.html`.

## 1. Decisions locked

| Decision | Choice |
|---|---|
| Visual direction | **C — Forensic Lab** (dark theme, JetBrains Mono metadata, evidence-card metaphor, LR-first surfacing). Step 5 Report is the only light-surface page. |
| Information architecture | **A — Cases-centric**. Each investigation is a first-class Case with its own corpus, method, run history, and signed report. The existing Ingest/Study/Run/Results/Forensic pages become the 5 steps *inside* a Case. |
| Method picker | **A — Recipe gallery** (5 named goals + Custom tile that opens the existing one-screen YAML form). |
| Mode (forensic vs research) | **Derived, not toggled.** No visible mode switch when creating a Case. See §3. |
| Step path | 5 fixed steps per Case: `1 · Evidence → 2 · Method → 3 · Run → 4 · Findings → 5 · Report`. |
| CLI compatibility | Unchanged. `bitig run study.yaml` continues to work without ever touching the Case concept. |

## 2. Case data model

A Case is a single directory on disk under `~/.bitig/cases/<slug>/` (configurable). Persistent.

```
~/.bitig/cases/r-v-doe/
├── case.json              # the record below
├── evidence/
│   ├── questioned/        # original files, content-addressed
│   ├── known/
│   └── control/           # impostor pool (forensic mode only)
├── study.yaml             # resolved config (recipe expansion + user overrides)
├── runs/
│   ├── 2026-05-17T12-04-21Z/   # one dir per run
│   │   ├── result.json
│   │   ├── tables/
│   │   └── figures/
│   └── latest -> 2026-05-17T12-04-21Z/
└── report/
    ├── draft.html          # editable until signed
    ├── signed.json         # present iff Sign & lock fired
    └── final.pdf           # written on Export PDF
```

`case.json` schema:

```jsonc
{
  "id": "r-v-doe",
  "title": "R v. Doe — anonymous letter authorship",
  "created_at": "2026-05-17T11:42:08Z",
  "examiner": "F. Bozdağ",
  "recipe": "imposters_lr",     // see §3
  "mode": "forensic",            // derived from recipe; not user-set
  "evidence": {
    "questioned": [{"path": "evidence/questioned/letter.txt", "sha256": "a8c2…", "tokens": 412}],
    "known":      [{"path": "evidence/known/doe_2019.txt",   "sha256": "…",   "tokens": 1847, "author": "Doe"}],
    "control":    {"corpus_id": "BUMR-AT-2024", "n_docs": 240}
  },
  "study_hash": "8e4d…",         // hash of the resolved study.yaml
  "corpus_hash": "7f3a…",
  "runs": ["2026-05-17T12-04-21Z"],
  "latest_run": "2026-05-17T12-04-21Z",
  "signed": false
}
```

Sources of truth:
- `case.json` is the canonical record. The GUI never invents fields that aren't here.
- `study.yaml` is regenerated from the recipe + user overrides; never hand-edited *inside* a Case (the Custom tile points at a YAML editor that writes `study.yaml` directly and flips `recipe` to `"custom"`).

## 3. Mode derivation rule

Recipes (see §5.2) declare a `mode` in code, not by user choice:

| Recipe id | Plain-language question | Methods | Mode |
|---|---|---|---|
| `imposters_lr` | Did *this person* write this? | General Impostors verification + LR + calibration | **forensic** |
| `delta_attribution` | Which author, out of N? | Burrows / Eder / Cosine Delta | research |
| `exploration` | How is this corpus structured? | PCA / UMAP / hierarchical | research |
| `zeta_contrast` | What distinguishes group A from B? | Craig / Eder Zeta | research |
| `bayesian` | Bayesian author posterior | Wallace–Mosteller | research |
| `custom` | (raw YAML) | anything | **forensic if the resolved study has a `verify` method; research otherwise** |

The Case writes its `mode` once, at recipe-selection time. Changing the recipe later re-derives the mode (with a confirmation dialog: "this will reset the report draft"). Sign & lock freezes the mode.

Why no toggle: a visible mode switch invites the wrong move — users in research-mode performing a verification analysis, or vice versa, with mismatched report semantics. The recipe *is* the question being asked; the mode follows from the question. The Custom tile keeps the escape hatch honest.

## 4. Visual tokens

| Token | Value | Used for |
|---|---|---|
| `--bg` | `#0d1117` | main canvas |
| `--bg-panel` | `#161b22` | cards, drawers, tile bodies |
| `--bg-deep` | `#010409` | YAML preview rail, code blocks |
| `--bg-report` | `#fafaf7` | Step 5 Report surface only |
| `--accent` | `#C9A34A` | primary action, active step, locked brass |
| `--ok` | `#3fb950` | verified, completed step, "reproducible" indicator |
| `--warn` | `#d29922` | running, attention |
| `--err` | `#f85149` | failed, chain-of-custody mismatch |
| `--info` | `#1f6feb` | research-mode tile dots, neutral hashes |
| `--text` | `#e6edf3` | primary on dark |
| `--text-2` | `#c9d1d9` | secondary on dark |
| `--text-muted` | `#7d8590` | metadata, hashes, captions, monospace headers |
| `--border` | `#30363d` | panel borders |
| `--font-mono` | `'JetBrains Mono', 'SF Mono', monospace` | hashes, IDs, paths, timestamps, stepper labels |
| `--font-sans` | `system-ui, -apple-system, 'Inter', sans-serif` | body, controls |
| `--font-serif` | `Georgia, 'Times New Roman', serif` | Step 5 Report body only — signals "document, not dashboard" |

Evidence-card pattern (used everywhere a piece of evidence is shown):

```
┌───────────────────────────────────────────┐
│ • file.txt                412 tokens · ? │  ← title + meta (mono)
│ // 7f3a… registered 2026-05-10           │  ← provenance (mono, muted)
└───────────────────────────────────────────┘
```

3px left border in accent (selected) / border (default) / err (custody mismatch).

## 5. The 5 steps

The top stepper is the same on every step:

```
1 · Evidence  ✓     2 · Method  ✓     3 · Run  ✓     4 · Findings  ▎    5 · Report →
```

Active step underlined in `--accent`. Past steps green-check, future steps muted.

### 5.1 Step 1 — Evidence

Three drop zones: `questioned/`, `known/`, `control/` (forensic mode only).

- Drag a folder or files in. Files are copied into the Case dir, hashed (SHA-256), and registered in `case.json`.
- Per-file metadata can be edited inline: author, year, role.
- Custody integrity is checked every time the Case is opened: if a registered file's hash changes on disk, that evidence card flips to `--err` and a banner blocks step 4+ until the user re-acknowledges.

### 5.2 Step 2 — Method (recipe gallery)

The six tiles from `method-picker.html`. Selecting a tile opens a side drawer with only the params that recipe cares about, plus a live `study.yaml` preview. Drawer fields are recipe-specific but share these slots:

- Feature (always)
- top-n / window / k as appropriate
- group_by column (always, if metadata present)
- seed (collapsed by default, surfaced for power users)

Custom tile opens the existing flat YAML editor (today's `ingest/study/run` form) in a slide-over panel. Closing the slide-over writes `study.yaml` and sets `recipe = "custom"`.

### 5.3 Step 3 — Run

Runs `bitig run` against the Case's resolved `study.yaml`. Streams logs into a side panel. On completion, writes a new dir under `runs/<iso-timestamp>/` and updates `latest_run`. Every artefact that lands in `runs/<…>` carries the four hashes (corpus, feature, study, seed) for chain-of-custody.

### 5.4 Step 4 — Findings (analyst's surface)

Layout per `findings-and-report.html`:

- **Headline scalar row** (forensic mode): LR · AUC · c@1 · C_llr. First tile (LR) gets the brass left-border + accent number. In research mode the headline row swaps to method-appropriate scalars (e.g. PCA: explained variance PC1 / PC2 / cumulative, plus n_features and n_docs; classification: accuracy / macro-F1 / ECE).
- **Figure gallery**: thumbnails of every PNG / HTML the run produced (`tippett`, `reliability`, `pca`, `scores`, …). Each thumbnail has a `static / interactive` toggle wired to the existing GUI plotly dispatcher (PR #37).
- **Run summary side panel**: sticky on the right. Recipe, method, feature, seed, spaCy model, elapsed, the four hashes, a green `● reproducible` indicator. Bottom: `Generate report →` (the only forward action on this step).

The Findings step is the analyst's working surface — multiple runs of the same Case can be compared here (a `Compare with…` dropdown on the run-summary panel switches the displayed run; figures and scalars re-render).

### 5.5 Step 5 — Report (evidential output)

**Two layouts, picked by `case.mode`:**

#### 5.5a Forensic layout (mockup matches)

- Light surface (`--bg-report`), serif body, navy text.
- Toolbar (dark): `▎report draft · not signed` left; `Export PDF` (accent) + `Sign & lock` (outlined) right.
- Sections, in order:
  1. **Title block**: examiner, date, bitig version, case hash.
  2. **Hypotheses**: H_p / H_d statements, copy-edit-able.
  3. **LR block**: brass-bordered 220px card showing `LR ≈ <value>` (Georgia, 34px) with verbal-scale ladder beside it. Active ladder rung highlighted in `--accent`.
  4. **Method paragraph** (left column).
  5. **Chain of custody** (right column): questioned + known + control corpora with token counts and SHA-256 prefixes.
  6. **Provenance footer**: the four hashes, full bitig version + spaCy model.

#### 5.5b Research layout

Same skeleton, different fields:
- Title block unchanged.
- Hypotheses block → **Research question** + **Hypothesis** (free-text).
- LR block → **Headline result** card (left, brass border, large serif number — same visual weight, different metric: classification accuracy, PCA cumulative variance, Bayesian posterior mode, etc.) + **Method context** (right): a few sentences pulled from `bitig.viz.captions` describing what the headline number means.
- Method paragraph + Chain of custody → **Methods** + **Data availability & citations** (the latter wires into the existing `CITATION.cff` + the corpus's own provenance entry).

Both layouts share the toolbar and produce the same PDF pipeline.

## 6. Sign & lock semantics

When the user hits **Sign & lock** on a Report draft:

1. The Case is frozen: any change to `case.json`, `study.yaml`, or anything under `evidence/` raises `--err`.
2. A `report/signed.json` is written:
   ```jsonc
   {
     "signed_at": "2026-05-17T13:01:44Z",
     "signed_by": "F. Bozdağ",                  // from preferences
     "case_state_hash": "…",                      // SHA-256 of case.json + study.yaml + sorted file hashes
     "report_html_hash": "…",
     "bitig_version": "0.1.1"
   }
   ```
3. **Export PDF** stamps the PDF footer with `signed_at` and `case_state_hash`.
4. A signed Case is read-only in the GUI. Cloning (`bitig case fork <id>`) produces an unsigned descendant if the user needs to iterate.

Sign & lock is *not* a cryptographic signature — it's a chain-of-custody anchor. If the user wants a hardware-key signature, that's a future plugin point that wraps `signed.json`.

## 7. Build sequence

1. **Case data model** — `src/bitig/cases.py`: `Case` dataclass, persistence (`Case.load(path)`, `Case.save()`), evidence registration with hashing, custody-integrity check, mode-derivation function.
2. **Recipe registry** — `src/bitig/recipes.py`: the 5 recipes as code (each: id, title, question, mode, default features, default methods, param schema). Custom is the absence of a recipe.
3. **CLI** — `bitig case new|open|list|status|fork|sign`. Each is a thin wrapper over `bitig.cases`.
4. **GUI pages** — `src/bitig/gui/pages/case/` with one module per step plus a Case-list landing page. The existing flat Ingest/Study/Run/Results/Forensic pages stay reachable from a `Legacy →` link in the Case-list rail (no migration; old pages keep working against session state).
5. **Recipe drawer + Custom slide-over** — shared param widgets in `src/bitig/gui/widgets/`, recipe-specific drawers wire those widgets to the recipe's param schema.
6. **Report renderer mode split** — `src/bitig/report/forensic.html.j2` + `src/bitig/report/research.html.j2`. The existing PANReport template likely *becomes* `forensic.html.j2` with minor edits. Both render from a common `ReportContext` Pydantic model.
7. **Sign & lock** — implemented last; everything before this step must work in unsigned mode.

Suggested PR boundaries: 1+2 in one PR (no UI), 3 in one PR, 4+5 in one PR per step (5 PRs total for the GUI build-out), 6 in one PR, 7 in one PR.

## 8. Out of scope (for v1)

- Multi-user / cloud-sync Cases. Single-user single-machine.
- Live re-run on evidence change. The user re-runs Step 3 manually.
- Hardware-key signatures.
- Colour-blind / contrast accessibility audit on the dark theme (open follow-up before public release).
- Mobile / narrow-window layouts. Desktop only.

## 9. Open follow-ups after the spec lands

- Pick the recipe-ID slugs (current draft above is a strawman; the brass tile order in `method-picker.html` is the user-visible order, but the slugs are dev-facing).
- Decide the Case dir default location: `~/.bitig/cases/` vs `~/Documents/bitig/cases/` vs project-local. Default proposed: `~/.bitig/cases/` (hidden by default, configurable in `~/.bitig/config.toml`).
- Confirm Export PDF backend: WeasyPrint (current docs/report path) vs Playwright (renders HTML with full JS, needed if any interactive plotly survives into the PDF — probably not).
