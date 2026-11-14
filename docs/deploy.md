# Deploying the Blind Spot API on Aiven Runtime

Status: **prepared, not deployed.** The image is defined in the root `Dockerfile` (python:3.12-slim, non-root, port 8000, healthcheck on `/api/health`). It sits at the repo root because Aiven Runtime always uses the Dockerfile's folder as the build context, and the image needs both `backend/` and `data/`. The root `.dockerignore` sends only the code and the demo JSON to the build, and explicitly excludes `.env`, `*.db`, `logs/`, `frontend/`, `node_modules` and `.git`.

## What runs on the server

- **With `DATABASE_URL`** pointing at Aiven for PostgreSQL, the API reads the crawled data from Postgres and every endpoint is live, including `POST /api/audit`. The crawler still runs locally into SQLite. `backend/sync_postgres.py` then upserts those rows into Postgres (idempotent; run it after every crawl).
- **Without `DATABASE_URL`**, or with an empty or unreachable Postgres, the API serves the demo from the committed JSON in `data/`. `GET /api/audit/demo`, the demo fund's profile, `GET /api/funds/search` and `GET /api/deals/{id}` work for every demo deal. `POST /api/audit` returns `503 data_unavailable`.
- At runtime the API writes only two caches to Postgres: the insight wording and Cala news results. The container file system is read-only for the `app` user.
- Results are identical on SQLite and Postgres: verified by computing the same audit, deal detail and profile on both backends.

## Environment variables

| Variable | Required | Kind | Value |
|---|---|---|---|
| `DATABASE_URL` | Yes, for live data | **secret** | The Aiven for PostgreSQL service URI (`postgres://avnadmin:…@…aivencloud.com:PORT/defaultdb?sslmode=require`). Aiven Runtime can also inject it through a service integration (see step 6). Keep `sslmode=require`. |
| `CALA_API_KEY` | Yes, for the live check and live news | **secret** | Your Cala key. Without it every audit's `live_check` is `"offline"` (stored data) and deal pages show only cached/precomputed news. |
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
4. **Select the manifest file `Dockerfile`** (the one at the repo root) and click **Scan**. The build context is then the repo root, which is what the image needs.
5. **Edit the application** (the edit control on the scan result):
   - Name: e.g. `blindspot-api`.
   - Port: `8000`, protocol HTTP. It is detected from `EXPOSE 8000`; confirm it.
   - Cloud/region: an EU region, e.g. `aws-eu-west-1` (the region used in Aiven's examples).
   - Plan: the smallest application plan is enough (e.g. `startup-50-1024` from Aiven's examples).
6. **Connect the database.** In **Configure** for service integrations, attach your existing Aiven for PostgreSQL service and expose its connection string as `DATABASE_URL`. Aiven's API calls this an `application_service_credential` integration; *check* the console label. If the console can't do that, add `DATABASE_URL` by hand as a secret (step 7), using the service URI from the PostgreSQL service's Overview page.
7. **Set the environment variables** from the table above. Use the **secret** kind for `DATABASE_URL`, `CALA_API_KEY`, `ANTHROPIC_API_KEY` and `AUDIT_ACCESS_CODE` (the API supports `kind: "secret"`; *check* the console label).
   - Do **not** put secrets in the Dockerfile `ENV` lines: Aiven reads `ENV` from the Dockerfile, and those values are public in the repo.
8. Click **Deploy**.
9. **Note the public URL** of the application. *Check:* Aiven's docs don't describe the default URL; it's shown on the application page. Custom domains can be added in step 5.

### Before the first deploy: load the data into Postgres

Run locally, after a crawl. `DATABASE_URL` in your local `.env` must be the same service:

```bash
backend/.venv/bin/python backend/sync_postgres.py      # prints row counts per table
```

The Aiven PostgreSQL service must allow connections from your machine (*check* **IP filter** / allowed IP addresses on the service if the sync can't connect).

### After the first deploy

- `curl https://<app-url>/api/health` should return `{"ok":true,"live_data":true}` with Postgres attached (`false` means the API is serving only the precomputed demo).
- `curl https://<app-url>/api/audit/demo` should return in under ~3 s on the first load (live Cala check) and well under 1 s after that. Then open one deal via `/api/deals/<company_id>`.
- **Cala check:** `curl https://<app-url>/api/health?cala=1`. Expected: `key_set: true`, `dns_resolves`,
  `tcp_connect`, `tls` and `reachable` all `true`, `http_status: 200`, `failed_step: null`. If not, `failed_step`
  names the step that fails (`dns`, `tcp`, `tls`, `http`) and `error_type` how (`timeout` = packets silently
  dropped). Aiven Runtime documents only blocked outbound ports 23, 25, 119, 135, 137-139, 179, 445, 465 and 631
  ([ports](https://aiven.io/docs/products/runtime/ports)); 443 is not among them and no egress setting is
  documented. While Cala is unreachable the live check is paused for 60 s at a time and audits use stored data.
- **`TRUSTED_PROXY_HOPS` check:** open the application logs and look at the client address in the uvicorn access log lines.
  - If every request shows the same private address (10.x, 172.16–31.x, 192.168.x), there is a proxy in front: set `TRUSTED_PROXY_HOPS=1` and redeploy.
  - If you see real public client IPs, keep `0`.
- **CORS check:**
  - `curl -sI -H "Origin: https://<your-app>.vercel.app" https://<app-url>/api/health | grep -i access-control` must show your origin.
  - The same request with `-H "Origin: https://evil.example"` must show nothing.
- **Healthcheck:** the image defines a Docker `HEALTHCHECK`. *Check* whether Aiven Runtime uses it. Its docs don't mention health checks, so you may need to configure one on `/api/health` in the console.

### Fresh data without redeploying

With `DATABASE_URL` attached, the API reads everything from Postgres, **including the demos and the fund search
list**: `backend/refresh.py` (run hourly on the crawl machine) rebuilds the demos, stores them in the `kv` table
and syncs to Postgres. The deployed API picks them up within 5 minutes, so no redeploy is needed for new data.
The demo JSON files baked into the image are only the fallback when no database is attached.

### Redeploying

Pushes do **not** deploy automatically. Open the application, then **Overview → Actions → Deploy latest commit**. Redeploy after every demo rebuild (`backend/build_demo.py` updates `data/demo_*.json`).

## Frontend (Vercel), for the frontend session

- Set `NEXT_PUBLIC_API_URL=https://<app-url>`. It is a URL, never a key.
- **Do not put `AUDIT_ACCESS_CODE` in a `NEXT_PUBLIC_*` variable.** Anything public ships to every browser and would make the code worthless.
- Either have the user type the code in the UI, or call `POST /api/audit` from a Next.js server route that adds `X-Access-Code` from a server-only Vercel env var.
- The demo (`GET /api/audit/demo`) needs no code.

## Local container test (needs Docker, not available on the dev Mac at the time of writing)

```bash
docker build -t blindspot-api .
docker run --rm -p 8000:8000 -e AUDIT_ACCESS_CODE=local -e ALLOWED_ORIGINS=http://localhost:3000 blindspot-api
curl localhost:8000/api/health
```

## Dependency audit

- `backend/requirements.txt` (Python 3.12, full pinned tree): `pip-audit --no-deps -r backend/requirements.txt` reports **no known vulnerabilities** (2026-11-14).
- This was checked against the pinned versions without building the image. Re-run `pip-audit` inside the image once Docker is available, because it also covers pip in the base image.
- `backend/requirements-py39.txt` is only for local development on macOS's Python 3.9. It has known CVEs (starlette, python-multipart, anyio) that are fixed only on Python 3.10 or newer.
