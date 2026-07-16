"""Scraper for jnj.com/media-center/press-releases — capital project
announcements: site name, investment size, facility type, and key
executive quotes (name + title).

STATUS: skeleton, not yet implemented. jnj_careers.py is the first working
scraper in this project; this module follows the same base.py pattern
(polite_get -> BeautifulSoup, render_with_playwright fallback) but the
listing/detail-page selectors still need to be filled in against the real
site, the same way described in jnj_careers.py's module docstring.

Target fields per press release:
    site_name, investment_amount, facility_type, executive_name,
    executive_title, quote_text, source_url, publish_date

Suggested approach once selectors are calibrated:
    1. Scrape the press release index for links + publish dates.
    2. Filter titles/summaries for capital-project signal words: "invest",
       "expand", "new facility", "manufacturing", "biologics", "plant".
    3. Fetch each matching release and extract body text.
    4. Try structured selectors for a quote block first; if the press
       release layout doesn't cooperate, fall back to
       extraction.llm_extractor.extract_records_from_text() on the raw
       article text — this is exactly the case that fallback exists for.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import get_session, polite_get, render_with_playwright

BASE_URL = "https://www.jnj.com"
INDEX_URL = BASE_URL + "/media-center/press-releases"

CAPITAL_PROJECT_SIGNAL_WORDS = [
    "invest",
    "investment",
    "expand",
    "expansion",
    "new facility",
    "manufacturing facility",
    "biologics",
    "breaks ground",
    "groundbreaking",
]


def fetch_index(max_pages: int = 3) -> list[dict]:
    """Return [{title, source_url, publish_date}, ...] from the press
    release index. TODO: verify pagination + card selectors against the
    live site (see jnj_careers.py docstring for the same calibration
    workflow).
    """
    session = get_session()
    response = polite_get(session, INDEX_URL)
    if response is None:
        print("  no static HTML for press release index, try render_with_playwright()")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    # Placeholder selector — replace once the real markup is known.
    cards = soup.select('a[href*="/media-center/press-releases/"]')
    results = []
    for card in cards:
        title = card.get_text(strip=True)
        href = card.get("href")
        if title and href:
            results.append({"title": title, "source_url": urljoin(BASE_URL, href)})
    return results


def is_capital_project(title: str) -> bool:
    lowered = title.lower()
    return any(word in lowered for word in CAPITAL_PROJECT_SIGNAL_WORDS)


def main() -> None:
    releases = fetch_index()
    relevant = [r for r in releases if is_capital_project(r["title"])]
    print(f"Found {len(releases)} press releases, {len(relevant)} look capital-project-related.")
    for r in relevant:
        print(f"  {r['title']}\n    {r['source_url']}")
    print(
        "\nThis scraper is a skeleton — extend fetch_index()/detail-page parsing "
        "once you've inspected the live site's markup (see module docstring)."
    )


if __name__ == "__main__":
    main()
