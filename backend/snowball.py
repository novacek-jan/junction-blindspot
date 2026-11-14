#!/usr/bin/env python3
"""Snowball crawler: grow the market of European companies with investor-backed rounds since 2022.

Seeds
  - companies already in SQLite that qualify (market.py): their investors are fetched (incoming INVESTED_IN),
  - knowledge_search queries ("seed round Finland 2025", ...): only the returned entity IDs are used
    (Company -> screened, Organization -> explored as an investor); names in the answer text are ignored.
Loop (priority queue in the crawl_queue table, so --resume continues where it stopped)
  investor -> its portfolio (outgoing INVESTED_IN) -> each new company is screened with ONE call
  (properties + HQ + industries + round links + its investors) -> cheap prefilter (Europe HQ, founded
  >= 2015 or unknown) -> only for companies that pass, rounds whose link has a source dated 2022+ (or no
  date) are fetched with their participants -> if the company qualifies, its investors are queued.
  Investors are prioritised by how many qualifying companies they appear in.
Every Cala response is cached (never fetched twice), requests are throttled with back-off on 429, a
402 (out of credit) stops the run cleanly, and --max-calls caps the spend.

Usage:  backend/.venv/bin/python -u backend/snowball.py --max-calls 3000 [--resume] [--queries 40]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["BLINDSPOT_BACKEND"] = "sqlite"   # the crawler always writes the local SQLite store

import db  # noqa: E402
import market  # noqa: E402
from audit import is_conflated  # noqa: E402
from cala_client import Cala, PaymentRequired, sources_of, val  # noqa: E402
from crawler import ROUND_FIELDS, ROUND_FIELDS_V1, conflation  # noqa: E402
from funds import FUNDS  # noqa: E402
from nordic_seeds import NORDIC_CRAWLED_FUNDS, NORDIC_SEED_FUNDS  # noqa: E402
from vc import VCRule  # noqa: E402

COMPANY_FIELDS = ["name", "website", "founding_date", "funding_stage", "total_funding", "total_funding_units"]
COMPANY_OUT = ["HAS_HEADQUARTERS_IN", "PARTICIPATES_IN_FUNDING_ROUND", "OPERATES_IN_INDUSTRY"]
COMPANY_IN = ["INVESTED_IN"]
P_SEED_EXPAND, P_QUERY, P_QUERY_COMPANY, P_QUERY_ORG, P_INVESTOR = 100.0, 50.0, 60.0, 15.0, 10.0
# Nordic focus: Finnish fund seeds first, then other Nordic funds, then Nordic discovery queries.
P_FUND_PRIORITY_COUNTRY, P_FUND_REGION = 95.0, 85.0
P_QUERY_PRIORITY_COUNTRY, P_QUERY_REGION = 75.0, 70.0
BUMP_PRIORITY_COUNTRY, BUMP_REGION = 3.0, 2.0      # investor bump per qualifying company there
REPRIORITISE_OLD_QUEUE = -50.0                      # pending items from the Europe-wide crawl go last
STAGE_WORDS = {"PRE_SEED": "pre-seed startup", "SEED": "seed round", "SERIES_A": "Series A"}
REGION_YEARS = ["2022", "2023", "2024", "2025", "2026"]
WORKERS = 4

QUERY_COUNTRIES = ["Germany", "France", "United Kingdom", "Sweden", "Finland", "Denmark", "Norway", "Netherlands",
                   "Spain", "Italy", "Poland", "Austria", "Switzerland", "Estonia", "Portugal", "Belgium", "Ireland",
                   "Czechia", "Lithuania", "Latvia"]
QUERY_STAGES = ["pre-seed startup", "seed round", "Series A"]
QUERY_YEARS = ["2024", "2025", "2023", "2022", "2026"]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def region_queries() -> list[tuple[str, str]]:
    """(query, country): every region country x (pre-seed, seed, Series A) x 2022..2026, priority country first."""
    countries = sorted(market.REGION_COUNTRIES, key=lambda c: (c != market.PRIORITY_COUNTRY, c))
    return [(f"{STAGE_WORDS[st]} {c} raised {y}", c) for c in countries for st in STAGE_WORDS for y in REGION_YEARS]


def queries(n: int) -> list[str]:
    """Deterministic list of discovery queries: country x stage x year, interleaved, plus spin-off queries."""
    out = [f"university spin-off raises seed {c}" for c in ("Europe", "Germany", "Nordics", "France", "United Kingdom")]
    for y in QUERY_YEARS:
        for s in QUERY_STAGES:
            for c in QUERY_COUNTRIES:
                out.append(f"{s} {c} raised {y}")
    return out[:n]


class Snowball:
    def __init__(self, max_calls: int):
        self.cala = Cala()
        if not self.cala.has_key:
            sys.exit("CALA_API_KEY missing: put it in .env (see .env.example)")
        self.max_calls = max_calls
        self.lock = threading.Lock()
        self.stats = Counter()
        self.entity_fund = {eid: spec["id"] for spec in FUNDS.values() for eid in spec["entities"]}
        self.vc = VCRule(self.entity_fund)

    # ---------------------------------------------------------------- one-time backfill (no Cala calls)

    def backfill(self) -> None:
        """Dated sources and date_kind for stored rounds (from cached responses); prefilter/qualifies for
        stored companies. Uses only the cache, never the network."""
        rounds = db._rows("SELECT * FROM rounds")
        fixed = 0
        for r in rounds:
            for fields in (ROUND_FIELDS, ROUND_FIELDS_V1):
                hit = db.cache_get("entity_retrieval:" + json.dumps(
                    {"entity_id": r["id"], "properties": fields, "relationships": {
                        "outgoing": {}, "incoming": {"PARTICIPATES_IN_FUNDING_ROUND": {"limit": 100, "offset": 0}}}},
                    sort_keys=True))
                if hit:
                    srcs = sources_of(hit, ["transaction_value", "round_label", "announcement_date", "event_date"])
                    ann, ev = val(hit, "announcement_date"), val(hit, "event_date")
                    date = ann or ev or r["date"]
                    kind = "announcement" if ann else ("event" if ev else r.get("date_kind"))
                    db._execute("UPDATE rounds SET sources=?, date=?, date_kind=? WHERE id=?",
                                [json.dumps(srcs), date, kind, r["id"]])
                    fixed += 1
                    break
        db.conn().commit()
        comps = db._rows("SELECT id, country, founded, fetched_at, screened_at FROM companies")
        parts = db.participants([r["id"] for r in rounds])
        by_company = {}
        for r in db.rounds_for_companies([c["id"] for c in comps]):
            by_company.setdefault(r["company_id"], []).append(r)
        n_q = 0
        for c in comps:
            pf = market.prefilter(c["country"], c["founded"])
            q = pf == "pass" and any(market.round_qualifies(r, parts.get(r["id"], []), is_conflated, self.vc.is_vc)
                                     for r in by_company.get(c["id"], []))
            n_q += q
            db.upsert_company_fields(c["id"], prefilter=pf, qualifies=int(q),
                                     screened_at=c["screened_at"] or c["fetched_at"],
                                     discovered_via=None if c["screened_at"] else "fund")
        log(f"[backfill] rounds with dated sources: {fixed}/{len(rounds)}; companies: {len(comps)}, "
            f"qualifying European: {n_q}")

    def seed(self, n_queries: int) -> None:
        q = db._rows("SELECT id FROM companies WHERE qualifies=1")
        added = db.queue_add([(c["id"], "expand", P_SEED_EXPAND, "seed") for c in q])
        added += db.queue_add([("q:" + text, "query", P_QUERY - i * 0.01, "knowledge_search")
                               for i, text in enumerate(queries(n_queries))])
        # investors already known from qualifying rounds
        inv = db._rows("SELECT p.entity_id, COUNT(DISTINCT r.company_id) AS n FROM round_participants p "
                       "JOIN rounds r ON r.id=p.round_id JOIN companies c ON c.id=r.company_id "
                       "WHERE c.qualifies=1 AND p.role != 'ISSUER' GROUP BY p.entity_id")
        added += db.queue_add([(r["entity_id"], "investor", P_INVESTOR + r["n"], "seed") for r in inv])
        log(f"[seed] {len(q)} qualifying seed companies, {n_queries} queries, {len(inv)} known investors; "
            f"{added} new queue items")

    def seed_region(self) -> None:
        """Nordic focus: older pending items go last; region fund seeds and region queries go first."""
        db._execute("UPDATE crawl_queue SET priority = priority + ? WHERE status='pending' AND priority < ?",
                    [REPRIORITISE_OLD_QUEUE, P_QUERY_REGION])
        db.conn().commit()
        for name, spec in FUNDS.items():
            db.upsert_fund(spec["id"], name, list(spec["entities"].items()))
        items = []
        for name, country in NORDIC_CRAWLED_FUNDS.items():
            p = P_FUND_PRIORITY_COUNTRY if country == market.PRIORITY_COUNTRY else P_FUND_REGION
            items += [(eid, "investor", p, f"seed_fund:{name}") for eid in FUNDS[name]["entities"]]
        for name, (country, ids) in NORDIC_SEED_FUNDS.items():
            p = P_FUND_PRIORITY_COUNTRY if country == market.PRIORITY_COUNTRY else P_FUND_REGION
            items += [(eid, "investor", p, f"seed_fund:{name}") for eid in ids]
        items += [("q:" + q, "query", (P_QUERY_PRIORITY_COUNTRY if c == market.PRIORITY_COUNTRY else P_QUERY_REGION)
                   - i * 0.001, "knowledge_search") for i, (q, c) in enumerate(region_queries())]
        # crawled-fund entities already explored by an earlier run must be revisited for their own rounds
        fund_entities = [it[0] for it in items if it[0] in self.entity_fund]
        for eid in fund_entities:
            db._execute("UPDATE crawl_queue SET status='pending', priority=? WHERE entity_id=? AND status!='running'",
                        [next(it[2] for it in items if it[0] == eid), eid])
        db.conn().commit()
        added = db.queue_add(items)
        log(f"[seed:{market.MARKET_REGION}] {len(NORDIC_CRAWLED_FUNDS)} crawled funds + {len(NORDIC_SEED_FUNDS)} seed "
            f"funds, {len(region_queries())} queries; {added} new queue items; older pending items deprioritised")

    # ---------------------------------------------------------------- task handlers

    def _queue_investors(self, company_id: str, investors: list[dict], source: str, country: str = None) -> None:
        """Only VCs are expanded (vc.py): angels, banks, grant bodies, corporates etc. are not queued."""
        ids = sorted({i["id"] for i in investors if i.get("id") and self.vc.is_vc(
            {"entity_id": i["id"], "name": i.get("name"), "entity_type": i.get("entity_type"),
             "role": i.get("role") or "INVESTOR"})})
        bump = (BUMP_PRIORITY_COUNTRY if country == market.PRIORITY_COUNTRY else
                BUMP_REGION if country in market.REGION_COUNTRIES else 1.0)
        with self.lock:
            db.queue_bump(ids, bump)
            db.queue_add([(i, "investor", P_INVESTOR + bump, f"{source}:{company_id}") for i in ids])

    def screen_company(self, cid: str, source: str) -> str:
        known = db._rows("SELECT screened_at FROM companies WHERE id=?", [cid])
        if known and known[0]["screened_at"]:
            return "already screened"
        c = self.cala.retrieve(cid, COMPANY_FIELDS, out=COMPANY_OUT, inc=COMPANY_IN)
        if not c.get("_ok"):
            return "not retrievable"
        rels = c["_rels"]
        hqs = rels.get("outgoing:HAS_HEADQUARTERS_IN", [])
        country = next((h["name"] for h in hqs if h.get("entity_type") == "Country"), hqs[0]["name"] if hqs else None)
        founded = val(c, "founding_date")
        founded = str(founded)[:4] if founded else None
        pf = market.crawl_prefilter(country, founded)
        industries = sorted({i["name"] for i in rels.get("outgoing:OPERATES_IN_INDUSTRY", []) if i.get("name")})
        investors = rels.get("incoming:INVESTED_IN", [])
        db.upsert_company({
            "id": cid, "name": val(c, "name") or c.get("name"), "website": val(c, "website"),
            "description": c.get("description"), "country": country, "founded": founded,
            "funding_stage": val(c, "funding_stage"), "total_funding": val(c, "total_funding"),
            "total_funding_currency": val(c, "total_funding_units"), "industries": json.dumps(industries),
            "sources": json.dumps(sources_of(c, ["name", "website", "funding_stage", "total_funding"])),
            "fetched_at": time.time(), "screened_at": time.time(), "prefilter": pf, "qualifies": 0,
            "discovered_via": source,
        })
        db.add_company_investors([(cid, i["id"], i.get("name"), i.get("entity_type"), "INVESTED_IN")
                                  for i in investors if i.get("id")])
        with self.lock:
            self.stats["screened"] += 1
            self.stats[f"prefilter:{pf}"] += 1
        if pf != "pass":
            return pf
        qualifies, round_investors = False, []
        for link in rels.get("outgoing:PARTICIPATES_IN_FUNDING_ROUND", []):
            if (link.get("properties") or {}).get("role") not in ("ISSUER", None):
                continue
            dates = [str(s.get("date"))[:10] for s in (link.get("properties") or {}).get("sources", []) if s.get("date")]
            if dates and max(dates) < market.PERIOD_FROM:
                continue        # every source of this round link predates 2022: the round cannot qualify
            stored = db._rows("SELECT * FROM rounds WHERE id=?", [link["id"]])
            if not stored:
                stored = self.fetch_round(link["id"], cid, c)
            for r in stored:
                r["sources"] = json.loads(r["sources"]) if isinstance(r["sources"], str) else r["sources"]
                parts = db.participants([r["id"]]).get(r["id"], [])
                if market.round_qualifies(r, parts, is_conflated, self.vc.is_vc):
                    qualifies = True
                    round_investors += [{"id": p["entity_id"], "name": p["name"], "entity_type": p["entity_type"],
                                         "role": p["role"]} for p in parts if p["role"] != "ISSUER"]
        if qualifies:
            db.upsert_company_fields(cid, qualifies=1)
            with self.lock:
                self.stats["qualifying"] += 1
            self._queue_investors(cid, investors + round_investors, "company", country)
        return "qualifies" if qualifies else "no qualifying round"

    def store_fetched_round(self, rnd: dict, cid: str) -> None:
        """Store an already retrieved round (a crawled fund's own round), whatever its issuer's region."""
        comp = db.companies([cid]).get(cid) or {}
        company = {"properties": {"total_funding": {"value": comp.get("total_funding")},
                                  "total_funding_units": {"value": comp.get("total_funding_currency")}}}
        self._store_round(rnd, cid, company)

    def fetch_round(self, rid: str, cid: str, company: dict) -> list[dict]:
        rnd = self.cala.retrieve(rid, ROUND_FIELDS, inc=["PARTICIPATES_IN_FUNDING_ROUND"])
        if not rnd.get("_ok"):
            rnd = self.cala.retrieve(rid, ROUND_FIELDS_V1, inc=["PARTICIPATES_IN_FUNDING_ROUND"])
        if not rnd.get("_ok"):
            return []
        with self.lock:
            self.stats["rounds_fetched"] += 1
        self._store_round(rnd, cid, company)
        return db._rows("SELECT * FROM rounds WHERE id=?", [rid])

    def _store_round(self, rnd: dict, cid: str, company: dict) -> None:
        rid = rnd["id"]
        label, amount, cur = val(rnd, "round_label"), val(rnd, "transaction_value"), val(rnd, "transaction_value_units")
        ann, ev = val(rnd, "announcement_date"), val(rnd, "event_date")
        parts = []
        for p in rnd["_rels"].get("incoming:PARTICIPATES_IN_FUNDING_ROUND", []):
            props = p.get("properties") or {}
            parts.append({"entity_id": p["id"], "name": p.get("name"), "entity_type": p.get("entity_type"),
                          "role": props.get("role"), "is_lead": props.get("is_lead")})
        reason = conflation(label, amount, val(company, "total_funding"),
                            cur is not None and cur == val(company, "total_funding_units"))
        row = {"id": rid, "company_id": cid, "label": label, "amount": amount, "currency": cur,
               "date": ann or ev, "date_kind": "announcement" if ann else ("event" if ev else None),
               "conflated": int(bool(reason)), "conflation_reason": reason,
               "sources": json.dumps(sources_of(rnd, ["transaction_value", "round_label", "announcement_date",
                                                      "event_date"]))}
        db.upsert_round(row, parts)

    def explore_investor(self, iid: str, priority: float) -> str:
        fund_id = self.entity_fund.get(iid)
        if fund_id:
            return self.explore_fund_entity(iid, fund_id, priority)
        name = db.investor_name(iid)
        if name is not None and not self.vc.is_vc({"entity_id": iid, "name": name, "role": "INVESTOR",
                                                   "entity_type": self._entity_type(iid)}):
            return "skipped: not a VC (no call)"
        e = self.cala.retrieve(iid, ["name"], out=["INVESTED_IN"])
        if not e.get("_ok"):
            return "not retrievable"
        port = [p["id"] for p in e["_rels"].get("outgoing:INVESTED_IN", []) if p.get("id")]
        screened = {r["id"] for r in db._rows("SELECT id FROM companies WHERE screened_at IS NOT NULL")}
        new = [p for p in port if p not in screened]
        with self.lock:
            self.stats["investors_explored"] += 1
            # +0.5: an investor's portfolio is screened before other investors of equal priority are explored
            added = db.queue_add([(p, "company", priority + 0.5, f"investor:{iid}") for p in new])
        return f"{len(port)} portfolio, {added} queued"

    def explore_fund_entity(self, eid: str, fund_id: str, priority: float) -> str:
        """A crawled fund (funds.py): portfolio (INVESTED_IN) and its own rounds since 2022
        (PARTICIPATES_IN_FUNDING_ROUND), so its thesis rests on its real deals. Same calls the fund
        crawler makes (cached), plus one call per own round with a 2022+ (or undated) source."""
        e = self.cala.retrieve(eid, ["name"], out=["INVESTED_IN", "PARTICIPATES_IN_FUNDING_ROUND"])
        if not e.get("_ok"):
            return "not retrievable"
        links = [(it["id"], "INVESTED_IN", (it.get("properties") or {}).get("valid_since"))
                 for it in e["_rels"].get("outgoing:INVESTED_IN", []) if it.get("id")]
        issuers = set()
        for it in e["_rels"].get("outgoing:PARTICIPATES_IN_FUNDING_ROUND", []):
            dates = [str(x.get("date"))[:10] for x in (it.get("properties") or {}).get("sources", []) if x.get("date")]
            if dates and max(dates) < market.PERIOD_FROM:
                continue
            stored = db._rows("SELECT company_id FROM rounds WHERE id=?", [it["id"]])
            if stored:
                issuers.add(stored[0]["company_id"])
                continue
            rnd = self.cala.retrieve(it["id"], ROUND_FIELDS, inc=["PARTICIPATES_IN_FUNDING_ROUND"])
            issuer = next((p["id"] for p in (rnd["_rels"].get("incoming:PARTICIPATES_IN_FUNDING_ROUND", [])
                                             if rnd.get("_ok") else [])
                           if (p.get("properties") or {}).get("role") == "ISSUER"), None)
            if issuer:
                issuers.add(issuer)
                self.store_fetched_round(rnd, issuer)    # the fund's own round counts for its thesis
        links += [(c, "ROUND", None) for c in sorted(issuers)]
        db.add_portfolio(fund_id, sorted(set(links), key=lambda l: (l[0], l[1], l[2] or "")))
        screened = {r["id"] for r in db._rows("SELECT id FROM companies WHERE screened_at IS NOT NULL")}
        targets = sorted({l[0] for l in links})
        own_rounds = [c for c in sorted(issuers) if c not in screened]
        with self.lock:
            self.stats["investors_explored"] += 1
            added = db.queue_add([(c, "company", priority + 1.0, f"fund:{fund_id}") for c in own_rounds])
            added += db.queue_add([(c, "company", priority + 0.5, f"fund:{fund_id}") for c in targets
                                   if c not in screened])
            # already screened companies with new own rounds: re-screen their rounds via a refresh task
        return f"fund {fund_id}: {len(targets)} portfolio, {len(issuers)} own rounds since 2022, {added} queued"

    def _entity_type(self, iid: str):
        r = db._rows("SELECT entity_type FROM round_participants WHERE entity_id=? LIMIT 1", [iid]) or \
            db._rows("SELECT entity_type FROM company_investors WHERE investor_id=? LIMIT 1", [iid])
        return r[0]["entity_type"] if r else None

    def expand_seed(self, cid: str) -> str:
        e = self.cala.retrieve(cid, ["name"], inc=["INVESTED_IN"])
        investors = e["_rels"].get("incoming:INVESTED_IN", []) if e.get("_ok") else []
        db.add_company_investors([(cid, i["id"], i.get("name"), i.get("entity_type"), "INVESTED_IN")
                                  for i in investors if i.get("id")])
        self._queue_investors(cid, investors, "seed")
        return f"{len(investors)} investors"

    def run_query(self, text: str) -> str:
        res = self.cala.knowledge_search(text) or {}
        ents = res.get("entities") or []
        companies = [e["id"] for e in ents if e.get("entity_type") == "Company" and e.get("id")]
        orgs = [e["id"] for e in ents if e.get("entity_type") == "Organization" and e.get("id")]
        with self.lock:
            self.stats["queries"] += 1
            self.stats["query_companies"] += len(companies)
            added = db.queue_add([(c, "company", P_QUERY_COMPANY, "knowledge_search") for c in companies])
            added += db.queue_add([(o, "investor", P_QUERY_ORG, "knowledge_search") for o in orgs])
        return f"{len(companies)} companies, {len(orgs)} orgs, {added} new"

    def process(self, task: dict) -> tuple[str, str]:
        kind, eid = task["kind"], task["entity_id"]
        if kind == "company":
            return "done", self.screen_company(eid, task["discovered_from"] or "queue")
        if kind == "investor":
            return "done", self.explore_investor(eid, task["priority"])
        if kind == "expand":
            return "done", self.expand_seed(eid)
        if kind == "query":
            return "done", self.run_query(eid[2:])
        return "error", f"unknown kind {kind}"

    # ---------------------------------------------------------------- main loop

    def run(self) -> int:
        t0, status, done = time.time(), 0, 0
        db._execute("UPDATE crawl_queue SET status='pending' WHERE status='running'")
        db.conn().commit()
        pool = ThreadPoolExecutor(WORKERS)
        inflight = {}
        stop = False
        try:
            while True:
                while not stop and len(inflight) < WORKERS * 2:
                    if self.cala.api_calls >= self.max_calls:
                        log(f"[budget] {self.cala.api_calls} calls reached --max-calls {self.max_calls}; finishing")
                        stop = True
                        break
                    with self.lock:
                        nxt = [t for t in db.queue_next(WORKERS * 4) if t["entity_id"] not in inflight][:1]
                        if not nxt:
                            break
                        task = nxt[0]
                        db.queue_set(task["entity_id"], "running")
                    inflight[task["entity_id"]] = (pool.submit(self.process, task), task)
                if not inflight:
                    break
                finished, _ = wait([f for f, _ in inflight.values()], return_when=FIRST_COMPLETED)
                for eid in [e for e, (f, _) in inflight.items() if f in finished]:
                    fut, task = inflight.pop(eid)
                    try:
                        st, note = fut.result()
                    except PaymentRequired as e:
                        db.queue_set(eid, "pending")
                        log(f"[stop] {e}. Top up Cala credit and re-run with --resume.")
                        stop, status = True, 2
                        continue
                    except Exception as e:  # noqa: BLE001 - one bad entity must not stop the crawl
                        st, note = "error", f"{type(e).__name__}: {e}"[:200]
                        log(f"[error] {task['kind']} {eid}: {note}")
                    db.queue_set(eid, st, note)
                    done += 1
                    if done % 25 == 0:
                        self.progress(t0)
        finally:
            pool.shutdown(wait=True)
            self.progress(t0)
            self.summary(time.time() - t0, status)
        return status

    def progress(self, t0: float) -> None:
        q = db._rows("SELECT COUNT(*) AS n FROM companies WHERE qualifies=1")[0]["n"]
        log(f"[progress] calls {self.cala.api_calls} (429 retries {self.cala.rate_limited}), "
            f"screened {self.stats['screened']}, new qualifying {self.stats['qualifying']}, "
            f"qualifying total {q}, investors explored {self.stats['investors_explored']}, "
            f"queries {self.stats['queries']}, {time.time() - t0:.0f}s")

    def summary(self, elapsed: float, status: int) -> None:
        q = db._rows("SELECT COUNT(*) AS n FROM companies WHERE qualifies=1")[0]["n"]
        scr = db._rows("SELECT prefilter, COUNT(*) AS n FROM companies GROUP BY prefilter")
        md = ["# Snowball crawl summary", "",
              f"Market: European companies with a round since {market.PERIOD_FROM} that has a named investor.", "",
              "| Metric | Value |", "|---|---|",
              f"| Qualifying European companies (total in DB) | {q} |",
              f"| Companies screened this run | {self.stats['screened']} |",
              f"| ...newly qualifying this run | {self.stats['qualifying']} |",
              f"| Rounds fetched this run | {self.stats['rounds_fetched']} |",
              f"| Investors explored this run | {self.stats['investors_explored']} |",
              f"| knowledge_search queries this run | {self.stats['queries']} "
              f"({self.stats['query_companies']} company entities) |",
              f"| Cala calls this run (incl. 429 retries) | {self.cala.api_calls} (retries {self.cala.rate_limited}) |",
              f"| Run time | {elapsed:.0f} s |",
              f"| Stopped by | {'402 out of credit' if status == 2 else 'budget or empty queue'} |", "",
              "## Companies by prefilter result (all in DB)", "", "| Prefilter | Companies |", "|---|---|"]
        md += [f"| {r['prefilter'] or 'not screened'} | {r['n']} |" for r in scr]
        md += ["", "## Queue", "", "| Kind:status | Items |", "|---|---|"]
        md += [f"| {k} | {v} |" for k, v in sorted(db.queue_stats().items())]
        (db.ROOT / "data" / "snowball_summary.md").write_text("\n".join(md) + "\n")
        log("\n".join(md))


def main() -> None:
    ap = argparse.ArgumentParser(description="Snowball the Cala investor network into data/cala.db")
    ap.add_argument("--max-calls", type=int, default=3000, help="stop after this many Cala calls (incl. retries)")
    ap.add_argument("--resume", action="store_true", help="continue the existing queue (skip backfill and seeding)")
    ap.add_argument("--queries", type=int, default=40, help="knowledge_search seed queries (first run)")
    ap.add_argument("--backfill-only", action="store_true",
                    help="recompute dated sources, prefilter and qualifies (VC rule) from the DB; no Cala calls")
    ap.add_argument("--seed-region", action="store_true",
                    help=f"(re)seed the {market.MARKET_REGION} focus: region funds and region queries first")
    args = ap.parse_args()
    s = Snowball(args.max_calls)
    if not args.resume or not db.queue_next(1):
        s.backfill()
        s.seed(args.queries)
    if args.seed_region:
        s.seed_region()
    if args.backfill_only:
        s.backfill()
        sys.exit(0)
    sys.exit(s.run())


if __name__ == "__main__":
    main()
