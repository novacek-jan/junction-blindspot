Mock responses for the endpoints the frontend calls, per `docs/api-contract.md` v2 (used when `NEXT_PUBLIC_USE_MOCKS=true`).

| File | Endpoint |
|---|---|
| `funds_search.json` | `GET /api/funds/search?q=` (client filters by `q`) |
| `fund_profile.json` | `GET /api/funds/{fund_id}/profile` (fund swapped for the selected one), copy of `docs/mocks/profile_v2.json` |
| `audit.json` | `POST /api/audit`, copy of `docs/mocks/audit_v2.json` |
| `audit_preview.json` | `POST /api/audit/preview` (mapping override echoed back) |
| `audit_demo.json` | `GET /api/audit/demo`, copy of `docs/mocks/audit_v2.json` |

Company names, news and URLs are fictional. Update these files in the same commit as any contract change.
