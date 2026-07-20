"""Job-postings-as-capital-project-signal scraper — Johnson & Johnson.

Premise: a surge of Engineering / C&Q / Validation / Commissioning / MSAT
open reqs at a specific site is the best *public* signal that the site has
an active new-build or expansion in progress. This module pulls J&J's open
postings, filters to those role families, groups them by site, and emits one
aggregate record per site so the networkmap pipeline can threshold on
posting count (5+ matching reqs at one site == strong "active project"
signal).

Output shape (one dict per site with >=1 matching posting):

    {
        "org": "Johnson & Johnson",
        "site": "Raritan, New Jersey, United States",   # as written by the source
        "matching_postings": 7,
        "sample_titles": ["Senior Engineer, C&Q", "Validation Lead", ...],
        "source_url": "https://careers.jnj.com/en/jobs/?search=engineering",
    }

This is the FIRST company of an eventual 7 (J&J, AbbVie, BMS, Novo Nordisk,
Novartis, Roche/Genentech, Lilly). It's written so the other six slot in as
sibling fetch_*() functions around the shared filter/group/emit core at the
bottom — see `_filter_and_group()` and the CompanyFetcher seam.

────────────────────────────────────────────────────────────────────────────
FETCH STRATEGY (per the "check for a JSON API first" requirement)
────────────────────────────────────────────────────────────────────────────
careers.jnj.com is built on the **Phenom People** talent-experience platform
(same as many pharma career sites). Phenom sites render their listings from a
JSON search API rather than server-side HTML, so we hit that API directly —
far more reliable than parsing rendered markup.

    Primary : GET the Phenom /api/jobs JSON endpoint (this module).
    Fallback: Playwright renders the search page and we scrape the DOM, only
              if the JSON endpoint is unavailable/changed.

⚠️  ENDPOINT VERIFICATION REQUIRED (could not be done from the build sandbox —
    outbound network to careers.jnj.com is blocked here). Before trusting the
    numbers, confirm the exact endpoint + response shape against the live site:

      1. Open https://careers.jnj.com/en/jobs/ in a browser.
      2. DevTools → Network → filter to Fetch/XHR.
      3. Type a keyword in the job search box. Watch for a request to
         something like `careers.jnj.com/api/jobs?...` returning JSON.
      4. Copy that request URL + query params into PHENOM_* below, and eyeball
         the JSON so the field names in `_parse_phenom_jobs()` match (the
         parser is already defensive across the common Phenom variants, but
         verify `title` / location / `postedDate` / apply-URL keys).

    Everything downstream of the fetch (keyword filter, per-site grouping,
    output shape) is fully unit-tested against a mock payload and does NOT
    depend on the live endpoint — so once the endpoint constant is confirmed,
    this runs end to end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

import requests

# ── Config ──────────────────────────────────────────────────────────────────

ORG = "Johnson & Johnson"

# Human-facing search page (used as the `source_url` in output, and as the
# Playwright fallback target).
CAREERS_SEARCH_URL = "https://careers.jnj.com/en/jobs/"

# Phenom JSON search API. VERIFY against the live Network tab (see module
# docstring). The path + param names below are the common Phenom shape; the
# host is confirmed (careers.jnj.com), the exact path/params are best-effort.
PHENOM_API_URL = "https://careers.jnj.com/api/jobs"
PHENOM_PAGE_SIZE = 100          # Phenom commonly caps at 100/req; adjust if needed
PHENOM_MAX_PAGES = 40           # hard stop so a shape change can't infinite-loop
PHENOM_REQUEST_DELAY_S = 1.0    # be polite between pages

REQUEST_TIMEOUT_S = 25

# Role families that signal capital-project / new-line activity. Matched as
# case-insensitive substrings against the job title.
KEYWORDS = (
    "engineering",
    "quality",
    "procurement",
    "c&q",
    "validation",
    "msat",
    "capital project",
    "commissioning",
)

# A site with at least this many matching open reqs is flagged as a strong
# active-project signal (used only for the console summary; the raw count is
# always emitted so the pipeline can apply its own threshold).
STRONG_SIGNAL_THRESHOLD = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Normalized posting record ───────────────────────────────────────────────

@dataclass
class Posting:
    title: str
    site: str          # location string, exactly as written by the source
    posted_date: Optional[str]
    url: Optional[str]


# ── J&J fetch (Phenom JSON API primary, Playwright fallback) ────────────────

def fetch_jnj_postings(
    *,
    session: Optional[requests.Session] = None,
    max_pages: int = PHENOM_MAX_PAGES,
) -> list[Posting]:
    """Return all J&J open postings as normalized Posting records.

    Tries the Phenom JSON API first; falls back to Playwright DOM scraping
    only if the API yields nothing (endpoint moved / shape changed / blocked).
    Raises nothing — returns [] on total failure so a caller batching 7
    companies isn't torpedoed by one site being down.
    """
    session = session or _new_session()

    try:
        postings = _fetch_via_phenom_api(session, max_pages=max_pages)
        if postings:
            return postings
        print("  [info] Phenom API returned 0 postings; trying Playwright fallback…")
    except requests.RequestException as exc:
        print(f"  [warn] Phenom API request failed ({exc}); trying Playwright fallback…")

    try:
        return _fetch_via_playwright()
    except Exception as exc:  # noqa: BLE001 — fallback is best-effort
        print(f"  [error] Playwright fallback failed: {exc}")
        return []


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _fetch_via_phenom_api(session: requests.Session, *, max_pages: int) -> list[Posting]:
    """Page through the Phenom /api/jobs endpoint and normalize every job.

    We pull the FULL open-req set (no server-side keyword filter) and filter
    locally — that keeps us robust to how a given Phenom deployment names its
    query params, and lets one fetch feed all our keyword logic.
    """
    postings: list[Posting] = []
    seen_urls: set[str] = set()

    for page in range(max_pages):
        params = {
            "page": page,                 # Phenom is typically 0-indexed
            "limit": PHENOM_PAGE_SIZE,
            "sortBy": "relevance",
            # If the live site keyword-searches server-side, you can add
            # "keywords": "engineering" etc. here — but we filter locally.
        }
        resp = session.get(PHENOM_API_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        payload = resp.json()

        page_postings = _parse_phenom_jobs(payload)
        if not page_postings:
            break  # ran off the end of the results

        new = 0
        for p in page_postings:
            key = p.url or f"{p.title}|{p.site}"
            if key in seen_urls:
                continue
            seen_urls.add(key)
            postings.append(p)
            new += 1

        # Stop when a page is short (last page) or contributes nothing new.
        if len(page_postings) < PHENOM_PAGE_SIZE or new == 0:
            break

        time.sleep(PHENOM_REQUEST_DELAY_S)

    return postings


def _parse_phenom_jobs(payload: dict[str, Any]) -> list[Posting]:
    """Defensively pull jobs out of a Phenom /api/jobs response.

    Handles the common Phenom variants without assuming one exact shape:
      • jobs live under payload["jobs"] (sometimes ["data"]["jobs"] / ["results"])
      • each job may be flat, or nested under job["data"]
      • field names vary (title/jobTitle, cityStateCountry/location/city+state,
        postedDate/datePosted/postingDate, applyUrl/jobUrl/url/applyURL)
    """
    jobs = (
        payload.get("jobs")
        or payload.get("results")
        or (payload.get("data") or {}).get("jobs")
        or []
    )

    out: list[Posting] = []
    for raw in jobs:
        job = raw.get("data", raw) if isinstance(raw, dict) else {}
        if not isinstance(job, dict):
            continue

        title = _first(job, "title", "jobTitle", "name")
        if not title:
            continue

        site = _first(job, "cityStateCountry", "location", "formattedLocation")
        if not site:
            # assemble from parts if the flattened field isn't present
            site = ", ".join(
                part for part in (
                    _first(job, "city"),
                    _first(job, "state", "region"),
                    _first(job, "country"),
                ) if part
            ) or "Unknown"

        out.append(
            Posting(
                title=title.strip(),
                site=site.strip(),
                posted_date=_first(job, "postedDate", "datePosted", "postingDate", "createDate"),
                url=_first(job, "applyUrl", "jobUrl", "url", "applyURL", "detailUrl"),
            )
        )
    return out


def _first(d: dict[str, Any], *keys: str) -> Optional[str]:
    """First present, non-empty, stringifiable value among `keys`."""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return str(v)
    return None


def _fetch_via_playwright() -> list[Posting]:
    """Fallback: render the careers search page and scrape job cards.

    Only imported on demand so the JSON-API path has zero Playwright/browser
    dependency. Selectors here are best-effort for the Phenom-rendered DOM and
    should be confirmed against the live page if this path is ever exercised.
    """
    from bs4 import BeautifulSoup  # local import: fallback-only dependency
    from playwright.sync_api import sync_playwright

    postings: list[Posting] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(CAREERS_SEARCH_URL, wait_until="domcontentloaded", timeout=45000)
            # Phenom job cards commonly render as <li> under a results list;
            # give the client-side app a moment to hydrate.
            page.wait_for_timeout(4000)
            soup = BeautifulSoup(page.content(), "html.parser")
        finally:
            browser.close()

    # Candidate selectors for a Phenom result card, tried in order.
    for selector in ("li.jobs-list-item", "[data-ph-at-id='job-link']", "a[href*='/jobs/']"):
        cards = soup.select(selector)
        if not cards:
            continue
        for card in cards:
            title_el = card.select_one("[class*='title'], h2, h3") or card
            title = title_el.get_text(strip=True)
            loc_el = card.select_one("[class*='location'], [data-ph-at-id*='location']")
            site = loc_el.get_text(strip=True) if loc_el else "Unknown"
            href = card.get("href") or (card.find("a") or {}).get("href")
            if title:
                postings.append(Posting(title=title, site=site, posted_date=None, url=href))
        if postings:
            break

    return postings


# ── Shared filter + group + emit core (reused by all 7 companies later) ─────

def title_matches(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in KEYWORDS)


def _site_key(site: str) -> str:
    """Grouping key for a site: case-insensitive, whitespace-collapsed.

    We group counts on this normalized key but EMIT the original site string
    as written (no company/site normalization — the networkmap pipeline's own
    resolver owns that). This only prevents 'Raritan, NJ' vs 'raritan, nj  '
    from being split into two counts.
    """
    return " ".join(site.lower().split())


def _filter_and_group(
    postings: Iterable[Posting],
    *,
    org: str,
    source_url: str,
    sample_titles_per_site: int = 5,
) -> list[dict[str, Any]]:
    """Keep only keyword-matching postings, group by site, shape the output."""
    grouped: dict[str, list[Posting]] = defaultdict(list)
    for p in postings:
        if title_matches(p.title):
            grouped[_site_key(p.site)].append(p)

    records: list[dict[str, Any]] = []
    for group in grouped.values():
        # Emit the most common original spelling as the display site value.
        display_site = _most_common_original(group)
        sample = _dedup_preserve_order(p.title for p in group)[:sample_titles_per_site]
        records.append(
            {
                "org": org,
                "site": display_site,
                "matching_postings": len(group),
                "sample_titles": sample,
                "source_url": source_url,
            }
        )

    records.sort(key=lambda r: r["matching_postings"], reverse=True)
    return records


def _most_common_original(postings: list[Posting]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for p in postings:
        counts[p.site] += 1
    return max(counts, key=counts.get)


def _dedup_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


# ── Public entry point for J&J ──────────────────────────────────────────────

# Seam for extending to the other 6 companies: each becomes a (org, fetch_fn,
# source_url) entry. Only J&J is wired up for now, per "start with just J&J".
CompanyFetcher = Callable[[], list[Posting]]


def scrape_jnj() -> list[dict[str, Any]]:
    """Fetch → filter → group. Returns the per-site signal records for J&J."""
    print(f"Fetching open postings for {ORG} …")
    postings = fetch_jnj_postings()
    print(f"  pulled {len(postings)} total open postings")
    records = _filter_and_group(postings, org=ORG, source_url=CAREERS_SEARCH_URL)
    matched = sum(r["matching_postings"] for r in records)
    print(f"  {matched} match target role families across {len(records)} site(s)")
    return records


# ── CLI ─────────────────────────────────────────────────────────────────────

def _print_console(records: list[dict[str, Any]]) -> None:
    if not records:
        print("\nNo matching postings found.")
        return
    print("\nPer-site capital-project signal (sorted by matching postings):\n")
    for r in records:
        flag = "  ★ STRONG SIGNAL" if r["matching_postings"] >= STRONG_SIGNAL_THRESHOLD else ""
        print(f"  [{r['matching_postings']:>3}] {r['site']}{flag}")
        for t in r["sample_titles"]:
            print(f"          · {t}")
    strong = [r for r in records if r["matching_postings"] >= STRONG_SIGNAL_THRESHOLD]
    print(
        f"\n{len(strong)} site(s) at or above the {STRONG_SIGNAL_THRESHOLD}-posting "
        f"strong-signal threshold."
    )
    print(
        "  (counts are PRE-resolution: site strings are emitted as written, so "
        "near-duplicate\n   spellings of one physical site may appear split — the "
        "networkmap resolver folds\n   them, so apply the final threshold after "
        "resolution, not on this preview.)"
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=f"{ORG} capital-project job-posting signal scraper.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of the console table.")
    args = parser.parse_args(argv)

    records = scrape_jnj()

    if args.json:
        json.dump(records, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_console(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
