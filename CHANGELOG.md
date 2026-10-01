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
- Reports no longer call a General Impostors score a likelihood ratio, and show one
  score per questioned document instead of the maximum.

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
- Unknown study parameters and unsupported feature types are refused at load time;
  `method:` on a Delta method is a deprecated alias for `variant:`. **[breaking]**
