# Python API

Auto-generated from the source via mkdocstrings. Every symbol listed below is re-exported
at `bitig` top level (unless otherwise noted).

## Corpus

::: bitig.corpus.Corpus
    options:
      show_root_full_path: false

::: bitig.corpus.Document
    options:
      show_root_full_path: false

## Features

::: bitig.features.base.FeatureMatrix
    options:
      show_root_full_path: false

::: bitig.features.mfw.MFWExtractor
    options:
      show_root_full_path: false

## Methods

### Delta

::: bitig.methods.delta.burrows.BurrowsDelta
    options:
      show_root_full_path: false

### Zeta

::: bitig.methods.zeta.ZetaClassic
    options:
      show_root_full_path: false

### Clustering

::: bitig.methods.cluster.HierarchicalCluster
    options:
      show_root_full_path: false

### Classification

::: bitig.methods.classify.build_classifier

::: bitig.methods.classify.cross_validate_bitig

## Results

::: bitig.result.Result
    options:
      show_root_full_path: false

::: bitig.provenance.Provenance
    options:
      show_root_full_path: false

## Forensic

`GeneralImpostors`, `Unmasking` and `CalibratedScorer` are re-exported at `bitig` top level;
`compute_pan_report` and `PANReport` are imported from `bitig.forensic`.

::: bitig.forensic.verify.GeneralImpostors
    options:
      show_root_full_path: false

::: bitig.forensic.unmasking.Unmasking
    options:
      show_root_full_path: false

::: bitig.forensic.lr.CalibratedScorer
    options:
      show_root_full_path: false

::: bitig.forensic.metrics.compute_pan_report

::: bitig.forensic.metrics.PANReport
    options:
      show_root_full_path: false

## Cases

The Forensic Lab case API is imported from `bitig.cases`, not from `bitig` top level.

::: bitig.cases.Case
    options:
      show_root_full_path: false

::: bitig.cases.SealVerification
    options:
      show_root_full_path: false

## Runner

::: bitig.runner.run_study

## Reporting

`build_report` is re-exported at `bitig` top level; `build_forensic_report` is imported from
`bitig.report`.

::: bitig.report.render.build_report

::: bitig.report.render.build_forensic_report
