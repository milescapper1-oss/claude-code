"""Basic entity resolution for site names and role titles.

Two complementary strategies, since they solve different problems:

1. A small hand-maintained alias table (SITE_ALIASES) for known J&J sites,
   because variants like "Wilson, NC" / "Wilson NC facility" / "North
   Carolina biologics site" don't share enough text to be found by fuzzy
   string matching alone — they need to be recognized as referring to the
   same place. Extend this table as you discover more sites/aliases.

2. Fuzzy clustering (stdlib difflib) for near-duplicate strings that
   *aren't* in the alias table yet — typos, punctuation differences,
   "Sr. Engineer" vs "Senior Engineer" — using SequenceMatcher on
   normalized text.

Use resolve_site() / resolve_title() to canonicalize a single record's
fields as you go, or dedup_records() to canonicalize + group a whole list
in one pass.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Known site aliases -> canonical name. Keys are matched after
# normalize_text(), so casing/punctuation in this table doesn't matter.
# Extend this as new sites/phrasings are discovered in scraped data.
SITE_ALIASES: dict[str, str] = {
    "wilson nc": "Wilson, NC (Biologics)",
    "wilson north carolina": "Wilson, NC (Biologics)",
    "wilson nc facility": "Wilson, NC (Biologics)",
    "north carolina biologics site": "Wilson, NC (Biologics)",
    "nc biologics site": "Wilson, NC (Biologics)",
    "cork ireland": "Cork, Ireland",
    "cork facility": "Cork, Ireland",
    "malvern pa": "Malvern, PA",
    "malvern pennsylvania": "Malvern, PA",
    "titusville nj": "Titusville, NJ",
    "raritan nj": "Raritan, NJ",
    "leiden netherlands": "Leiden, Netherlands",
    "beerse belgium": "Beerse, Belgium",
    "latina italy": "Latina, Italy",
}

# Titles that mean "no seniority/level info", stripped for matching so
# "Senior Quality Engineer" and "Sr. Quality Engineer" cluster together.
SENIORITY_TOKENS = [
    r"\bsenior\b",
    r"\bsr\.?\b",
    r"\bjunior\b",
    r"\bjr\.?\b",
    r"\blead\b",
    r"\bprincipal\b",
    r"\bstaff\b",
    r"\b(i|ii|iii|iv|v)\b",
]

FUZZY_MATCH_THRESHOLD = 0.82


def normalize_text(raw: str) -> str:
    text = raw.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)  # drop all punctuation, including commas
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(raw: str) -> str:
    text = normalize_text(raw)
    for pattern in SENIORITY_TOKENS:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class EntityResolver:
    """Canonicalizes a growing stream of site names or titles.

    First checks the static alias table, then compares against strings it
    has already seen this run and reuses the closest canonical form above
    FUZZY_MATCH_THRESHOLD, otherwise registers the input as a new
    canonical form.
    """

    def __init__(self, aliases: dict[str, str] | None = None, normalizer=normalize_text):
        self.aliases = aliases or {}
        self.normalizer = normalizer
        # normalized canonical form -> display canonical form
        self._canonical: dict[str, str] = {}

    def resolve(self, raw: str) -> str:
        if not raw or not raw.strip():
            return raw
        normalized = self.normalizer(raw)

        alias_hit = self.aliases.get(normalized)
        if alias_hit:
            self._canonical.setdefault(normalize_text(alias_hit), alias_hit)
            return alias_hit

        best_match, best_score = None, 0.0
        for seen_normalized, seen_canonical in self._canonical.items():
            score = _similar(normalized, seen_normalized)
            if score > best_score:
                best_match, best_score = seen_canonical, score

        if best_match and best_score >= FUZZY_MATCH_THRESHOLD:
            return best_match

        # New canonical entry — use the raw (trimmed) form as the display
        # value the first time we see something like it.
        canonical_display = raw.strip()
        self._canonical[normalized] = canonical_display
        return canonical_display


def resolve_site(raw: str, resolver: EntityResolver | None = None) -> str:
    resolver = resolver or EntityResolver(aliases=SITE_ALIASES, normalizer=normalize_text)
    return resolver.resolve(raw)


def resolve_title(raw: str, resolver: EntityResolver | None = None) -> str:
    resolver = resolver or EntityResolver(normalizer=normalize_title)
    return resolver.resolve(raw)


def dedup_records(
    records: list[dict],
    *,
    site_field: str = "site",
    title_field: str = "title",
) -> list[dict]:
    """Add canonical_site/canonical_title fields to each record in place
    (returning the same list) using one resolver per field so canonical
    forms are consistent across the whole batch.
    """
    site_resolver = EntityResolver(aliases=SITE_ALIASES, normalizer=normalize_text)
    title_resolver = EntityResolver(normalizer=normalize_title)

    for record in records:
        if record.get(site_field):
            record["canonical_site"] = resolve_site(record[site_field], site_resolver)
        if record.get(title_field):
            record["canonical_title"] = resolve_title(record[title_field], title_resolver)
    return records


if __name__ == "__main__":
    demo_sites = [
        "Wilson, NC",
        "Wilson NC facility",
        "North Carolina biologics site",
        "Cork, Ireland",
        "Cork facility",
        "Raritan NJ",
    ]
    resolver = EntityResolver(aliases=SITE_ALIASES, normalizer=normalize_text)
    print("Site canonicalization demo:")
    for site in demo_sites:
        print(f"  {site!r:45} -> {resolver.resolve(site)!r}")
