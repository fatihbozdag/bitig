# Corpus acquisition and screening follow-up

## Material Passport

- Date: 2026-09-18. Stage: acquisition and first-pass screening.
- Status: **partial; not ready for research analysis**.
- Inputs: existing 132 article files, publisher pages, public dated archives.
- Outputs: 246-row local corpus, cached evidence, screening ledger and coverage report.
- No model fitting or research analysis was executed.

## Completed work

Added **114 candidate articles**, bringing the corpus to **246 rows**. All current
file checksums pass. All original 132 files are byte-for-byte unchanged, checked
against `study-data/corpus/meta.before-import.05006b7a6afb.tsv`.

Publisher publication-date metadata verifies **235 rows**; 11 remain unverified,
including excluded duplicates. Conflicting dates were not silently reconciled.
Current publisher pages are explicitly distinguished from historical archive
captures. This does not establish that a current article's wording is identical
to its original publication. Publisher HTML and metadata evidence are retained
with SHA-256 hashes under `study-data/publisher-evidence/`.

First-pass screening produces **156 provisional inclusions**, **82 exclusions**,
and **8 pending date decisions**. Exclusions comprise 43 publisher-identity
duplicates, 27 high-overlap rows, two out-of-window publications and ten
out-of-scope or ambiguous items. Screening used titles and article leads, date
evidence, and the existing 0.8 overlap threshold. It is AI-assisted screening,
**not independent human coding or completed full-text extraction review**.

High-overlap rows are conservatively held out, with original texts retained.
An overlap score alone does not prove agency authorship; shared quotations and
republication require adjudication. Lower overlap does not prove independence.

## Coverage after first-pass screening

The five-article floor remains unchanged. Counts below are provisional, not final
adjudicated sample sizes.

| Event | Sabah | Hürriyet | Sözcü | Cumhuriyet |
|---|---:|---:|---:|---:|
| Şule Çet | 1 | 0 | 0 | 0 |
| Emine Bulut | 11 | 15 | 11 | 3 |
| Ceren Özdemir | 15 | 12 | 11 | 3 |
| Pınar Gültekin | 26 | 9 | 8 | 3 |
| Başak Cengiz | 16 | 0 | 4 | 8 |

**Nine of twenty cells remain below the floor.** As explicitly requested, the
Şule Çet window remains **24 May–1 June 2018**, inclusive. A relevant
[Sabah article dated 1 June](https://www.sabah.com.tr/Yasam/luks-plazada-dehset-4317485)
was located through the publisher archive despite lacking the event name in its
URL. No event window, newspaper roster, or minimum count was relaxed.

This was a bounded acquisition pass, not proof that additional eligible articles
do not exist. Search and publisher-link discovery were supplemented with Sabah's
dated archive, limited to 20 pages/category/day. One 30 May archive request failed;
seven publisher requests failed. Per-request failures and evidence are retained.
The Wayback CDX probe timed out. Cached failures are not retried automatically.

## Reproducible workflow

Install acquisition dependencies with `uv pip install trafilatura`.

```bash
python discover_news.py --fetch
python review_corpus.py --fetch --candidates study-data/sabah-discovery/candidates.json
python review_corpus.py --import-candidates --apply-evidence
python review_corpus.py --decisions study-data/first-pass-decisions.json
python run_analysis.py
```

Fetches are opt-in; the default review command only reads local evidence. Imports
remain pending until reviewed. Metadata edits preserve backups; a decision ledger
must match each article's checksum. Duplicate matching handles AMP pages, default
ports, changed headline slugs and supported publisher redirects.

`study-data/first-pass-decisions.json` records screening decisions and reasons.
`study-data/review-queue.json` lists all rows. `study-data/coverage.json` identifies
missing cells, integrity failures and outstanding first-pass reviews. Final
review must check event inclusion, complete body extraction and shared wording;
record `inclusion_review_status=adjudicated` only after that review. The decision
ledger accepts that field and `extraction_review_note`.

The analysis preflight now refuses provisional first-pass rows even if numerical
coverage is later filled. The specified independent second-coder subset and
agreement assessment remain research work; no such assessment was fabricated.

## Validation

- Acquisition and audit regression modules: 34 tests passed before the final
  additional import regression; the final acquisition module passes 15 tests.
- Ruff lint and formatting pass for all changed scripts and acquisition tests.
- Repository pre-commit hooks pass, including mypy; `git diff --check` passes.
- All 246 article checksums pass; all original 132 files are unchanged.
- Local analysis preflight correctly exits without running the study.

Remaining work is the nine coverage gaps, eight active date decisions, final
inclusion/extraction/shared-wording review and independent second coding. These
are deliberately visible requirements, not software failures or invented data.
