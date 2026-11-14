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
  "suggested_peers": [{ "id": "uuid", "name": "Cherry Ventures", "co_investments": 7 }],
  "sources": [Source]
}
```

## POST /api/audit  (multipart/form-data)
Fields: `fund_id` (str), `peer_ids` (comma-separated str), `crm_csv` (file; columns `company,website,status,date`; status in `invested|passed|in_review`).
Header `X-Access-Code: <code>` is required (the backend's `AUDIT_ACCESS_CODE`; ask the team, never commit it).
`crm_csv` must be sent as `text/csv`, at most 2 MB and 5,000 rows. Errors are JSON `{ "error": str, "detail": str }`:
401 missing/wrong code, 413 too large / too many rows, 415 not text/csv, 429 rate limit (10 audits per 10 min per IP),
503 audits disabled or no live data on this deployment. `GET /api/audit/demo` stays public.
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
`why_missed` is computed by rules (lead never co-invested with the fund, country outside the fund's top countries, stage outside its stages), max 2 items.
`recent_news` comes from Cala `knowledge_search`, cached.
