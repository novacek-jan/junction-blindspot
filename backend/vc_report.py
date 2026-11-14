#!/usr/bin/env python3
"""Write data/vc_check.md: every non-issuer round participant since 2022 with its VC classification.

    backend/.venv/bin/python backend/vc_report.py
Fix a wrong line by adding the normalized name to vc_lists.ALLOW or vc_lists.BLOCK.
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("BLINDSPOT_BACKEND", "sqlite")

import db  # noqa: E402
import market  # noqa: E402
from vc import VCRule, _norm  # noqa: E402


def main() -> None:
    rule = VCRule(r["entity_id"] for r in db._rows("SELECT entity_id FROM fund_entities"))
    rows = db._rows("SELECT p.entity_id, p.name, p.entity_type, p.role, p.round_id FROM round_participants p "
                    "JOIN rounds r ON r.id = p.round_id WHERE r.date >= ? AND p.role != 'ISSUER'",
                    [market.PERIOD_FROM])
    rounds, info = defaultdict(set), {}
    for r in rows:
        key = (r["entity_id"], r["role"])
        rounds[key].add(r["round_id"])
        info.setdefault(key, r)
    lines = sorted(((len(rs), info[k]) for k, rs in rounds.items()),
                   key=lambda x: (-x[0], (x[1]["name"] or "").casefold()))
    cats = Counter()
    out = ["# VC check", "",
           f"Every non-issuer participant in rounds since {market.PERIOD_FROM} in the database, with the VC rule's "
           "verdict (backend/vc.py). Wrong line? Add its normalized name to `backend/vc_lists.py` (ALLOW or BLOCK).",
           "", "| Rounds | Name | Normalized | Cala type | Role | Category | VC |", "|---|---|---|---|---|---|---|"]
    for n, p in lines:
        cat, is_vc = rule.participant(p)
        cats[(cat, is_vc)] += 1
        out.append(f"| {n} | {p['name']} | {_norm(p['name'])} | {p['entity_type'] or ''} | {p['role']} | {cat} | "
                   f"{'yes' if is_vc else 'no'} |")
    summary = ["", "## Totals", "", "| Category | VC | Participants |", "|---|---|---|"]
    summary += [f"| {c} | {'yes' if v else 'no'} | {k} |" for (c, v), k in sorted(cats.items(), key=lambda x: -x[1])]
    path = db.ROOT / "data" / "vc_check.md"
    path.write_text("\n".join(out[:6] + summary + ["", "## All participants", ""] + out[4:6] + out[6:]) + "\n")
    print(f"wrote {path}: {len(lines)} participants; " +
          ", ".join(f"{c}{'(VC)' if v else ''}={k}" for (c, v), k in sorted(cats.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
