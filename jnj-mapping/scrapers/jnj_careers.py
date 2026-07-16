"""Scraper for careers.jnj.com — the first working script in jnj-mapping.

Pulls open job postings and filters them down to roles relevant to
industrial valve procurement (diaphragm valves for biopharma manufacturing):
Engineering, Quality, Procurement, C&Q, Validation, MSAT, Capital Project.
Active postings in those functions at a given site are a signal that the
site has a live capital project and is worth prospecting.

Strategy: try requests + BeautifulSoup against the static HTML first (cheap,
fast, no browser). If the listing page turns out to be JS-rendered (no job
cards found in the static HTML), fall back to Playwright.

    SITE STRUCTURE ASSUMPTIONS — VERIFY AND ADJUST
    ------------------------------------------------
    This module was written without live access to careers.jnj.com (network
    access from the build environment was blocked), so the constants below
    are best-effort defaults based on common enterprise career-site
    patterns, not confirmed selectors. Before relying on this scraper:

    1. Run with --debug to dump the raw HTML/rendered HTML to data/ and
       inspect it in a browser's dev tools.
    2. Update SEARCH_URL_TEMPLATE to match the site's actual search/listing
       URL and query parameters (keyword, location, pagination).
    3. Update JOB_CARD_SELECTORS with the real selector(s) for a single job
       listing element, in priority order (first match wins).
    4. Update the field-level heuristics in extract_job_from_node() if
       title/location/date aren't being found correctly.

    The scraper is written defensively (multiple candidate selectors, a
    Playwright fallback, heuristic field extraction) specifically so it
    degrades gracefully and is easy to recalibrate once you can see the
    real markup, rather than hard-failing on a wrong assumption.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from scrapers.base import get_session, polite_get, render_with_playwright

BASE_URL = "https://careers.jnj.com"
# Best-effort guess at the search/listing endpoint and its query params.
# Common patterns on enterprise career sites: ?keywords=, ?q=, ?page=.
SEARCH_URL_TEMPLATE = BASE_URL + "/en/jobs/search?page={page}"
MAX_PAGES = 10

# Roles relevant to industrial valve procurement (diaphragm valves for
# biopharma manufacturing): engineering, C&Q, quality, procurement roles.
KEYWORDS = [
    "Engineering",
    "Quality",
    "Procurement",
    "C&Q",
    "Validation",
    "MSAT",
    "Capital Project",
]

# Rough function classification, checked in order — first match wins.
# Extend this as you observe more title patterns in real listings.
FUNCTION_RULES: list[tuple[str, list[str]]] = [
    ("MSAT", ["msat", "manufacturing science", "tech transfer", "technology transfer"]),
    ("C&Q/Validation", ["c&q", "c & q", "commissioning", "qualification", "validation"]),
    ("Quality", ["quality"]),
    ("Procurement", ["procurement", "sourcing", "supply chain", "buyer", "category manager"]),
    ("Engineering", ["engineering", "capital project", "process engineer", "facilities"]),
]

# Candidate CSS selectors for a single job-listing element, tried in order.
# Common patterns across Workday, iCIMS, SmartRecruiters, Radancy, and
# similar enterprise ATS platforms that career sites are often built on.
JOB_CARD_SELECTORS = [
    '[data-testid="job-card"]',
    '[data-automation-id="jobTitle"]',
    "li.job-listing",
    "li.jobs-list-item",
    "div.job-listing-item",
    "div.search-result",
    "article.job",
    'a[href*="/job/"]',
    'a[href*="/jobs/"]',
]

DATE_PATTERN = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)


@dataclass
class JobPosting:
    title: str
    location: str
    function: str
    posting_date: Optional[str]
    source_url: str
    matched_keyword: str


def classify_function(title: str) -> Optional[str]:
    lowered = title.lower()
    for function, keywords in FUNCTION_RULES:
        if any(kw in lowered for kw in keywords):
            return function
    return None


def matched_keyword(title: str) -> Optional[str]:
    lowered = title.lower()
    for kw in KEYWORDS:
        if kw.lower() in lowered:
            return kw
    return None


def _first_text(node: Tag, selectors: list[str]) -> Optional[str]:
    for sel in selectors:
        found = node.select_one(sel)
        if found and found.get_text(strip=True):
            return found.get_text(strip=True)
    return None


def extract_job_from_node(node: Tag, page_url: str) -> Optional[dict]:
    """Heuristically pull title/href/location/date out of one job card.

    Career sites vary widely in markup, so this looks for common patterns
    (class/id containing "location"/"date", the node itself or its first
    link as the title) rather than assuming one fixed structure.
    """
    link = node if node.name == "a" else node.select_one("a[href]")
    href = link.get("href") if link else None
    title = (link.get_text(strip=True) if link else None) or _first_text(
        node, ["h1", "h2", "h3", "h4", '[class*="title"]']
    )
    if not title or not href:
        return None

    location = _first_text(
        node,
        [
            '[class*="location"]',
            '[class*="city"]',
            '[data-automation-id*="location"]',
        ],
    )
    if not location:
        text = node.get_text(" ", strip=True)
        loc_match = re.search(r"\b[A-Z][a-zA-Z.\- ]+,\s*[A-Z]{2}\b", text)
        location = loc_match.group(0) if loc_match else "Unknown"

    date_text = _first_text(node, ['[class*="date"]', "time"])
    if not date_text:
        text = node.get_text(" ", strip=True)
        date_match = DATE_PATTERN.search(text)
        date_text = date_match.group(0) if date_match else None

    return {
        "title": title,
        "source_url": urljoin(page_url, href),
        "location": location,
        "posting_date": date_text,
    }


def parse_job_cards(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for selector in JOB_CARD_SELECTORS:
        nodes = soup.select(selector)
        if not nodes:
            continue
        jobs = []
        seen_urls = set()
        for node in nodes:
            job = extract_job_from_node(node, page_url)
            if job and job["source_url"] not in seen_urls:
                seen_urls.add(job["source_url"])
                jobs.append(job)
        if jobs:
            print(f"  matched selector '{selector}' -> {len(jobs)} job cards")
            return jobs
    return []


def fetch_all_listings(*, max_pages: int, debug: bool, debug_dir: Path) -> list[dict]:
    session = get_session()
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    for page_num in range(1, max_pages + 1):
        url = SEARCH_URL_TEMPLATE.format(page=page_num)
        print(f"Fetching page {page_num}: {url}")
        response = polite_get(session, url)
        html = response.text if response is not None else None

        jobs = parse_job_cards(html, url) if html else []

        if not jobs:
            print("  no job cards in static HTML, falling back to Playwright...")
            rendered = render_with_playwright(url, wait_selector=None)
            if rendered:
                html = rendered.html
                jobs = parse_job_cards(html, url)

        if debug and html:
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / f"jnj_careers_page_{page_num}.html"
            debug_file.write_text(html, encoding="utf-8")
            print(f"  [debug] saved raw HTML to {debug_file}")

        if not jobs:
            print(f"  no jobs found on page {page_num}, stopping pagination.")
            break

        new_jobs = [j for j in jobs if j["source_url"] not in seen_urls]
        if not new_jobs:
            print("  page returned no new jobs (likely repeated/last page), stopping.")
            break

        for job in new_jobs:
            seen_urls.add(job["source_url"])
        all_jobs.extend(new_jobs)

    return all_jobs


def filter_relevant_jobs(raw_jobs: list[dict]) -> list[JobPosting]:
    postings = []
    for job in raw_jobs:
        kw = matched_keyword(job["title"])
        if not kw:
            continue
        postings.append(
            JobPosting(
                title=job["title"],
                location=job["location"],
                function=classify_function(job["title"]) or "Other",
                posting_date=job.get("posting_date"),
                source_url=job["source_url"],
                matched_keyword=kw,
            )
        )
    return postings


def print_results(postings: list[JobPosting]) -> None:
    if not postings:
        print("\nNo relevant postings found.")
        return

    print(f"\n{len(postings)} relevant job posting(s):\n")
    col_widths = {"title": 55, "location": 22, "function": 16, "date": 12}
    header = (
        f"{'TITLE':<{col_widths['title']}} "
        f"{'LOCATION':<{col_widths['location']}} "
        f"{'FUNCTION':<{col_widths['function']}} "
        f"{'POSTED':<{col_widths['date']}}"
    )
    print(header)
    print("-" * len(header))
    for p in postings:
        title = (p.title[: col_widths["title"] - 1] + "…") if len(p.title) > col_widths["title"] else p.title
        print(
            f"{title:<{col_widths['title']}} "
            f"{p.location:<{col_widths['location']}} "
            f"{p.function:<{col_widths['function']}} "
            f"{(p.posting_date or 'Unknown'):<{col_widths['date']}}"
        )
        print(f"  {p.source_url}")


def write_outputs(postings: list[JobPosting], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    json_path = out_dir / f"jnj_careers_{timestamp}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in postings], f, indent=2)
    print(f"\nWrote {json_path}")

    csv_path = out_dir / f"jnj_careers_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(postings[0]).keys()) if postings else [])
        writer.writeheader()
        for p in postings:
            writer.writerow(asdict(p))
    print(f"Wrote {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape careers.jnj.com for procurement-relevant roles.")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    parser.add_argument("--debug", action="store_true", help="Save raw HTML of each page to data/debug/")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data",
    )
    args = parser.parse_args()

    debug_dir = args.out_dir / "debug"
    raw_jobs = fetch_all_listings(max_pages=args.max_pages, debug=args.debug, debug_dir=debug_dir)
    print(f"\nScraped {len(raw_jobs)} total job posting(s) before filtering.")

    postings = filter_relevant_jobs(raw_jobs)
    print_results(postings)

    if postings:
        write_outputs(postings, args.out_dir)
    else:
        print(
            "\nNothing to write. If this is unexpected, re-run with --debug and "
            "inspect data/debug/*.html — the site's real markup likely differs "
            "from the selectors in JOB_CARD_SELECTORS (see the module docstring)."
        )


if __name__ == "__main__":
    main()
