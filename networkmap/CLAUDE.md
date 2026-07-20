# Saunders Valve-BD Network Map — agent context

You are helping maintain a biopharma business-development targeting database for
selling **Saunders diaphragm valves + predictive-maintenance** into biopharma
capital projects (CIP/SIP, utilities, fill-finish, upstream/downstream).

**8 target accounts:** Eli Lilly · Bristol Myers Squibb · Novo Nordisk · AbbVie ·
AstraZeneca · Novartis · Roche/Genentech · Johnson & Johnson.

## Persona framework (rank by influence over valve spec/procurement/lifecycle)
- **Tier 1 primary:** Engineering/Capital Projects, Engineering Standards, Asset
  Reliability & Maintenance, Utilities/CIP-SIP, MSAT, Site Leads
- **Tier 2 influencers:** QA & Validation, Process Dev, Advanced Mfg, Strategic
  Sourcing/Procurement, External Mfg Tech
- **Tier 3 strategic:** EVP Mfg + direct reports, Mfg Finance, non-US regional
- **De-prioritise:** commercial/marketing/IR/clinical/regulatory/BD&L/medical

## How the pipeline works
`data/contacts_source.csv` is the **single source of truth**. Everything else in
`data/` is generated — never hand-edit generated files.

```
pip install -r requirements.txt        # once (openpyxl)
# append rows to data/contacts_source.csv, then:
python scripts/build.py                 # -> json, ranked csv, persona csv, xlsx
python scripts/make_orgmap.py           # -> data/orgmaps/*.html
git add . && git commit -m "..." && git push
```

`build.py` auto-tiers every contact from its title (tier / role level / org layer /
persona). To change rules, edit `classify()`, `level()`, `PERSONAS` in `scripts/build.py`.

## Conventions (important)
- **Never scrape LinkedIn directly** (ToS) — the user pastes Navigator exports.
- Org layers are **inferred from titles, NOT confirmed reporting lines** — always
  keep that caveat on any org chart or hierarchy.
- **Exclude non-target companies** (Pfizer, Merck/MSD, GSK, Sanofi, Takeda, CDMOs
  like Catalent/Lonza/Vetter, vendors, consultants) and de-prioritise commercial/
  regulatory/medical roles. Only the 8 accounts above are targets.
- Only `name`, `title`, `company` are required per contact; title drives tiering.

## Current state
~510 contacts (Navigator ~407 / Public ~103), all 8 accounts, ~100 decision-makers,
~47 event speakers, 41 events, 25 projects. A separate master DB also holds ~545 IIR
project contacts + 69 IIR projects to be merged.

## Open tasks
1. **Merge IIR:** add an `IIR` source value + a `project` column linking contacts to
   `live_projects.csv`; dedup ~545 project contacts against existing contacts.
2. **Backfill thin accounts** (Roche, Novartis) from per-company Navigator sweeps.
3. **Automation:** (a) GitHub Action to run build on push; (b) Claude-API chatbot over
   `contacts_research.json`; (c) Salesforce sync (Accounts/Contacts/Opportunities/
   Campaigns, upsert via Bulk API, dedup on name+company/email).

Start by reading `README.md` and running `python scripts/build.py` to confirm the
pipeline works, then continue with the open tasks.
