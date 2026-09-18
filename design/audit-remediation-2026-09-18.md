# September audit remediation

## Final software verification

The final software pass also closes three edge cases: methods that own feature
extraction reject unused feature references, report-generation errors persist in
run status and produce nonzero CLI exits, and source distributions include the
root scripts required by the shipped tests. Completed method results remain
available when report generation fails.

The source distribution and wheel build successfully. All 15 shipped collection
tests pass from the extracted source archive. The final non-slow suite passes
**741 tests**, with 24 slow tests deselected. Pre-commit (Ruff and mypy), explicit
lint/format checks of new scripts/tests, and the strict documentation build pass.

## Earlier remediation checkpoint

Subsequent corpus acquisition and screening are recorded in
[the corpus follow-up](corpus-readiness-2026-09-18.md). The counts and acquisition
status below describe the earlier software-remediation checkpoint.

This change addresses the twelve findings in `audit-2026-09-18.md`. The historical
audit is retained unchanged. No research model was refitted and no new articles
were collected.

| Finding | Remediation |
|---|---|
| Signature downgrade | Missing HMAC fails; signer metadata and scheme are checked. Callers can require a scheme with `--require-signature hmac` or `expected_signature_plugin`. Providing a key also requires HMAC. Schema-2 signatures authenticate the entire canonical payload. Null seals check consistency only. |
| CV leakage | CLI and runner split raw corpora, then fit extractors inside training folds. Predictions and probabilities come from the same fitted model. Missing target classes are rejected; splits and feature hashes are persisted. |
| Ignored configuration | Language, normalization, CV folds/groups, estimator options/seeds, cache and plot/report settings are applied. Unsupported settings/feature combinations fail explicitly. |
| Calibration imbalance | CalibratedScorer records calibration prevalence and removes its prior odds during LR conversion. |
| Provenance identity | Corpus hashes bind ID/text/metadata together; feature hashes bind training data, learned vocabulary/scaling, parsing model identity, configuration, ordered features/documents, actual values, and package version. |
| Bayesian correctness | In-sample accuracy is labelled; explicit CV is supported. Group scale now controls author variation, and posterior summaries include convergence diagnostics. PyMC import is lazy. |
| Acquisition | Manifest repair preserves original texts and backs up metadata. File and body checksums are separate; capture/publication dates and title/body are explicit. Resume counts include previous rows, overlaps are recomputed over all articles, and stable URL IDs prevent timestamp collisions. |
| False run success | Per-method status is persisted, failures produce nonzero CLI exits, failed methods appear in reports, and existing run directories are refused. |
| Function-word scaling | Z-scoring learns training statistics and applies them unchanged to new documents. |
| Cache | Atomic writes, corrupt-entry recovery, and loaded pipeline/weight fingerprints prevent unsafe reuse. |
| Report assets | Figures are embedded; analysis artifacts are sealed in a manifest. Export verifies the seal before serving an existing frozen report. |
| MFW semantics | Default z-score rates use all document tokens. `frequency_basis="vocabulary"` explicitly restores legacy rates. |

## Compatibility and remaining research work

Hashes and MFW z-score results intentionally change. Do not compare historical and
new scores without recording the frequency basis and evaluation design. Re-run
studies into new directories, never over existing artifacts. Legacy signatures
retain their legacy verification format; new signatures use schema 2. An expected
scheme/key is required for authentication against an adversary who can rewrite
both a Null seal and its manifest.

The local corpus still has 132 articles: Hürriyet 59, Sözcü 60, Cumhuriyet 12, Sabah 1.
All 132 file checksums now match. Publication dates and event inclusion were not
invented: legacy rows are marked pending/unverified, with original metadata backed
up under `study-data/corpus/meta.before-repair.*.tsv`. `study-data/coverage.json`
shows every configured event × newspaper cell, including absent cells.

Before running the four-paper study, acquire the missing coverage, verify article
publication dates and event inclusion, and review high-overlap text. Set reviewed
rows to `inclusion_status=included` and `publication_date_status=verified`; exclude
unusable rows. The configurable coverage floor defaults to five included articles
per cell; it is an operational gate, not a power-analysis guarantee. The analysis
script additionally requires review of overlap >= 0.8. For acquisition, install the script dependency with `uv pip install trafilatura`.
The collection command is `python collect_corpus.py --collect`; local checks/repair use `--repair-manifest`.
`python run_analysis.py` validates; `--execute` explicitly launches the study only
after those gates pass. Exact body-only inputs and the study configuration are
retained beside each run.

On Apple Silicon with Homebrew libraries, WeasyPrint may need
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`. Missing native libraries now produce
a report-rendering error instead of an unhandled import failure.

## Verification evidence

- Non-slow repository suite: **725 passed**, including PDF export; 24 slow tests deselected.
- Bayesian unit module (no sampling): **7 passed**.
- Targeted rerun after final runner/provenance/CLI changes: **99 passed**.
- An additional fitted-scaling provenance regression checks that different learned
  standard deviations change the hash even when one target's numeric values match.
  The final feature/provenance regression run passed **72 tests**.
- Ruff lint/format and mypy pass. The strict MkDocs build and all applicable
  pre-commit hooks pass (including checks of the new scripts/tests).
- A separately generated, sealed synthetic PDF was inspected with `pdfimages`:
  the expected 40 × 40 RGB figure is embedded, and the case seal remains valid.
- Local corpus validation reports 132 files, zero integrity problems, and correctly
  refuses the full analysis because coverage/review requirements are not met.

The slow NLP/model-download suite and a new research fit were not run. Existing
GUI rendering was not manually exercised; GUI-independent case orchestration,
report generation, and its regression tests were exercised.
