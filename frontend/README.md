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
