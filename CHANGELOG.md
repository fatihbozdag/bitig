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
- Unknown study parameters and unsupported feature types are refused at load time;
  `method:` on a Delta method is a deprecated alias for `variant:`. **[breaking]**
