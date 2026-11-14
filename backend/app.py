"""Blind Spot API (FastAPI). Contract: docs/api-contract.md.

Run:  cd backend && .venv/bin/uvicorn app:app --port 8000

Two modes:
- with data/cala.db (local, after a crawl): every endpoint is live.
- without it (a server: *.db is never committed): the demo is served from the precomputed
  data/demo_audit.json, data/demo_profile.json and data/demo_deals.json; POST /api/audit returns 503.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from starlette.formparsers import MultiPartParser  # noqa: E402

import audit  # noqa: E402
import db  # noqa: E402
from cala_client import Cala  # noqa: E402
from settings import load_env  # noqa: E402

load_env()
db.ALLOW_CREATE = False          # never create an empty DB on a server
log = logging.getLogger("blindspot")

DATA = db.ROOT / "data"
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 5000
MAX_BODY_BYTES = MAX_CSV_BYTES + 64 * 1024          # multipart overhead + form fields
# Keep uploads in memory: Starlette spools parts above spool_max_size to a temp file on disk.
MultiPartParser.spool_max_size = MAX_BODY_BYTES * 2
RATE_LIMIT = int(os.environ.get("AUDIT_RATE_LIMIT", "10"))        # audits per IP ...
RATE_WINDOW_S = int(os.environ.get("AUDIT_RATE_WINDOW_S", "600"))  # ... per 10 minutes


def allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return [o for o in origins if o != "*" and o.startswith(("http://", "https://"))]


app = FastAPI(title="Blind Spot API", version="1",
              docs_url="/docs" if os.environ.get("ENABLE_DOCS") == "1" else None,
              redoc_url=None, openapi_url="/openapi.json" if os.environ.get("ENABLE_DOCS") == "1" else None)
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "X-Access-Code"], allow_credentials=False)
_cala = Cala()


# ------------------------------------------------------------------ errors: clean JSON, no internals

def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "detail": message})


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


@app.exception_handler(ApiError)
async def _api_error(_: Request, e: ApiError):
    return _error(e.status, e.code, e.message)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, e: StarletteHTTPException):
    return _error(e.status_code, "http_error", str(e.detail) if e.status_code < 500 else "internal error")


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, e: RequestValidationError):
    fields = sorted({".".join(str(p) for p in err.get("loc", [])[1:]) for err in e.errors()})
    return _error(422, "invalid_request", "invalid or missing fields: " + ", ".join(f for f in fields if f))


@app.exception_handler(db.DBUnavailable)
async def _no_db(_: Request, e: db.DBUnavailable):
    return _error(503, "data_unavailable", "live data is not available on this deployment; use the demo")


@app.exception_handler(Exception)
async def _unexpected(_: Request, e: Exception):
    log.error("unhandled %s", type(e).__name__)   # no request data, no traceback in the response
    return _error(500, "internal_error", "internal error")


# ------------------------------------------------------------------ precomputed demo (works without the DB)

class Demo:
    def __init__(self):
        self._lock = threading.Lock()
        self._loaded = False
        self.audit_bytes: Optional[bytes] = None
        self.profile: Optional[dict] = None
        self.deals: dict = {}

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            if (DATA / "demo_audit.json").exists():
                self.audit_bytes = (DATA / "demo_audit.json").read_bytes()
            if (DATA / "demo_profile.json").exists():
                self.profile = json.loads((DATA / "demo_profile.json").read_text())
            if (DATA / "demo_deals.json").exists():
                self.deals = json.loads((DATA / "demo_deals.json").read_text())
            self._loaded = True

    def funds(self) -> list[dict]:
        self.load()
        if not self.audit_bytes:
            return []
        a = json.loads(self.audit_bytes)
        return sorted([a["fund"]] + a["peers"], key=lambda f: f["name"])


demo = Demo()


@app.get("/api/health")
def health():
    return {"ok": True, "live_data": db.available()}


@app.get("/api/funds/search")
def funds_search(q: str = ""):
    if db.available():
        return audit.search_funds(q[:100])
    ql = q.strip().lower()[:100]
    return [f for f in demo.funds() if ql in f["name"].lower()]


@app.get("/api/funds/{fund_id}/profile")
def fund_profile(fund_id: str):
    demo.load()
    if not db.available():
        if demo.profile and demo.profile["fund"]["id"] == fund_id:
            return demo.profile
        raise ApiError(503, "data_unavailable", "only the demo fund is available on this deployment")
    try:
        return audit.profile(fund_id)
    except audit.NotFound:
        raise ApiError(404, "not_found", "fund not found")


@app.get("/api/audit/demo")
def audit_demo():
    """Precomputed by backend/build_demo.py and held in memory: responds in milliseconds."""
    demo.load()
    if not demo.audit_bytes:
        raise ApiError(503, "demo_unavailable", "demo audit has not been built")
    return Response(content=demo.audit_bytes, media_type="application/json")


@app.get("/api/deals/{company_id}")
def deal(company_id: str, fund_id: Optional[str] = None):
    demo.load()
    if not db.available():
        if company_id in demo.deals:
            return demo.deals[company_id]
        raise ApiError(404, "not_found", "deal not found")
    try:
        return audit.deal_detail(company_id, fund_id, _cala)
    except audit.NotFound:
        if company_id in demo.deals:
            return demo.deals[company_id]
        raise ApiError(404, "not_found", "deal not found")


# ------------------------------------------------------------------ POST /api/audit (protected: it spends Cala/Claude)

_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _hits_lock:
        q = _hits[ip]
        while q and q[0] < now - RATE_WINDOW_S:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return True
        q.append(now)
        if len(_hits) > 10_000:   # bound memory
            for k in [k for k, v in _hits.items() if not v or v[-1] < now - RATE_WINDOW_S]:
                del _hits[k]
        return False


def client_ip(request: Request) -> str:
    """Client IP for rate limiting.

    TRUSTED_PROXY_HOPS=0 (default): the TCP peer address; X-Forwarded-For is ignored (it can be forged).
    TRUSTED_PROXY_HOPS=N: N trusted proxies each append to X-Forwarded-For, so the client is the
    N-th entry from the right. Entries further left are client-supplied and never trusted.
    """
    try:
        hops = max(0, int(os.environ.get("TRUSTED_PROXY_HOPS", "0")))
    except ValueError:
        hops = 0
    peer = request.client.host if request.client else "unknown"
    if hops == 0:
        return peer
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if not parts:
        return peer
    return parts[-hops] if len(parts) >= hops else parts[0]


def _check_access(request: Request) -> None:
    expected = os.environ.get("AUDIT_ACCESS_CODE", "")
    if not expected:
        raise ApiError(503, "audit_disabled", "audits are disabled: AUDIT_ACCESS_CODE is not configured")
    given = request.headers.get("x-access-code", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise ApiError(401, "unauthorized", "missing or invalid X-Access-Code")


async def _read_body_capped(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise ApiError(413, "too_large", "CSV must be at most 2 MB")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise ApiError(413, "too_large", "CSV must be at most 2 MB")
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/api/audit")
async def run_audit(request: Request):
    _check_access(request)
    ip = client_ip(request)
    if _rate_limited(ip):
        raise ApiError(429, "rate_limited", f"at most {RATE_LIMIT} audits per {RATE_WINDOW_S // 60} minutes")
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise ApiError(415, "unsupported_media_type", "send multipart/form-data")
    body = await _read_body_capped(request)
    request._body = body                       # parse from memory; nothing is written to disk
    try:
        form = await request.form(max_files=1, max_fields=10, max_part_size=MAX_BODY_BYTES)
    except Exception:
        raise ApiError(400, "bad_multipart", "could not parse the multipart form")
    try:
        upload = form.get("crm_csv")
        fund_id = str(form.get("fund_id") or "").strip()
        peer_ids = [p.strip() for p in str(form.get("peer_ids") or "").split(",") if p.strip()]
        if upload is None or isinstance(upload, str) or not fund_id:
            raise ApiError(422, "invalid_request", "fields fund_id and crm_csv (file) are required")
        ctype = (upload.content_type or "").split(";")[0].strip().lower()
        if ctype != "text/csv":
            raise ApiError(415, "unsupported_media_type", "crm_csv must be text/csv")
        raw = await upload.read()
        if len(raw) > MAX_CSV_BYTES:
            raise ApiError(413, "too_large", "CSV must be at most 2 MB")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        del raw
        rows, _ = audit.parse_crm(text)
        if len(rows) > MAX_CSV_ROWS:
            raise ApiError(413, "too_many_rows", f"CSV must have at most {MAX_CSV_ROWS} rows")
        if not db.available():
            raise db.DBUnavailable()
        try:
            return audit.run_audit(fund_id, peer_ids[:50], text)
        except audit.NotFound:
            raise ApiError(404, "not_found", "fund or peer not found")
    finally:
        await form.close()                      # the CRM data is discarded after the audit
