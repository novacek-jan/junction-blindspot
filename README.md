# Blind Spot Audit

Junction 2026 project.

VC funds only see the deals that reach them. **Blind Spot Audit** compares a fund's CRM pipeline with the deals its peer funds actually closed, using funding-round and investor data from [Cala](https://cala.ai), and shows the companies, sectors and stages the fund never saw.

## How it works

1. Pick a fund and its peers (e.g. Earlybird plus other German or EU VCs).
2. Pull the peers' portfolio companies and funding rounds from the Cala investor graph: round label, amount, date, lead investors and co-investors, each with sources.
3. Filter that market by country, sector and stage.
4. Match it against the fund's CRM export. Every deal the peers did that never appeared in the pipeline is a blind spot.

`cala_results/` holds raw Cala API responses from our feasibility tests, and `cala_funding_fields_hack_guide.md` documents the Cala data model.

## Run locally

```bash
git clone https://github.com/novacek-jan/junction-blindspot.git
cd junction-blindspot
cp .env.example .env   # then fill in CALA_API_KEY, ANTHROPIC_API_KEY, DATABASE_URL
```

Application code is in progress; run instructions will be added here as the app takes shape. Never commit `.env`.
