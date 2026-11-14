# Blindspot API contract (v2)

**v2 product model.** The market is every European company with a closed funding round since **2022-01-01**
that has at least one named investor (VC, angel, accelerator, university fund, ...), as found in Cala by
snowballing the investor network and `knowledge_search` seeds. It is no longer limited to peer funds' deals.
A **blind spot** is a market company inside the fund's thesis that never appears in its CRM.
The period is **since 2022-01-01 everywhere**.

**Transition.** Until the frontend switches, `POST /api/audit` and `GET /api/audit/demo` return the v2 fields
below **and** the legacy v1 fields (`peers`, `venn`, `heatmap`, `top_blind_spots`, `never_seen_deals`,
`top_missed_leads`, `summary.market_deals`, `summary.in_pipeline`). Legacy fields are deprecated and will be
removed; build against v2 only. v2 mocks: `docs/mocks/`.

Single source of truth between `/backend` (FastAPI) and `/frontend` (Next.js).
Backend base URL: `http://localhost:8000` locally. Frontend reads it from `NEXT_PUBLIC_API_URL` (a URL, never a key).
All API keys (Cala, Anthropic, database) live ONLY in the backend `.env` / hosting env vars.
Any change to this contract must update this file and `frontend/mocks/` in the same commit.

Common types:
- `Source = { "name": str, "url": str, "rank": "FILING"|"PRIMARY"|"PRESS"|"AGGREGATOR"|null, "date": "YYYY-MM-DD"|null }`
  (`rank`: FILING = registries/regulators, PRIMARY = the company or its investors, PRESS = independent press,
  AGGREGATOR = funding databases; `date` = publication/retrieval date of the source)
- Amounts are numbers in the original currency plus a `currency` code. Dates are ISO `YYYY-MM-DD`.
- Stages use Cala codes: `PRE_SEED, SEED, SERIES_A, SERIES_B, SERIES_C, ...`

## GET /api/funds/search?q=earlybird
```json
[{ "id": "uuid", "name": "Earlybird Venture Capital" }]
```

## GET /api/funds/{fund_id}/profile
The fund's thesis, inferred from its own investments in Cala. No user input. **Every number uses the same
period (since 2022-01-01) and scope (companies headquartered in Europe).**
```json
{
  "fund": { "id": "uuid", "name": "Earlybird Venture Capital" },
  "period": { "from": "2022-01-01", "to": "2026-11-14" },
  "scope": "Europe",
  "investments_since_2022": 9,
  "out_of_scope_deals": 1,
  "stages":     [{ "label": "SEED", "share": 0.33 }],
  "countries":  [{ "name": "Germany", "count": 4 }],
  "industries": [{ "name": "Software and services", "count": 3 }],
  "thesis": {
    "stages": ["PRE_SEED", "SEED", "SERIES_A"],
    "countries": ["Germany", "Austria", "Switzerland", "Liechtenstein", "Finland", "Sweden", "Denmark", "Norway", "Iceland", "France", "Monaco"],
    "industries": [{ "code": "SOFTWARE_AND_SERVICES", "name": "Software and services" }]
  },
  "suggested_peers": [{ "id": "uuid", "name": "Cherry Ventures", "co_investments": 7, "score": 51.2,
                       "reasons": ["DACH focus: 80% of your deals, 80% of theirs"] }],
  "sources": [Source]
}
```
- `investments_since_2022`: rounds since 2022-01-01 of European companies in which the fund is a named
  participant (or, where Cala has no participant list, the first such round of each portfolio company).
  `out_of_scope_deals`: the same, for companies outside Europe (shown nowhere else).
- `stages` / `countries` / `industries`: counts and shares over exactly those rounds.
- `thesis` is the **hard filter** applied to the market: stages with at least 15% of those rounds, plus every
  stage between the lowest and the highest of them (an early-stage fund never sees Series C); the fund's
  countries widened to their region (e.g. Germany → DACH); its industries (Cala codes). A company with no
  industry in Cala is not excluded by the industry filter.
- `suggested_peers` (thesis similarity, `backend/peers.py`) is context for the UI only; peers no longer define
  the market.

## POST /api/audit  (multipart/form-data)
Fields: `fund_id` (str), `crm_csv` (file: any CRM export as `.csv` or `.xlsx`), optional `mapping` (JSON string, see below). `peer_ids` is accepted for backwards compatibility and ignored in v2.
Header `X-Access-Code: <code>` is required (the backend's `AUDIT_ACCESS_CODE`; ask the team, never commit it).

**Accepted files.** `.csv` (any delimiter `, ; tab |`, UTF-8/UTF-16/Windows-1252, report title rows above the header are skipped) or `.xlsx` (first sheet only; read with cached cell values, formulas are never calculated, macro workbooks `.xlsm` and legacy `.xls` are rejected). Detection uses the file extension and content; the part's content type may be `text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `application/vnd.ms-excel`, `application/octet-stream`, `text/plain` or empty. At most 2 MB and 5,000 data rows. The file is parsed in memory, never stored, and discarded after the request.

**Column detection** (deterministic rules, no LLM): header synonyms plus sample values select one column per field:
- `company`: e.g. Company, Company Name, Organization (Name), Account Name, Startup, Name, Associated Company; deal titles (Deal Name, Opportunity Name) only as a last resort; person/owner columns are never used.
- `website`: e.g. Website, Domain(s), URL, Company Domain Name, Homepage; values must look like domains.
- `status`: e.g. Status, Stage, Deal Stage, Pipeline Stage, List Status, Outcome, Decision; a column holding decisions (won/lost, passed) beats a pure pipeline-stage column.
- `date`: e.g. Date Added, Created (At/Date), Create Date, First Contact, Added At; dates become ISO `YYYY-MM-DD` (d/m vs m/d decided per column).
Only `company` or `website` is required (422 `no_company_column` otherwise).

**Status mapping** (case-insensitive, whole words; passed terms are checked first, so "Not invested" and "Closed Lost" are passed):
- `invested`: Portfolio, Portfolio Company, Portco, Invested, Investment Made, Closed Won, Won, Funded, Signed, Closed Deal
- `passed`: Pass, Passed, Declined, Lost, Closed Lost, Rejected, Dead, Killed, No Go, Turned Down, Not Interested, Not a Fit, Dropped, Not Invested, Abandoned, Dismissed
- `in_review`: everything else (Due Diligence, IC, Term Sheet, Lead, Contacted, Open, ...)
- `seen`: empty status cell or no status column. In the audit `summary`, seen rows count as `in_review` (the company reached the pipeline without a decision).

**`mapping` override** (optional, both endpoints): `{"company": "<header>", "website": "<header>"|null, "status": "<header>"|null, "date": "<header>"|null}`. Keys must be those four fields and values existing headers (as returned by the preview's `columns`); `null` disables a field. 422 `invalid_mapping` otherwise.

Errors are JSON `{ "error": str, "detail": str }`: 401 missing/wrong code, 413 too large / too many rows / workbook expands beyond 64 MB, 415 not `.csv`/`.xlsx` (or macros, legacy `.xls`), 422 no company column / invalid mapping, 429 rate limit (10 audits per 10 min per IP), 503 audits disabled or no live data on this deployment. `GET /api/audit/demo` stays public.

## POST /api/audit/preview  (multipart/form-data)
Same upload, header, limits and optional `mapping` as `POST /api/audit` (`fund_id` / `peer_ids` are ignored). Spends no Cala or Claude calls; own rate limit (30 per 10 min per IP). Returns what the import detected so the user can confirm or override the mapping before running the audit:
```json
{
  "file_type": "xlsx",
  "columns": ["Deal Name", "Associated Company", "Company Domain Name", "Deal Stage", "Create Date"],
  "mapping": { "company": "Associated Company", "website": "Company Domain Name", "status": "Deal Stage", "date": "Create Date" },
  "row_count": 412,
  "skipped_rows": 3,
  "matched_rows": 187,
  "status_counts": { "invested": 12, "passed": 240, "in_review": 151, "seen": 9 },
  "sample_rows": [
    { "company": "Vayu Robotics", "website": "vayu-robotics.se", "status": "passed", "raw_status": "Closed lost", "date": "2024-06-14", "matched": true }
  ],
  "warnings": ["no website column found: companies are matched by name only"]
}
```
`row_count` counts rows with a company name or website; `skipped_rows` the rest. `matched_rows` is how many rows match any crawled Cala company (by domain, then normalized name), or `null` when live data is unavailable. `sample_rows` holds the first 5 rows. `mapping` values and `date`, `raw_status`, `website` may be `null`/empty.

### Response of POST /api/audit (v2)
```json
{
  "audit_id": "str",
  "fund": { "id": "uuid", "name": "Earlybird Venture Capital" },
  "simulated_crm": true,
  "period": { "from": "2022-01-01", "to": "2026-11-14" },
  "thesis": {
    "stages": ["PRE_SEED", "SEED", "SERIES_A"],
    "countries": ["Germany", "Austria", "Switzerland"],
    "industries": [{ "code": "SOFTWARE_AND_SERVICES", "name": "Software and services" }],
    "basis_rounds": 9
  },
  "headline": { "never_seen": 23, "text": "23 companies in your thesis raised since 2022 and never hit your CRM" },
  "summary": { "market_companies": 41, "in_crm": 18, "invested": 4, "passed": 9, "in_review": 5,
               "never_seen": 23, "coverage_pct": 43.9 },
  "never_seen": [{
    "company_id": "uuid", "name": "Vayu Robotics", "website": "vayu-robotics.se", "country": "Sweden",
    "industries": ["Software and services"],
    "round": {
      "id": "uuid", "label": "SEED", "amount": 4200000, "currency": "EUR",
      "date": "2024-06-14", "date_kind": "announcement",
      "investors": [{ "id": "uuid", "name": "Creandum", "type": "Organization", "is_lead": true }],
      "sources": [{ "name": "tech.eu", "url": "https://tech.eu/...", "rank": "PRESS", "date": "2024-06-14" }]
    }
  }],
  "top_investors_in_blind_spots": [{ "id": "uuid", "name": "Creandum", "companies": 4 }],
  "market_coverage": { "european_companies_screened": 3100, "qualifying_companies": 260,
                       "investors_explored": 410, "as_of": "2026-11-14" }
}
```
Semantics:
- **Market** (`summary.market_companies`): companies headquartered in Europe with a *qualifying round*: closed
  since 2022-01-01 (announcement date, else event date), at least one named investor of any type, at least one
  Cala source, and not flagged as merged/implausible (e.g. a 3B Series B). The market is then cut by the
  fund's `thesis` (stage of the qualifying round, country, industry). Every number is computed in code.
- **CRM matching**: by website domain, else normalized company name. The fund's own Cala portfolio counts as
  `invested` even if missing from the CRM. Statuses: see the CSV import section (`seen` counts as `in_review`).
  `in_crm = invested + passed + in_review`; `coverage_pct = 100 · in_crm / market_companies` (one decimal).
- **Blind spots** (`never_seen`): market companies not in the CRM, `never_seen.length == summary.never_seen ==
  headline.never_seen` (list capped at 200). Sorted by round amount (descending), then date, then id.
  `round` is the company's latest qualifying round in the thesis. Investors are **context**, not the headline.
- **Sources are mandatory**: every `round.sources` has at least one entry (a round without a Cala source never
  enters the market). Every entry has the keys `name`, `url`, `rank`, `date`; `rank` or `date` is `null` only
  when Cala has none (e.g. some press sources carry no rank). Sources are ordered strongest first: FILING,
  PRIMARY, PRESS, AGGREGATOR, unranked; newest first within a rank, so `sources[0]` is the one to show as
  "source: PRESS · tech.eu · 2024-06-14".
- `round.date_kind`: `"announcement"` or `"event"` (which Cala field the date came from). `amount`/`currency`
  may be `null`. `investors[].type` is the Cala entity type (Organization, Company, Person, ...).
- `top_investors_in_blind_spots`: investors appearing in the most blind-spot rounds (max 10).
- `market_coverage`: how much of Cala the crawler has explored, for an honest "market as known today" note.
- No LLM is involved in the audit; `top_blind_spots`, `venn` and `heatmap` are removed in v2.
- Company and investor `name`s are display names: the brand from Cala aliases instead of an upper-case legal
  name (e.g. "FIRSTMINUTE CAPITAL LLP" → "Firstminute Capital"), otherwise the legal name in title case
  without its legal suffix.

## GET /api/audit/demo
Returns a precomputed audit (same shape as POST /api/audit, v2 + legacy during the transition) for the demo fund (Earlybird Venture Capital) and `data/demo_pipeline.csv`, a **simulated** CRM (`simulated_crm: true`). Must respond in under 1 second. Mock: `docs/mocks/audit_v2.json`.

## GET /api/deals/{company_id}?fund_id=uuid
```json
{
  "id": "uuid", "name": "Vayu Robotics", "website": "vayu-robotics.se",
  "description": "Autonomous robots for industrial sites.",
  "country": "Sweden", "founded": "2022",
  "rounds": [{
    "id": "uuid", "label": "SEED", "amount": 4200000, "currency": "EUR", "date": "2024-06-14",
    "date_kind": "announcement", "qualifying": true,
    "lead_investors": [{ "id": "uuid", "name": "Creandum" }],
    "participants": [{ "id": "uuid", "name": "Giant Ventures" }],
    "sources": [Source], "conflated": false
  }],
  "why_missed": [{ "reason": "Lead investor Creandum has never co-invested with you" }],
  "recent_news": [{ "title": "Vayu Robotics opens Helsinki office", "date": "2026-10-02", "source": "tech.eu", "url": "https://..." }],
  "sources": [Source]
}
```
`rounds[].date` is **nullable** (e.g. EU grants without a date); `rounds[]` is sorted newest first with undated rounds last. `rounds[].amount` and `rounds[].currency` can also be `null`.
`rounds[].sources` use the v2 `Source` (with `date`). `rounds[].qualifying` marks rounds that count for the market (since 2022-01-01, named investor, sourced, not merged).
`why_missed` is computed by rules (lead never co-invested with the fund, country outside the fund's top countries, stage outside its stages), max 2 items.
`recent_news` comes from Cala `knowledge_search`, cached.
