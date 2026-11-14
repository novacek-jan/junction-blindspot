# Blindspot — frontend

Next.js (App Router, TypeScript, Tailwind v4). Data shapes follow `../docs/api-contract.md`.

```bash
cp .env.example .env.local   # NEXT_PUBLIC_USE_MOCKS=true serves frontend/mocks/*.json
npm install
npm run dev                  # http://localhost:3000
```

Set `NEXT_PUBLIC_USE_MOCKS=false` to call the backend at `NEXT_PUBLIC_API_URL`. No API keys live in the frontend.

- `/` start: fund search → Cala profile → peers → CSV → run audit (or **Try the demo** → `GET /api/audit/demo`)
- `/results`: headline, Venn, country × stage heatmap, top blind spots, never-seen deals table; row click opens the deal panel (`GET /api/deals/{id}`)
- `lib/api.ts` is the only API client; `lib/types.ts` mirrors the contract.

## CRM upload, access code and errors

The upload takes any CRM export as `.csv` or `.xlsx` (max 2 MB). The file is sent with its own content type to `POST /api/audit/preview`, which shows "We read N companies, M matched in Cala." and the detected columns as dropdowns; a changed column re-runs the preview, and the final mapping is sent with `POST /api/audit`.

Both calls send the optional access code as the `X-Access-Code` header. It lives in React state only (never storage or the URL).

| Backend response | Message shown |
|---|---|
| 401 | Invalid access code. |
| 413 | File too large. Max 2 MB and 5,000 rows. |
| 415 | Upload a .csv or .xlsx file. Legacy .xls and macro workbooks are not supported. |
| 422 `no_company_column` | No company or website column found in this file. |
| 422 `invalid_mapping` | Those columns don't match this file. Pick them again. |
| 429 | Too many requests, try again in a minute. |
| 503 | Live audits are temporarily unavailable. Try the demo instead. (+ Run the demo button) |
| other 5xx, network error | Backend unavailable. Try the demo instead. (+ Run the demo button) |
| no response in 15 s | No response after 15 seconds. Try the demo instead. (+ Run the demo button) |

In mock mode, add `?mockError=401` (or `413`, `415`, `422`, `invalid_mapping`, `429`, `503`, `500`, `network`) to the start page URL to simulate these when a file is uploaded.

## Deploy

Vercel project `blindspot` (root directory `frontend`) redeploys on every push to `main`. `NEXT_PUBLIC_USE_MOCKS` is set in the Vercel project settings, not in committed files.
