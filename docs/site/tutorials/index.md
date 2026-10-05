# Tutorials

Three runnable tutorials ship with bitig.

## [Federalist Papers](federalist.md)

Revisit the classical Mosteller & Wallace (1964) authorship attribution on the 85
Federalist Papers. The example corpus holds essay bodies only, with headers and author bylines
stripped, and labels No. 58 as Madison, so it has 11 disputed papers (Nos. 49–57, 62, 63). A
declarative study explores the single-author papers; the disputed papers are then attributed
with `bitig delta` and `bitig bayesian`, trained on the known papers.

Illustrates: corpus ingestion, MFW feature extraction, Burrows Delta, PCA visualisation, a
Ward dendrogram, Craig's Zeta contrast between Hamilton and Madison, and attribution with
`--test-filter`.

## [PAN-CLEF verification](pan-clef.md)

An end-to-end forensic-verification pipeline on a PAN-CLEF-style setup: pair a
questioned document with a candidate's known samples plus an impostor pool, score with
General Impostors, calibrate via Platt scaling, and report the full PAN metric suite —
AUC, c@1, F0.5u, Brier, ECE, C_llr — alongside a forensic HTML report with LR framing
and chain-of-custody.

Illustrates: the full `bitig.forensic` workflow end-to-end.

## [Turkish stylometry](turkish.md)

Set up a Turkish project (`bitig init --language tr`) and explore a corpus of public-domain
Ömer Seyfettin short stories from Turkish Wikisource with MFW, PCA and Ward clustering.

Illustrates: the Turkish language profile, the `bitig[turkish]` extra and Stanza, and which
features `bitig run` builds without parsing.
