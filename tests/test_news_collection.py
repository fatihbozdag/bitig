"""Local acquisition contracts: no network in tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "news_collection", Path(__file__).parents[1] / "collect_corpus.py"
)
news = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(news)


def _legacy(directory):
    directory.mkdir()
    body = b"shared body words here"
    data = b"Article title\n\n" + body
    (directory / "a.txt").write_bytes(data)
    row = {
        "filename": "a.txt",
        "newspaper": "Sabah",
        "event": "ceren_ozdemir",
        "date": "20191203",
        "section": "body",
        "url": "http://example.com/article",
        "snapshot_ts": "20191203000100",
        "sha256": news.digest(body),
        "agency_overlap": "0",
    }
    # Write the historical columns only, before the new schema existed.
    import csv

    with (directory / "meta.tsv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row), delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
    return data


def test_repair_preserves_bytes_and_backups_and_is_idempotent(tmp_path):
    directory = tmp_path / "corpus"
    data = _legacy(directory)
    rows = news.repair_manifest(directory)
    assert (directory / "a.txt").read_bytes() == data
    assert rows[0]["sha256"] == news.digest(data)
    assert rows[0]["section"] == "title+body"
    assert rows[0]["publication_date"] == ""
    assert rows[0]["inclusion_status"] == "pending"
    assert list(directory.glob("meta.before-repair.*.tsv"))
    original = (directory / "meta.tsv").read_bytes()
    news.repair_manifest(directory)
    assert original == (directory / "meta.tsv").read_bytes()


def test_unexplained_mismatch_cannot_be_blessed(tmp_path):
    directory = tmp_path / "corpus"
    _legacy(directory)
    (directory / "a.txt").write_text("tampered")
    original = (directory / "meta.tsv").read_bytes()
    with pytest.raises(ValueError, match="Unexplained"):
        news.repair_manifest(directory)
    assert original == (directory / "meta.tsv").read_bytes()


def test_resume_honors_existing_cap_without_network(tmp_path, monkeypatch):
    directory = tmp_path / "corpus"
    _legacy(directory)
    monkeypatch.setattr(news, "CASES", [("ceren_ozdemir", "20191203", "20191203", "ceren-ozdemir")])
    monkeypatch.setattr(news, "PAPERS", {"Sabah": "sabah.com.tr"})
    monkeypatch.setattr(news, "cdx_day", lambda *args: pytest.fail("already at cap"))
    news.collect(directory, cap=1)
    assert len(news.load_rows(directory)) == 1


def test_overlap_recomputed_against_existing_articles(tmp_path):
    directory = tmp_path / "corpus"
    data = _legacy(directory)
    rows = news.repair_manifest(directory)
    (directory / "b.txt").write_bytes(data)
    rows.append({**rows[0], "filename": "b.txt", "newspaper": "Cumhuriyet"})
    news.recompute_overlap(directory, rows)
    assert all(float(row["agency_overlap"]) == 1 for row in rows)
    assert rows[0]["duplicate_family"] == rows[1]["duplicate_family"]
    report = news.coverage_report(directory, rows)
    assert not report["ready_for_full_comparison"]
    assert not report["integrity_problems"]


def test_canonical_url_preserves_article_identifiers():
    assert news.canonical_url("http://x.test/?id=1&utm_source=x") == "https://x.test/?id=1"
    assert news.canonical_url("http://x.test/?id=1") != news.canonical_url("http://x.test/?id=2")


@pytest.mark.parametrize(
    "left,right",
    [
        (
            "http://www.hurriyet.com.tr:80/amp/gundem/old-41390326",
            "https://www.hurriyet.com.tr/gundem/new-41390326",
        ),
        (
            "http://www.sozcu.com.tr/2019/gundem/story-5296679/amp/",
            "https://www.sozcu.com.tr/new-title-wp5296679",
        ),
        (
            "http://www.cumhuriyet.com.tr/amp/haber/turkiye/1706572/old.html",
            "https://www.cumhuriyet.com.tr/haber/new-1706572",
        ),
    ],
)
def test_publisher_aliases_share_identity(left, right):
    assert news.article_identity(left) == news.article_identity(right)


@pytest.fixture
def review(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "collect_corpus", news)
    spec = importlib.util.spec_from_file_location(
        "news_review", Path(__file__).parents[1] / "review_corpus.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publication_date_conflicts_are_not_silently_resolved(review):
    page = b"""<html><meta name="datePublished" content="2020-07-21T08:00:00+03:00">
    <script type="application/ld+json">{"@type":"NewsArticle", "datePublished":
    "2020-07-22T10:00:00+03:00", "dateModified":"2020-07-28"}</script></html>"""
    assert review.publication_dates(page) == ["2020-07-21", "2020-07-22"]


def test_evidence_application_preserves_text_and_excludes_alias(review, tmp_path):
    import json

    directory = tmp_path / "corpus"
    data = _legacy(directory)
    rows = news.repair_manifest(directory)
    rows[0]["url"] = "https://www.hurriyet.com.tr/gundem/story-41390326"
    (directory / "b.txt").write_bytes(data)
    rows.append(
        {
            **rows[0],
            "filename": "b.txt",
            "url": "http://www.hurriyet.com.tr:80/amp/gundem/story-41390326",
        }
    )
    news.write_rows(directory, rows)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    key = news.digest(news.article_identity(rows[0]["url"]).encode())[:24]
    page = b'<meta name="datePublished" content="2019-12-05">'
    (evidence / f"{key}.html").write_bytes(page)
    record = {
        "status": "fetched",
        "identity_matches": True,
        "publication_dates": ["2019-12-05"],
        "html_sha256": news.digest(page),
        "final_url": rows[0]["url"],
    }
    (evidence / f"{key}.json").write_text(json.dumps(record))
    review.apply_evidence(directory, evidence)
    updated = news.load_rows(directory)
    assert updated[0]["publication_date_status"] == "verified"
    assert updated[0]["inclusion_status"] == "pending"
    assert updated[1]["inclusion_status"] == "excluded"
    assert updated[1]["duplicate_of"] == "a.txt"
    assert (directory / "a.txt").read_bytes() == data
    assert (directory / "b.txt").read_bytes() == data
    assert list(directory.glob("meta.before-review.*.tsv"))


def test_tampered_evidence_does_not_verify_date(review, tmp_path):
    import json

    directory = tmp_path / "corpus"
    _legacy(directory)
    rows = news.repair_manifest(directory)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    key = news.digest(news.article_identity(rows[0]["url"]).encode())[:24]
    (evidence / f"{key}.html").write_text("tampered")
    (evidence / f"{key}.json").write_text(
        json.dumps(
            {
                "status": "fetched",
                "identity_matches": True,
                "publication_dates": ["2019-12-05"],
                "html_sha256": "0" * 64,
                "final_url": rows[0]["url"],
            }
        )
    )
    review.apply_evidence(directory, evidence)
    assert news.load_rows(directory)[0]["publication_date_status"] == "unverified"


def test_first_pass_screening_cannot_satisfy_readiness(tmp_path, monkeypatch):
    directory = tmp_path / "corpus"
    _legacy(directory)
    rows = news.repair_manifest(directory)
    monkeypatch.setattr(news, "CASES", [("ceren_ozdemir", "20191203", "20191210", "ceren-ozdemir")])
    monkeypatch.setattr(news, "PAPERS", {"Sabah": "sabah.com.tr"})
    rows[0].update(
        inclusion_status="included",
        publication_date_status="verified",
        publication_date="2019-12-05",
        review_scope="first-pass, AI-assisted",
    )
    report = news.coverage_report(directory, rows, minimum=1)
    assert not report["insufficient_cells"]
    assert report["review_problems"]
    assert not report["ready_for_full_comparison"]
    rows[0]["inclusion_review_status"] = "adjudicated"
    assert news.coverage_report(directory, rows, minimum=1)["ready_for_full_comparison"]


def test_review_ledger_rejects_wrong_text_without_mutation(review, tmp_path):
    import json

    directory = tmp_path / "corpus"
    _legacy(directory)
    news.repair_manifest(directory)
    before = (directory / "meta.tsv").read_bytes()
    ledger = tmp_path / "decisions.json"
    ledger.write_text(
        json.dumps([{"filename": "a.txt", "sha256": "0" * 64, "inclusion_status": "included"}])
    )
    with pytest.raises(ValueError, match="checksum"):
        review.apply_decisions(directory, ledger)
    assert (directory / "meta.tsv").read_bytes() == before


def test_redirect_requires_same_publisher_and_matching_slug(review):
    assert review.matching_redirect(
        "https://www.sozcu.com.tr/hayatim/story/", "https://www.sozcu.com.tr/story-wp1234567"
    )
    assert not review.matching_redirect(
        "https://www.sozcu.com.tr/story/", "https://other.test/story-wp1234567"
    )
    assert not review.matching_redirect(
        "https://www.sozcu.com.tr/story/", "https://www.sozcu.com.tr/unrelated-wp1234567"
    )


def test_candidate_import_is_idempotent_and_retains_pending_review(review, tmp_path, monkeypatch):
    import json
    import sys
    from types import SimpleNamespace

    directory = tmp_path / "corpus"
    _legacy(directory)
    news.repair_manifest(directory)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    page = b"<html>source evidence</html>"
    (evidence / "new.html").write_bytes(page)
    record = {
        "status": "fetched",
        "url": "https://www.sozcu.com.tr/report-wp1234567",
        "final_url": "https://www.sozcu.com.tr/report-wp1234567",
        "publication_dates": ["2019-12-05"],
        "html_sha256": news.digest(page),
        "title": "Ceren Özdemir report",
        "retrieved_at": "2026-09-18T00:00:00Z",
    }
    (evidence / "new.json").write_text(json.dumps(record))
    text = "Ceren Özdemir news. " + "article text " * 50
    monkeypatch.setitem(
        sys.modules,
        "trafilatura",
        SimpleNamespace(extract=lambda *args, **kwargs: json.dumps({"text": text})),
    )
    assert review.import_candidates(directory, evidence) == 1
    assert review.import_candidates(directory, evidence) == 0
    row = news.load_rows(directory)[1]
    assert row["inclusion_status"] == "pending"
    assert row["snapshot_ts"] == ""
    assert row["source_version"] == "current publisher page"
    assert news.digest((directory / row["filename"]).read_bytes()) == row["sha256"]
