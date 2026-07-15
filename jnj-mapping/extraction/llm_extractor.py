"""LLM-based fallback extractor, used when a scraper's structured CSS
selectors fail to find data on a page (e.g. a press release or economic
development article with markup too inconsistent to hand-write selectors
for). Feeds raw page text to Claude and gets back structured JSON.

Requires ANTHROPIC_API_KEY (see .env.example). Uses python-dotenv so a
local .env file is picked up automatically.
"""

from __future__ import annotations

import json
import os
from typing import Optional, TypedDict

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")

RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": ["string", "null"],
                        "description": "Person's full name, if the page names one. Null if this record is about a site/project with no named individual.",
                    },
                    "title": {
                        "type": ["string", "null"],
                        "description": "The person's job title, e.g. 'Vice President of Engineering'.",
                    },
                    "org": {
                        "type": "string",
                        "description": "Organization, e.g. 'Johnson & Johnson' or a named subsidiary.",
                    },
                    "site": {
                        "type": ["string", "null"],
                        "description": "The facility/site name or location this record relates to, e.g. 'Wilson, NC biologics site'.",
                    },
                    "function": {
                        "type": ["string", "null"],
                        "description": "Functional area if discernible: Engineering, Quality, Procurement, C&Q/Validation, MSAT, or null if not applicable/unknown.",
                    },
                    "date": {
                        "type": ["string", "null"],
                        "description": "Date associated with this record (announcement date, posting date), in ISO 8601 (YYYY-MM-DD) if possible, else the raw text found.",
                    },
                },
                "required": ["org", "name", "title", "site", "function", "date"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["records"],
    "additionalProperties": False,
}

EXTRACTION_PROMPT = """\
You are extracting structured data from a page about Johnson & Johnson for a \
sales/market-research project mapping capital projects and the people \
relevant to industrial valve procurement (diaphragm valves for biopharma \
manufacturing: engineering, C&Q, quality, procurement, and MSAT roles).

From the page text below, extract every distinct fact you can find about:
- named people (with title/role) connected to J&J facilities or projects
- named J&J manufacturing/biologics sites or capital projects, even if no
  individual is named for them

Return one record per distinct person OR per distinct site/project mention \
(use null for fields that don't apply — e.g. a site-only record has \
name=null and title=null). Do not invent information that is not present \
in the text. If nothing relevant is in the text, return an empty list.

Source URL: {source_url}
{date_context}

PAGE TEXT:
{text}
"""


class ExtractedRecord(TypedDict):
    name: Optional[str]
    title: Optional[str]
    org: str
    site: Optional[str]
    function: Optional[str]
    source_url: str
    date: Optional[str]


def extract_records_from_text(
    text: str,
    source_url: str,
    *,
    date: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> list[ExtractedRecord]:
    """Send raw page text to Claude and get back structured records.

    Truncates very long input rather than silently dropping the call —
    callers scraping long press releases or article pages should be fine
    within this limit; if you're hitting it often, chunk the text instead
    of raising the limit blindly.
    """
    import anthropic

    max_chars = 40_000
    if len(text) > max_chars:
        text = text[:max_chars]

    client = anthropic.Anthropic()

    date_context = f"Known publish date: {date}" if date else ""
    prompt = EXTRACTION_PROMPT.format(
        source_url=source_url, date_context=date_context, text=text
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        output_config={"format": {"type": "json_schema", "schema": RECORD_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )

    text_block = next((b.text for b in response.content if b.type == "text"), None)
    if text_block is None:
        return []

    parsed = json.loads(text_block)
    records = []
    for record in parsed.get("records", []):
        records.append(
            ExtractedRecord(
                name=record.get("name"),
                title=record.get("title"),
                org=record.get("org", "Johnson & Johnson"),
                site=record.get("site"),
                function=record.get("function"),
                source_url=source_url,
                date=record.get("date") or date,
            )
        )
    return records


if __name__ == "__main__":
    sample_text = (
        "Johnson & Johnson today announced a $2 billion expansion of its "
        "biologics manufacturing site in Wilson, North Carolina. "
        "\"This facility will be central to our next generation of "
        "biologics production,\" said Jane Smith, Vice President of "
        "Engineering at Johnson & Johnson."
    )
    for record in extract_records_from_text(
        sample_text, source_url="https://example.com/press-release", date="2026-01-01"
    ):
        print(record)
