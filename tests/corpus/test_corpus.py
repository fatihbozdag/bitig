"""Tests for the Corpus collection."""

import pytest

from bitig.corpus import Corpus, Document


def _doc(i: int, **meta: object) -> Document:
    return Document(id=f"doc-{i}", text=f"text {i}", metadata=dict(meta))


def test_corpus_wraps_documents():
    docs = [_doc(1, author="A"), _doc(2, author="B")]
    c = Corpus(documents=docs)
    assert len(c) == 2
    assert list(c) == docs


def test_corpus_is_indexable():
    docs = [_doc(1), _doc(2), _doc(3)]
    c = Corpus(documents=docs)
    assert c[0] == docs[0]
    assert c[-1] == docs[-1]


def test_corpus_filter_by_exact_metadata():
    docs = [_doc(1, author="A"), _doc(2, author="B"), _doc(3, author="A")]
    c = Corpus(documents=docs)
    result = c.filter(author="A")
    assert len(result) == 2
    assert all(d.metadata["author"] == "A" for d in result)


def test_corpus_filter_by_list_metadata():
    docs = [_doc(1, group="native"), _doc(2, group="L2"), _doc(3, group="bilingual")]
    c = Corpus(documents=docs)
    result = c.filter(group=["native", "L2"])
    assert len(result) == 2


def test_corpus_groupby_returns_dict_of_corpora():
    docs = [_doc(1, author="A"), _doc(2, author="B"), _doc(3, author="A")]
    c = Corpus(documents=docs)
    groups = c.groupby("author")
    assert set(groups.keys()) == {"A", "B"}
    assert len(groups["A"]) == 2
    assert len(groups["B"]) == 1
    assert all(isinstance(g, Corpus) for g in groups.values())


def test_corpus_groupby_missing_field_raises():
    c = Corpus(documents=[_doc(1, author="A")])
    with pytest.raises(KeyError):
        c.groupby("nonexistent_field")


def test_corpus_hash_is_stable_and_order_independent():
    a = Corpus(documents=[_doc(1), _doc(2), _doc(3)])
    b = Corpus(documents=[_doc(3), _doc(1), _doc(2)])  # different order
    assert a.hash() == b.hash()


def test_corpus_hash_differs_for_different_content():
    a = Corpus(documents=[_doc(1), _doc(2)])
    b = Corpus(documents=[_doc(1), _doc(3)])
    assert a.hash() != b.hash()


def test_corpus_metadata_column_extracts_field_per_document():
    docs = [_doc(1, author="A"), _doc(2, author="B"), _doc(3, author="A")]
    c = Corpus(documents=docs)
    assert c.metadata_column("author") == ["A", "B", "A"]


def test_corpus_default_language_is_english() -> None:
    from bitig.corpus import Corpus, Document

    c = Corpus(documents=[Document(id="d0", text="hello")])
    assert c.language == "en"


def test_corpus_accepts_language_argument() -> None:
    from bitig.corpus import Corpus, Document

    c = Corpus(documents=[Document(id="d0", text="merhaba")], language="tr")
    assert c.language == "tr"


def test_corpus_hash_differs_by_language() -> None:
    from bitig.corpus import Corpus, Document

    doc = Document(id="d0", text="merhaba")
    en = Corpus(documents=[doc], language="en")
    tr = Corpus(documents=[doc], language="tr")
    assert en.hash() != tr.hash()


def test_hash_binds_texts_to_their_ids_and_labels() -> None:
    """Swapping two documents' texts must change the hash (audit 2026-09-26 N-P1.16)."""
    a = Corpus(
        documents=[
            Document(id="a", text="upon upon whilst", metadata={"author": "Hamilton"}),
            Document(id="b", text="while while whilst", metadata={"author": "Madison"}),
        ]
    )
    swapped = Corpus(
        documents=[
            Document(id="a", text="while while whilst", metadata={"author": "Hamilton"}),
            Document(id="b", text="upon upon whilst", metadata={"author": "Madison"}),
        ]
    )
    assert a.hash() != swapped.hash()
    # Still independent of document order.
    assert a.hash() == Corpus(documents=list(reversed(a.documents))).hash()


def test_provenance_records_corpus_hash_scheme() -> None:
    from bitig.corpus.corpus import CORPUS_HASH_SCHEME
    from bitig.provenance import Provenance

    p = Provenance.current(
        spacy_model="m",
        spacy_version="v",
        corpus_hash="h",
        feature_hash=None,
        seed=1,
        resolved_config={},
    )
    assert p.corpus_hash_scheme == CORPUS_HASH_SCHEME == 2
    legacy = p.to_dict()
    legacy.pop("corpus_hash_scheme")
    assert Provenance.from_dict(legacy).corpus_hash_scheme == 1
