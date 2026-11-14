"""Blind Spot API (FastAPI). Contract: docs/api-contract.md.

Run:  cd backend && .venv/bin/uvicorn app:app --port 8000
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

import audit  # noqa: E402
import db  # noqa: E402
from cala_client import Cala  # noqa: E402
from settings import load_env  # noqa: E402

load_env()
DEMO_AUDIT = db.ROOT / "data" / "demo_audit.json"

app = FastAPI(title="Blind Spot API", version="1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://([a-z0-9-]+\.)*vercel\.app",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
_cala = Cala()
_demo_cache: Optional[bytes] = None


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/funds/search")
def funds_search(q: str = ""):
    return audit.search_funds(q)


@app.get("/api/funds/{fund_id}/profile")
def fund_profile(fund_id: str):
    try:
        return audit.profile(fund_id)
    except audit.NotFound as e:
        raise HTTPException(404, str(e))


@app.post("/api/audit")
async def run_audit(fund_id: str = Form(...), peer_ids: str = Form(""), crm_csv: UploadFile = File(...)):
    raw = await crm_csv.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    try:
        return audit.run_audit(fund_id, [p.strip() for p in peer_ids.split(",") if p.strip()], text)
    except audit.NotFound as e:
        raise HTTPException(404, str(e))


@app.get("/api/audit/demo")
def audit_demo():
    """Precomputed (backend/build_demo.py) and held in memory: responds in milliseconds."""
    global _demo_cache
    if _demo_cache is None:
        if not DEMO_AUDIT.exists():
            raise HTTPException(503, "demo audit not built yet: run backend/build_demo.py")
        _demo_cache = DEMO_AUDIT.read_bytes()
    return JSONResponse(content=json.loads(_demo_cache))


@app.get("/api/deals/{company_id}")
def deal(company_id: str, fund_id: Optional[str] = None):
    try:
        return audit.deal_detail(company_id, fund_id, _cala)
    except audit.NotFound as e:
        raise HTTPException(404, str(e))
