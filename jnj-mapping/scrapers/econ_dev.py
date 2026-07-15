"""Scraper for state/local economic development sites (NCBiotech, state
commerce department press releases, etc.) that often name specific J&J
capital-project details and named leaders that J&J's own site omits.

STATUS: skeleton, not yet implemented. Unlike the other two sources, this
one has no single URL — it's a set of independent sites, each with its own
markup, so this module is a small per-source registry plus a shared
search-and-filter pattern rather than one fixed scraper.

Target fields per hit: source_name, headline, site_name, investment_amount,
named_people (list), source_url, publish_date.

Suggested approach:
    1. Maintain SOURCES below as {name, search_url_template} entries — one
       per state/regional economic development site worth tracking for J&J
       capital projects (NCBiotech, NC Commerce, Ireland IDA, Belgium
       investment agencies, etc. depending on which J&J sites you're
       tracking).
    2. For each source, run a site search for "Johnson & Johnson" / "J&J"
       (many of these sites expose a simple ?q= or /search endpoint).
    3. Because every source has different markup, structured CSS selectors
       won't scale here the way they do for a single career site — lean on
       extraction.llm_extractor.extract_records_from_text() as the primary
       extraction path for this module, not just the fallback.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import get_session, polite_get

# One entry per economic-development site to track. search_url_template
# must contain a {query} placeholder. Fill in real search endpoints as you
# identify the sites relevant to the J&J locations you're tracking.
SOURCES = [
    {
        "name": "NCBiotech",
        "search_url_template": "https://www.ncbiotech.org/?s={query}",
    },
    # Add more state/regional economic development sources here, e.g.:
    # {"name": "NC Commerce", "search_url_template": "https://www.commerce.nc.gov/search?q={query}"},
]

SEARCH_QUERY = "Johnson %26 Johnson"


def search_source(source: dict, query: str = SEARCH_QUERY) -> list[dict]:
    session = get_session()
    url = source["search_url_template"].format(query=query)
    print(f"Searching {source['name']}: {url}")
    response = polite_get(session, url)
    if response is None:
        return []

    soup = BeautifulSoup(response.text, "lxml")
    # Placeholder — every site's search-result markup differs. Replace with
    # real selectors per source, or route the raw page text through
    # extraction.llm_extractor instead of hand-writing selectors for each.
    links = soup.select("a[href]")
    results = []
    seen = set()
    for link in links:
        text = link.get_text(strip=True)
        href = link.get("href")
        if not text or not href or href in seen:
            continue
        if "johnson" in text.lower():
            seen.add(href)
            results.append(
                {
                    "source_name": source["name"],
                    "headline": text,
                    "source_url": urljoin(url, href),
                }
            )
    return results


def main() -> None:
    all_results = []
    for source in SOURCES:
        all_results.extend(search_source(source))

    print(f"\n{len(all_results)} hit(s) across {len(SOURCES)} source(s):\n")
    for r in all_results:
        print(f"  [{r['source_name']}] {r['headline']}\n    {r['source_url']}")

    print(
        "\nThis scraper is a skeleton — add real search endpoints to SOURCES "
        "and prefer extraction.llm_extractor over hand-written selectors here, "
        "since each economic-development site has different markup."
    )


if __name__ == "__main__":
    main()
