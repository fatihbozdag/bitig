"""September audit contracts: assert scientific/integrity outcomes, not code shape."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from typing import ClassVar

import numpy as np
import pytest
import spacy
import yaml
from typer.testing import CliRunner

from bitig.cases import Case
from bitig.cli import app
from bitig.corpus import Corpus, Document
from bitig.features import FunctionWordExtractor, MFWExtractor
from bitig.forensic.lr import CalibratedScorer
from bitig.methods.classify import build_classifier, cross_validate_bitig
from bitig.preprocess.pipeline import SpacyPipeline
from bitig.report.case_report import ReportRendererError, build_case_report
from bitig.result import Result
from bitig.runner import StudyRunStatus, run_study
from bitig.signatures import HmacSignaturePlugin


def test_signature_removal_and_downgrade_fail_closed(tmp_path):
    case = Case.create(tmp_path, id="signed", title="test", examiner="test", recipe="exploration")
    payload = case.mark_signed(signature_plugin=HmacSignaturePlugin(key="key"))
    assert case.verify_seal(signature_key="key").ok
    payload.pop("signature")
    seal = case.report_dir / "signed.json"
    seal.write_text(json.dumps(payload))
    assert not case.verify_seal(signature_key="wrong").ok
    payload["signature_plugin_id"] = "null"
    seal.write_text(json.dumps(payload))
    assert not case.verify_seal().ok
    case.record.signature_plugin_id = "null"
    assert not case.verify_seal(expected_signature_plugin="hmac").ok
    seal.write_text("[]")
    assert not case.verify_seal().ok


def test_sealed_assets_are_embedded_and_mutation_blocks_export(tmp_path):
    case = Case.create(tmp_path, id="assets", title="test", examiner="test", recipe="exploration")
    run = case.runs_dir / "run" / "pca"
    run.mkdir(parents=True)
    Result("pca").save(run)
    figure = run / "figure.png"
    original = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
    )
    figure.write_bytes(original)
    case.register_run("run")
    case.mark_signed()
    frozen = (case.report_dir / "signed.html").read_bytes()
    assert base64.b64encode(original) in frozen
    assert case.verify_seal().ok
    figure.write_bytes(b"changed")
    assert not case.verify_seal().ok
    with pytest.raises(ReportRendererError, match="verification failed"):
        build_case_report(case)
    assert (case.report_dir / "signed.html").read_bytes() == frozen


def test_corpus_hash_binds_text_to_identity():
    a = Corpus([Document("a", "alpha"), Document("b", "beta")])
    b = Corpus([Document("a", "beta"), Document("b", "alpha")])
    assert a.hash() != b.hash()
    assert a.hash() == Corpus(list(reversed(a.documents))).hash()


def test_feature_hash_binds_fitted_training_state():
    target = Corpus([Document("t", "alpha beta")])
    a = MFWExtractor(n=1, scale="none").fit(Corpus([Document("a", "alpha")])).transform(target)
    b = MFWExtractor(n=1, scale="none").fit(Corpus([Document("b", "beta")])).transform(target)
    assert a.provenance_hash != b.provenance_hash


@pytest.mark.parametrize("positive", [10, 50, 90])
@pytest.mark.parametrize("method", ["platt", "isotonic"])
def test_uninformative_calibration_has_neutral_lr(positive, method):
    scorer = CalibratedScorer(method=method).fit(
        np.zeros(100), np.array([1] * positive + [0] * (100 - positive))
    )
    np.testing.assert_allclose(scorer.predict_log_lr(np.array([0.0])), [0.0], atol=1e-4)


def test_function_words_use_training_stats():
    train = Corpus([Document("a", "the the and"), Document("b", "the and and")])
    extractor = FunctionWordExtractor(wordlist=["the", "and"], scale="zscore")
    np.testing.assert_allclose(extractor.fit_transform(train).X, [[1, -1], [-1, 1]])
    np.testing.assert_allclose(
        extractor.transform(Corpus([Document("c", "the the the")])).X, [[3, -3]]
    )


def test_mfw_rates_use_all_document_tokens_and_offer_legacy_mode():
    corpus = Corpus([Document("a", "the the the alpha"), Document("b", "the beta gamma delta")])
    np.testing.assert_allclose(MFWExtractor(n=1).fit_transform(corpus).X, [[1], [-1]])
    np.testing.assert_allclose(
        MFWExtractor(n=1, frequency_basis="vocabulary").fit_transform(corpus).X, [[0], [0]]
    )


class FoldAuditExtractor(MFWExtractor):
    fits: ClassVar[list] = []
    transforms: ClassVar[list] = []

    def _fit(self, corpus):
        type(self).fits.append({d.id for d in corpus})
        super()._fit(corpus)

    def _transform(self, corpus):
        type(self).transforms.append(({d.id for d in corpus}, set(self._vocabulary)))
        return super()._transform(corpus)


def test_cv_never_learns_held_out_vocabulary_and_reproduces():
    corpus = Corpus(
        [
            Document(
                f"d{i}",
                f"common unique{chr(97 + i)} " + ("alpha " if i % 2 else "beta ") * 3,
                {"label": str(i % 2)},
            )
            for i in range(12)
        ]
    )
    labels = np.array(corpus.metadata_column("label"))
    FoldAuditExtractor.fits = []
    FoldAuditExtractor.transforms = []
    result = cross_validate_bitig(
        build_classifier("rf", n_estimators=7),
        corpus,
        labels,
        extractor=FoldAuditExtractor(scale="none"),
        folds=3,
        seed=123,
    )
    for train_ids, fold in zip(FoldAuditExtractor.fits, result["folds"], strict=True):
        test_ids = {corpus.documents[i].id for i in fold["test_indices"]}
        assert train_ids.isdisjoint(test_ids)
    for ids, vocabulary in FoldAuditExtractor.transforms:
        if len(ids) == 4:  # validation transform
            assert all(f"unique{chr(97 + int(i[1:]))}" not in vocabulary for i in ids)
    repeat = cross_validate_bitig(
        build_classifier("rf", n_estimators=7),
        corpus,
        labels,
        extractor=MFWExtractor(scale="none"),
        folds=3,
        seed=123,
    )
    np.testing.assert_array_equal(result["predictions"], repeat["predictions"])
    np.testing.assert_array_equal(result["proba"], repeat["proba"])
    assert len(result["folds"]) == 3
    with pytest.raises(ValueError, match="omits a target class"):
        cross_validate_bitig(
            build_classifier("rf"),
            corpus,
            labels,
            extractor=MFWExtractor(),
            cv_kind="loao",
            groups_from=labels,
        )


def test_cache_invalidates_weights_and_recovers_corruption(tmp_path):
    first = SpacyPipeline(cache_dir=tmp_path)
    first._nlp = spacy.blank("en")
    first._nlp.meta["version"] = "1"
    second = SpacyPipeline(cache_dir=tmp_path)
    second._nlp = spacy.blank("en")
    second._nlp.meta["version"] = "2"
    doc = Document("a", "Hello world.")
    assert first._key(doc) != second._key(doc)
    first.cache.put(first._key(doc), b"bad cache")
    assert next(first.parse(Corpus([doc])).spacy_docs()).text == doc.text
    assert not list(tmp_path.glob(".docbin-*"))


def test_import_does_not_load_optional_pymc():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import bitig, sys; assert 'pymc' not in sys.modules; assert 'arviz' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _study(tmp_path, **overrides):
    directory = tmp_path / "corpus"
    directory.mkdir()
    for i in range(12):
        (directory / f"d{i}.txt").write_text(("ve bir " if i % 2 else "için bu ") * (i + 1))
    (directory / "meta.tsv").write_text(
        "filename\tauthor\tevent\n" + "".join(f"d{i}.txt\t{i % 2}\t{i // 2}\n" for i in range(12))
    )
    config = {
        "corpus": {"path": str(directory), "metadata": str(directory / "meta.tsv")},
        "features": [{"id": "f", "type": "function_word"}],
        "preprocess": {"language": "tr"},
        "methods": [
            {
                "id": "rf",
                "kind": "classify",
                "features": "f",
                "group_by": "author",
                "cv": {"kind": "group_kfold", "groups_from": "event", "folds": 2},
                "params": {"estimator": "rf", "n_estimators": 7},
            }
        ],
        "viz": {"format": ["svg"], "dpi": 72},
        "report": {"format": "html"},
        **overrides,
    }
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def test_runner_honors_language_folds_parameters_and_formats(tmp_path):
    path = _study(tmp_path)
    out = run_study(path, output_dir=tmp_path / "out", run_name="run")
    result = Result.from_json(out / "rf" / "result.json")
    assert result.params["n_estimators"] == 7
    assert result.params["random_state"] == 42
    assert len(result.values["folds"]) == 2
    assert result.values["accuracy"] >= 0.8
    assert (out / "rf" / "confusion_matrix.svg").is_file()
    assert not (out / "rf" / "confusion_matrix.png").exists()
    assert (out / "report.html").is_file()
    assert StudyRunStatus.load(out).status == "succeeded"
    with pytest.raises(FileExistsError):
        run_study(path, output_dir=tmp_path / "out", run_name="run")


def test_runner_failure_is_nonzero_and_reported(tmp_path):
    path = _study(
        tmp_path, methods=[{"id": "bad", "kind": "reduce", "features": "f", "n_components": 999}]
    )
    result = CliRunner().invoke(
        app, ["run", str(path), "--output", str(tmp_path / "out"), "--name", "run"]
    )
    assert result.exit_code == 1
    assert "failed" in result.output
    assert "FAILED" in (tmp_path / "out" / "run" / "report.html").read_text()


def test_runner_rejects_unsupported_settings_before_output(tmp_path):
    path = _study(tmp_path, preprocess={"normalize": {"expand_contractions": True}})
    with pytest.raises(ValueError, match="expand_contractions"):
        run_study(path, output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("kind", ["rolling_delta", "verify", "zeta", "consensus"])
def test_runner_rejects_unused_feature_references(tmp_path, kind):
    path = _study(
        tmp_path,
        methods=[{"id": "method", "kind": kind, "features": "f", "group_by": "author"}],
    )
    with pytest.raises(ValueError, match="extracts its own features"):
        run_study(path, output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_report_failure_is_persisted_and_cli_exits_nonzero(tmp_path, monkeypatch):
    def fail_report(*args, **kwargs):
        raise OSError("report destination unavailable")

    monkeypatch.setattr("bitig.report.render.build_report", fail_report)
    path = _study(tmp_path)
    result = CliRunner().invoke(
        app, ["run", str(path), "--output", str(tmp_path / "out"), "--name", "run"]
    )
    assert result.exit_code == 2
    assert "report destination unavailable" in result.output
    status = StudyRunStatus.load(tmp_path / "out" / "run")
    assert status.status == "partial"
    assert status.methods == {"rf": None}
    assert status.report_error == "OSError: report destination unavailable"
    assert (tmp_path / "out" / "run" / "rf" / "result.json").is_file()


def test_hierarchical_group_scale_is_connected_without_sampling(monkeypatch):
    pm = pytest.importorskip("pymc")
    from pytensor.graph.basic import ancestors

    from bitig.features import FeatureMatrix
    from bitig.methods.bayesian import HierarchicalGroupComparison

    class GraphCheckedError(Exception):
        pass

    def inspect_graph(*args, **kwargs):
        model = pm.modelcontext(None)
        assert model["sigma_group"] in set(ancestors([model["theta_author"]]))
        raise GraphCheckedError

    monkeypatch.setattr(pm, "sample", inspect_graph)
    fm = FeatureMatrix(np.array([[1.0], [2.0], [3.0], [4.0]]), list("abcd"), ["x"], "scalar")
    with pytest.raises(GraphCheckedError):
        HierarchicalGroupComparison(group_by="group").fit_transform(
            fm, np.array(["a", "a", "b", "b"]), np.array(["one", "one", "two", "two"])
        )


def test_feature_provenance_binds_scaling_even_when_target_values_match():
    corpus = Corpus([Document("a", "alpha alpha beta"), Document("b", "alpha beta beta")])
    target = Corpus([Document("t", "alpha beta")])
    extractor = MFWExtractor(n=2).fit(corpus)
    before = extractor.transform(target)
    extractor._column_stds *= 2
    after = extractor.transform(target)
    np.testing.assert_array_equal(before.X, after.X)
    assert before.provenance_hash != after.provenance_hash
