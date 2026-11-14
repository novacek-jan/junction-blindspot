#!/usr/bin/env python3
"""Build the demo: a SIMULATED CRM export for the demo fund and its precomputed audit.

  data/demo_pipeline.csv  - simulated CRM: ~40% of the fund's in-thesis peer deals
                            (a few invested, most passed / in_review) + ~15 out-of-market noise rows
  data/demo_audit.json    - GET /api/audit/demo response (demo fund vs all other crawled funds)

Deterministic: a fixed random seed, so the same data gives the same CSV.
Usage:  backend/.venv/bin/python backend/build_demo.py [--regen-csv]
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit  # noqa: E402
import db  # noqa: E402

DEMO_FUND = "Earlybird Venture Capital"  # most 2023+ round coverage among the early-stage funds
CSV_PATH = db.ROOT / "data" / "demo_pipeline.csv"
JSON_PATH = db.ROOT / "data" / "demo_audit.json"
SEED = 2026
SHARE_IN_PIPELINE = 0.40
NEWS_PREFETCH = 20

# Out-of-market noise: plausible inbound deals that are not in the peer market (fictional names).
NOISE = [
    ("Lumora Analytics", "lumora-analytics.io"), ("Fernwerk Robotics", "fernwerk.de"), ("Tidewell Health", "tidewell.health"),
    ("Kvarn Logistics", "kvarn.se"), ("Patchbay Audio", "patchbay.fm"), ("Orchard Ledger", "orchardledger.com"),
    ("Brisa Mobility", "brisa-mobility.es"), ("Quillnest", "quillnest.ai"), ("Halvard Security", "halvard.no"),
    ("Mosaic Grid", "mosaicgrid.energy"), ("Pinecrest Labs", "pinecrestlabs.co.uk"), ("Velora Pay", "velorapay.eu"),
    ("Strata Forms", "strataforms.app"), ("Nimbus Kitchen", "nimbuskitchen.fr"), ("Arclight Bio", "arclightbio.ch"),
]


def demo_fund_and_peers() -> tuple[dict, list[str]]:
    funds = db.list_funds()
    fund = next(f for f in funds if f["name"] == DEMO_FUND)
    return fund, [f["id"] for f in funds if f["id"] != fund["id"]]


def build_csv(fund: dict, peers: list[str]) -> None:
    rng = random.Random(SEED)
    # Market with an empty CRM = every in-thesis peer deal the fund could have seen.
    empty = audit.run_audit(fund["id"], peers, "company,website,status,date\n")
    deals = [d for d in empty["never_seen_deals"] if not d["conflated"]]
    rng.shuffle(deals)
    picked = deals[: round(len(deals) * SHARE_IN_PIPELINE)]
    rows = []
    for i, d in enumerate(picked):
        status = "invested" if i < max(1, len(picked) // 12) else ("passed" if rng.random() < 0.65 else "in_review")
        seen = date.fromisoformat(d["date"]) - timedelta(days=rng.randint(14, 120))
        website = d["website"] if rng.random() < 0.7 else ""   # some CRM rows lack a website: name matching
        rows.append((d["name"], website or "", status, seen.isoformat()))
    for name, site in NOISE:
        seen = date(2023, 1, 1) + timedelta(days=rng.randint(0, 1000))
        rows.append((name, site, rng.choice(["passed", "passed", "in_review"]), seen.isoformat()))
    rows.sort(key=lambda r: r[3])
    lines = ["# SIMULATED CRM export for the Blind Spot demo. Not real pipeline data of " + fund["name"] + ".",
             "company,website,status,date"]
    lines += [",".join('"' + v.replace('"', '""') + '"' if "," in v else v for v in r) for r in rows]
    CSV_PATH.write_text("\n".join(lines) + "\n")
    print(f"wrote {CSV_PATH} ({len(picked)} market deals of {len(deals)}, {len(NOISE)} noise rows)")


def main() -> None:
    fund, peers = demo_fund_and_peers()
    if "--regen-csv" in sys.argv or not CSV_PATH.exists():
        build_csv(fund, peers)
    result = audit.run_audit(fund["id"], peers, CSV_PATH.read_text())
    JSON_PATH.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"wrote {JSON_PATH}: {json.dumps(result['summary'])}")
    if "--no-news" not in sys.argv:   # warm the knowledge_search cache for the deals a demo will click
        from cala_client import Cala
        cala = Cala()
        top = [d for d in result["never_seen_deals"] if not d["conflated"]][:NEWS_PREFETCH]
        for d in top:
            audit.recent_news(cala, d["name"], d["website"], wait=180)
        print(f"news cached for top {len(top)} never-seen deals")


if __name__ == "__main__":
    main()
