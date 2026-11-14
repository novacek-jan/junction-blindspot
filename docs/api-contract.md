# Blindspot API contract (v1)

Single source of truth between `/backend` (FastAPI) and `/frontend` (Next.js).
Backend base URL: `http://localhost:8000` locally. Frontend reads it from `NEXT_PUBLIC_API_URL` (a URL, never a key).
All API keys (Cala, Anthropic, database) live ONLY in the backend `.env` / hosting env vars.
Any change to this contract must update this file and `frontend/mocks/` in the same commit.

Common types:
- `Source = { "name": str, "url": str, "rank": "FILING"|"PRIMARY"|"PRESS"|"AGGREGATOR"|null }`
- Amounts are numbers in the original currency plus a `currency` code. Dates are ISO `YYYY-MM-DD`.
- Stages use Cala codes: `PRE_SEED, SEED, SERIES_A, SERIES_B, SERIES_C, ...`

## GET /api/funds/search?q=earlybird
```json
[{ "id": "uuid", "name": "Earlybird Venture Capital" }]
```

## GET /api/funds/{fund_id}/profile
Thesis inferred from the fund's real investments in Cala. No user input.
```json
{
  "fund": { "id": "uuid", "name": "Point Nine" },
  "investments_since_2022": 34,
  "stages":     [{ "label": "SEED", "share": 0.55 }],
  "countries":  [{ "name": "Germany", "count": 12 }],
  "industries": [{ "name": "Software and services", "count": 18 }],
  "suggested_peers": [{ "id": "uuid", "name": "Cherry Ventures", "co_investments": 7, "score": 51.2,
                       "reasons": ["DACH focus: 80% of your deals, 80% of theirs", "Pre-seed rounds: 43% of your deals, 56% of theirs"] }],
  "sources": [Source]
}
```

`suggested_peers` are the default peers, chosen by **thesis similarity** (`backend/peers.py`): up to 10 funds (`PEER_COUNT`) with `score` >= 25, best first. Each fund's thesis is its share of deals since 2023 by geography (country and region), stage and sector; the score is `100 × (0.35·geography + 0.25·stage + 0.25·sector overlap + 0.15·min(1, co_investments/5))`, where overlap is the histogram intersection of the two funds' shares (0–1). Funds with fewer than 5 deals since 2023 fall back to all their dated deals, then to their portfolio companies. `reasons` (1–3 strings) explain the strongest overlaps for the UI. `score` is 0–100 with one decimal.

## POST /api/audit  (multipart/form-data)
Fields: `fund_id` (str), `peer_ids` (comma-separated str; **empty or omitted = the profile's `suggested_peers`**), `crm_csv` (file: any CRM export as `.csv` or `.xlsx`), optional `mapping` (JSON string, see below).
The market contains only deals of the selected peers that fall inside the audited fund's thesis (European HQ, thesis regions and stages, announced since 2023). The response's `peers` lists the selected peers that contributed at least one market company.
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

### Response of POST /api/audit
```json
{
  "audit_id": "str",
  "fund": { "id": "uuid", "name": "Point Nine" },
  "peers": [{ "id": "uuid", "name": "Cherry Ventures" }],
  "simulated_crm": true,
  "summary": { "market_deals": 142, "in_pipeline": 54, "invested": 6, "passed": 32, "in_review": 16, "never_seen": 88, "coverage_pct": 38.0 },
  "venn": { "pipeline_only": 130, "overlap": 54, "market_only": 88 },
  "heatmap": {
    "countries": ["Germany", "Sweden"],
    "stages": ["PRE_SEED", "SEED", "SERIES_A"],
    "cells": [{ "country": "Sweden", "stage": "SEED", "total": 11, "never_seen": 9, "share": 0.82 }]
  },
  "top_blind_spots": [{ "title": "Nordic seed", "detail": "You missed 9 of 11 Nordic seed rounds." }],
  "never_seen_deals": [{
    "company_id": "uuid", "name": "Vayu Robotics", "website": "vayu-robotics.se",
    "country": "Sweden", "stage": "SEED", "amount": 4200000, "currency": "EUR", "date": "2024-06-14",
    "lead_investors": [{ "id": "uuid", "name": "Creandum" }],
    "sources": [Source], "conflated": false
  }],
  "top_missed_leads": [{ "id": "uuid", "name": "Creandum", "deals": 7 }]
}
```
Audit semantics:
- `never_seen_deals` contains only counted deals. Rounds flagged as merged/conflated (implausible size for their label, e.g. a 3B Series B) are excluded entirely, so `never_seen_deals.length == summary.never_seen` (up to 200) and the heatmap counts the same set. `conflated` is therefore always `false` here; conflated rounds remain visible with `conflated: true` in `GET /api/deals/{id}` → `rounds[]`.
- `peers` lists only peer funds that contributed at least one company to the market; requested peers without market companies are omitted.
- `top_blind_spots` has 3 items whenever the data has at least 3 distinct facts (fewer only when almost nothing was missed; empty when nothing was).
- Company and investor `name`s are display names: the brand from Cala aliases instead of an upper-case legal name (e.g. "FIRSTMINUTE CAPITAL LLP" → "Firstminute Capital"), otherwise the legal name in title case without its legal suffix. Fund names are the fund's brand.

## GET /api/audit/demo
Returns a precomputed audit (same shape as POST /api/audit) for the demo fund and `data/demo_pipeline.csv`. Must respond in under 1 second.

## GET /api/deals/{company_id}?fund_id=uuid
```json
{
  "id": "uuid", "name": "Vayu Robotics", "website": "vayu-robotics.se",
  "description": "Autonomous robots for industrial sites.",
  "country": "Sweden", "founded": "2022",
  "rounds": [{
    "label": "SEED", "amount": 4200000, "currency": "EUR", "date": "2024-06-14",
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
`why_missed` is computed by rules (lead never co-invested with the fund, country outside the fund's top countries, stage outside its stages), max 2 items.
`recent_news` comes from Cala `knowledge_search`, cached.
