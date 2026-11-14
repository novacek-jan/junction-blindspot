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

## Access code and errors

A real audit can send an optional access code as the `X-Access-Code` header on `POST /api/audit`. It lives in React state only (never storage or the URL). The backend must allow that header in CORS.

| Backend response | Message shown |
|---|---|
| 401 | Invalid access code. |
| 413 / 422 | CSV too large or invalid. Max 2 MB and 5,000 rows. |
| 429 | Too many audits, try again in a minute. |
| 5xx, network error, no response in 15 s | Backend unavailable. Try the demo instead. (+ Run the demo button) |

In mock mode, add `?mockError=401` (or `413`, `422`, `429`, `500`, `network`) to the start page URL to simulate these on "Run audit".

## Deploy

Vercel project `blindspot` (root directory `frontend`) redeploys on every push to `main`. `NEXT_PUBLIC_USE_MOCKS` is set in the Vercel project settings, not in committed files.
