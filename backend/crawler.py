#!/usr/bin/env python3
"""Crawl peer VC funds' portfolios and funding rounds from Cala into SQLite.

  fund entities -> INVESTED_IN companies + PARTICIPATES_IN_FUNDING_ROUND rounds (-> ISSUER)
  company       -> name, website, description, HQ country, stage, total funding, rounds
                   (+ enrichment call: founding_date, OPERATES_IN_INDUSTRY)
  round         -> round_label, transaction_value (+currency), announcement_date,
                   participants with role and is_lead, sources

All rounds are stored; the API applies the date window (2023+). Every Cala response
is cached (db.cache_*), so re-runs only fetch what is missing. Writes go to the
normalized tables as soon as each entity is processed, so the API (WAL mode) can
read while this runs.

Usage:  backend/.venv/bin/python backend/crawler.py   (CALA_API_KEY from .env)
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402
from cala_client import Cala, sources_of, val  # noqa: E402
from funds import FUNDS  # noqa: E402

WORKERS = 4
MIN_DATE = "2023-01-01"   # summary window; all rounds are stored
CONFLATION_THRESHOLDS = {"PRE_SEED": 5e6, "SEED": 10e6, "SERIES_A": 75e6, "SERIES_B": 250e6,
                         "SERIES_C": 600e6, "SERIES_D": 1.5e9, "SERIES_E": 2e9, "SERIES_F": 3e9}  # = audit.MAX_PLAUSIBLE_ROUND
FUND_ENTITY_TYPES = ["Organization", "Company"]

# Argument lists are kept identical to the v1 crawler so its cached responses are reused.
COMPANY_FIELDS = ["name", "website", "funding_stage", "total_funding", "total_funding_units"]
COMPANY_RELS = ["HAS_HEADQUARTERS_IN", "PARTICIPATES_IN_FUNDING_ROUND"]
ROUND_FIELDS = ["round_label", "transaction_value", "transaction_value_units", "announcement_date", "event_date"]
# Rounds fetched by earlier runs used this list; it is the fallback if Cala rejects event_date.
# Note: adding event_date changes the cache key, so the next run refetches every round once.
ROUND_FIELDS_V1 = ["round_label", "transaction_value", "transaction_value_units", "announcement_date"]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def conflation(label, amount, company_total, same_currency) -> str:
    reasons = []
    thr = CONFLATION_THRESHOLDS.get(label or "")
    if thr and isinstance(amount, (int, float)) and amount > thr:
        reasons.append(f"{label} above {thr / 1e6:.0f}M")  # noqa
    if isinstance(amount, (int, float)) and isinstance(company_total, (int, float)) and same_currency \
            and amount > company_total * 1.05:
        reasons.append("round larger than company total_funding")
    return "; ".join(reasons)


class Crawler:
    def __init__(self):
        self.cala = Cala()
        if not self.cala.has_key:
            sys.exit("CALA_API_KEY missing: put it in .env (see .env.example)")
        self.pool = ThreadPoolExecutor(WORKERS)
        self.done_companies: set[str] = set()
        self.done_rounds: dict[str, dict] = {}
        self.failed_companies: list[str] = []

    # -- rounds

    def round(self, rid: str) -> dict:
        if rid in self.done_rounds:
            return self.done_rounds[rid]
        r = self.cala.retrieve(rid, ROUND_FIELDS, inc=["PARTICIPATES_IN_FUNDING_ROUND"])
        if not r.get("_ok"):
            r = self.cala.retrieve(rid, ROUND_FIELDS_V1, inc=["PARTICIPATES_IN_FUNDING_ROUND"])
        self.done_rounds[rid] = r
        return r

    def store_round(self, rnd: dict, company_id: str, company: dict) -> None:
        if not rnd.get("_ok"):
            return
        label, amount = val(rnd, "round_label"), val(rnd, "transaction_value")
        cur = val(rnd, "transaction_value_units")
        parts = []
        for p in rnd["_rels"].get("incoming:PARTICIPATES_IN_FUNDING_ROUND", []):
            props = p.get("properties") or {}
            parts.append({"entity_id": p["id"], "name": p.get("name"), "entity_type": p.get("entity_type"),
                          "role": props.get("role"), "is_lead": props.get("is_lead")})
        reason = conflation(label, amount, val(company, "total_funding"),
                            cur is not None and cur == val(company, "total_funding_units"))
        db.upsert_round({
            "id": rnd["id"], "company_id": company_id, "label": label, "amount": amount, "currency": cur,
            "date": val(rnd, "announcement_date") or val(rnd, "event_date"), "conflated": int(bool(reason)), "conflation_reason": reason,
            "sources": json.dumps(sources_of(rnd, ["transaction_value", "round_label", "announcement_date"])),
        }, parts)

    # -- companies

    def company(self, cid: str) -> None:
        """Process one company; any failure is logged with the company id and the crawl continues."""
        if cid in self.done_companies:
            return
        self.done_companies.add(cid)
        try:
            self._company(cid)
        except Exception as e:  # noqa: BLE001 - one bad company must not stop the crawl
            self.failed_companies.append(cid)
            log(f"[error] company {cid}: {type(e).__name__}: {e}")

    def _company(self, cid: str) -> None:
        c = self.cala.retrieve(cid, COMPANY_FIELDS, out=COMPANY_RELS)
        if not c.get("_ok"):
            return
        enr = self.cala.retrieve(cid, ["founding_date"], out=["OPERATES_IN_INDUSTRY"])
        hqs = c["_rels"].get("outgoing:HAS_HEADQUARTERS_IN", [])
        country = next((h["name"] for h in hqs if h.get("entity_type") == "Country"), hqs[0]["name"] if hqs else None)
        founded = val(enr, "founding_date")
        industries = sorted({i["name"] for i in enr["_rels"].get("outgoing:OPERATES_IN_INDUSTRY", []) if i.get("name")})
        db.upsert_company({
            "id": cid, "name": val(c, "name") or c.get("name"), "website": val(c, "website"),
            "description": c.get("description"), "country": country,
            "founded": str(founded)[:4] if founded else None,
            "funding_stage": val(c, "funding_stage"), "total_funding": val(c, "total_funding"),
            "total_funding_currency": val(c, "total_funding_units"),
            "industries": json.dumps(industries),
            "sources": json.dumps(sources_of(c, ["name", "website", "funding_stage", "total_funding"])),
            "fetched_at": time.time(),
        })
        for it in c["_rels"].get("outgoing:PARTICIPATES_IN_FUNDING_ROUND", []):
            if (it.get("properties") or {}).get("role") in ("ISSUER", None):
                self.store_round(self.round(it["id"]), cid, c)

    # -- funds

    def fund(self, name: str, spec: dict) -> list[str]:
        allowed = spec["entities"]
        hits = {e["id"]: e["name"] for e in self.cala.search(name, FUND_ENTITY_TYPES)}
        entities = [(eid, hits.get(eid, label)) for eid, label in allowed.items()]
        db.upsert_fund(spec["id"], name, entities)
        rels = list(self.pool.map(lambda e: self.cala.retrieve(e[0], ["name"], out=["INVESTED_IN", "PARTICIPATES_IN_FUNDING_ROUND"]), entities))
        links, round_ids = [], set()
        for ent in rels:
            for it in ent["_rels"].get("outgoing:INVESTED_IN", []):
                links.append((it["id"], "INVESTED_IN", (it.get("properties") or {}).get("valid_since")))
            for it in ent["_rels"].get("outgoing:PARTICIPATES_IN_FUNDING_ROUND", []):
                round_ids.add(it["id"])
        for rnd in self.pool.map(self.round, sorted(round_ids)):
            for p in rnd["_rels"].get("incoming:PARTICIPATES_IN_FUNDING_ROUND", []):
                if (p.get("properties") or {}).get("role") == "ISSUER":
                    links.append((p["id"], "ROUND", None))
        db.add_portfolio(spec["id"], sorted(set(links), key=lambda l: (l[0], l[1], l[2] or "")))
        cids = sorted({l[0] for l in links})
        log(f"[fund] {name}: {len(entities)} entities, {len(cids)} portfolio companies, {len(round_ids)} fund rounds")
        return cids

    def run(self) -> None:
        t0 = time.time()
        # The demo fund (CLI arg, default Point Nine) goes first so its data lands early.
        for name, spec in FUNDS.items():   # register every fund + entity up front (lead -> fund mapping)
            db.upsert_fund(spec["id"], name, list(spec["entities"].items()))
        first = sys.argv[1] if len(sys.argv) > 1 else "Point Nine"
        order = sorted(FUNDS.items(), key=lambda kv: kv[0] != first)
        for name, spec in order:
            cids = self.fund(name, spec)
            list(self.pool.map(self.company, cids))
            log(f"[fund] {name}: companies stored ({len(self.done_companies)} total, "
                f"{self.cala.api_calls} API calls, {self.cala.rate_limited} rate-limited, {len(self.cala.errors)} errors)")
        self.summary(time.time() - t0)

    def summary(self, elapsed: float) -> None:
        c = db.conn()
        n_comp = c.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        rounds = [dict(r) for r in c.execute("SELECT r.label, r.date, r.conflated, co.country FROM rounds r "
                                             "JOIN companies co ON co.id=r.company_id WHERE r.date >= ?", (MIN_DATE,))]
        md = ["# Crawl summary", "", f"Funds: {len(FUNDS)}. Rounds window: announced on or after {MIN_DATE}.", "",
              "| Metric | Value |", "|---|---|",
              f"| Companies | {n_comp} |", f"| Rounds since {MIN_DATE[:4]} | {len(rounds)} |",
              f"| ...flagged conflated | {sum(r['conflated'] for r in rounds)} |",
              f"| API calls this run | {self.cala.api_calls} (rate-limited and retried: {self.cala.rate_limited}) |",
              f"| Cache hits this run | {self.cala.cache_hits} |", f"| API errors | {len(self.cala.errors)} |",
              f"| Companies that failed processing | {len(self.failed_companies)} |",
              f"| Run time | {elapsed:.0f} s |", "", "## Rounds by HQ country", "", "| Country | Rounds |", "|---|---|"]
        md += [f"| {k} | {v} |" for k, v in Counter(r["country"] or "Unknown" for r in rounds).most_common()]
        md += ["", "## Rounds by label", "", "| Label | Rounds |", "|---|---|"]
        md += [f"| {k} | {v} |" for k, v in Counter(r["label"] or "UNLABELLED" for r in rounds).most_common()]
        if self.cala.errors:
            md += ["", "## Errors (first 20)", ""] + [f"- {e}" for e in self.cala.errors[:20]]
        out = db.ROOT / "data" / "crawl_summary.md"
        out.write_text("\n".join(md) + "\n")
        log("\n".join(md))


if __name__ == "__main__":
    Crawler().run()
