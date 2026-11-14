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
import shutil
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("BLINDSPOT_BACKEND", "sqlite")   # built from the local crawl

import audit  # noqa: E402
import db  # noqa: E402

# Demos: (slug, fund name). The default demo is Lifeline Ventures once its thesis rests on at least
# LIFELINE_MIN_BASIS de-duplicated basis rounds since 2022, otherwise Earlybird. The default is also written
# to the legacy file names (data/demo_audit.json, demo_profile.json, demo_deals.json, demo_pipeline.csv).
DEMOS = [("lifeline", "Lifeline Ventures"), ("earlybird", "Earlybird Venture Capital")]
LIFELINE_MIN_BASIS = 10
DATA = db.ROOT / "data"
INDEX_PATH = DATA / "demos.json"
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


def paths(slug: str) -> dict:
    return {k: DATA / f"demo_{slug}_{k}.{ext}" for k, ext in
            (("audit", "json"), ("profile", "json"), ("deals", "json"), ("pipeline", "csv"))}


def build_csv(fund: dict, csv_path: Path) -> None:
    """SIMULATED CRM: the fund's real known deals (invested) + SHARE_IN_PIPELINE of its v2 market
    (passed / in_review only: we never invent investments) + out-of-market noise rows."""
    rng = random.Random(f"{SEED}:{fund['id']}")
    rows = []
    # 1. The fund's own known deals: its Cala portfolio companies with a dated round since 2022.
    own = db.fund_portfolio(fund["id"])
    comps = db.companies(own)
    latest: dict[str, str] = {}
    for r in db.rounds_for_companies(own):
        if r["date"] and r["date"] >= audit.MARKET_FROM and not audit.is_conflated(r):
            latest[r["company_id"]] = max(latest.get(r["company_id"], ""), r["date"])
    for cid, d in sorted(latest.items()):
        c = comps.get(cid)
        if not c:                  # own round stored before its issuer was screened: no name yet, skip
            continue
        seen = date.fromisoformat(d) - timedelta(days=rng.randint(30, 150))
        rows.append((c["name"], audit.normalize_domain(c["website"]) or "", "invested", seen.isoformat()))
    n_own = len(rows)
    # 2. A plausible share of the market the fund did see: mostly passed, some still in review.
    empty = audit.run_audit(fund["id"], [], "company,website,status,date\n", briefing_mode="none")
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
    csv_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {csv_path}: {n_own} own deals (invested), {len(picked)} of {len(deals)} market companies "
          f"(passed/in_review), {len(NOISE)} noise rows")


def build_demo(slug: str, fund_name: str, regen_csv: bool, news: bool) -> dict:
    fund = next(f for f in db.list_funds() if f["name"] == fund_name)
    p = paths(slug)
    if regen_csv or not p["pipeline"].exists():
        build_csv(fund, p["pipeline"])
    result = audit.run_audit(fund["id"], [], p["pipeline"].read_text(), briefing_attempts=3)   # offline: retry
    assert result["simulated_crm"] is True, "demo CSV must carry the SIMULATED marker"
    missing = [d["name"] for d in result["never_seen"] if not d["round"]["sources"]]
    assert not missing, f"blind spots without a Cala source: {missing}"
    assert all(d["round"]["label"] in result["thesis"]["stages"] for d in result["never_seen"])
    from cala_client import Cala
    cala = Cala()
    if news:   # fetch news (knowledge_search) for the deals a demo will click first
        for d in result["never_seen"][:NEWS_PREFETCH]:
            audit.recent_news(cala, d["name"], d["website"], wait=180)
    # Every demo deal's detail is bundled so /api/deals works on a server without the DB.
    details = {d["company_id"]: audit.deal_detail(d["company_id"], fund["id"], cala, news_cache_only=True)
               for d in result["never_seen"]}
    profile = audit.profile(fund["id"])
    for key, data in (("audit", result), ("profile", profile), ("deals", details)):
        p[key].write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"[{slug}] {fund_name}: {json.dumps(result['summary'])} | {len(details)} deals, "
          f"{sum(1 for v in details.values() if v['recent_news'])} with news")
    return {"slug": slug, "fund": fund, "summary": result["summary"], "basis_rounds": result["thesis"]["basis_rounds"]}


def main() -> None:
    regen, news = "--regen-csv" in sys.argv, "--no-news" not in sys.argv
    built = [build_demo(slug, name, regen, news) for slug, name in DEMOS]
    lifeline_basis = next(b["basis_rounds"] for b in built if b["slug"] == "lifeline")
    main_slug = "lifeline" if lifeline_basis >= LIFELINE_MIN_BASIS else "earlybird"
    for key, legacy in (("audit", "demo_audit.json"), ("profile", "demo_profile.json"),
                        ("deals", "demo_deals.json"), ("pipeline", "demo_pipeline.csv")):
        shutil.copyfile(paths(main_slug)[key], DATA / legacy)
    INDEX_PATH.write_text(json.dumps([{"slug": b["slug"], "fund": b["fund"], "default": b["slug"] == main_slug}
                                      for b in built], indent=1, ensure_ascii=False))
    print(f"wrote {INDEX_PATH} (default demo: {main_slug}; Lifeline basis rounds {lifeline_basis}, "
          f"threshold {LIFELINE_MIN_BASIS})")


if __name__ == "__main__":
    main()
