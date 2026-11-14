"""All database access for the Blind Spot backend lives in this module.

SQLite (WAL mode, so the API can read while the crawler writes) today; the
functions below are the only place SQL is written, so switching to Aiven
PostgreSQL later means re-implementing this file only.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "cala.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, tool TEXT, response TEXT, fetched_at REAL);
CREATE TABLE IF NOT EXISTS funds (id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fund_entities (fund_id TEXT, entity_id TEXT, name TEXT, PRIMARY KEY (fund_id, entity_id));
CREATE TABLE IF NOT EXISTS fund_portfolio (fund_id TEXT, company_id TEXT, via TEXT, valid_since TEXT,
                                           PRIMARY KEY (fund_id, company_id, via));
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY, name TEXT, website TEXT, description TEXT, country TEXT, founded TEXT,
    funding_stage TEXT, total_funding REAL, total_funding_currency TEXT,
    industries TEXT, sources TEXT, fetched_at REAL);
CREATE TABLE IF NOT EXISTS rounds (
    id TEXT PRIMARY KEY, company_id TEXT, label TEXT, amount REAL, currency TEXT, date TEXT,
    conflated INTEGER, conflation_reason TEXT, sources TEXT);
CREATE INDEX IF NOT EXISTS rounds_company ON rounds(company_id);
CREATE TABLE IF NOT EXISTS round_participants (
    round_id TEXT, entity_id TEXT, name TEXT, entity_type TEXT, role TEXT, is_lead INTEGER,
    PRIMARY KEY (round_id, entity_id));
CREATE INDEX IF NOT EXISTS rp_entity ON round_participants(entity_id);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, updated_at REAL);
"""

_local = threading.local()

# The API sets this to False: on a server without the crawled DB it must not create an
# empty one (the demo is then served from the precomputed JSON in data/).
ALLOW_CREATE = True


class DBUnavailable(Exception):
    pass


def available() -> bool:
    return db_path().exists()


def db_path() -> Path:
    return Path(os.environ.get("BLINDSPOT_DB", DEFAULT_DB))


def conn() -> sqlite3.Connection:
    """One connection per thread, WAL mode, generous busy timeout."""
    c = getattr(_local, "conn", None)
    if c is None:
        path = db_path()
        if not path.exists():
            if not ALLOW_CREATE:
                raise DBUnavailable("crawled data is not available on this deployment")
            path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(path, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=30000")
        c.executescript(SCHEMA)
        _local.conn = c
    return c


def _rows(sql: str, params: Iterable = ()) -> list[dict]:
    return [dict(r) for r in conn().execute(sql, tuple(params)).fetchall()]


def _in(ids: Iterable[str]) -> tuple[str, list[str]]:
    ids = list(ids)
    return ",".join("?" * len(ids)) or "NULL", ids


# ------------------------------------------------------------------ API cache

def cache_get(key: str) -> Optional[dict]:
    row = conn().execute("SELECT response FROM cache WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def cache_put(key: str, tool: str, response) -> None:
    c = conn()
    c.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (key, tool, json.dumps(response), time.time()))
    c.commit()


def cache_count() -> int:
    return conn().execute("SELECT COUNT(*) FROM cache").fetchone()[0]


# ------------------------------------------------------------------ crawler writes

def upsert_fund(fund_id: str, name: str, entities: list[tuple[str, str]]) -> None:
    c = conn()
    c.execute("INSERT OR REPLACE INTO funds VALUES (?,?)", (fund_id, name))
    c.executemany("INSERT OR REPLACE INTO fund_entities VALUES (?,?,?)", [(fund_id, e, n) for e, n in entities])
    c.commit()


def add_portfolio(fund_id: str, links: list[tuple[str, str, Optional[str]]]) -> None:
    c = conn()
    c.executemany("INSERT OR REPLACE INTO fund_portfolio VALUES (?,?,?,?)", [(fund_id, *l) for l in links])
    c.commit()


def upsert_company(row: dict) -> None:
    cols = ["id", "name", "website", "description", "country", "founded", "funding_stage", "total_funding",
            "total_funding_currency", "industries", "sources", "fetched_at"]
    c = conn()
    c.execute(f"INSERT OR REPLACE INTO companies ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
              [row.get(k) for k in cols])
    c.commit()


def upsert_round(row: dict, participants: list[dict]) -> None:
    cols = ["id", "company_id", "label", "amount", "currency", "date", "conflated", "conflation_reason", "sources"]
    c = conn()
    c.execute(f"INSERT OR REPLACE INTO rounds ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
              [row.get(k) for k in cols])
    c.execute("DELETE FROM round_participants WHERE round_id=?", (row["id"],))
    c.executemany("INSERT OR REPLACE INTO round_participants VALUES (?,?,?,?,?,?)",
                  [(row["id"], p["entity_id"], p["name"], p.get("entity_type"), p.get("role"), int(bool(p.get("is_lead"))))
                   for p in participants])
    c.commit()


def kv_put(key: str, value) -> None:
    c = conn()
    c.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?)", (key, json.dumps(value), time.time()))
    c.commit()


def kv_get(key: str):
    row = conn().execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


# ------------------------------------------------------------------ API reads

def list_funds() -> list[dict]:
    return _rows("SELECT id, name FROM funds ORDER BY name")


def get_fund(fund_id: str) -> Optional[dict]:
    r = _rows("SELECT id, name FROM funds WHERE id=?", [fund_id])
    return r[0] if r else None


def fund_entity_ids(fund_id: str) -> list[str]:
    return [r["entity_id"] for r in _rows("SELECT entity_id FROM fund_entities WHERE fund_id=?", [fund_id])]


def entity_to_fund() -> dict[str, str]:
    return {r["entity_id"]: r["fund_id"] for r in _rows("SELECT entity_id, fund_id FROM fund_entities")}


def fund_portfolio(fund_id: str) -> set[str]:
    """Company ids linked to the fund via INVESTED_IN or as a participant in one of the company's rounds."""
    direct = {r["company_id"] for r in _rows("SELECT company_id FROM fund_portfolio WHERE fund_id=?", [fund_id])}
    ph, ids = _in(fund_entity_ids(fund_id))
    via_rounds = {r["company_id"] for r in _rows(
        f"SELECT DISTINCT r.company_id FROM round_participants p JOIN rounds r ON r.id=p.round_id "
        f"WHERE p.entity_id IN ({ph}) AND p.role != 'ISSUER'", ids)}
    return direct | via_rounds


def fund_round_ids(fund_id: str) -> set[str]:
    ph, ids = _in(fund_entity_ids(fund_id))
    return {r["round_id"] for r in _rows(
        f"SELECT round_id FROM round_participants WHERE entity_id IN ({ph}) AND role != 'ISSUER'", ids)}


def companies(ids: Iterable[str]) -> dict[str, dict]:
    ph, ids = _in(ids)
    out = {}
    for r in _rows(f"SELECT * FROM companies WHERE id IN ({ph})", ids):
        r["industries"] = json.loads(r["industries"] or "[]")
        r["sources"] = json.loads(r["sources"] or "[]")
        out[r["id"]] = r
    return out


def rounds_for_companies(ids: Iterable[str]) -> list[dict]:
    ph, ids = _in(ids)
    rows = _rows(f"SELECT * FROM rounds WHERE company_id IN ({ph})", ids)
    for r in rows:
        r["sources"] = json.loads(r["sources"] or "[]")
        r["conflated"] = bool(r["conflated"])
    return rows


def participants(round_ids: Iterable[str]) -> dict[str, list[dict]]:
    ph, ids = _in(round_ids)
    out: dict[str, list[dict]] = {}
    for r in _rows(f"SELECT * FROM round_participants WHERE round_id IN ({ph}) ORDER BY name", ids):
        r["is_lead"] = bool(r["is_lead"])
        out.setdefault(r["round_id"], []).append(r)
    return out


def companies_for_entity(entity_id: str) -> set[str]:
    """Companies whose rounds an (uncrawled) investor entity participated in."""
    return {r["company_id"] for r in _rows(
        "SELECT DISTINCT r.company_id FROM round_participants p JOIN rounds r ON r.id=p.round_id "
        "WHERE p.entity_id=? AND p.role != 'ISSUER'", [entity_id])}
