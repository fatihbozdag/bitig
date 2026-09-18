"""Discover Sabah article URLs through its public dated archive (no article import)."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from collect_corpus import CASES, atomic_write, daterange
from lxml import html


def discover_day(task: tuple[str, str, str], directory: Path) -> dict:
    event, day, slug = task
    date = f"{day[:4]}/{day[4:6]}/{day[6:]}"
    result = {"event": event, "day": day, "urls": [], "errors": [], "truncated": []}
    for category in ("yasam", "gundem"):
        for page in range(1, 21):
            url = (
                f"https://www.sabah.com.tr/json/get/timeline/{date}?page={page}&category={category}"
            )
            cache = directory / f"{day}-{category}-{page}.html"
            try:
                if cache.exists():
                    data = cache.read_bytes()
                else:
                    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(request, timeout=20) as response:
                        data = response.read()
                    atomic_write(cache, data)
                    time.sleep(0.15)
                if len(data.strip()) < 10:
                    break
                tree = html.fromstring(data.decode("utf-8", "replace"))
                boxes = tree.xpath(
                    '//div[contains(concat(" ",normalize-space(@class)," ")," box ")]'
                )
                if not boxes:
                    result["errors"].append(f"Unexpected archive response: {url}")
                    break
                for link in tree.xpath("//a/@href"):
                    terms = {
                        "sule_cet": ("sule", "plaza"),
                        "basak_cengiz": ("basak-cengiz", "samuray"),
                    }.get(event, (slug,))
                    if any(term in link.lower() for term in terms) and not any(
                        x in link for x in ("/webtv/", "/fotohaber/")
                    ):
                        result["urls"].append(urllib.parse.urljoin(url, link))
                if page == 20:
                    result["truncated"].append(category)
            except Exception as exc:
                result["errors"].append(f"{url}: {type(exc).__name__}: {exc}")
                break
    result["urls"] = sorted(set(result["urls"]))
    atomic_write(
        directory / f"{day}.json", json.dumps(result, ensure_ascii=False, indent=2).encode()
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Enable network discovery")
    parser.add_argument("--output", type=Path, default=Path("study-data/sabah-discovery"))
    args = parser.parse_args()
    if not args.fetch:
        parser.error("Use --fetch to enable archive discovery")
    tasks = [
        (event, day, slug) for event, start, end, slug in CASES for day in daterange(start, end)
    ]
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(lambda t: discover_day(t, args.output), tasks):
            results.append(result)
            print(result["day"], len(result["urls"]), result["errors"], flush=True)
    urls = sorted({url for result in results for url in result["urls"]})
    atomic_write(args.output / "candidates.json", json.dumps(urls, indent=2).encode())
    print(f"Discovered {len(urls)} URLs")


if __name__ == "__main__":
    main()
