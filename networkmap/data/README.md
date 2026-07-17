# networkmap/data — researched target-account contacts

`contacts_networkmap.csv` is pipeline-ready in the schema the networkmap
ingester reads: `name,title,company,site,linkedin_url,last_seen`.
`contacts_research.json` is the same records with provenance
(`region, function, source_url, source_note, confidence`) **plus `tier` and
`rationale`**.
`contacts_ranked.csv` is the same records in the **Saunders diaphragm-valve
BD targeting format** — `Name | Title | Company | Tier | Site/Region |
Rationale`, sorted Tier 1 → 3 with de-prioritised names at the bottom.

## Targeting framework (what the tiers mean)

Contacts are ranked by influence over **valve specification, procurement, and
lifecycle/reliability decisions** (Saunders diaphragm valves + predictive
maintenance into CIP/SIP, utilities, upstream/downstream, fill & finish):

- **Tier 1 — PRIMARY** (specify / standardise / own valve & asset decisions):
  Engineering & Capital Projects, Engineering Standards owners, Asset
  Reliability & Maintenance, Utilities & Technical Services (steam/water/
  CIP/SIP), Biologics/large-molecule Tech Ops & MSAT, and site/plant leads at
  biologics & sterile sites.
- **Tier 2 — INFLUENCERS**: QA & Validation, Process Development & Engineering,
  Advanced Manufacturing/Technology, Strategic Sourcing/Procurement, External
  Manufacturing Technology.
- **Tier 3 — STRATEGIC/ACCESS**: EVP Manufacturing & direct reports,
  manufacturing-finance/capital-project business leads, non-US regional leads.
- **De-prioritise**: commercial/marketing, research-site leadership, IR, tax,
  clinical dev, regulatory affairs — low valve/equipment relevance.

Tier is auto-assigned from each contact's function/title by the build script;
verify Tier 3 vs Tier 1 at the margin before outreach.

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

Current count: **45 contacts** across the 6 accounts (AbbVie 6, BMS 7, Eli
Lilly 14, Novartis 5, Novo Nordisk 8, Roche/Genentech 5), of which **13 are
conference-confirmed speakers** (`meet_confidence: confirmed_speaker` — ISPE
Europe, ISPE Facilities of the Future, ISPE Aseptic, BPI Europe, and
Bioprocessing Summit 2026). J&J's 25 live separately in jnj-mapping, for **70
total** across all 7 accounts. Lilly is heaviest because it has by far the most active capital
projects; the BMS Devens working-level engineers (Daniel Post — capital
projects & utilities; Richard Martel — single-use) came via ISPE.org member
profiles, a good vein for sub-executive names.

## Confidence / caveats

- `confidence: stale_risk` — **Columba McGarvey** and **Darren Egan** (AbbVie
  Sligo site directors): only found in sources dated ~2019–2020. Verify they
  still hold these roles before outreach.
- Strongest **capital-project** matches (people whose actual job is delivering
  a build): **Flemming Dahl** (Novo — SVP, Head of Product Supply Fill & Finish
  Expansions), **Jay Kuykendall** (Novo — Project VP, Clayton expansion), and
  **Matthew von Zirkelbach** (Lilly — VP & Site Head, Lebanon Medicine
  Foundry). The two ISPE speakers (**Robert O'Keeffe**, Lilly Engineering /
  C&Q; **Lars Hovmand-Lyster**, Novo Engineering) are the best working-level
  engineering/C&Q contacts.
- `region` (US/Europe/Global) is the reliable geography field; `site` is
  emitted **as written** (often a multi-site list for global execs) and the
  networkmap resolver owns normalization — don't treat `site` as a canonical
  key.
- Lower manufacturing relevance (included for completeness): **Guy Oliver**
  (BMS UK&I country GM) and **Thierry Diagana** (Novartis — research-site
  leadership, not manufacturing).
- **Deliberately excluded**, left for your LinkedIn Navigator pass: names that
  surfaced only in gated sales databases (RocketReach/ZoomInfo/TheOrg) with no
  primary-source corroboration — e.g. AbbVie's CPO — and ASME BPE committee
  members whose only rosters were 2009–2012 (too stale).
- `site` is emitted **as written** (often a multi-site list for global execs).
  The networkmap org/site resolver owns normalization — don't treat these as
  canonical site keys.
- Genentech has a live open req "Project Director – Capital Projects,
  Oceanside" (careers.gene.com) — a named *role* but not yet a named person;
  noted in the JSON's Nazeli Dertsakian source_note.
- **Franck Bure** (Roche/Genentech) is a confirmed 2026 ISPE Aseptic
  Conference speaker but the listing carried **no job title** — a verified
  where-to-meet name whose role/function is unknown. Confirm before treating
  him as a manufacturing/engineering lead.

## Not yet included (next passes)

- Conference / "where to meet" data for these 6 (the J&J set has it; these
  don't yet).
- Site-level engineering/C&Q/procurement managers below the executive tier —
  those rarely appear in press; the careers-scraper signal
  (`scrapers/jnj_careers_signal.py`, extended to these accounts) is the
  intended route to surface which sites to dig into.
