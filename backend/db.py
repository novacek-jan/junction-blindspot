"""All database access for the Blind Spot backend lives in this module.

Two backends behind the same functions:
- SQLite (data/cala.db, WAL mode): the crawler's working store and local development.
- PostgreSQL (Aiven, via DATABASE_URL): what the deployed API reads. Filled from SQLite by
  sync_sqlite_to_postgres() (backend/sync_postgres.py).

Backend choice: BLINDSPOT_BACKEND=sqlite|postgres if set; otherwise postgres when DATABASE_URL is a
postgres:// URL, else sqlite. SQL is written once with "?" placeholders and translated for psycopg.
Every value is passed as a query parameter; only constant table/column names are formatted in.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

from settings import load_env

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
CREATE TABLE IF NOT EXISTS display_names (entity_id TEXT PRIMARY KEY, name TEXT, display TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS company_investors (company_id TEXT, investor_id TEXT, name TEXT, entity_type TEXT, via TEXT,
                                              PRIMARY KEY (company_id, investor_id, via));
CREATE INDEX IF NOT EXISTS ci_investor ON company_investors(investor_id);
CREATE TABLE IF NOT EXISTS crawl_queue (entity_id TEXT PRIMARY KEY, kind TEXT, priority REAL, status TEXT,
                                        discovered_from TEXT, note TEXT, updated_at REAL);
CREATE INDEX IF NOT EXISTS cq_status ON crawl_queue(status, priority);
"""

# Columns added after the first release: (table, column, type). Applied to existing databases on connect.
MIGRATIONS = [
    ("companies", "screened_at", "REAL"),
    ("companies", "prefilter", "TEXT"),          # pass | out_of_europe | too_old | no_hq
    ("companies", "qualifies", "INTEGER"),       # has a qualifying round since 2022 (see snowball.py)
    ("companies", "discovered_via", "TEXT"),     # fund:<id> | investor:<id> | knowledge_search | seed
    ("rounds", "date_kind", "TEXT"),             # announcement | event
]

# table -> (columns, primary key columns)
TABLES = {
    "funds": (["id", "name"], ["id"]),
    "fund_entities": (["fund_id", "entity_id", "name"], ["fund_id", "entity_id"]),
    "fund_portfolio": (["fund_id", "company_id", "via", "valid_since"], ["fund_id", "company_id", "via"]),
    "companies": (["id", "name", "website", "description", "country", "founded", "funding_stage", "total_funding",
                   "total_funding_currency", "industries", "sources", "fetched_at",
                   "screened_at", "prefilter", "qualifies", "discovered_via"], ["id"]),
    "rounds": (["id", "company_id", "label", "amount", "currency", "date", "conflated", "conflation_reason",
                "sources", "date_kind"], ["id"]),
    "company_investors": (["company_id", "investor_id", "name", "entity_type", "via"],
                          ["company_id", "investor_id", "via"]),
    "crawl_queue": (["entity_id", "kind", "priority", "status", "discovered_from", "note", "updated_at"], ["entity_id"]),
    "round_participants": (["round_id", "entity_id", "name", "entity_type", "role", "is_lead"],
                           ["round_id", "entity_id"]),
    "kv": (["key", "value", "updated_at"], ["key"]),
    "display_names": (["entity_id", "name", "display", "source"], ["entity_id"]),
    "cache": (["key", "tool", "response", "fetched_at"], ["key"]),
}

PG_DOUBLE_COLUMNS = [("cache", "fetched_at"), ("companies", "total_funding"), ("companies", "fetched_at"),
                     ("rounds", "amount"), ("kv", "updated_at")]

_local = threading.local()
_pg_lock = threading.RLock()
_pg = {"conn": None, "has_data": None, "checked": 0.0}

# The API sets this to False: on a server without the crawled DB it must not create an
# empty one (the demo is then served from the precomputed JSON in data/).
ALLOW_CREATE = True


class DBUnavailable(Exception):
    pass


def backend() -> str:
    load_env()
    forced = os.environ.get("BLINDSPOT_BACKEND", "").strip().lower()
    if forced in ("sqlite", "postgres"):
        return forced
    url = os.environ.get("DATABASE_URL", "")
    return "postgres" if url.startswith(("postgres://", "postgresql://")) else "sqlite"


def db_path() -> Path:
    return Path(os.environ.get("BLINDSPOT_DB", DEFAULT_DB))


def available() -> bool:
    """True when crawled data can be served (SQLite file exists / Postgres reachable and non-empty)."""
    if backend() == "sqlite":
        return db_path().exists()
    now = time.time()
    if _pg["has_data"] is not None and now - _pg["checked"] < 30:
        return _pg["has_data"]
    try:
        _pg["has_data"] = bool(_rows("SELECT COUNT(*) AS n FROM funds")[0]["n"])
    except Exception:
        _pg["has_data"] = False
    _pg["checked"] = now
    return _pg["has_data"]


def _sqlite_conn(path: Optional[Path] = None) -> sqlite3.Connection:
    path = path or db_path()
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
    for table, col, typ in MIGRATIONS:
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    c.commit()
    return c


def _pg_connect(url: Optional[str] = None):
    import psycopg
    from psycopg.rows import dict_row
    load_env()
    url = url or os.environ.get("DATABASE_URL", "")
    if not url:
        raise DBUnavailable("DATABASE_URL is not set")
    try:
        c = psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=10,
                            application_name="blindspot-api")
    except psycopg.Error:
        raise DBUnavailable("database is not reachable")
    c.execute(SCHEMA.replace(" REAL", " DOUBLE PRECISION"))   # Postgres REAL is only 4-byte float
    for table, col in PG_DOUBLE_COLUMNS:
        c.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE DOUBLE PRECISION")   # migrate old REAL columns
    for table, col, typ in MIGRATIONS:
        c.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ.replace('REAL', 'DOUBLE PRECISION')}")
    return c


def conn():
    """SQLite: one connection per thread. Postgres: one shared autocommit connection (psycopg 3
    connections are thread-safe; calls are serialized), reopened if it was closed."""
    if backend() == "postgres":
        with _pg_lock:
            c = _pg["conn"]
            if c is None or c.closed or c.broken:
                c = _pg["conn"] = _pg_connect()
            return c
    c = getattr(_local, "conn", None)
    if c is None:
        c = _local.conn = _sqlite_conn()
    return c


def _sql(sql: str) -> str:
    return sql.replace("?", "%s") if backend() == "postgres" else sql


def _execute(sql: str, params: Iterable = ()):
    c = conn()
    if backend() == "postgres":
        with _pg_lock:
            return c.execute(_sql(sql), tuple(params)).fetchall() if sql.lstrip().upper().startswith("SELECT") \
                else c.execute(_sql(sql), tuple(params))
    cur = c.execute(sql, tuple(params))
    return cur.fetchall() if sql.lstrip().upper().startswith("SELECT") else cur


def _rows(sql: str, params: Iterable = ()) -> list[dict]:
    return [dict(r) for r in _execute(sql, params)]


def _sources(raw) -> list[dict]:
    """Stored sources as contract-shaped dicts; every key present (date may be None for old rows)."""
    out = []
    for src in (json.loads(raw) if isinstance(raw, str) else (raw or [])):
        out.append({"name": src.get("name") or "", "url": src.get("url") or "", "rank": src.get("rank"),
                    "date": src.get("date")})
    return out


def _in(ids: Iterable[str]) -> tuple[str, list[str]]:
    ids = list(ids)
    return ",".join("?" * len(ids)) or "NULL", ids


def _upsert_sql(table: str, dialect: str) -> str:
    cols, keys = TABLES[table]
    if dialect == "sqlite":
        return f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in keys) or f"{keys[0]}=EXCLUDED.{keys[0]}"
    return (f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) "
            f"ON CONFLICT ({','.join(keys)}) DO UPDATE SET {updates}")


def _upsert(table: str, rows: list[tuple]) -> None:
    if not rows:
        return
    c = conn()
    if backend() == "postgres":
        with _pg_lock, c.cursor() as cur:
            cur.executemany(_upsert_sql(table, "postgres"), rows)
    else:
        c.executemany(_upsert_sql(table, "sqlite"), rows)
        c.commit()


# ------------------------------------------------------------------ API cache

def cache_get(key: str) -> Optional[dict]:
    rows = _rows("SELECT response FROM cache WHERE key=?", [key])
    return json.loads(rows[0]["response"]) if rows else None


def cache_put(key: str, tool: str, response) -> None:
    _upsert("cache", [(key, tool, json.dumps(response), time.time())])


def cache_count() -> int:
    return _rows("SELECT COUNT(*) AS n FROM cache")[0]["n"]


# ------------------------------------------------------------------ crawler writes

def upsert_fund(fund_id: str, name: str, entities: list[tuple[str, str]]) -> None:
    _upsert("funds", [(fund_id, name)])
    _upsert("fund_entities", [(fund_id, e, n) for e, n in entities])


def add_portfolio(fund_id: str, links: list[tuple[str, str, Optional[str]]]) -> None:
    _upsert("fund_portfolio", [(fund_id, *l) for l in links])


def upsert_company(row: dict) -> None:
    _upsert("companies", [tuple(row.get(k) for k in TABLES["companies"][0])])


def upsert_round(row: dict, participants: list[dict]) -> None:
    _upsert("rounds", [tuple(row.get(k) for k in TABLES["rounds"][0])])
    _execute("DELETE FROM round_participants WHERE round_id=?", [row["id"]])
    if backend() == "sqlite":
        conn().commit()
    _upsert("round_participants", [(row["id"], p["entity_id"], p["name"], p.get("entity_type"), p.get("role"),
                                    int(bool(p.get("is_lead")))) for p in participants])


def company_ids() -> set[str]:
    return {r["id"] for r in _rows("SELECT id FROM companies")}


def round_issuers() -> dict[str, str]:
    """round id -> issuing company id, for every stored round."""
    return {r["id"]: r["company_id"] for r in _rows("SELECT id, company_id FROM rounds")}


def display_names() -> dict[str, str]:
    """entity id -> brand display name (from Cala aliases), see backend/enrich_names.py."""
    return {r["entity_id"]: r["display"] for r in _rows("SELECT entity_id, display FROM display_names")}


def upsert_display_names(rows: list[tuple[str, str, str, str]]) -> None:
    _upsert("display_names", rows)


def shouting_entities() -> list[dict]:
    """Companies and investors whose name is all upper case and that have no display name yet."""
    rows = _rows("SELECT id AS entity_id, name FROM companies UNION "
                 "SELECT DISTINCT entity_id, name FROM round_participants WHERE role != 'ISSUER'")
    done = set(display_names())
    seen, out = set(), []
    for r in rows:
        n = r["name"] or ""
        if r["entity_id"] not in done and r["entity_id"] not in seen and any(ch.isalpha() for ch in n) and n == n.upper():
            seen.add(r["entity_id"])
            out.append(r)
    return sorted(out, key=lambda r: r["entity_id"])


# ------------------------------------------------------------------ snowball crawler state

def upsert_company_fields(company_id: str, **fields) -> None:
    """Update selected columns of an existing company (screening results)."""
    cols = [k for k in fields if k in TABLES["companies"][0] and k != "id"]
    if cols:
        _execute(f"UPDATE companies SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?",
                 [fields[k] for k in cols] + [company_id])
        if backend() == "sqlite":
            conn().commit()


def add_company_investors(rows: list[tuple[str, str, str, str, str]]) -> None:
    _upsert("company_investors", rows)


def queue_add(items: list[tuple[str, str, float, str]]) -> int:
    """Enqueue (entity_id, kind, priority, discovered_from) unless already queued; returns how many are new."""
    if not items:
        return 0
    existing = {r["entity_id"] for r in _rows("SELECT entity_id FROM crawl_queue")}
    now, seen, new = time.time(), set(), []
    for entity_id, kind, priority, source in items:
        if entity_id not in existing and entity_id not in seen:
            seen.add(entity_id)
            new.append((entity_id, kind, priority, "pending", source, None, now))
    _upsert("crawl_queue", new)
    return len(new)


def queue_bump(entity_ids: list[str], by: float = 1.0) -> None:
    """Raise the priority of pending items (an investor seen in one more qualifying company)."""
    for eid in entity_ids:
        _execute("UPDATE crawl_queue SET priority = priority + ? WHERE entity_id=? AND status='pending'", [by, eid])
    if backend() == "sqlite":
        conn().commit()


def queue_next(limit: int) -> list[dict]:
    return _rows("SELECT * FROM crawl_queue WHERE status='pending' ORDER BY priority DESC, updated_at ASC, entity_id "
                 "LIMIT ?", [limit])


def queue_set(entity_id: str, status: str, note: Optional[str] = None) -> None:
    _execute("UPDATE crawl_queue SET status=?, note=?, updated_at=? WHERE entity_id=?",
             [status, note, time.time(), entity_id])
    if backend() == "sqlite":
        conn().commit()


def queue_stats() -> dict:
    return {f"{r['kind']}:{r['status']}": r["n"] for r in
            _rows("SELECT kind, status, COUNT(*) AS n FROM crawl_queue GROUP BY kind, status")}


def kv_put(key: str, value) -> None:
    _upsert("kv", [(key, json.dumps(value), time.time())])


def kv_get(key: str):
    rows = _rows("SELECT value FROM kv WHERE key=?", [key])
    return json.loads(rows[0]["value"]) if rows else None


# ------------------------------------------------------------------ API reads

def _by_name(rows: list[dict], key: str = "name") -> list[dict]:
    """Sort in Python: SQLite and Postgres collate text differently; results must not depend on the backend."""
    return sorted(rows, key=lambda r: ((r.get(key) or "").casefold(), r.get(key) or "", str(r.get("id") or r.get("entity_id"))))


def list_funds() -> list[dict]:
    return _by_name(_rows("SELECT id, name FROM funds"))


def list_funds_ids() -> list[str]:
    return [r["id"] for r in _rows("SELECT id FROM funds")]


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


def all_fund_portfolios() -> dict[str, set[str]]:
    """fund id -> portfolio company ids for every fund, in two queries (same rule as fund_portfolio)."""
    out: dict[str, set[str]] = {r["id"]: set() for r in _rows("SELECT id FROM funds")}
    for r in _rows("SELECT fund_id, company_id FROM fund_portfolio"):
        out.setdefault(r["fund_id"], set()).add(r["company_id"])
    for r in _rows("SELECT DISTINCT fe.fund_id, r.company_id FROM fund_entities fe "
                   "JOIN round_participants p ON p.entity_id = fe.entity_id "
                   "JOIN rounds r ON r.id = p.round_id WHERE p.role != 'ISSUER'"):
        out.setdefault(r["fund_id"], set()).add(r["company_id"])
    return out


def fund_round_ids(fund_id: str) -> set[str]:
    ph, ids = _in(fund_entity_ids(fund_id))
    return {r["round_id"] for r in _rows(
        f"SELECT round_id FROM round_participants WHERE entity_id IN ({ph}) AND role != 'ISSUER'", ids)}


def companies(ids: Iterable[str]) -> dict[str, dict]:
    ph, ids = _in(ids)
    out = {}
    for r in _rows(f"SELECT * FROM companies WHERE id IN ({ph})", ids):
        r["industries"] = json.loads(r["industries"] or "[]")
        r["sources"] = _sources(r["sources"])
        out[r["id"]] = r
    return out


def rounds_for_companies(ids: Iterable[str]) -> list[dict]:
    ph, ids = _in(ids)
    rows = _rows(f"SELECT * FROM rounds WHERE company_id IN ({ph})", ids)
    for r in rows:
        r["sources"] = _sources(r["sources"])
        r["conflated"] = bool(r["conflated"])
    return rows


def participants(round_ids: Iterable[str]) -> dict[str, list[dict]]:
    ph, ids = _in(round_ids)
    out: dict[str, list[dict]] = {}
    for r in _by_name(_rows(f"SELECT * FROM round_participants WHERE round_id IN ({ph})", ids)):
        r["is_lead"] = bool(r["is_lead"])
        out.setdefault(r["round_id"], []).append(r)
    return out


def market_rounds(since: str) -> list[dict]:
    """Every round dated on/after `since` (the audit applies market.py's rules to them)."""
    rows = _rows("SELECT * FROM rounds WHERE date >= ?", [since])
    for r in rows:
        r["sources"] = _sources(r["sources"])
        r["conflated"] = bool(r["conflated"])
    return rows


def market_coverage(qualifying: int) -> dict:
    """How much of Cala the crawler has explored (for an honest 'market as known today' note)."""
    eu = _rows("SELECT COUNT(*) AS n FROM companies WHERE prefilter IS NOT NULL AND prefilter != 'out_of_europe' "
               "AND prefilter != 'no_hq'")[0]["n"]
    inv = _rows("SELECT COUNT(*) AS n FROM crawl_queue WHERE kind='investor' AND status='done'")[0]["n"]
    last = _rows("SELECT MAX(fetched_at) AS t FROM companies")[0]["t"]
    as_of = time.strftime("%Y-%m-%d", time.gmtime(last)) if last else None
    import market
    reg = sorted(market.REGION_COUNTRIES)
    ph = ",".join("?" * len(reg))
    reg_q = _rows(f"SELECT COUNT(*) AS n FROM companies WHERE qualifies=1 AND country IN ({ph})", reg)[0]["n"]
    prio_q = _rows("SELECT COUNT(*) AS n FROM companies WHERE qualifies=1 AND country=?",
                   [market.PRIORITY_COUNTRY])[0]["n"]
    return {"european_companies_screened": eu, "qualifying_companies": qualifying, "investors_explored": inv,
            "as_of": as_of, "region": market.MARKET_REGION, "region_countries": reg,
            "region_qualifying_companies": reg_q,
            "priority_country": market.PRIORITY_COUNTRY, "priority_country_qualifying_companies": prio_q}


def investor_name(entity_id: str) -> Optional[str]:
    """Name of an investor entity seen as a round participant or a company investor (None if unknown)."""
    r = _rows("SELECT name FROM round_participants WHERE entity_id=? AND role != 'ISSUER' LIMIT 1", [entity_id])
    if not r:
        r = _rows("SELECT name FROM company_investors WHERE investor_id=? LIMIT 1", [entity_id])
    return r[0]["name"] if r else None


def investor_portfolio(entity_id: str) -> set[str]:
    """Companies of a (non-crawled) investor: rounds it joined plus INVESTED_IN links seen on companies."""
    a = {r["company_id"] for r in _rows(
        "SELECT DISTINCT r.company_id FROM round_participants p JOIN rounds r ON r.id=p.round_id "
        "WHERE p.entity_id=? AND p.role != 'ISSUER'", [entity_id])}
    b = {r["company_id"] for r in _rows("SELECT company_id FROM company_investors WHERE investor_id=?", [entity_id])}
    return a | b


def all_company_names() -> list[dict]:
    """id, name and website of every crawled company (CRM preview matching)."""
    return _rows("SELECT id, name, website FROM companies")


def companies_for_entity(entity_id: str) -> set[str]:
    """Companies whose rounds an (uncrawled) investor entity participated in."""
    return {r["company_id"] for r in _rows(
        "SELECT DISTINCT r.company_id FROM round_participants p JOIN rounds r ON r.id=p.round_id "
        "WHERE p.entity_id=? AND p.role != 'ISSUER'", [entity_id])}


# ------------------------------------------------------------------ SQLite -> Postgres sync

SYNC_TABLES = ["funds", "fund_entities", "fund_portfolio", "companies", "rounds", "round_participants", "kv",
               "display_names", "company_investors", "cache"]


def sync_sqlite_to_postgres(sqlite_path: Optional[Path] = None, pg_url: Optional[str] = None,
                            batch: int = 1000) -> dict[str, dict]:
    """Upsert every row of the crawled SQLite DB into Postgres (idempotent).

    Only the knowledge_search part of the API cache is copied (news on deal pages); raw
    entity_retrieval responses stay local. A round's participants are replaced as a whole,
    inside one transaction per table. Returns {table: {"sqlite": n, "upserted": n, "postgres": n}}.
    """
    src = _sqlite_conn(sqlite_path)
    dst = _pg_connect(pg_url)
    report: dict[str, dict] = {}
    try:
        for table in SYNC_TABLES:
            cols, _ = TABLES[table]
            where = " WHERE tool='knowledge_search'" if table == "cache" else ""
            rows = [tuple(r) for r in src.execute(f"SELECT {','.join(cols)} FROM {table}{where}").fetchall()]
            with dst.transaction(), dst.cursor() as cur:
                if table == "round_participants":
                    round_ids = sorted({r[0] for r in rows})
                    for i in range(0, len(round_ids), batch):
                        cur.execute("DELETE FROM round_participants WHERE round_id = ANY(%s)",
                                    (round_ids[i:i + batch],))
                sql = _upsert_sql(table, "postgres")
                for i in range(0, len(rows), batch):
                    cur.executemany(sql, rows[i:i + batch])
            n_pg = dst.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            report[table] = {"sqlite": len(rows), "upserted": len(rows), "postgres": n_pg}
    finally:
        src.close()
        dst.close()
    _pg["has_data"] = None
    return report
