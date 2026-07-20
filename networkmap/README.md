# Saunders Valve-BD Network Map

Target-account contact + project + event intelligence for selling Saunders diaphragm
valves and predictive-maintenance into biopharma capital projects.

**8 target accounts:** Eli Lilly · Bristol Myers Squibb · Novo Nordisk · AbbVie ·
AstraZeneca · Novartis · Roche/Genentech · Johnson & Johnson.

---

## The one rule

**`data/contacts_source.csv` is the single source of truth.** You edit that; everything
else is generated. Never hand-edit the generated files — they get overwritten.

---

## Setup (once)

```bash
cd networkmap
pip install -r requirements.txt      # just openpyxl
```

## To add contacts (e.g. a LinkedIn Sales Navigator sweep)

1. Open `data/contacts_source.csv` in VS Code (or Excel).
2. **Append** one row per person. Columns:

   | column | required | notes |
   |---|---|---|
   | `name` | ✅ | full name |
   | `title` | ✅ | drives auto-tiering — keep it as LinkedIn shows it |
   | `company` | ✅ | use the exact account name (`Eli Lilly`, `Bristol Myers Squibb`, `Roche/Genentech`, `Johnson & Johnson`, …) |
   | `site` | | e.g. `Cork, Ireland` |
   | `region` | | `US` / `Europe` / `Asia` / `global` |
   | `function` | | optional hint; title alone usually tiers fine |
   | `source` | | `Navigator` or `Public` |
   | `meet_at` | | event where they speak/attend → feeds "Where to Meet" |
   | `meet_confidence` | | `confirmed-speaker` / `conference-active` |
   | `notes` | | free text / provenance |

   Example:
   ```csv
   Jane Doe,"Director, Capital Projects",Eli Lilly,"Kinsale, Ireland",Europe,,Navigator,,,LinkedIn sweep 2026-07
   ```

3. Regenerate everything:

   ```bash
   python scripts/build.py          # -> json, ranked csv, persona csv, xlsx
   python scripts/make_orgmap.py    # -> data/orgmaps/*.html (per-account org charts)
   ```

4. Commit & push:

   ```bash
   git add networkmap/
   git commit -m "Add <account> Navigator sweep (N contacts)"
   git push
   ```

## What gets generated (in `data/`)

| file | what |
|---|---|
| `contacts_all.xlsx` | multi-tab workbook: Summary · Decision-Makers · All Contacts · one tab per account |
| `contacts_ranked.csv` | Name · Title · Company · Tier · Site/Region · Rationale |
| `contacts_persona_match.csv` | every contact → specific persona + source + where-to-meet |
| `contacts_research.json` | full structured records (what the org-map reads) |
| `orgmaps/*.html` | one printable org chart per account (open `index.html`) |

Companion data you maintain by hand: `events_targets.csv` (target conferences),
`live_projects.csv` (IIR-style capital projects), `events_speakers.csv`.

## How tiering works

`scripts/build.py` reads each `title` and assigns:
- **Tier** (1 primary / 2 influencer / 3 exec / 0 de-prioritise) — valve-BD influence
- **Role level** (1–6) and **Org layer** (Leadership / Global-Functional / Site-Working)
- **Persona** (Utilities/CIP-SIP, Capital Projects, MSAT, Maintenance, Procurement, …)

To change the rules, edit the `classify()`, `level()`, and `PERSONAS` blocks in
`scripts/build.py`, then re-run. All contacts re-tier consistently.

## Caveat (important)

Org layers are **inferred from job titles** — a seniority proxy, **not confirmed
reporting lines** (LinkedIn does not expose who reports to whom). Names and titles are
real; the vertical bands are best-inference.
