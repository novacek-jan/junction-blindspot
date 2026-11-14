"""Blind Spot API (FastAPI). Contract: docs/api-contract.md.

Run:  cd backend && .venv/bin/uvicorn app:app --port 8000

Two modes:
- with data/cala.db (local, after a crawl): every endpoint is live.
- without it (a server: *.db is never committed): the demo is served from the precomputed
  data/demo_audit.json, data/demo_profile.json and data/demo_deals.json; POST /api/audit returns 503.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
import threading
import time
from collections import Counter, defaultdict, deque
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
import crm_import  # noqa: E402
import db  # noqa: E402
from cala_client import Cala  # noqa: E402
from matching import CompanyIndex  # noqa: E402
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


@app.exception_handler(crm_import.ImportError_)
async def _import_error(_: Request, e: crm_import.ImportError_):
    return _error(e.status, e.code, e.message)


@app.exception_handler(db.DBUnavailable)
async def _no_db(_: Request, e: db.DBUnavailable):
    return _error(503, "data_unavailable", "live data is not available on this deployment; use the demo")


@app.exception_handler(Exception)
async def _unexpected(_: Request, e: Exception):
    log.error("unhandled %s", type(e).__name__)   # no request data, no traceback in the response
    return _error(500, "internal_error", "internal error")


# ------------------------------------------------------------------ precomputed demo (works without the DB)

class Demo:
    """Precomputed demos (backend/build_demo.py): data/demos.json lists them; per demo
    data/demo_<slug>_{audit,profile,deals}.json. The first/default one is the main demo."""

    def __init__(self):
        self._lock = threading.Lock()
        self._loaded = False
        self.index: list = []
        self.audits: dict = {}      # fund id -> raw JSON bytes
        self.profiles: dict = {}    # fund id -> profile
        self.deals: dict = {}       # fund id -> {company id -> deal detail}
        self.default_id: Optional[str] = None
        self._loaded_at = 0.0

    REFRESH_S = 300

    def load(self) -> None:
        with self._lock:
            if self._loaded and time.time() - self._loaded_at < self.REFRESH_S:
                return
            if self._load_from_db():
                return
            if self._loaded:
                return
            index_path = DATA / "demos.json"
            if index_path.exists():
                self.index = json.loads(index_path.read_text())
            elif (DATA / "demo_audit.json").exists():     # older single-demo layout
                a = json.loads((DATA / "demo_audit.json").read_text())
                self.index = [{"slug": "main", "fund": a["fund"], "default": True}]
            for d in self.index:
                fid, slug = d["fund"]["id"], d["slug"]
                files = {k: DATA / f"demo_{slug}_{k}.json" for k in ("audit", "profile", "deals")}
                if slug == "main":
                    files = {k: DATA / f"demo_{k}.json" for k in ("audit", "profile", "deals")}
                if files["audit"].exists():
                    self.audits[fid] = files["audit"].read_bytes()
                if files["profile"].exists():
                    self.profiles[fid] = json.loads(files["profile"].read_text())
                if files["deals"].exists():
                    self.deals[fid] = json.loads(files["deals"].read_text())
            self._finish()

    def _finish(self) -> None:
        default = next((d for d in self.index if d.get("default")), self.index[0] if self.index else None)
        self.default_id = default["fund"]["id"] if default else None
        self._loaded, self._loaded_at = True, time.time()

    def _load_from_db(self) -> bool:
        """Demos stored in kv by backend/refresh.py (hourly) are fresher than the files baked into the image."""
        try:
            if not db.available():
                return False
            index = db.kv_get("demo:index")
            if not index:
                return False
            audits, profiles, deals = {}, {}, {}
            for d in index:
                fid = d["fund"]["id"]
                a = db.kv_get(f"demo:audit:{fid}")
                if a is None:
                    return False
                audits[fid] = json.dumps(a, ensure_ascii=False).encode()
                profiles[fid] = db.kv_get(f"demo:profile:{fid}") or {}
                deals[fid] = db.kv_get(f"demo:deals:{fid}") or {}
        except Exception:
            return False
        self.index, self.audits, self.profiles, self.deals = index, audits, profiles, deals
        self._finish()
        return True

    def funds(self) -> list[dict]:
        self.load()
        return [{"id": d["fund"]["id"], "name": d["fund"]["name"]} for d in self.index]

    def deal(self, company_id: str, fund_id: Optional[str]):
        self.load()
        if fund_id and company_id in self.deals.get(fund_id, {}):
            return self.deals[fund_id][company_id]
        for deals in self.deals.values():
            if company_id in deals:
                return deals[company_id]
        return None


demo = Demo()


@app.get("/api/health")
def health():
    return {"ok": True, "live_data": db.available()}


@app.get("/api/funds/search")
def funds_search(q: str = ""):
    if db.available():
        return audit.search_funds(q[:100])
    ql = q.strip().lower()[:100]
    return [f for f in demo.funds() if ql in f["name"].lower()]   # no basis_rounds without live data


@app.get("/api/funds/{fund_id}/profile")
def fund_profile(fund_id: str):
    demo.load()
    if not db.available():
        if fund_id in demo.profiles:
            return demo.profiles[fund_id]
        raise ApiError(503, "data_unavailable", "only the demo funds are available on this deployment")
    try:
        return audit.profile(fund_id)
    except audit.NotFound:
        raise ApiError(404, "not_found", "fund not found")


@app.get("/api/audit/demos")
def audit_demos():
    """Available precomputed demos; `default` marks the main one."""
    demo.load()
    return [{"fund": d["fund"], "default": d["fund"]["id"] == demo.default_id} for d in demo.index]


@app.get("/api/audit/demo")
def audit_demo(fund_id: Optional[str] = None):
    """Precomputed by backend/build_demo.py and held in memory: responds in milliseconds.
    Without fund_id: the main demo (Lifeline Ventures)."""
    demo.load()
    fid = fund_id or demo.default_id
    if not fid or fid not in demo.audits:
        if fund_id:
            raise ApiError(404, "not_found", "no demo for this fund")
        raise ApiError(503, "demo_unavailable", "demo audit has not been built")
    return Response(content=demo.audits[fid], media_type="application/json")


@app.get("/api/deals/{company_id}")
def deal(company_id: str, fund_id: Optional[str] = None):
    demo.load()
    if not db.available():
        hit = demo.deal(company_id, fund_id)
        if hit is not None:
            return hit
        raise ApiError(404, "not_found", "deal not found")
    try:
        return audit.deal_detail(company_id, fund_id, _cala)
    except audit.NotFound:
        hit = demo.deal(company_id, fund_id)
        if hit is not None:
            return hit
        raise ApiError(404, "not_found", "deal not found")


# ------------------------------------------------------------------ POST /api/audit and /api/audit/preview (protected)

_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()
PREVIEW_RATE_LIMIT = int(os.environ.get("PREVIEW_RATE_LIMIT", "30"))   # previews are cheap (no Cala/Claude)


def _rate_limited(ip: str, bucket: str = "audit", limit: Optional[int] = None) -> bool:
    limit = RATE_LIMIT if limit is None else limit
    now = time.time()
    key = f"{bucket}:{ip}"
    with _hits_lock:
        q = _hits[key]
        while q and q[0] < now - RATE_WINDOW_S:
            q.popleft()
        if len(q) >= limit:
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


ALLOWED_UPLOAD_TYPES = {
    "", "text/csv", "application/csv", "text/plain", "text/tab-separated-values", "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream",
}


async def _receive_crm(request: Request, bucket: str, limit: int):
    """Shared upload handling: access code, per-IP limit, 2 MB cap, in-memory multipart, CSV/XLSX
    detection by extension and content. Returns (form, fields, table)."""
    _check_access(request)
    if _rate_limited(client_ip(request), bucket, limit):
        raise ApiError(429, "rate_limited", f"at most {limit} requests per {RATE_WINDOW_S // 60} minutes")
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise ApiError(415, "unsupported_media_type", "send multipart/form-data")
    request._body = await _read_body_capped(request)   # parse from memory; nothing is written to disk
    try:
        form = await request.form(max_files=1, max_fields=10, max_part_size=MAX_BODY_BYTES)
    except Exception:
        raise ApiError(400, "bad_multipart", "could not parse the multipart form")
    try:
        upload = form.get("crm_csv")
        if upload is None or isinstance(upload, str):
            raise ApiError(422, "invalid_request", "field crm_csv (file: .csv or .xlsx) is required")
        ctype = (upload.content_type or "").split(";")[0].strip().lower()
        if ctype not in ALLOWED_UPLOAD_TYPES:
            raise ApiError(415, "unsupported_media_type", "upload a .csv or .xlsx file")
        raw = await upload.read()
        if len(raw) > MAX_CSV_BYTES:
            raise ApiError(413, "too_large", "file must be at most 2 MB")
        mapping = None
        if form.get("mapping"):
            try:
                mapping = json.loads(str(form.get("mapping")))
                assert isinstance(mapping, dict) and all(isinstance(v, (str, type(None))) for v in mapping.values())
            except (ValueError, AssertionError):
                raise ApiError(422, "invalid_mapping", "mapping must be a JSON object of field -> column header")
        table = crm_import.load_table(upload.filename or "", raw)
        mapping = crm_import.resolve_mapping(table, mapping)
        rows = crm_import.normalize_rows(table, mapping)
        fields = {"fund_id": str(form.get("fund_id") or "").strip(),
                  "peer_ids": [p.strip() for p in str(form.get("peer_ids") or "").split(",") if p.strip()],
                  "fingerprint": hashlib.sha1(raw).hexdigest()}
        del raw
        return form, fields, table, mapping, rows
    except BaseException:
        await form.close()
        raise


@app.post("/api/audit/preview")
async def audit_preview(request: Request):
    """Detected column mapping, row count, Cala match count and 5 sample rows. Spends nothing."""
    form, fields, table, mapping, rows = await _receive_crm(request, "preview", PREVIEW_RATE_LIMIT)
    try:
        matched_flags = None
        warnings = []
        if db.available():
            index = CompanyIndex(db.all_company_names())
            matched_flags = [bool(index.match(r["company"], r["website"])) for r in rows]
        else:
            warnings.append("live data is not available on this deployment: matches were not counted")
        if not mapping["status"]:
            warnings.append("no status column found: every row counts as seen (in review)")
        if not mapping["website"]:
            warnings.append("no website column found: companies are matched by name only")
        skipped = len(table["rows"]) - len(rows)
        if skipped:
            warnings.append(f"{skipped} rows without company name or website were skipped")
        counts = Counter(r["status"] for r in rows)
        return {
            "file_type": table["kind"],
            "columns": table["headers"],
            "mapping": mapping,
            "row_count": len(rows),
            "skipped_rows": skipped,
            "matched_rows": sum(matched_flags) if matched_flags is not None else None,
            "status_counts": {k: counts.get(k, 0) for k in ("invested", "passed", "in_review", "seen")},
            "sample_rows": [{"company": r["company"], "website": r["website"], "status": r["status"],
                             "raw_status": r["raw_status"], "date": r["date"],
                             "matched": matched_flags[i] if matched_flags is not None else None}
                            for i, r in enumerate(rows[:5])],
            "warnings": warnings,
        }
    finally:
        await form.close()                      # the CRM data is discarded after the preview


@app.post("/api/audit")
async def run_audit(request: Request):
    form, fields, table, mapping, rows = await _receive_crm(request, "audit", RATE_LIMIT)
    try:
        if not fields["fund_id"]:
            raise ApiError(422, "invalid_request", "field fund_id is required")
        if not db.available():
            raise db.DBUnavailable()
        try:
            return audit.run_audit_rows(fields["fund_id"], fields["peer_ids"][:50], rows, table["simulated"],
                                        fields["fingerprint"])
        except audit.NotFound:
            raise ApiError(404, "not_found", "fund or peer not found")
    finally:
        await form.close()                      # the CRM data is discarded after the audit
