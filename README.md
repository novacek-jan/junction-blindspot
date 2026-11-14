# Blind Spot Audit

Junction 2026 project.

VC funds only see the deals that reach them. **Blind Spot Audit** compares a fund's CRM pipeline with the deals its peer funds actually closed, using funding-round and investor data from [Cala](https://cala.ai), and shows the companies, sectors and stages the fund never saw.

## How it works

1. Pick a fund and its peers (20 European VCs are crawled, e.g. Earlybird, Point Nine, Creandum, Northzone).
2. The fund's **thesis** is inferred from its real investments in Cala since 2022: the span of stages it invests in and the regions it invests in.
3. The **market** is every peer portfolio company with an in-thesis funding round since 2023, taken from the Cala investor graph (round label, amount, date, lead investors and co-investors, each with sources).
4. The fund's CRM export is matched against that market by website domain, falling back to normalized company name. Every market deal that never appeared in the pipeline is a blind spot.

Rounds whose amount is implausible for their label (e.g. a SEED above 10M) are flagged as *conflated*. They're excluded from all counts but still returned with `conflated: true`.

The API contract shared with the frontend is in `docs/api-contract.md`. `cala_results/` holds raw Cala API responses from the feasibility tests, and `cala_funding_fields_hack_guide.md` documents the Cala data model.

## Run the backend locally

Requires Python 3.9+.

```bash
git clone https://github.com/novacek-jan/junction-blindspot.git
cd junction-blindspot
cp .env.example .env            # fill in CALA_API_KEY; ANTHROPIC_API_KEY is optional
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# 1. Crawl Cala into data/cala.db. Every response is cached, so re-runs only fetch what's missing.
#    A full crawl of 20 funds is a few thousand calls and takes over an hour because of Cala's rate limit.
mkdir -p logs
nohup backend/.venv/bin/python -u backend/crawler.py > logs/crawl.log 2>&1 &

# 2. Build the demo: a SIMULATED CRM export (data/demo_pipeline.csv) and the precomputed audit
#    (data/demo_audit.json). Re-run after the crawl finishes; add --regen-csv to regenerate the CSV.
backend/.venv/bin/python backend/build_demo.py

# 3. Start the API on http://localhost:8000
cd backend && .venv/bin/uvicorn app:app --port 8000
```

The API can serve requests while the crawler is writing, because SQLite runs in WAL mode.

| Endpoint | What it returns |
|---|---|
| `GET /api/funds/search?q=` | Crawled funds matching the query |
| `GET /api/funds/{fund_id}/profile` | Inferred thesis: stages, countries, industries, suggested peers |
| `POST /api/audit` | Multipart: `fund_id`, `peer_ids` (comma-separated), `crm_csv` (`company,website,status,date`) |
| `GET /api/audit/demo` | Precomputed audit for the demo fund (Earlybird) vs. all other crawled funds |
| `GET /api/deals/{company_id}?fund_id=` | Company, rounds with leads and participants, why it was missed, recent news |

Tests: `cd backend && .venv/bin/python -m pytest -q tests`

### Backend layout

| File | Role |
|---|---|
| `backend/db.py` | All database access. SQLite now; swap this file to move to Aiven PostgreSQL |
| `backend/cala_client.py` | Throttled, cached Cala MCP client |
| `backend/crawler.py`, `backend/funds.py` | The crawler, and the hand-checked Cala entity ids for each fund |
| `backend/audit.py`, `backend/matching.py` | Deterministic profile, market, matching, classification and why-missed rules |
| `backend/insights.py` | Claude Haiku rewords up to 3 code-computed facts. It falls back to a template if the key is missing, the call fails, or the reworded text changes a number |
| `backend/app.py` | FastAPI app. CORS allows `http://localhost:3000` and `*.vercel.app` |

Keys are read only from `.env`. Never commit it; `.env`, `*.db` and `logs/` are gitignored.
