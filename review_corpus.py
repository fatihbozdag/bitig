"""Cache publisher evidence for corpus review; never infer inclusion from keywords.

Default is local-only. --fetch enables bounded publisher requests. Evidence JSON
and HTML are retained separately from the immutable article text files.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from collect_corpus import (
    CASES,
    article_identity,
    atomic_write,
    canonical_url,
    coverage_report,
    digest,
    load_rows,
    recompute_overlap,
    row_identity,
    write_rows,
)
from lxml import html


def publication_dates(page: bytes) -> list[str]:
    tree = html.fromstring(page)
    values = tree.xpath(
        '//meta[@name="datePublished" or @itemprop="datePublished" '
        'or @property="article:published_time"]/@content'
    )

    def walk(value):
        if isinstance(value, dict):
            kind = value.get("@type", [])
            kinds = [kind] if isinstance(kind, str) else kind
            if (
                isinstance(kinds, list)
                and any(k in {"NewsArticle", "Article", "ReportageNewsArticle"} for k in kinds)
                and isinstance(value.get("datePublished"), str)
            ):
                values.append(value["datePublished"])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for raw in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            walk(json.loads(raw))
        except (ValueError, TypeError):
            continue
    dates = set()
    for value in values:
        try:
            dates.add(datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat())
        except (ValueError, TypeError):
            continue
    return sorted(dates)


def matching_redirect(original: str, final: str) -> bool:
    if article_identity(original) == article_identity(final):
        return True
    left, right = (urllib.parse.urlsplit(u) for u in (original, final))
    if (left.hostname or "").removeprefix("www.") != (right.hostname or "").removeprefix("www."):
        return False
    # Legacy publisher URLs without IDs migrated to the same slug plus an ID.
    old_slug = left.path.removesuffix("/amp/").rstrip("/").rsplit("/", 1)[-1]
    new_slug = re.sub(r"-(?:wp)?\d{6,}$", "", right.path.rstrip("/").rsplit("/", 1)[-1])
    return bool(old_slug) and old_slug == new_slug and not left.query and not right.query


def fetch_evidence(url: str, output: Path) -> dict:
    key = digest(article_identity(url).encode())[:24]
    record_path = output / f"{key}.json"
    if record_path.exists():
        return json.loads(record_path.read_text())
    record = {"url": url, "article_identity": article_identity(url)}
    record["retrieved_at"] = datetime.now(UTC).isoformat()
    try:
        # Current publisher version; do not pretend this is the historical snapshot.
        request_url = canonical_url(url).replace(":80/", "/").replace("/amp/", "/")
        request = urllib.request.Request(request_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            page = response.read(8_000_001)
            final_url = response.url
        if len(page) > 8_000_000:
            raise ValueError("Publisher response exceeds 8 MB evidence limit")
        record.update(final_url=final_url, html_sha256=digest(page))
        atomic_write(output / f"{key}.html", page)
        tree = html.fromstring(page)
        record["title"] = tree.xpath("string(//h1)").strip()
        record["publication_dates"] = publication_dates(page)
        record["identity_matches"] = article_identity(final_url) == article_identity(url)
        record["status"] = "fetched"
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    atomic_write(record_path, json.dumps(record, ensure_ascii=False, indent=2).encode())
    return record


def apply_evidence(directory: Path, evidence: Path) -> dict:
    """Apply verifiable dates and objective exclusions; retain unresolved review tasks."""
    rows = load_rows(directory)
    manifest = directory / "meta.tsv"
    before = manifest.read_bytes()
    atomic_write(directory / f"meta.before-review.{digest(before)[:12]}.tsv", before)
    windows = {event: (start, end) for event, start, end, _ in CASES}
    seen: dict[str, str] = {}
    for row in rows:
        identity = article_identity(row["url"])
        row["article_identity"] = identity
        key = digest(identity.encode())[:24]
        record_path = evidence / f"{key}.json"
        if record_path.exists():
            record = json.loads(record_path.read_text())
            page = evidence / f"{key}.html"
            dates = record.get("publication_dates", [])
            matches = matching_redirect(row["url"], record.get("final_url", ""))
            if (
                record.get("status") == "fetched"
                and matches
                and page.exists()
                and digest(page.read_bytes()) == record.get("html_sha256")
            ):
                row["canonical_article_url"] = record["final_url"]
                identity = row_identity(row)
                row["article_identity"] = identity
            if (
                record.get("status") == "fetched"
                and matches
                and len(dates) == 1
                and page.exists()
                and digest(page.read_bytes()) == record.get("html_sha256")
            ):
                row.update(
                    publication_date=dates[0],
                    date=dates[0],
                    publication_date_status="verified",
                    publication_date_source=record["final_url"],
                    publication_date_evidence=str(record_path),
                    publication_date_evidence_sha256=digest(record_path.read_bytes()),
                    publication_date_review="publisher metadata; AI-assisted; current page",
                )
        if identity in seen:
            row.update(
                inclusion_status="excluded",
                exclusion_reason="duplicate publisher article identity (AMP/port/headline alias)",
                duplicate_of=seen[identity],
            )
        else:
            seen[identity] = row["filename"]
            published = row.get("publication_date", "").replace("-", "")
            start, end = windows[row["event"]]
            if row.get("publication_date_status") == "verified" and not start <= published <= end:
                row.update(
                    inclusion_status="excluded", exclusion_reason="publication outside event window"
                )
    write_rows(directory, rows)
    report = coverage_report(directory, rows)
    atomic_write(
        directory.parent / "coverage.json",
        json.dumps(report, ensure_ascii=False, indent=2).encode(),
    )
    queue = [
        {
            "filename": r["filename"],
            "title": r.get("title", ""),
            "url": r["url"],
            "event": r["event"],
            "publication_date_status": r.get("publication_date_status", "unverified"),
            "inclusion_status": r.get("inclusion_status", "pending"),
            "agency_overlap": r.get("agency_overlap", ""),
            "exclusion_reason": r.get("exclusion_reason", ""),
        }
        for r in rows
    ]
    atomic_write(
        directory.parent / "review-queue.json",
        json.dumps(queue, ensure_ascii=False, indent=2).encode(),
    )
    return report


def import_candidates(directory: Path, evidence: Path) -> int:
    """Import in-window publisher texts as pending candidates, retaining source HTML."""
    import trafilatura
    from collect_corpus import PAPERS

    rows = load_rows(directory)
    seen = {row_identity(r) for r in rows}
    before = (directory / "meta.tsv").read_bytes()
    atomic_write(directory / f"meta.before-import.{digest(before)[:12]}.tsv", before)
    added = 0
    for record_path in sorted(evidence.glob("*.json")):
        record = json.loads(record_path.read_text())
        url = record.get("final_url", record["url"])
        identity = article_identity(url)
        if record["status"] != "fetched" or identity in seen:
            continue
        if any(part in url for part in ("/video", "/webtv/", "/galeri", "/yazarlar/")):
            continue
        dates = record.get("publication_dates", [])
        if len(dates) != 1:
            continue
        page = record_path.with_suffix(".html")
        if not page.exists() or digest(page.read_bytes()) != record["html_sha256"]:
            raise ValueError(f"Evidence integrity failure: {page}")
        title = record.get("title", "")
        anchors = {
            "sule_cet": "Şule Çet",
            "emine_bulut": "Emine Bulut",
            "ceren_ozdemir": "Ceren Özdemir",
            "pinar_gultekin": "Pınar Gültekin",  # noqa: RUF001 -- Turkish proper name
            "basak_cengiz": "Başak Cengiz",
        }
        host = (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.")
        papers = [paper for paper, domain in PAPERS.items() if domain == host]
        if len(papers) != 1:
            continue
        raw = trafilatura.extract(
            page.read_bytes(),
            output_format="json",
            with_metadata=True,
            include_comments=False,
            favor_precision=True,
        )
        article = json.loads(raw) if raw else {}
        body = re.sub(
            r"\[old_news_related_template\b[^\]]*\]", "", article.get("text") or ""
        ).strip()
        if len(body) <= 400:
            continue
        lead = (title + " " + body[:1500]).casefold().replace(" ", "")
        events = [
            event
            for event, start, end, slug in CASES
            if (slug in url or anchors[event].casefold().replace(" ", "") in lead)
            and start <= dates[0].replace("-", "") <= end
        ]
        if len(events) != 1:
            continue
        data = body.encode()
        paper, event = papers[0], events[0]
        filename = f"{paper}_{event}_{digest(identity.encode())[:20]}.txt"
        target = directory / filename
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite {target}")
        atomic_write(target, data)
        rows.append(
            {
                "filename": filename,
                "newspaper": paper,
                "event": event,
                "section": "body",
                "title": title,
                "url": url,
                "sha256": digest(data),
                "body_sha256": digest(data),
                "snapshot_ts": "",
                "capture_date": record["retrieved_at"][:10],
                "source_version": "current publisher page",
                "publication_date": dates[0],
                "date": dates[0],
                "publication_date_status": "verified",
                "publication_date_source": url,
                "publication_date_evidence": str(record_path),
                "publication_date_evidence_sha256": digest(record_path.read_bytes()),
                "inclusion_status": "pending",
                "agency_overlap": "",
                "acquisition_note": "URL/title/date screened; full text and event inclusion review pending",
            }
        )
        seen.add(identity)
        added += 1
    recompute_overlap(directory, rows)
    write_rows(directory, rows)
    return added


def apply_decisions(directory: Path, decisions_path: Path) -> None:
    """Apply an explicit, checksum-bound screening ledger, preserving provenance fields."""
    rows = load_rows(directory)
    by_name = {r["filename"]: r for r in rows}
    decisions = json.loads(decisions_path.read_text())
    allowed = {
        "reviewer",
        "review_basis",
        "event_screening",
        "review_scope",
        "inclusion_status",
        "exclusion_reason",
        "overlap_review",
        "review_note",
        "inclusion_review_status",
        "extraction_review_note",
    }
    seen = set()
    for decision in decisions:
        name = decision["filename"]
        if name in seen or name not in by_name:
            raise ValueError(f"Duplicate or unknown review filename: {name}")
        seen.add(name)
        row = by_name[name]
        if (
            decision["sha256"] != row["sha256"]
            or digest((directory / name).read_bytes()) != row["sha256"]
        ):
            raise ValueError(f"Review checksum mismatch: {name}")
        if set(decision) - allowed - {"filename", "sha256"}:
            raise ValueError(f"Unsupported review fields: {name}")
        if decision.get("inclusion_status") not in {"included", "excluded", "pending"}:
            raise ValueError(f"Unsupported inclusion decision: {name}")
        row.update({key: value for key, value in decision.items() if key in allowed})
    before = (directory / "meta.tsv").read_bytes()
    atomic_write(directory / f"meta.before-decisions.{digest(before)[:12]}.tsv", before)
    write_rows(directory, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("study-data/corpus"))
    parser.add_argument("--evidence", type=Path, default=Path("study-data/publisher-evidence"))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--candidates", type=Path, help="JSON list of additional publisher URLs")
    parser.add_argument("--apply-evidence", action="store_true")
    parser.add_argument("--import-candidates", action="store_true")
    parser.add_argument("--decisions", type=Path, help="Apply a checksum-bound review ledger")
    args = parser.parse_args()
    rows = load_rows(args.corpus)
    urls = {article_identity(r["url"]): r["url"] for r in reversed(rows)}
    if args.candidates:
        from urllib.parse import urlsplit

        from collect_corpus import PAPERS

        for url in json.loads(args.candidates.read_text()):
            if (urlsplit(url).hostname or "").removeprefix("www.") not in PAPERS.values():
                raise ValueError(f"Candidate is not one of the configured publishers: {url}")
            urls[article_identity(url)] = url
    if args.fetch:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(lambda u: fetch_evidence(u, args.evidence), urls.values()):
                print(result["status"], result["article_identity"], flush=True)
    from collections import Counter

    records = [json.loads(p.read_text()) for p in args.evidence.glob("*.json")]
    print(json.dumps(dict(Counter(r["status"] for r in records))))
    if args.import_candidates:
        print(f"Imported candidates: {import_candidates(args.corpus, args.evidence)}")
    if args.decisions:
        apply_decisions(args.corpus, args.decisions)
    if args.apply_evidence or args.import_candidates or args.decisions:
        apply_evidence(args.corpus, args.evidence)


if __name__ == "__main__":
    main()
