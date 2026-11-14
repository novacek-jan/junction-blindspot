#!/usr/bin/env python3
"""Hourly market refresh: Postgres sync, demo rebuild (no new Cala calls), report.

    backend/.venv/bin/python backend/refresh.py
Prints one JSON line with the numbers for the hourly report. Committing data/demo_*.json is left to the
caller (the git working copy is shared with the frontend session).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable


def run(args: list[str]) -> str:
    env = dict(os.environ, BLINDSPOT_BACKEND="sqlite")
    out = subprocess.run([PY, *args], cwd=HERE.parent, env=env, capture_output=True, text=True, timeout=1800)
    if out.returncode != 0:
        raise SystemExit(f"{' '.join(args)} failed:\n{out.stderr[-2000:]}")
    return out.stdout


def main() -> None:
    t0 = time.time()
    sync = run([str(HERE / "sync_postgres.py")])
    run([str(HERE / "build_demo.py"), "--no-news"])           # cached news only: no Cala calls
    sys.path.insert(0, str(HERE))
    os.environ["BLINDSPOT_BACKEND"] = "sqlite"
    import db
    import market
    data = HERE.parent / "data"
    # Store the demos in kv as well, so a deployed API with Postgres serves fresh demos without a redeploy.
    index = json.loads((data / "demos.json").read_text())
    db.kv_put("demo:index", index)
    for d in index:
        for kind in ("audit", "profile", "deals"):
            db.kv_put(f"demo:{kind}:{d['fund']['id']}", json.loads((data / f"demo_{d['slug']}_{kind}.json").read_text()))
    import audit
    db.kv_put("search:all", audit._all_investors())           # fund search list, served from kv (fast)
    sync = run([str(HERE / "sync_postgres.py")])            # push the demo and search kv rows too
    demos = {d["slug"]: json.loads((data / f"demo_{d['slug']}_audit.json").read_text())
             for d in json.loads((data / "demos.json").read_text())}
    reg = sorted(market.REGION_COUNTRIES)
    q = db._rows(f"SELECT country, COUNT(*) AS n FROM companies WHERE qualifies=1 AND country IN "
                 f"({','.join('?' * len(reg))}) GROUP BY country", reg)
    report = {
        "at": time.strftime("%Y-%m-%d %H:%M"),
        "region_qualifying": sum(r["n"] for r in q),
        "by_country": {r["country"]: r["n"] for r in q},
        "finland_qualifying": next((r["n"] for r in q if r["country"] == "Finland"), 0),
        "europe_qualifying": db._rows("SELECT COUNT(*) AS n FROM companies WHERE qualifies=1")[0]["n"],
        "demos": {slug: {"never_seen": a["summary"]["never_seen"], "market_companies": a["summary"]["market_companies"],
                         "thesis_stages": a["thesis"]["stages"], "basis_rounds": a["thesis"]["basis_rounds"]}
                  for slug, a in demos.items()},
        "postgres_sync": [l for l in sync.splitlines() if l.startswith(("companies", "rounds"))],
        "seconds": round(time.time() - t0),
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
