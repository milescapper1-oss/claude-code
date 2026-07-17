# networkmap/data — researched target-account contacts

`contacts_networkmap.csv` is pipeline-ready in the schema the networkmap
ingester reads: `name,title,company,site,linkedin_url,last_seen`.
`contacts_research.json` is the same records with provenance
(`region, function, source_url, source_note, confidence`).

## Scope

Covers **6 of the 7 target accounts** — AbbVie, Bristol Myers Squibb, Eli
Lilly, Novartis, Novo Nordisk, Roche/Genentech. **Johnson & Johnson (the 7th)
is researched separately** and lives in the jnj-mapping project's
`data/contacts.json` (25 contacts, richer conference/where-to-meet data).

## Methodology

Compiled via web search (2026-07-17). Every record traces to a public,
non-LinkedIn source — company/investor press releases, official leadership
pages, government economic-development announcements (IDA Ireland, NCBiotech,
EDPNC), and trade press. `linkedin_url` is **intentionally left blank**: this
project does not source from LinkedIn.

Ingestion rules applied at build time: rows missing *both* name and company
are skipped; exact `(name, company)` duplicates are deduped.

## Confidence / caveats

- `confidence: stale_risk` — **Columba McGarvey** and **Darren Egan** (AbbVie
  Sligo site directors): only found in sources dated ~2019–2020. Verify they
  still hold these roles before outreach.
- Most entries are **operations/manufacturing/supply-chain leadership** (EVP
  Ops, Chief Supply Chain Officer, site GM). The strongest single
  capital-project match is **Jay Kuykendall — Project VP, Novo Nordisk Clayton
  expansion** (a role dedicated to delivering one build).
- `site` is emitted **as written** (often a multi-site list for global execs).
  The networkmap org/site resolver owns normalization — don't treat these as
  canonical site keys.
- Genentech has a live open req "Project Director – Capital Projects,
  Oceanside" (careers.gene.com) — a named *role* but not yet a named person;
  noted in the JSON's Nazeli Dertsakian source_note.

## Not yet included (next passes)

- Conference / "where to meet" data for these 6 (the J&J set has it; these
  don't yet).
- Site-level engineering/C&Q/procurement managers below the executive tier —
  those rarely appear in press; the careers-scraper signal
  (`scrapers/jnj_careers_signal.py`, extended to these accounts) is the
  intended route to surface which sites to dig into.
