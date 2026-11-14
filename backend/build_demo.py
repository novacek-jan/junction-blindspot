#!/usr/bin/env python3
"""Build the demo: a SIMULATED CRM export for the demo fund and its precomputed audit.

  data/demo_pipeline.csv  - simulated CRM: ~40% of the fund's in-thesis peer deals
                            (a few invested, most passed / in_review) + ~15 out-of-market noise rows
  data/demo_audit.json    - GET /api/audit/demo response (v2 + legacy v1 fields during the transition)
  data/demo_profile.json  - GET /api/funds/{demo fund}/profile
  data/demo_deals.json    - GET /api/deals/{id} for every demo deal (served when the DB is absent)

Deterministic: a fixed random seed, so the same data gives the same CSV.
Usage:  backend/.venv/bin/python backend/build_demo.py [--regen-csv]
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("BLINDSPOT_BACKEND", "sqlite")   # built from the local crawl

import audit  # noqa: E402
import db  # noqa: E402

DEMO_FUND = "Earlybird Venture Capital"  # best round coverage since 2022 among the early-stage funds
CSV_PATH = db.ROOT / "data" / "demo_pipeline.csv"
JSON_PATH = db.ROOT / "data" / "demo_audit.json"
PROFILE_PATH = db.ROOT / "data" / "demo_profile.json"
DEALS_PATH = db.ROOT / "data" / "demo_deals.json"
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
    # v2: peers no longer define the market (it is every qualifying European company in the thesis).
    return fund, []


def build_csv(fund: dict, peers: list[str]) -> None:
    """SIMULATED CRM: the fund's real known deals (invested) + SHARE_IN_PIPELINE of its v2 market
    (passed / in_review only: we never invent investments) + out-of-market noise rows."""
    rng = random.Random(SEED)
    rows = []
    # 1. The fund's own known deals: its Cala portfolio companies with a dated round since 2022.
    own = db.fund_portfolio(fund["id"])
    comps = db.companies(own)
    latest: dict[str, str] = {}
    for r in db.rounds_for_companies(own):
        if r["date"] and r["date"] >= audit.MARKET_FROM and not audit.is_conflated(r):
            latest[r["company_id"]] = max(latest.get(r["company_id"], ""), r["date"])
    for cid, d in sorted(latest.items()):
        c = comps[cid]
        seen = date.fromisoformat(d) - timedelta(days=rng.randint(30, 150))
        rows.append((c["name"], audit.normalize_domain(c["website"]) or "", "invested", seen.isoformat()))
    n_own = len(rows)
    # 2. A plausible share of the market the fund did see: mostly passed, some still in review.
    empty = audit.run_audit(fund["id"], peers, "company,website,status,date\n")
    deals = sorted((d for d in empty["never_seen"] if d["company_id"] not in own), key=lambda d: d["company_id"])
    rng.shuffle(deals)
    picked = deals[: round(len(deals) * SHARE_IN_PIPELINE)]
    for d in picked:
        status = "passed" if rng.random() < 0.65 else "in_review"
        seen = date.fromisoformat(d["round"]["date"]) - timedelta(days=rng.randint(14, 120))
        website = d["website"] if rng.random() < 0.7 else ""   # some CRM rows lack a website: name matching
        rows.append((d["name"], website or "", status, seen.isoformat()))
    # 3. Out-of-market noise (fictional inbound companies).
    for name, site in NOISE:
        seen = date(2022, 1, 1) + timedelta(days=rng.randint(0, 1400))
        rows.append((name, site, rng.choice(["passed", "passed", "in_review"]), seen.isoformat()))
    rows.sort(key=lambda r: (r[3], r[0]))
    lines = ["# SIMULATED CRM export for the Blind Spot demo. Not real pipeline data of " + fund["name"] + ".",
             "# invested = real portfolio companies from Cala; passed/in_review rows and noise rows are simulated.",
             "company,website,status,date"]
    lines += [",".join('"' + v.replace('"', '""') + '"' if "," in v else v for v in r) for r in rows]
    CSV_PATH.write_text("\n".join(lines) + "\n")
    print(f"wrote {CSV_PATH}: {n_own} own deals (invested), {len(picked)} of {len(deals)} market companies "
          f"(passed/in_review), {len(NOISE)} noise rows")


def main() -> None:
    fund, peers = demo_fund_and_peers()
    if "--regen-csv" in sys.argv or not CSV_PATH.exists():
        build_csv(fund, peers)
    result = audit.run_audit(fund["id"], peers, CSV_PATH.read_text())
    assert result["simulated_crm"] is True, "demo CSV must carry the SIMULATED marker"
    missing = [d["name"] for d in result["never_seen"] if not d["round"]["sources"]]
    assert not missing, f"blind spots without a Cala source: {missing}"
    assert all(d["round"]["label"] in result["thesis"]["stages"] for d in result["never_seen"])
    JSON_PATH.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"wrote {JSON_PATH}: {json.dumps(result['summary'])}")

    from cala_client import Cala
    cala = Cala()
    deals = [{"company_id": d["company_id"], "name": d["name"], "website": d["website"], "conflated": False}
             for d in result["never_seen"]]
    if "--no-news" not in sys.argv:   # fetch news (knowledge_search) for the deals a demo will click first
        for d in [d for d in deals if not d["conflated"]][:NEWS_PREFETCH]:
            audit.recent_news(cala, d["name"], d["website"], wait=180)
    # Every demo deal's detail is bundled so /api/deals works on a server without the DB.
    details = {d["company_id"]: audit.deal_detail(d["company_id"], fund["id"], cala, news_cache_only=True)
               for d in deals}
    PROFILE_PATH.write_text(json.dumps(audit.profile(fund["id"]), indent=1, ensure_ascii=False))
    DEALS_PATH.write_text(json.dumps(details, indent=1, ensure_ascii=False))
    print(f"wrote {PROFILE_PATH} and {DEALS_PATH} ({len(details)} deals, "
          f"{sum(1 for v in details.values() if v['recent_news'])} with news)")

if __name__ == "__main__":
    main()
