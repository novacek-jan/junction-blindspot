# Deploying the Blind Spot API on Aiven Runtime

Status: **prepared, not deployed.** The image is defined in `backend/Dockerfile` (python:3.12-slim, non-root, port 8000, healthcheck on `/api/health`).

## What runs on the server

- The server has **no SQLite database** (`*.db` is never committed). The API serves the demo from the committed JSON files in `data/`, so `GET /api/audit/demo`, the demo fund's profile, `GET /api/funds/search` and `GET /api/deals/{id}` all work for every demo deal.
- `POST /api/audit` and live profiles for other funds return `503 data_unavailable` until a database is attached. Moving `backend/db.py` to Aiven for PostgreSQL is the planned next step.
- The container writes nothing at runtime: `/app` is read-only for the `app` user.

## Environment variables

| Variable | Required | Kind | Value |
|---|---|---|---|
| `CALA_API_KEY` | Yes, for live news on deal pages | **secret** | Your Cala key. Without it, deal pages show only the cached/precomputed news. |
| `ANTHROPIC_API_KEY` | No | **secret** | Enables Claude Haiku wording for the blind-spot insights. Without it a template is used. The demo JSON is precomputed either way. |
| `AUDIT_ACCESS_CODE` | Yes, to enable `POST /api/audit` | **secret** | A long random string, e.g. `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`. If unset, audits are disabled (503). |
| `ALLOWED_ORIGINS` | Yes | variable | `https://<your-app>.vercel.app` plus any preview or custom domains, comma-separated. Add `http://localhost:3000` only if you need local frontend dev against this server. `*` is ignored. |
| `TRUSTED_PROXY_HOPS` | Yes | variable | `0` (default) means rate limiting uses the TCP peer address. Set it to `1` if Aiven's ingress sits in front of the app and appends to `X-Forwarded-For` (see the check below). Never set it higher than the number of proxies you actually trust. |
| `ENABLE_DOCS` | No | variable | `0` (default). `1` exposes `/docs` and `/openapi.json`; keep `0` in production. |
| `PORT` | No | variable | Defaults to `8000`, matching `EXPOSE 8000`. Only change it if you also change the port in Aiven. |
| `AUDIT_RATE_LIMIT`, `AUDIT_RATE_WINDOW_S` | No | variable | Default 10 audits per 600 s per client IP. |

## Steps in the Aiven console

These follow Aiven's [deploy apps](https://aiven.io/docs/products/runtime/deploy-apps) and [Containerfile](https://aiven.io/docs/products/runtime/manifest-files/containerfiles) docs (Aiven Runtime, formerly Aiven Apps). Items marked *check* are not covered by those docs. Verify them in the console.

1. **Permissions.** Connecting GitHub needs the organization admin role, and deploying needs project manager, admin or `project:services:write`. To connect a GitHub *organization* you must be its owner. The repo `novacek-jan/junction-blindspot` is under a personal account, which also works.
2. In your Aiven project, open **Runtime** and click **Deploy application**.
3. **Connect GitHub**, then select Account `novacek-jan`, Repository `junction-blindspot`, Branch `main`. Click **Next**.
4. **Select the manifest file `backend/Dockerfile`** and click **Scan**.
   - *Check:* the build context must be the **repository root**, because the Dockerfile copies `backend/` and `data/`. In the Aiven API this is `build_path: "./"` (the default) with `containerfile_path: "./backend/Dockerfile"`.
   - If the console builds from `backend/` instead, the build fails at `COPY data/...`. Then use the API/CLI with those two fields, or ask us to add a root-level Dockerfile.
5. **Edit the application** (the edit control on the scan result):
   - Name: e.g. `blindspot-api`.
   - Port: `8000`, protocol HTTP. It is detected from `EXPOSE 8000`; confirm it.
   - Cloud/region: an EU region, e.g. `aws-eu-west-1` (the region used in Aiven's examples).
   - Plan: the smallest application plan is enough (e.g. `startup-50-1024` from Aiven's examples).
6. **Set the environment variables** from the table above. Use the **secret** kind for `CALA_API_KEY`, `ANTHROPIC_API_KEY` and `AUDIT_ACCESS_CODE` (the API supports `kind: "secret"`; *check* the console label).
   - Do **not** put secrets in the Dockerfile `ENV` lines: Aiven reads `ENV` from the Dockerfile, and those values are public in the repo.
7. Click **Deploy**.
8. **Note the public URL** of the application. *Check:* Aiven's docs don't describe the default URL; it's shown on the application page. Custom domains can be added in step 5.

### After the first deploy

- `curl https://<app-url>/api/health` should return `{"ok":true,"live_data":false}`.
- `curl https://<app-url>/api/audit/demo` should return in well under 1 s. Then open one deal via `/api/deals/<company_id>`.
- **`TRUSTED_PROXY_HOPS` check:** open the application logs and look at the client address in the uvicorn access log lines.
  - If every request shows the same private address (10.x, 172.16–31.x, 192.168.x), there is a proxy in front: set `TRUSTED_PROXY_HOPS=1` and redeploy.
  - If you see real public client IPs, keep `0`.
- **CORS check:**
  - `curl -sI -H "Origin: https://<your-app>.vercel.app" https://<app-url>/api/health | grep -i access-control` must show your origin.
  - The same request with `-H "Origin: https://evil.example"` must show nothing.
- **Healthcheck:** the image defines a Docker `HEALTHCHECK`. *Check* whether Aiven Runtime uses it. Its docs don't mention health checks, so you may need to configure one on `/api/health` in the console.

### Redeploying

Pushes do **not** deploy automatically. Open the application, then **Overview → Actions → Deploy latest commit**. Redeploy after every demo rebuild (`backend/build_demo.py` updates `data/demo_*.json`).

## Frontend (Vercel), for the frontend session

- Set `NEXT_PUBLIC_API_URL=https://<app-url>`. It is a URL, never a key.
- **Do not put `AUDIT_ACCESS_CODE` in a `NEXT_PUBLIC_*` variable.** Anything public ships to every browser and would make the code worthless.
- Either have the user type the code in the UI, or call `POST /api/audit` from a Next.js server route that adds `X-Access-Code` from a server-only Vercel env var.
- The demo (`GET /api/audit/demo`) needs no code.

## Local container test (needs Docker, not available on the dev Mac at the time of writing)

```bash
docker build -f backend/Dockerfile -t blindspot-api .
docker run --rm -p 8000:8000 -e AUDIT_ACCESS_CODE=local -e ALLOWED_ORIGINS=http://localhost:3000 blindspot-api
curl localhost:8000/api/health
```

## Dependency audit

- `backend/requirements.txt` (Python 3.12, full pinned tree): `pip-audit --no-deps -r backend/requirements.txt` reports **no known vulnerabilities** (2026-11-14).
- This was checked against the pinned versions without building the image. Re-run `pip-audit` inside the image once Docker is available, because it also covers pip in the base image.
- `backend/requirements-py39.txt` is only for local development on macOS's Python 3.9. It has known CVEs (starlette, python-multipart, anyio) that are fixed only on Python 3.10 or newer.
