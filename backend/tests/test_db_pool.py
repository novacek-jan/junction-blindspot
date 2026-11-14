"""Postgres connection pool and availability (db.py), with fake connections: no database needed."""
import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
psycopg = pytest.importorskip("psycopg")
import db  # noqa: E402

URL = "postgres://avnadmin:s3cr3tPassw0rd@pg-blindspot-abc.aivencloud.com:26883/defaultdb?sslmode=require"


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    """fail: raise OperationalError on the next execute (as a dropped connection does) and become broken."""

    def __init__(self, pool, n):
        self.pool, self.n = pool, n
        self.closed = self.broken = False
        self.fail = False

    def execute(self, q, p=()):
        if self.fail:
            self.broken = True
            raise psycopg.OperationalError("consuming input failed: server closed the connection unexpectedly")
        with self.pool.lock:
            self.pool.active += 1
            self.pool.peak = max(self.pool.peak, self.pool.active)
        time.sleep(self.pool.delay)
        with self.pool.lock:
            self.pool.active -= 1
        return FakeCursor([{"n": True}])

    def close(self):
        self.closed = True


class FakePg:
    def __init__(self):
        self.conns, self.fail_open, self.delay = [], 0, 0.0
        self.lock = threading.Lock()
        self.active = self.peak = 0

    def open(self, *a, **k):
        if self.fail_open:
            self.fail_open -= 1
            raise db.DBUnavailable("database is not reachable: OperationalError: connection timeout expired")
        c = FakeConn(self, len(self.conns))
        self.conns.append(c)
        return c

    def open_now(self):
        return sum(1 for c in self.conns if not c.closed)


@pytest.fixture
def pg(monkeypatch):
    fake = FakePg()
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(db, "backend", lambda: "postgres")
    monkeypatch.setattr(db, "_pg_open", fake.open)
    monkeypatch.setattr(db, "_pg", {"idle": [], "open": 0, "in_use": 0, "schema_ready": True, "has_data": None,
                                    "checked": 0.0, "last_ok": None, "error": None})
    monkeypatch.setattr(db, "_pg_sem", threading.BoundedSemaphore(db.PG_POOL_MAX))
    return fake


def test_failed_check_is_retried_not_sticky(pg):
    pg.fail_open = 1
    assert db.available() is False
    st = db.status()
    assert st["available"] is False and st["error_type"] == "DBUnavailable"
    assert db.available() is False and len(pg.conns) == 0          # within 5 s: the failure is remembered
    db._pg["checked"] -= db.PG_FAIL_TTL_S + 1                       # 5 s later: checked again
    assert db.available() is True
    st = db.status()
    assert st["available"] is True and st["last_ok_at"] and st["pool"]["open"] == 1 and st["pool"]["idle"] == 1


def test_dropped_connection_is_replaced_and_query_retried(pg):
    assert db._rows("SELECT 1 AS n") == [{"n": True}]
    pg.conns[0].fail = True                                          # the network dropped the pooled connection
    assert db._rows("SELECT 1 AS n") == [{"n": True}]               # retried once on a fresh connection
    assert pg.conns[0].closed and not pg.conns[1].closed
    assert db.status()["pool"]["open"] == 1 and db.status()["error_type"] == "OperationalError"


def test_both_attempts_fail_raises_db_unavailable(pg):
    db._rows("SELECT 1 AS n")
    pg.conns[0].fail = True
    pg.fail_open = 1                                                  # and the reconnect fails too
    with pytest.raises(db.DBUnavailable):
        db._rows("SELECT 1 AS n")
    assert db.status()["pool"]["open"] == 0
    assert db._rows("SELECT 1 AS n") == [{"n": True}]               # and the next call recovers


def test_idle_connections_are_recycled(pg):
    db._rows("SELECT 1 AS n")
    c, _ = db._pg["idle"][0]
    db._pg["idle"][0] = (c, time.time() - db.PG_MAX_IDLE_S - 1)       # idle longer than a minute
    db._rows("SELECT 1 AS n")
    assert c.closed and len(pg.conns) == 2 and db.status()["pool"]["open"] == 1


def test_pool_is_bounded_and_connections_returned(pg):
    pg.delay = 0.05
    errors = []

    def work():
        try:
            for _ in range(3):
                db._rows("SELECT 1 AS n")
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=work) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert pg.peak <= db.PG_POOL_MAX and len(pg.conns) <= db.PG_POOL_MAX     # never more than 4 connections
    st = db.status()["pool"]
    assert st["open"] == pg.open_now() <= db.PG_POOL_MAX and st["in_use"] == 0


def test_error_message_has_no_credentials_or_addresses(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    e = psycopg.OperationalError(
        'connection to server at "pg-blindspot-abc.aivencloud.com" (16.170.186.71), port 26883 failed: '
        'FATAL: password authentication failed for user "avnadmin" (s3cr3tPassw0rd) '
        f"dsn {URL} via 2a05:d016:1:2::71 at 12:30:45")
    msg = db._safe_error(e)
    for secret in ("s3cr3tPassw0rd", "pg-blindspot-abc", "16.170.186.71", "avnadmin", "2a05:d016", "postgres://"):
        assert secret not in msg
    assert "password authentication failed" in msg and "12:30:45" in msg


def test_status_shape(pg):
    db.available()
    st = db.status()
    assert set(st) == {"backend", "available", "checked_at", "last_ok_at", "error_type", "error", "error_at", "pool"}
    assert set(st["pool"]) == {"max", "open", "idle", "in_use"} and st["pool"]["max"] == db.PG_POOL_MAX


def test_connect_options_keepalive_and_timeouts():
    assert db.PG_KEEPALIVES["keepalives"] == 1 and db.PG_KEEPALIVES["keepalives_idle"] <= 60
    assert "statement_timeout" in db.PG_OPTIONS and "lock_timeout" in db.PG_OPTIONS
    assert db.PG_CONNECT_TIMEOUT_S <= 5 and db.PG_MAX_IDLE_S <= 60


# ---------------------------------------------------------------- regression: the API must stay on Postgres
# Root cause of the 503s on Aiven: the live check imported crawler.py for conflation(), and crawler.py sets
# BLINDSPOT_BACKEND=sqlite at import, which switched the running API to a (missing) SQLite file.

LIVE_MERGE_SCRIPT = r"""
import json, os, sys
sys.path.insert(0, sys.argv[1])
import app, db, live_check
rnd = {"id": "r1", "properties": {"round_label": {"value": "SEED"}, "transaction_value": {"value": 1e6},
       "announcement_date": {"value": "2026-10-01"}}, "_rels": {"incoming:PARTICIPATES_IN_FUNDING_ROUND": []}}
live_check._round_record(rnd, {"properties": {}})
print(json.dumps({"backend": db.backend(), "crawler_imported": "crawler" in sys.modules,
                  "env": os.environ.get("BLINDSPOT_BACKEND")}))
"""


def test_live_check_merge_keeps_api_on_postgres():
    import json
    import subprocess
    backend_dir = str(Path(__file__).resolve().parent.parent)
    env = {k: v for k, v in os.environ.items() if k not in ("BLINDSPOT_BACKEND", "BLINDSPOT_DB")}
    env["DATABASE_URL"] = "postgres://u:p@127.0.0.1:1/x"           # never contacted: nothing queries here
    out = subprocess.run([sys.executable, "-c", LIVE_MERGE_SCRIPT, backend_dir], env=env, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res == {"backend": "postgres", "crawler_imported": False, "env": None}


def test_pinned_backend_ignores_later_env_changes(monkeypatch):
    monkeypatch.setattr(db, "_pinned_backend", None)
    monkeypatch.setenv("BLINDSPOT_BACKEND", "postgres")
    assert db.pin_backend() == "postgres"
    monkeypatch.setenv("BLINDSPOT_BACKEND", "sqlite")              # what importing crawler.py does
    assert db.backend() == "postgres"
