"""Collect an event-anchored news corpus; repair/validate locally without network access.

Collection preserves provenance, but inclusion and publication dates need human verification.
Use --repair-manifest for legacy files; --collect explicitly enables network acquisition.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import io
import json
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

CASES = [
    ("sule_cet", "20180524", "20180601", "sule-cet"),
    ("emine_bulut", "20190818", "20190825", "emine-bulut"),
    ("ceren_ozdemir", "20191203", "20191210", "ceren-ozdemir"),
    ("pinar_gultekin", "20200721", "20200728", "pinar-gultekin"),
    ("basak_cengiz", "20211109", "20211116", "basak-cengiz"),
]
PAPERS = {
    "Sabah": "sabah.com.tr",
    "Hürriyet": "hurriyet.com.tr",
    "Sözcü": "sozcu.com.tr",
    "Cumhuriyet": "cumhuriyet.com.tr",
}
UA = {"User-Agent": "Mozilla/5.0 (research; news-construal-study)"}
FIELDS = [
    "filename",
    "newspaper",
    "event",
    "date",
    "section",
    "url",
    "snapshot_ts",
    "sha256",
    "agency_overlap",
    "body_sha256",
    "title",
    "publication_date",
    "publication_date_status",
    "capture_date",
    "inclusion_status",
    "duplicate_family",
]


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def canonical_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    # Drop tracking keys, not all query parameters (some identify the article).
    query = urllib.parse.urlencode(
        sorted(
            (k, v)
            for k, v in urllib.parse.parse_qsl(parts.query)
            if not k.startswith("utm_") and k not in {"fbclid", "gclid"}
        )
    )
    return urllib.parse.urlunsplit(("https", parts.netloc.lower(), parts.path, query, ""))


def article_identity(url: str) -> str:
    """Collapse known publishers' AMP/port/headline aliases, retaining unknown queries."""
    parts = urllib.parse.urlsplit(canonical_url(url))
    host = (parts.hostname or "").removeprefix("www.")
    if host not in PAPERS.values():
        return canonical_url(url)
    path = re.sub(r"^/amp/", "/", parts.path).removesuffix("/amp/").rstrip("/")
    match = re.search(r"(?:-|/)(?:wp)?(\d{6,})(?:\.html)?$", path)
    if not match and host == "cumhuriyet.com.tr":
        match = re.search(r"/haber/[^/]+/(\d{6,})/", path)
    if match:
        return f"{host}:article:{match[1]}"
    return urllib.parse.urlunsplit(("https", host, path, parts.query, ""))


def row_identity(row: dict[str, str]) -> str:
    return article_identity(row.get("canonical_article_url") or row["url"])


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_rows(directory: Path) -> list[dict[str, str]]:
    manifest = directory / "meta.tsv"
    if not manifest.exists():
        return []
    with manifest.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    filenames = [r["filename"] for r in rows]
    if len(filenames) != len(set(filenames)):
        raise ValueError("duplicate filenames in manifest; resolve before proceeding")
    for row in rows:
        if Path(row["filename"]).name != row["filename"] or not (
            directory / row["filename"]
        ).resolve().is_relative_to(directory.resolve()):
            raise ValueError("manifest filenames must stay within corpus directory")
    return rows


def write_rows(directory: Path, rows: list[dict[str, str]]) -> None:
    fields = list(dict.fromkeys(FIELDS + [k for r in rows for k in r]))
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(directory / "meta.tsv", out.getvalue().encode("utf-8"))


def body_text(directory: Path, row: dict[str, str]) -> str:
    text = (directory / row["filename"]).read_text(encoding="utf-8")
    return text.split("\n\n", 1)[1] if row["section"] == "title+body" else text


def recompute_overlap(directory: Path, rows: list[dict[str, str]]) -> None:
    events: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        events[row["event"]].append(row)
    for event_rows in events.values():
        tokens = [body_text(directory, r).lower().split() for r in event_rows]
        overlaps = [0.0] * len(event_rows)
        for i, left in enumerate(event_rows):
            for j in range(i + 1, len(event_rows)):
                if left["newspaper"] != event_rows[j]["newspaper"]:
                    similarity = difflib.SequenceMatcher(
                        None, tokens[i], tokens[j], autojunk=False
                    ).ratio()
                    overlaps[i] = max(overlaps[i], similarity)
                    overlaps[j] = max(overlaps[j], similarity)
        for i, row in enumerate(event_rows):
            row["agency_overlap"] = f"{overlaps[i]:.6f}"
            row["duplicate_family"] = digest(" ".join(tokens[i]).encode("utf-8"))


def repair_manifest(directory: Path) -> list[dict[str, str]]:
    """Migrate only verifiable legacy body hashes; retain text bytes and a manifest backup."""
    rows = load_rows(directory)
    for row in rows:
        data = (directory / row["filename"]).read_bytes()
        file_hash = digest(data)
        if file_hash != row["sha256"]:
            parts = data.split(b"\n\n", 1)
            if len(parts) != 2 or digest(parts[1]) != row["sha256"]:
                raise ValueError(
                    f"Unexplained checksum mismatch: {row['filename']}; refusing repair"
                )
            row["title"] = parts[0].decode("utf-8")
            row["body_sha256"] = row["sha256"]
            row["section"] = "title+body"
            row["sha256"] = file_hash
        else:
            row.setdefault("body_sha256", digest(body_text(directory, row).encode("utf-8")))
        row.setdefault("capture_date", row["snapshot_ts"][:8])
        row.setdefault("publication_date", "")
        row.setdefault("publication_date_status", "unverified")
        row.setdefault("inclusion_status", "pending")
        # Legacy 'date' was capture day, not an article publication date.
        row["date"] = row["publication_date"]
    recompute_overlap(directory, rows)
    manifest = directory / "meta.tsv"
    if manifest.exists():
        backup = directory / f"meta.before-repair.{digest(manifest.read_bytes())[:12]}.tsv"
        if not backup.exists():
            atomic_write(backup, manifest.read_bytes())
    write_rows(directory, rows)
    return rows


def coverage_report(directory: Path, rows: list[dict[str, str]], *, minimum: int = 5) -> dict:
    counts = Counter((r["event"], r["newspaper"]) for r in rows)
    included = Counter(
        (r["event"], r["newspaper"]) for r in rows if r.get("inclusion_status") == "included"
    )
    cells = [
        {
            "event": event,
            "newspaper": paper,
            "collected": counts[event, paper],
            "included": included[event, paper],
        }
        for event, *_ in CASES
        for paper in PAPERS
    ]
    problems = []
    review_problems = []
    selected_identities: set[str] = set()
    windows = {event: (start, end) for event, start, end, _ in CASES}
    for row in rows:
        path = directory / row["filename"]
        if not path.is_file() or digest(path.read_bytes()) != row["sha256"]:
            problems.append(f"checksum/missing file: {row['filename']}")
        if row.get("inclusion_status") == "included":
            if (
                row.get("review_scope", "").startswith("first-pass")
                and row.get("inclusion_review_status") != "adjudicated"
            ):
                review_problems.append(f"first-pass inclusion/extraction review: {row['filename']}")
            identity = row_identity(row)
            if identity in selected_identities:
                problems.append(f"duplicate included article: {row['filename']}")
            selected_identities.add(identity)
            try:
                published = datetime.fromisoformat(row.get("publication_date", "")).strftime(
                    "%Y%m%d"
                )
                start, end = windows[row["event"]]
                valid_date = start <= published <= end
            except (ValueError, KeyError):
                valid_date = False
            if row.get("publication_date_status") != "verified" or not valid_date:
                problems.append(f"unverified/out-of-window publication date: {row['filename']}")
    missing = [c for c in cells if c["included"] < minimum]
    return {
        "rows": len(rows),
        "minimum_per_cell": minimum,
        "cells": cells,
        "insufficient_cells": missing,
        "integrity_problems": problems,
        "review_problems": review_problems,
        "ready_for_full_comparison": bool(rows)
        and not missing
        and not problems
        and not review_problems,
        "interpretation": "Coverage gate only; human event inclusion and duplicate review remain required.",
    }


def daterange(start: str, end: str):
    first, last = (datetime.strptime(d, "%Y%m%d") for d in (start, end))
    for offset in range((last - first).days + 1):
        yield (first + timedelta(days=offset)).strftime("%Y%m%d")


def cdx_day(domain: str, day: str, slug: str, limit: int = 4000):
    params = {
        "url": domain,
        "matchType": "domain",
        "from": day,
        "to": day,
        "collapse": "urlkey",
        "limit": limit,
        "output": "json",
        "fl": "timestamp,original",
        "filter": f"original:.*{slug}.*",
    }
    request = urllib.request.Request(
        "https://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(params), headers=UA
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    rows = json.loads(data)[1:] if data.strip() else []
    if len(rows) >= limit:
        raise RuntimeError("CDX result limit reached; narrow the query before collection")
    return [
        (ts, url)
        for ts, url in rows
        if slug in url.lower() and "/galeri" not in url and "/video" not in url
    ]


def extract(ts: str, url: str):
    import trafilatura  # Only collection needs this optional script dependency.

    snapshot = f"https://web.archive.org/web/{ts}id_/{url}"
    request = urllib.request.Request(snapshot, headers=UA)
    with urllib.request.urlopen(request, timeout=90) as response:
        html = response.read().decode("utf-8", "replace")
    raw = trafilatura.extract(html, output_format="json", with_metadata=True, favor_precision=True)
    data = json.loads(raw) if raw else {}
    if len(data.get("text") or "") <= 400:
        return None
    return {
        "text": data["text"],
        "title": data.get("title") or "",
        "publication_date": data.get("date") or "",
    }


def collect(directory: Path, *, cap: int = 20) -> None:
    rows = repair_manifest(directory)
    urls = {row_identity(r) for r in rows}
    counts = Counter(
        (event, paper)
        for event, paper, _ in {
            (r["event"], r["newspaper"], row_identity(r))
            for r in rows
            if r.get("inclusion_status") != "excluded"
        }
    )
    bodies = {(r["event"], r["newspaper"], r["body_sha256"]) for r in rows}
    for event, start, end, slug in CASES:
        for paper, domain in PAPERS.items():
            for day in daterange(start, end):
                if counts[event, paper] >= cap:
                    break
                for ts, url in cdx_day(domain, day, slug):
                    clean = canonical_url(url)
                    if article_identity(clean) in urls:
                        continue
                    article = extract(ts, url)
                    time.sleep(1)
                    if not article:
                        continue
                    data = article["text"].encode("utf-8")
                    body_hash = digest(data)
                    if (event, paper, body_hash) in bodies:
                        continue
                    filename = f"{paper}_{event}_{digest(clean.encode())[:20]}.txt"
                    target = directory / filename
                    if target.exists() and target.read_bytes() != data:
                        raise ValueError(f"refusing to overwrite different content: {filename}")
                    atomic_write(target, data)
                    row = {
                        "filename": filename,
                        "newspaper": paper,
                        "event": event,
                        "date": article["publication_date"],
                        "section": "body",
                        "url": clean,
                        "snapshot_ts": ts,
                        "sha256": body_hash,
                        "body_sha256": body_hash,
                        "title": article["title"],
                        "publication_date": article["publication_date"],
                        "publication_date_status": "unverified",
                        "capture_date": ts[:8],
                        "inclusion_status": "pending",
                        "agency_overlap": "",
                    }
                    rows.append(row)
                    # Each accepted article is checkpointed. A crash can leave an orphan
                    # file, but never a manifest row pointing to unwritten bytes.
                    recompute_overlap(directory, rows)
                    write_rows(directory, rows)
                    urls.add(article_identity(clean))
                    bodies.add((event, paper, body_hash))
                    counts[event, paper] += 1
                    if counts[event, paper] >= cap:
                        break


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("study-data/corpus"))
    parser.add_argument("--repair-manifest", action="store_true")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--minimum-per-cell", type=int, default=5)
    args = parser.parse_args()
    if args.minimum_per_cell < 2:
        parser.error("minimum-per-cell must be at least 2")
    if args.collect:
        collect(args.corpus)
    rows = repair_manifest(args.corpus) if args.repair_manifest else load_rows(args.corpus)
    report = coverage_report(args.corpus, rows, minimum=args.minimum_per_cell)
    atomic_write(
        args.corpus.parent / "coverage.json",
        json.dumps(report, indent=2, ensure_ascii=False).encode(),
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"cells", "insufficient_cells"}}, indent=2
        )
    )
    print(f"Insufficient event/paper cells: {len(report['insufficient_cells'])}")


if __name__ == "__main__":
    main()
