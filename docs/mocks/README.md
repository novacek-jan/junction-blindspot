# v2 API mocks

Shapes for the v2 product model (`docs/api-contract.md`). Companies, investors, amounts and URLs in these
files are **fictional placeholders** for building the UI; only the fund name/id is real.
- `audit_v2.json`: `POST /api/audit` and `GET /api/audit/demo` (v2 fields only; the live backend also returns
  the deprecated v1 fields during the transition).
- `profile_v2.json`: `GET /api/funds/{fund_id}/profile`.
