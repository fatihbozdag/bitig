"""Tests for the spaCy preprocessing pipeline — run against the small English model."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bitig.corpus import Corpus, Document
from bitig.preprocess.pipeline import ParsedCorpus, SpacyPipeline


def _tiny(text: str) -> Document:
    return Document(id=f"d-{hash(text) & 0xFFFF}", text=text, metadata={})


@pytest.mark.spacy
def test_pipeline_parses_documents(tmp_path: Path) -> None:
    corpus = Corpus(documents=[_tiny("Hello world."), _tiny("spaCy parses sentences.")])
    pipe = SpacyPipeline(model="en_core_web_sm", cache_dir=tmp_path)
    parsed = pipe.parse(corpus)
    assert isinstance(parsed, ParsedCorpus)
    assert len(parsed) == 2
    for doc in parsed.spacy_docs():
        assert len(list(doc.sents)) >= 1


@pytest.mark.spacy
def test_pipeline_cache_hit_is_fast(tmp_path: Path) -> None:
    corpus = Corpus(documents=[_tiny("The same sentence every time.")])
    pipe = SpacyPipeline(model="en_core_web_sm", cache_dir=tmp_path)

    pipe.parse(corpus)  # cold
    keys_after_first = set(pipe.cache.keys())

    pipe.parse(corpus)  # warm
    keys_after_second = set(pipe.cache.keys())

    assert keys_after_first == keys_after_second
    assert len(keys_after_first) == 1


@pytest.mark.spacy
def test_pipeline_cache_invalidates_on_text_change(tmp_path: Path) -> None:
    pipe = SpacyPipeline(model="en_core_web_sm", cache_dir=tmp_path)
    pipe.parse(Corpus(documents=[_tiny("original text")]))
    pipe.parse(Corpus(documents=[_tiny("different text")]))
    assert len(pipe.cache.keys()) == 2


@pytest.mark.spacy
def test_parsed_corpus_iteration_preserves_order(tmp_path: Path) -> None:
    corpus = Corpus(documents=[_tiny("A."), _tiny("B."), _tiny("C.")])
    pipe = SpacyPipeline(model="en_core_web_sm", cache_dir=tmp_path)
    parsed = pipe.parse(corpus)
    texts = [doc.text.strip() for doc in parsed.spacy_docs()]
    assert texts == ["A.", "B.", "C."]


# --------------------------------------------------------------------------- #
# Task 3.3 — language/backend dispatch (no spaCy model load required)
# --------------------------------------------------------------------------- #


def test_pipeline_resolves_english_defaults_from_registry(tmp_path: Path) -> None:
    pipe = SpacyPipeline(cache_dir=tmp_path)
    assert pipe.language == "en"
    assert pipe.backend == "spacy"
    assert pipe.model == "en_core_web_trf"


def test_pipeline_resolves_turkish_backend_to_spacy_stanza(tmp_path: Path) -> None:
    pipe = SpacyPipeline(language="tr", cache_dir=tmp_path)
    assert pipe.backend == "spacy_stanza"
    assert pipe.model == "tr"


def test_pipeline_explicit_backend_wins_over_language_default(tmp_path: Path) -> None:
    pipe = SpacyPipeline(language="tr", backend="spacy", model="custom_model", cache_dir=tmp_path)
    assert pipe.backend == "spacy"
    assert pipe.model == "custom_model"


def test_pipeline_unknown_language_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown language code"):
        SpacyPipeline(language="xx", cache_dir=tmp_path)


def test_pipeline_backend_version_native_matches_prior_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """English native-spaCy backend_version is 'spacy=<version>' — preserves cache keys."""
    import spacy

    monkeypatch.setattr(spacy, "__version__", "3.7.2")
    pipe = SpacyPipeline(language="en", cache_dir=tmp_path)
    assert pipe.backend_version == "spacy=3.7.2"


def test_pipeline_backend_version_stanza_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stanza backend_version is structurally different from native — no cache collisions."""

    def fake_version(pkg: str) -> str:
        return {"spacy_stanza": "1.0.4", "stanza": "1.6.1"}[pkg]

    monkeypatch.setattr("importlib.metadata.version", fake_version)

    pipe = SpacyPipeline(language="tr", cache_dir=tmp_path)
    assert pipe.backend_version == "spacy_stanza=1.0.4;stanza=1.6.1"


def test_pipeline_exclude_warns_on_spacy_stanza_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exclude= is meaningless on spacy_stanza; we emit a warning on nlp property access."""
    import sys

    fake_spacy_stanza = type(
        "M",
        (),
        {
            "__version__": "1.0.4",
            "load_pipeline": staticmethod(lambda lang: object()),
        },
    )
    fake_stanza = type("M", (), {"__version__": "1.8.0"})
    monkeypatch.setitem(sys.modules, "spacy_stanza", fake_spacy_stanza)
    monkeypatch.setitem(sys.modules, "stanza", fake_stanza)

    # Our logger has propagate=False so caplog can't see it; patch the module logger directly.
    mock_log = MagicMock()
    monkeypatch.setattr("bitig.preprocess.pipeline._log", mock_log)

    pipe = SpacyPipeline(language="tr", cache_dir=tmp_path, exclude=["ner"])
    _ = pipe.nlp  # triggers lazy load
    assert mock_log.warning.called
    # Verify the warning message mentions 'exclude' and 'ignored'.
    call_args = mock_log.warning.call_args
    fmt = call_args.args[0] if call_args.args else ""
    assert "exclude" in fmt and "ignored" in fmt
