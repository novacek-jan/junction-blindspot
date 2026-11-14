# Blindspot — frontend

Next.js (App Router, TypeScript, Tailwind v4). Data shapes follow `../docs/api-contract.md`.

```bash
cp .env.example .env.local   # NEXT_PUBLIC_USE_MOCKS=true serves frontend/mocks/*.json
npm install
npm run dev                  # http://localhost:3000
```

Set `NEXT_PUBLIC_USE_MOCKS=false` to call the backend at `NEXT_PUBLIC_API_URL`. No API keys live in the frontend.

- Design: `design/claude/` (Main = `/`, Results = `/results`, DealPanel = side panel). Space Grotesk for headings and numbers, Inter for text. Blue = never seen, green = in your CRM.
- `/` start: fund search with the thesis summary from the profile, CRM upload (preview + column mapping), access code, Run audit. No sample audit is linked anywhere in the UI.
- `/results` ("Audits"): the audit run in this tab (sessionStorage key `blindspot:audit:v3`, only audits from a real upload), otherwise a "No audits yet" empty state. Hero eyebrow "{Fund} · audit of {date}", thesis chips (sectors in API order, first 3 + "+N"), dot field, "Why they slipped through" from `audit.briefing` (any insight kind; "of {total}" under the number; coverage shows its worst- and best-covered sectors (`worst_industry`, `best_industry` with `%` seen) as chips; hidden when null), the never-seen table newest first, side panel from `GET /api/deals/{id}?fund_id=`, market sentence from `market_coverage`.
- Live check: under the thesis chips, a status line from `audit.live_check` (ok: "Rounds re-checked live with Cala", partial: "Partly re-checked with Cala", offline: "Using stored Cala data", plus "· N new rounds found" when `updated > 0`); rows whose round the live check updated get a "New" chip. Hidden when `live_check` is missing.
- Loading: `components/ResultsSkeleton` (hero, dot card, briefing cards, table) on /results while an audit or demo loads, and on / in place of the form while a real audit runs (form state kept; errors bring the form back).
- Side panel: "Latest news from Cala" under the rounds timeline, up to 5 items from `recent_news` (skeleton while loading, hidden when empty).
- Activity (cacheComponents): Next hides pages instead of unmounting them, so `/` and `/results` remount their content under a new key whenever they are hidden. Every visit to `/` (logo, "New audit" pill or hero button, browser back) starts with an empty form; only the access code is kept for the tab. `/results` re-reads the tab's latest audit on every visit.
- `/` is always the New audit page (never redirects, even with an audit stored in the tab); there are no redirects or rewrites in `next.config.ts` and no `vercel.json`.
- Backup URL (unlinked): `/results?demo=lifeline` or `?demo=earlybird` fetches that precomputed demo fresh from `GET /api/audit/demo` (never stored).
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
| 503 | Live audits are temporarily unavailable. |
| other 5xx, network error | Backend unavailable. |
| no response in 15 s | No response after 15 seconds. |

In mock mode, add `?mockError=401` (or `413`, `415`, `422`, `invalid_mapping`, `429`, `503`, `500`, `network`) to the start page URL to simulate these when a file is uploaded.

## Deploy

Vercel project `blindspot` (root directory `frontend`) redeploys on every push to `main`. `NEXT_PUBLIC_USE_MOCKS` is set in the Vercel project settings, not in committed files.
