#!/usr/bin/env python3
"""Fetch Cala aliases for entities with upper-case legal names and store their brand display name.

Usage:  backend/.venv/bin/python backend/enrich_names.py
Only entities without a stored display name are fetched (one cached Cala call each). Stops cleanly
on Cala 402. Re-run sync_postgres.py afterwards so the deployed API gets the names.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["BLINDSPOT_BACKEND"] = "sqlite"

import db  # noqa: E402
from cala_client import Cala, PaymentRequired, val  # noqa: E402
from names import brand_name, title_case, strip_legal_suffix  # noqa: E402


def main() -> None:
    cala = Cala()
    todo = db.shouting_entities()
    print(f"{len(todo)} upper-case names without a display name")

    def one(r):
        ent = cala.retrieve(r["entity_id"], ["aliases"])
        aliases = val(ent, "aliases") or []
        display = brand_name(r["name"], aliases if isinstance(aliases, list) else [])
        fallback = title_case(strip_legal_suffix(r["name"]))
        source = "cala_alias" if ent.get("_ok") and display != fallback else "title_case"
        return (r["entity_id"], r["name"], display, source)

    rows, stopped = [], False
    with ThreadPoolExecutor(4) as pool:
        try:
            for row in pool.map(one, todo):
                rows.append(row)
                if len(rows) % 50 == 0:
                    db.upsert_display_names(rows[-50:])
        except PaymentRequired as e:
            stopped = True
            print(f"stopped: {e}")
    db.upsert_display_names(rows)
    by_src = {s: sum(1 for r in rows if r[3] == s) for s in ("cala_alias", "title_case")}
    print(f"stored {len(rows)} display names {by_src}; API calls {cala.api_calls}, errors {len(cala.errors)}"
          + (" (stopped early: out of Cala credit)" if stopped else ""))


if __name__ == "__main__":
    main()
