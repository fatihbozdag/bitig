# Changelog

## Unreleased

Remediation of the 2026-09-26 audit (`design/audit-2026-09-26.md`). Several changes
alter numbers bitig produces or refuse inputs it used to accept; they are marked
**[results]** and **[breaking]**.

### Forensic Lab (Cases)

- Case runs analyse only registered evidence, re-hashed as it is read; every recipe runs
  end-to-end. The verification recipe needs a *Candidate author*. **[breaking]**
- `verify_seal` rejects stripped or downgraded HMAC signatures; a supplied key always
  requires a valid signature. **[breaking]**
- Signing requires registered evidence, intact custody, an unedited `study.yaml` and a
  run computed on the current case state; signing is atomic. **[breaking]**
- The seal covers every run output (`run_manifest`). Seals made by 0.3.1 and earlier
  fail verification as "legacy seal". **[breaking]**
- Export refuses a signed case whose seal no longer verifies.
- New: `bitig case add-evidence`, `bitig case reacknowledge` (sealed custody log),
  `bitig case fork --acknowledge-mismatch`.
- HMAC signatures (scheme 2) cover the whole `signed.json` payload, signer included;
  `verify_seal` cross-checks the signer in `case.json`. A Null-plugin seal is reported as
  "UNSIGNED — not tamper-evident", never "seal verified". The GUI verify dialog takes a key.
- A stale `Case` handle can no longer overwrite a newer `case.json` (e.g. un-sign a case
  signed elsewhere); it raises and must be reloaded.
- `bitig case list` / the GUI list unreadable cases instead of failing on the first one.
- Reports no longer call a General Impostors score a likelihood ratio, and show one
  score per questioned document instead of the maximum.

- New `bitig case run <id>`: runs a case from the CLI with the same guards as the GUI
  (exit 0 succeeded, 1 partial or failed, 2 blocked).
- `bitig case verify` exit codes: 0 verified (valid HMAC), 1 not signed, 2 broken,
  3 intact Null seal (not tamper-evident), 4 HMAC seal that cannot be checked without a key
  ("CANNOT VERIFY" instead of "SEAL BROKEN"). `$BITIG_SIGNATURE_KEY` alone no longer fails
  a Null seal; an explicit `--key` still requires a valid HMAC. `SealVerification.status`
  exposes the outcome. **[breaking]** (scripts that treated exit 0 as success for Null seals)
- `Case.set_param` no longer freezes the auto-filled verify `target_ids` into the overrides,
  so questioned documents added later are analysed. A target list that does not match the
  questioned evidence now blocks the run with a clear message instead of failing every method.

### Methods and metrics

- **[results]** General Impostors samples `ceil(sqrt(pool))` impostors per iteration
  (was 1) and its `verified` threshold must exceed chance.
- **[results]** Isotonic calibration adds one pseudo-trial per class, caps
  `|log10 LR|` at `log10(n)` and needs >= 20 trials per class.
- **[results]** `CalibratedScorer.predict_log_lr` divides out the calibration set's prior
  odds (`prior_target_`), so LRs no longer depend on its class balance.
- **[results]** `c@1` and `F0.5u` follow the PAN evaluator: only `p == 0.5` is a
  non-answer, and every non-answer counts in F0.5u.
- **[results]** MFW z-scores use `count / document token count` (was: counts
  renormalised over the retained vocabulary). Delta, PCA, General Impostors and
  rolling Delta values change.
- **[results]** Bootstrap consensus: a clade's support is the fraction of trees containing
  all its members in which it appears; a subsample's root no longer counts as a clade;
  majority rule is strictly > `support_threshold`.
- **[results]** `bitig run` honours `preprocess.language`; the study seed reaches every
  stochastic method.
- **[results]** `Corpus.hash` binds texts to ids and metadata (scheme 2, recorded as
  `Provenance.corpus_hash_scheme`).
- **[results]** `FunctionWordExtractor(scale="zscore")` z-scores relative frequencies (it
  returned raw counts); English contractions and French elided forms in the bundled lists
  now match. Character/word n-gram `zscore` uses relative frequencies; new
  `max_features` caps their vocabulary.
- **[results]** Lexical diversity: undefined values are NaN with a warning (HD-D below 42
  tokens, MTLD without a complete factor, Yule's I for all-unique text) instead of 0 or a
  token-count floor; Yule's I uses the canonical `V²/(M2 − V)`. `bitig run` refuses NaN
  features.
- **[results]** German and French readability count syllables as vowel nuclei instead of
  hyphenation points, which undercounted (Abend, Oma, ami, école = 1). On gold lists of
  ~100 words each: German 96%, French 98% correct.
- **[results]** `HierarchicalGroupComparison` uses `sigma_group` for the author spread (it
  was created but unused) and standardises each feature, returning the mean/SD used.
  `BayesianAuthorshipAttributor` rejects negative or NaN input at predict time too.
- **[results]** Unmasking merges a trailing chunk shorter than half `chunk_size` into the
  previous chunk instead of counting it as a sample.
- **[results]** Classification CV refits the feature extractor inside each training
  fold (`bitig classify`, `kind: classify`); `loao` grouped by a relabelling of the target
  is refused everywhere. The Bayesian runner reports `resubstitution_accuracy`
  (was `accuracy`).
- `bitig run` exits 1 if any method failed (listing them; `error.txt` holds the
  traceback) and refuses a run directory holding a previous run unless `--overwrite`.
  **[breaking]**
- English readability never triggers an NLTK download; a missing cmudict raises with the
  install command (`python -m nltk.downloader cmudict`). Provenance records library
  versions and a cmudict checksum, and no longer claims a spaCy model for runs that
  parse nothing. **[breaking]**
- Unknown study parameters and unsupported feature types are refused at load time;
  `method:` on a Delta method is a deprecated alias for `variant:`. **[breaking]**

### Documentation

- New Forensic Lab page (EN/TR) documenting the case workflow, seals and `bitig case verify`.
- Tutorials corrected against real runs: Federalist (11 disputed papers, no projection step,
  measured PCA variance, uncalibrated Naive Bayes posteriors, byline caveat), Turkish (actual
  run outputs), PAN-CLEF (measured metrics; per-trial LR instead of a mean over trials).
- CLI and `study.yaml` references regenerated from the code; settings the runner ignores are
  marked. Getting-started, methods, features, topic-invariance and verification pages fixed.
- README and quickstart: PCA claims corrected and figure regenerated; stale status lines and
  test-count badge removed. `CITATION.cff` no longer claims feature parity with Stylo.
- [results] The Turkish example study no longer includes Burrows Delta, which failed on its
  single-author corpus.
