#!/usr/bin/env python3
"""Write data/lifeline_check.md: every round counted for Lifeline Ventures' thesis (basis rounds since 2022).

    backend/.venv/bin/python backend/lifeline_report.py
For each round: company, date, label, the Lifeline entity it came through, source URL. Rounds that reach
Lifeline only via "Lifeline Ventures AB" (a Swedish entity Cala links to Finnish rounds) are flagged.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("BLINDSPOT_BACKEND", "sqlite")

import audit  # noqa: E402
import db  # noqa: E402

LIFELINE = "476a73ac-afa2-4713-9f73-188bc7ec0b95"
AB = "4d668c75-c7a0-4f5b-baea-ce0fa6a34e31"


def main() -> None:
    prof = audit._profile(LIFELINE)
    basis = prof["_basis"]
    names = {r["entity_id"]: r["name"] for r in
             db._rows("SELECT entity_id, name FROM fund_entities WHERE fund_id=?", [LIFELINE])}
    parts = db.participants([r["id"] for r in basis])
    comps = db.companies({r["company_id"] for r in basis})
    lines = ["# Lifeline Ventures: rounds counted for the thesis", "",
             f"Basis rounds since 2022 (de-duplicated, European companies): **{len(basis)}**. "
             f"Thesis stages: {', '.join(prof['thesis']['stages'])}. Countries: {', '.join(prof['thesis']['countries'])}.",
             "", "A round is flagged **AB only** when Lifeline appears in it only through the Swedish entity "
             "\"Lifeline Ventures AB\" (Cala links it to Finnish rounds; see backend/funds.py).", "",
             "| Company | Country | Date | Label | Via Lifeline entity | Source | Flag |", "|---|---|---|---|---|---|---|"]
    flagged = 0
    for r in sorted(basis, key=lambda r: (r["date"], comps.get(r["company_id"], {}).get("name") or "")):
        via = sorted({p["entity_id"] for p in parts.get(r["id"], []) if p["entity_id"] in names and p["role"] != "ISSUER"})
        ab_only = via == [AB]
        flagged += ab_only
        src = audit.rank_sources(r["sources"])[0] if r["sources"] else None
        source = f"[{src['name']}]({src['url']}) {src['rank'] or '-'}" if src else ""
        via_text = ", ".join(names[v] for v in via) or "portfolio (no participant list)"
        c = comps.get(r["company_id"], {})
        lines.append(f"| {c.get('name') or r['company_id']} | {c.get('country') or ''} | {r['date']} | {r['label']} | "
                     f"{via_text} | {source} | {'**AB only**' if ab_only else ''} |")
    lines.insert(3, f"Rounds reaching Lifeline only via Lifeline Ventures AB: **{flagged}**.")
    path = db.ROOT / "data" / "lifeline_check.md"
    path.write_text("\n".join(lines) + "\n")
    print(f"wrote {path}: {len(basis)} basis rounds, {flagged} via AB only; thesis {prof['thesis']['stages']}")


if __name__ == "__main__":
    main()
