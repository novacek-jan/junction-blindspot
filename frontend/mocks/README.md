Mock responses for every endpoint in `docs/api-contract.md` (used when `NEXT_PUBLIC_USE_MOCKS=true`).

| File | Endpoint |
|---|---|
| `funds_search.json` | `GET /api/funds/search?q=` (client filters by `q`) |
| `fund_profile.json` | `GET /api/funds/{fund_id}/profile` (fund swapped for the selected one) |
| `audit.json` | `POST /api/audit` |
| `audit_preview.json` | `POST /api/audit/preview` (mapping override echoed back) |
| `audit_demo.json` | `GET /api/audit/demo` |
| `deal_details.json` | `GET /api/deals/{company_id}` — map of `company_id` → response |

Company names, news and URLs are fictional. Update these files in the same commit as any contract change.
