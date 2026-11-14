#!/usr/bin/env python3
"""Copy the crawled SQLite data (data/cala.db) into PostgreSQL (DATABASE_URL), idempotently.

Usage:  backend/.venv/bin/python backend/sync_postgres.py
Upserts funds, fund entities, portfolios, companies, rounds, participants, the insight cache
and the knowledge_search (news) cache. Prints row counts per table. Never deletes tables.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402


def main() -> None:
    t0 = time.time()
    report = db.sync_sqlite_to_postgres()
    print(f"{'table':<20}{'sqlite':>10}{'upserted':>10}{'postgres':>10}")
    for table, r in report.items():
        print(f"{table:<20}{r['sqlite']:>10}{r['upserted']:>10}{r['postgres']:>10}")
    print(f"done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
