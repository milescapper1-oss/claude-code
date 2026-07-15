# jnj-mapping

Builds a targeted contact/organization map of Johnson & Johnson, scoped to
people relevant to industrial valve procurement (diaphragm valves for
biopharma manufacturing — engineering, C&Q, quality, procurement, and MSAT
roles).

Does **not** scrape LinkedIn (against ToS, gets blocked). Instead it's built
around public sources:

1. **J&J careers site** (`careers.jnj.com`) — open job postings tell you
   which sites have active capital projects and what roles they're hiring
   for. `scrapers/jnj_careers.py`.
2. **Press releases** (`jnj.com/media-center/press-releases`) — capital
   project announcements: site, investment size, facility type, executive
   quotes. `scrapers/press_releases.py`.
3. **State/local economic development sites** (NCBiotech, state commerce
   departments, etc.) — often name project details and leaders that J&J's
   own site doesn't. `scrapers/econ_dev.py`.

## Status

`scrapers/jnj_careers.py` is the first working script. The other two
scrapers are skeletons (see their module docstrings) — build them out the
same way once you've validated the careers scraper against the live site.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # only needed for the JS-rendered fallback path
cp .env.example .env          # fill in ANTHROPIC_API_KEY for extraction/llm_extractor.py
```

## Usage

```bash
# Run from the jnj-mapping/ directory (or add it to PYTHONPATH) so the
# `scrapers` and `extraction` packages resolve.
python -m scrapers.jnj_careers

# Save raw HTML for each page it visits, to calibrate selectors:
python -m scrapers.jnj_careers --debug

# Fewer pages, custom output location:
python -m scrapers.jnj_careers --max-pages 3 --out-dir ./data
```

Console output prints a results table before anything is written to disk.
Successful runs then write `data/jnj_careers_<timestamp>.json` and
`.csv` — one row per relevant job posting.

## Before you rely on this in production

`scrapers/jnj_careers.py` was written without live access to
`careers.jnj.com` from the build environment, so its CSS selectors and
search-URL pattern are best-effort defaults based on common enterprise
career-site patterns (Workday/iCIMS/SmartRecruiters/Radancy-style markup),
**not confirmed against the real site**. Run with `--debug`, inspect
`data/debug/*.html`, and adjust `JOB_CARD_SELECTORS` /
`SEARCH_URL_TEMPLATE` in `scrapers/jnj_careers.py` to match what you
actually see — the module docstring walks through exactly what to check.

## Project layout

```
scrapers/            one module per source (requests+BeautifulSoup first,
                      Playwright fallback for JS-rendered pages)
  base.py               shared HTTP session, robots.txt check, Playwright helper
  jnj_careers.py        careers.jnj.com — first working scraper
  press_releases.py     jnj.com press releases — skeleton
  econ_dev.py           state/local econ-dev sites — skeleton

extraction/
  llm_extractor.py     Claude-based fallback extractor for pages where
                        structured selectors fail — feed raw text, get back
                        JSON records (name, title, org, site, function,
                        source_url, date)

data/                 scraped output (JSON/CSV), gitignored — regenerate by
                      running the scrapers

                      Two exceptions, checked into git: contacts.json/csv
                      and conferences.json/csv are manually-researched (not
                      scraper output) — see data/README.md for methodology,
                      sources, and known gaps before relying on them.

dedup.py              entity resolution for site names and role titles
                      (alias table + fuzzy matching), e.g. reconciling
                      "Wilson, NC" / "Wilson NC facility" / "North Carolina
                      biologics site" to one canonical site
```

## Respectful scraping

`scrapers/base.py` checks `robots.txt` before every request, rate-limits
requests (`SCRAPER_REQUEST_DELAY_SECONDS` in `.env`, default 2s), retries
with backoff on 403/429, and sends a real browser User-Agent. Keep these in
place if you extend the scrapers — don't remove the delay or robots.txt
check to go faster.
