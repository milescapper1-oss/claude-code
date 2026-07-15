"""Shared scraping utilities: polite HTTP session, robots.txt check, and a
Playwright fallback for pages that only render their content via JavaScript.

Every scraper module in this package should go through polite_get() first
and only reach for render_with_playwright() when the static HTML doesn't
contain the data it needs.
"""

from __future__ import annotations

import os
import time
import urllib.robotparser
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_DELAY_SECONDS = float(os.environ.get("SCRAPER_REQUEST_DELAY_SECONDS", "2"))

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def robots_allowed(url: str, user_agent: str = "*") -> bool:
    """Check robots.txt for the given URL's host before scraping it."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    parser = _robots_cache.get(origin)
    if parser is None:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(f"{origin}/robots.txt")
        try:
            parser.read()
        except OSError:
            # robots.txt unreachable — fail open, but callers should still
            # rate-limit and identify themselves via a real User-Agent.
            parser = None
        _robots_cache[origin] = parser
    if parser is None:
        return True
    return parser.can_fetch(user_agent, url)


def polite_get(
    session: requests.Session,
    url: str,
    *,
    max_retries: int = 3,
    timeout: int = 20,
    **kwargs,
) -> Optional[requests.Response]:
    """GET a URL with robots.txt compliance, rate limiting, and retries.

    Returns None (rather than raising) if the URL is disallowed by
    robots.txt or every retry fails, so callers can fall back to
    Playwright or just skip the page.
    """
    if not robots_allowed(url):
        print(f"  [skip] robots.txt disallows: {url}")
        return None

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(REQUEST_DELAY_SECONDS)
            response = session.get(url, timeout=timeout, **kwargs)
            if response.status_code == 200:
                return response
            if response.status_code in (403, 429) and attempt < max_retries:
                backoff = REQUEST_DELAY_SECONDS * (2**attempt)
                print(f"  [retry] {response.status_code} on {url}, backing off {backoff:.0f}s")
                time.sleep(backoff)
                continue
            print(f"  [warn] HTTP {response.status_code} on {url}")
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(REQUEST_DELAY_SECONDS * (2**attempt))
    print(f"  [error] giving up on {url}: {last_error}")
    return None


@dataclass
class RenderedPage:
    url: str
    html: str


def render_with_playwright(
    url: str,
    *,
    wait_selector: Optional[str] = None,
    wait_ms: int = 3000,
    timeout_ms: int = 30000,
) -> Optional[RenderedPage]:
    """Fall back to a headless browser for JS-rendered pages.

    Only import Playwright here (not at module level) so that scrapers
    which never need it don't require the dependency/browser install to
    even import.
    """
    if not robots_allowed(url):
        print(f"  [skip] robots.txt disallows: {url}")
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "  [error] playwright is not installed. Run:\n"
            "    pip install playwright && playwright install chromium"
        )
        return None

    time.sleep(REQUEST_DELAY_SECONDS)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=timeout_ms)
                except Exception:
                    # Selector never showed up — return whatever rendered
                    # anyway so callers/debug output can inspect it.
                    print(f"  [warn] selector '{wait_selector}' not found on {url}")
            else:
                page.wait_for_timeout(wait_ms)
            html = page.content()
            return RenderedPage(url=url, html=html)
        finally:
            browser.close()
