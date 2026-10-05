# Python API

Kaynaktan mkdocstrings aracılığıyla otomatik oluşturulmuştur. Aşağıda listelenen her sembol,
`bitig` üst düzeyinde yeniden dışa aktarılır (aksi belirtilmedikçe).

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

`GeneralImpostors`, `Unmasking` ve `CalibratedScorer`, `bitig` üst düzeyinde yeniden dışa
aktarılır; `compute_pan_report` ve `PANReport` ise `bitig.forensic` modülünden içe aktarılır.

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

Adli Laboratuvar vaka API'si `bitig` üst düzeyinden değil, `bitig.cases` modülünden içe
aktarılır.

::: bitig.cases.Case
    options:
      show_root_full_path: false

::: bitig.cases.SealVerification
    options:
      show_root_full_path: false

## Runner

::: bitig.runner.run_study

## Reporting

`build_report`, `bitig` üst düzeyinde yeniden dışa aktarılır; `build_forensic_report` ise
`bitig.report` modülünden içe aktarılır.

::: bitig.report.render.build_report

::: bitig.report.render.build_forensic_report
