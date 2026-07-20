"""Offline smoke test for jnj_careers_signal.py.

Exercises everything downstream of the network fetch — Phenom parsing,
keyword filter, per-site grouping, dedup, output shape — against a mock
payload, since the live careers.jnj.com endpoint is not reachable from the
build sandbox. Not shipped as part of the module; a dev-time check.
"""
import json

import jnj_careers_signal as m

# Mock Phenom /api/jobs payload mixing shapes the defensive parser must handle:
#  - nested under "data" (typical Phenom) AND flat
#  - cityStateCountry vs city/state/country parts vs "location"
#  - applyUrl vs jobUrl vs url; postedDate vs datePosted
MOCK = {
    "jobs": [
        {"data": {"title": "Senior Engineer, C&Q", "cityStateCountry": "Raritan, New Jersey, United States",
                  "postedDate": "2026-07-01", "applyUrl": "https://careers.jnj.com/en/jobs/r-1/senior-engineer-cq/"}},
        {"data": {"title": "Validation Specialist", "cityStateCountry": "Raritan, New Jersey, United States",
                  "postedDate": "2026-07-02", "applyUrl": "https://careers.jnj.com/en/jobs/r-2/validation/"}},
        {"data": {"title": "Commissioning Lead", "city": "Raritan", "state": "New Jersey", "country": "United States",
                  "datePosted": "2026-07-03", "jobUrl": "https://careers.jnj.com/en/jobs/r-3/commissioning/"}},
        {"data": {"title": "MSAT Engineer", "location": "Raritan, NJ",  # near-dup spelling, diff casing/spacing
                  "postedDate": "2026-07-04", "url": "https://careers.jnj.com/en/jobs/r-4/msat/"}},
        {"data": {"title": "Quality Manager", "cityStateCountry": "Raritan, New Jersey, United States",
                  "postedDate": "2026-07-05", "applyUrl": "https://careers.jnj.com/en/jobs/r-5/quality-mgr/"}},
        # Cork site — only 2 matching
        {"title": "Process Engineering Lead", "cityStateCountry": "Cork, Ireland",  # flat (no "data")
         "postedDate": "2026-07-01", "applyUrl": "https://careers.jnj.com/en/jobs/r-6/process-eng/"},
        {"data": {"title": "Procurement Analyst", "cityStateCountry": "Cork, Ireland",
                  "postedDate": "2026-07-02", "applyUrl": "https://careers.jnj.com/en/jobs/r-7/procurement/"}},
        # Non-matching titles (must be filtered out)
        {"data": {"title": "Sales Representative", "cityStateCountry": "New Brunswick, New Jersey, United States",
                  "applyUrl": "https://careers.jnj.com/en/jobs/r-8/sales/"}},
        {"data": {"title": "Marketing Manager", "cityStateCountry": "Cork, Ireland",
                  "applyUrl": "https://careers.jnj.com/en/jobs/r-9/marketing/"}},
        # Duplicate of r-1 (dedup on url should drop it at fetch layer; here we
        # test parse only, so it will appear — grouping dedups sample titles)
        {"data": {"title": "Senior Engineer, C&Q", "cityStateCountry": "Raritan, New Jersey, United States",
                  "applyUrl": "https://careers.jnj.com/en/jobs/r-1/senior-engineer-cq/"}},
    ]
}

failures = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


print("=== _parse_phenom_jobs (defensive field extraction) ===")
parsed = m._parse_phenom_jobs(MOCK)
check("parsed all 10 job entries", len(parsed) == 10)
check("nested 'data' title extracted", any(p.title == "MSAT Engineer" for p in parsed))
check("flat (no 'data') entry extracted", any(p.title == "Process Engineering Lead" for p in parsed))
check("city/state/country assembled when no cityStateCountry",
      any(p.site == "Raritan, New Jersey, United States" and p.title == "Commissioning Lead" for p in parsed))
check("alt date field (datePosted) read", any(p.posted_date == "2026-07-03" for p in parsed))
check("alt url field (jobUrl/url) read",
      any(p.url == "https://careers.jnj.com/en/jobs/r-4/msat/" for p in parsed))

print("\n=== title_matches (keyword filter) ===")
check("matches 'C&Q'", m.title_matches("Senior Engineer, C&Q"))
check("matches 'commissioning' (case-insensitive)", m.title_matches("COMMISSIONING Lead"))
check("matches 'msat'", m.title_matches("MSAT Engineer"))
check("rejects 'Sales Representative'", not m.title_matches("Sales Representative"))
check("rejects 'Marketing Manager'", not m.title_matches("Marketing Manager"))

print("\n=== _filter_and_group (grouping + output shape) ===")
records = m._filter_and_group(parsed, org=m.ORG, source_url=m.CAREERS_SEARCH_URL)
# INTENTIONAL: "Raritan, New Jersey, United States" and "Raritan, NJ" are left
# as SEPARATE records — folding NJ<->New Jersey is site normalization, which
# the requirements explicitly reserve for the downstream pipeline's resolver.
# This scraper only collapses pure case/whitespace noise. So we expect 3
# records: full-spelling Raritan, Cork, and the "Raritan, NJ" near-dup.
check("3 records emitted; non-matching-only sites dropped; near-dup site left as-written",
      len(records) == 3)
check("sorted by matching_postings desc", records[0]["matching_postings"] >= records[-1]["matching_postings"])

raritan = next((r for r in records if r["site"] == "Raritan, New Jersey, United States"), None)
check("full-spelling Raritan present", raritan is not None)
# r-1,2,3,5 matching + dup r-1 all share the full spelling -> 5 rows, dedup in samples
check("Raritan count reflects grouped matches (dup posting counted, sample deduped)",
      raritan["matching_postings"] == 5)
check("'Raritan, NJ' near-dup emitted separately for the resolver to fold",
      any(r["site"] == "Raritan, NJ" for r in records))
check("sample_titles deduped (no repeated 'Senior Engineer, C&Q')",
      raritan["sample_titles"].count("Senior Engineer, C&Q") == 1)
check("sample_titles capped at 5", len(raritan["sample_titles"]) <= 5)
check("output has exact required keys",
      set(raritan.keys()) == {"org", "site", "matching_postings", "sample_titles", "source_url"})
check("org is 'Johnson & Johnson'", raritan["org"] == m.ORG)

cork = next((r for r in records if r["site"].startswith("Cork")), None)
check("Cork present with 2 matching (eng + procurement, marketing excluded)",
      cork is not None and cork["matching_postings"] == 2)

print("\n=== full JSON output preview ===")
print(json.dumps(records, indent=2))

print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILURE(S): {failures}"))
raise SystemExit(1 if failures else 0)
