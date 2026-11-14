"""Deterministic Blind Spot logic: fund profile, peer market, audit and deal detail.

Every number returned by the API is computed here from the crawled Cala data.
Only the wording of `top_blind_spots` comes from an LLM (insights.py), and only
after the facts and numbers are fixed.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Optional
from urllib.parse import urlparse

import db
import crm_import
import insights
import peers as peerscore
from matching import CompanyIndex, classify, normalize_domain
from names import display

PROFILE_FROM = "2022-01-01"
MARKET_FROM = "2023-01-01"
EQUITY_STAGES = ["PRE_SEED", "SEED", "SERIES_A", "SERIES_B", "SERIES_C", "SERIES_D", "SERIES_E", "SERIES_F",
                 "SERIES_G", "SERIES_H"]
STAGE_RANK = {s: i for i, s in enumerate(EQUITY_STAGES)}
THESIS_STAGE_MIN_SHARE = 0.10
# Geography of the market (product rule): all crawled funds are European, so the market only
# contains companies headquartered in Europe. Within that scope, a region is in the fund's thesis
# when it holds at least THESIS_REGION_MIN_SHARE of the fund's whole Cala portfolio (companies
# with a known HQ, all countries in the denominator).
MARKET_SCOPE = "Europe"
THESIS_REGION_MIN_SHARE = 0.05
MAX_NEVER_SEEN = 200
# A reworded insight must keep one of these verbs: peers *did* these rounds (not "reviewed" or "saw").
PEER_VERBS = ["did", "done", "closed", "backed", "funded", "invested", "led", "made", "completed"]
# Largest plausible round per label (any currency). Anything above is treated as conflated / a data
# error (e.g. a valuation stored as the round size) and is excluded from counts. Same values as the
# crawler's CONFLATION_THRESHOLDS; applied again here so they work on already-crawled data.
MAX_PLAUSIBLE_ROUND = {"PRE_SEED": 5e6, "SEED": 10e6, "SERIES_A": 75e6, "SERIES_B": 250e6,
                       "SERIES_C": 600e6, "SERIES_D": 1.5e9, "SERIES_E": 2e9, "SERIES_F": 3e9}


def is_conflated(r: dict) -> bool:
    cap = MAX_PLAUSIBLE_ROUND.get(r.get("label") or "")
    return bool(r.get("conflated")) or bool(cap and isinstance(r.get("amount"), (int, float)) and r["amount"] > cap)

REGIONS = {
    "Nordics": ["Sweden", "Denmark", "Norway", "Finland", "Iceland"],
    "DACH": ["Germany", "Austria", "Switzerland", "Liechtenstein"],
    "UK & Ireland": ["United Kingdom", "Ireland"],
    "France": ["France", "Monaco"],
    "Benelux": ["Netherlands", "Belgium", "Luxembourg"],
    "Southern Europe": ["Spain", "Italy", "Portugal", "Greece", "Malta", "Cyprus"],
    "CEE": ["Poland", "Czechia", "Slovakia", "Hungary", "Romania", "Bulgaria", "Croatia", "Slovenia", "Serbia",
            "Ukraine", "Estonia", "Latvia", "Lithuania"],
    "North America": ["United States", "Canada"],
    "Türkiye": ["Türkiye", "Turkey"],
    "Israel": ["Israel"],
}
EUROPE_REGIONS = {"Nordics", "DACH", "UK & Ireland", "France", "Benelux", "Southern Europe", "CEE", "Türkiye"}
REGION_ADJ = {"Nordics": "Nordic", "DACH": "DACH", "UK & Ireland": "UK & Irish", "France": "French",
              "Benelux": "Benelux", "Southern Europe": "Southern European", "CEE": "CEE",
              "North America": "North American", "Israel": "Israeli", "Türkiye": "Turkish"}
COUNTRY_REGION = {c: r for r, cs in REGIONS.items() for c in cs}


def region_of(country: Optional[str]) -> Optional[str]:
    return COUNTRY_REGION.get(country or "", country)


def stage_human(label: str) -> str:
    return {"PRE_SEED": "pre-seed", "SEED": "seed"}.get(label, label.replace("_", " ").title())


def industry_human(code: str) -> str:
    return code.replace("_", " ").capitalize().replace(" and ", " and ")


class NotFound(Exception):
    pass


# ---------------------------------------------------------------- helpers

def _fund_names() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """(fund id -> name, entity id -> fund id, entity id -> brand display name)."""
    funds = {f["id"]: f["name"] for f in db.list_funds()}
    return funds, db.entity_to_fund(), db.display_names()


def _investor(entity_id: str, name: str, funds: dict, ent2fund: dict, known: Optional[dict] = None) -> dict:
    """Collapse a fund's legal entities onto the fund (e.g. 'Creandum Kommanditbolag' -> Creandum);
    other investors get their brand name instead of an upper-case legal name."""
    fid = ent2fund.get(entity_id)
    return {"id": fid, "name": funds[fid]} if fid else {"id": entity_id, "name": display(name, known, entity_id)}


def _leads_and_participants(round_ids, funds, ent2fund, known=None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rid, parts in db.participants(round_ids).items():
        leads, others, seen = [], [], set()
        for p in parts:
            if p["role"] == "ISSUER":
                continue
            inv = _investor(p["entity_id"], p["name"], funds, ent2fund, known)
            if inv["id"] in seen:
                continue
            seen.add(inv["id"])
            (leads if p["is_lead"] else others).append(inv)
        out[rid] = {"leads": leads, "participants": others}
    return out


def _amount(v):
    if v is None:
        return None
    return int(v) if float(v).is_integer() else float(v)


# ---------------------------------------------------------------- funds

def search_funds(q: str) -> list[dict]:
    q = (q or "").strip().lower()
    funds = db.list_funds()
    if not q:
        return funds
    starts = [f for f in funds if f["name"].lower().startswith(q)]
    contains = [f for f in funds if q in f["name"].lower() and f not in starts]
    return starts + contains


def _fund_or_404(fund_id: str) -> dict:
    f = db.get_fund(fund_id)
    if not f:
        raise NotFound(f"fund {fund_id} not found")
    return f


def profile(fund_id: str) -> dict:
    p = _profile(fund_id)
    out = {k: v for k, v in p.items() if not k.startswith("_")}
    out["suggested_peers"] = select_peers(fund_id, p["_portfolios"])
    return out


def rank_peers(fund_id: str, portfolios: Optional[dict] = None) -> list[dict]:
    """Every other fund with its thesis-similarity score and reasons (see peers.py), best first."""
    portfolios = portfolios if portfolios is not None else db.all_fund_portfolios()
    names = {f["id"]: f["name"] for f in db.list_funds()}
    all_ids = set().union(*portfolios.values()) if portfolios else set()
    comps = db.companies(all_ids)
    by_company: dict[str, list] = defaultdict(list)
    for r in db.rounds_for_companies(all_ids):
        by_company[r["company_id"]].append(r)
    equity = set(EQUITY_STAGES)

    def thesis_of(fid):
        return peerscore.thesis(portfolios.get(fid, set()), comps, by_company, region_of, equity, is_conflated)

    mine = thesis_of(fund_id)
    own = portfolios.get(fund_id, set())
    ranked = []
    for fid, name in names.items():
        if fid == fund_id:
            continue
        theirs = thesis_of(fid)
        co = len(own & portfolios.get(fid, set()))
        sc, parts = peerscore.score(mine, theirs, co)
        ranked.append({"id": fid, "name": name, "co_investments": co, "score": sc,
                       "reasons": peerscore.reasons(mine, theirs, parts, co, stage_human, industry_human,
                                                    lambda r: REGION_ADJ.get(r, r))})
    ranked.sort(key=lambda p: (-p["score"], p["name"].casefold()))
    return ranked


def select_peers(fund_id: str, portfolios: Optional[dict] = None) -> list[dict]:
    """Default peers: the top PEER_COUNT funds scoring at least MIN_PEER_SCORE."""
    return [p for p in rank_peers(fund_id, portfolios) if p["score"] >= peerscore.MIN_PEER_SCORE][:peerscore.peer_count()]


def _profile(fund_id: str) -> dict:
    fund = _fund_or_404(fund_id)
    portfolios = db.all_fund_portfolios()
    portfolio = portfolios.get(fund_id, set())
    comps = db.companies(portfolio)
    rounds = [r for r in db.rounds_for_companies(portfolio)
              if r["date"] and r["date"] >= PROFILE_FROM and not is_conflated(r)]
    active = sorted({r["company_id"] for r in rounds})
    stage_counts = Counter(r["label"] for r in rounds if r["label"] in STAGE_RANK)
    total = sum(stage_counts.values())
    stages = [{"label": s, "share": round(n / total, 2)}
              for s, n in sorted(stage_counts.items(), key=lambda kv: (-kv[1], STAGE_RANK[kv[0]]))] if total else []
    # Countries over the fund's whole Cala portfolio (a far larger sample than the recent rounds).
    countries = Counter(c["country"] for c in comps.values() if c["country"])
    industries = Counter(i for c in active if c in comps for i in comps[c]["industries"])

    sources, seen = [], set()
    for r in sorted(rounds, key=lambda r: r["date"], reverse=True):
        for s in r["sources"]:
            if s["url"] not in seen and len(sources) < 10:
                seen.add(s["url"])
                sources.append(s)

    # Thesis = every stage between the fund's lowest and highest stage with >= 10% share
    # (so a PRE_SEED..SERIES_B fund includes SERIES_A), and every region it recently invested in.
    core = [STAGE_RANK[s["label"]] for s in stages if s["share"] >= THESIS_STAGE_MIN_SHARE]
    thesis_stages = set(EQUITY_STAGES[min(core):max(core) + 1]) if core else {"SEED", "SERIES_A"}
    known = sum(countries.values())
    region_counts = Counter()
    for country, n in countries.items():
        region_counts[region_of(country)] += n
    thesis_regions = {r for r, n in region_counts.items()
                      if r in EUROPE_REGIONS and known and n / known >= THESIS_REGION_MIN_SHARE}
    thesis_regions = thesis_regions or set(EUROPE_REGIONS)
    return {
        "fund": fund,
        "investments_since_2022": len(active),
        "stages": stages,
        "countries": [{"name": k, "count": v} for k, v in sorted(countries.items(), key=lambda kv: (-kv[1], kv[0]))],
        "industries": [{"name": industry_human(k), "count": v}
                       for k, v in sorted(industries.items(), key=lambda kv: (-kv[1], kv[0]))],
        "suggested_peers": [],          # filled by profile() (thesis similarity, see peers.py)
        "sources": sources,
        "_portfolio": portfolio,
        "_portfolios": portfolios,
        "_thesis_stages": thesis_stages,
        "_thesis_regions": thesis_regions,
        "_top_countries": [k for k, _ in sorted(countries.items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
    }


# ---------------------------------------------------------------- audit

def parse_crm(text: str) -> tuple[list[dict], bool]:
    """CRM CSV text -> (normalized rows, simulated flag), using the same column detection as uploads.
    Lines starting with '#' are comments; a comment containing 'SIMULATED' marks the file as simulated."""
    table = crm_import.load_table("crm.csv", text.encode("utf-8"))
    rows = crm_import.normalize_rows(table, crm_import.resolve_mapping(table))
    return rows, table["simulated"]


def run_audit(fund_id: str, peer_ids: list[str], crm_text: str) -> dict:
    """Audit from CRM CSV text (demo builder, tests)."""
    rows, simulated = parse_crm(crm_text)
    return run_audit_rows(fund_id, peer_ids, rows, simulated, crm_text)


def run_audit_rows(fund_id: str, peer_ids: list[str], crm_rows: list[dict], simulated: bool,
                   fingerprint: str) -> dict:
    """Audit from normalized CRM rows ({company, website, status, date}). Status "seen" (no status
    recorded) counts as in_review: the company reached the pipeline without a decision."""
    prof = _profile(fund_id)
    funds, ent2fund, known = _fund_names()
    peer_ids = [p for p in dict.fromkeys(peer_ids) if p and p != fund_id]
    if not peer_ids:            # no peers sent: use the thesis-similarity default
        peer_ids = [p["id"] for p in select_peers(fund_id, prof["_portfolios"])]
    unknown = [p for p in peer_ids if p not in funds]      # one lookup instead of a query per peer
    if unknown:
        raise NotFound(f"fund {unknown[0]} not found")

    peer_portfolio = set().union(*(prof["_portfolios"].get(p, set()) for p in peer_ids)) if peer_ids else set()
    comps = db.companies(peer_portfolio)
    regions = prof["_thesis_regions"]
    stages = prof["_thesis_stages"]

    # Market: peers' portfolio companies with an in-thesis round since 2023 (deal = latest such round)
    counted: dict[str, dict] = {}
    for r in db.rounds_for_companies(comps):
        c = comps[r["company_id"]]
        if not r["date"] or r["date"] < MARKET_FROM or r["label"] not in stages or region_of(c["country"]) not in regions:
            continue
        if not r["sources"] or is_conflated(r):   # needs a Cala source; merged/implausible rounds never count
            continue
        cur = counted.get(c["id"])
        if cur is None or (r["date"], r["amount"] or 0) > (cur["date"], cur["amount"] or 0):
            counted[c["id"]] = r

    index = CompanyIndex(comps.values())
    status, pipeline_only = classify(counted, crm_rows, index, known_invested=prof["_portfolio"])

    st = Counter(status.values())
    market = len(counted)
    in_pipeline = market - st["never_seen"]
    summary = {"market_deals": market, "in_pipeline": in_pipeline, "invested": st["invested"],
               "passed": st["passed"], "in_review": st["in_review"], "never_seen": st["never_seen"],
               "coverage_pct": round(100.0 * in_pipeline / market, 1) if market else 0.0}

    # Heatmap: country x stage over counted market deals
    cell = defaultdict(lambda: [0, 0])
    for cid, r in counted.items():
        k = (comps[cid]["country"], r["label"])
        cell[k][0] += 1
        cell[k][1] += status[cid] == "never_seen"
    country_tot = Counter()
    for (country, _), (t, _) in cell.items():
        country_tot[country] += t
    hm_countries = [c for c, _ in sorted(country_tot.items(), key=lambda kv: (-kv[1], kv[0]))]
    hm_stages = sorted({s for _, s in cell}, key=STAGE_RANK.get)
    heatmap = {"countries": hm_countries, "stages": hm_stages,
               "cells": [{"country": c, "stage": s, "total": cell[(c, s)][0], "never_seen": cell[(c, s)][1],
                          "share": round(cell[(c, s)][1] / cell[(c, s)][0], 2)}
                         for c in hm_countries for s in hm_stages if (c, s) in cell]}

    # Never-seen deals: only counted (non-conflated) deals, so the table, summary and heatmap
    # describe exactly the same set. Conflated rounds stay visible on the deal page only.
    lp = _leads_and_participants([r["id"] for r in counted.values()], funds, ent2fund, known)

    def deal(cid, r):
        c = comps[cid]
        return {"company_id": cid, "name": display(c["name"], known, cid),
                "website": normalize_domain(c["website"]) or c["website"],
                "country": c["country"], "stage": r["label"], "amount": _amount(r["amount"]),
                "currency": r["currency"], "date": r["date"],
                "lead_investors": lp.get(r["id"], {}).get("leads", []),
                "sources": r["sources"], "conflated": False}

    never = [deal(cid, r) for cid, r in counted.items() if status[cid] == "never_seen"]
    never.sort(key=lambda d: (-(d["amount"] or 0), d["date"] or "", d["company_id"]))
    never_seen_deals = never[:MAX_NEVER_SEEN]

    leads = Counter()
    lead_names = {}
    for d in never:
        for l in d["lead_investors"]:
            if l["id"] != fund_id:
                leads[l["id"]] += 1
                lead_names[l["id"]] = l["name"]
    top_missed_leads = [{"id": k, "name": lead_names[k], "deals": n}
                        for k, n in sorted(leads.items(), key=lambda kv: (-kv[1], lead_names[kv[0]]))[:5]]

    facts = blind_spot_facts(counted, status, comps, top_missed_leads)
    audit_id = hashlib.sha1("|".join([fund_id, ",".join(sorted(peer_ids)), fingerprint]).encode()).hexdigest()[:12]
    return {
        "audit_id": audit_id,
        "fund": prof["fund"],
        # Only peers that contributed at least one company to the counted market.
        "peers": [{"id": p, "name": funds[p]} for p in peer_ids if prof["_portfolios"].get(p, set()) & set(counted)],
        "simulated_crm": simulated,
        "summary": summary,
        "venn": {"pipeline_only": pipeline_only, "overlap": in_pipeline, "market_only": st["never_seen"]},
        "heatmap": heatmap,
        "top_blind_spots": insights.phrase(facts),
        "never_seen_deals": never_seen_deals,
        "top_missed_leads": top_missed_leads,
    }


def blind_spot_facts(counted: dict, status: dict, comps: dict, top_leads: list[dict]) -> list[dict]:
    """3 facts whenever the data allows, numbers fixed in code. In order of strength:
    region x stage pockets with >= 3 deals and >= 50% unseen (best two), the top missed lead
    (>= 2 deals), remaining pockets, smaller pockets (>= 2 deals), whole regions, whole stages,
    and finally a lead with a single missed deal. Facts repeating the same numbers are skipped."""
    by_cell, by_region, by_stage = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for cid, r in counted.items():
        reg, ns = region_of(comps[cid]["country"]), status[cid] == "never_seen"
        for agg, k in ((by_cell, (reg, r["label"])), (by_region, reg), (by_stage, r["label"])):
            agg[k][0] += 1
            agg[k][1] += ns

    def cell_fact(reg, stg, t, ns):
        adj, sh = REGION_ADJ.get(reg, reg), stage_human(stg)
        return {"title": f"{adj} {sh}", "detail": f"You never saw {ns} of {t} {adj} {sh} rounds your peers did since 2023.",
                "keep": [adj, sh], "verbs": PEER_VERBS, "_sig": (ns, t, adj)}

    def lead_fact(l):
        noun = "deal" if l["deals"] == 1 else "deals"
        return {"title": f"{l['name']} deals", "keep": [l["name"]], "verbs": ["led"], "_sig": ("lead", l["id"]),
                "detail": f"{l['name']} led {l['deals']} peer {noun} that never reached your pipeline."}

    cells = sorted(((reg, stg, t, ns) for (reg, stg), (t, ns) in by_cell.items() if ns),
                   key=lambda x: (-x[3], -x[3] / x[2], x[0], STAGE_RANK.get(x[1], 99)))
    strong = [c for c in cells if c[2] >= 3 and c[3] / c[2] >= 0.5]
    medium = [c for c in cells if c not in strong and c[2] >= 2]
    regions = sorted(((reg, t, ns) for reg, (t, ns) in by_region.items() if ns), key=lambda x: (-x[2], x[0]))
    stages = sorted(((stg, t, ns) for stg, (t, ns) in by_stage.items() if ns), key=lambda x: (-x[2], STAGE_RANK.get(x[0], 99)))

    candidates = [cell_fact(*c) for c in strong[:2]]
    candidates += [lead_fact(l) for l in top_leads[:1] if l["deals"] >= 2]
    candidates += [cell_fact(*c) for c in strong[2:] + medium]
    for reg, t, ns in regions:
        adj = REGION_ADJ.get(reg, reg)
        candidates.append({"title": f"{adj} deals", "keep": [adj], "verbs": PEER_VERBS, "_sig": (ns, t, adj),
                           "detail": f"You never saw {ns} of {t} {adj} rounds your peers did since 2023."})
    for stg, t, ns in stages:
        sh = stage_human(stg)
        candidates.append({"title": f"{sh[:1].upper() + sh[1:]} rounds", "keep": [sh], "verbs": PEER_VERBS, "_sig": (ns, t, sh),
                           "detail": f"You never saw {ns} of {t} {sh} rounds your peers did since 2023."})
    candidates += [lead_fact(l) for l in top_leads[:2] if l["deals"] == 1]

    facts, sigs = [], set()
    for f in candidates:
        if f["_sig"] in sigs:
            continue
        sigs.add(f.pop("_sig"))
        facts.append(f)
        if len(facts) == 3:
            break
    return facts


# ---------------------------------------------------------------- deal detail

DATE_IN_URL = [re.compile(r"/(20\d\d)/(\d\d)/(\d\d)/"), re.compile(r"(20\d\d)-(\d\d)-(\d\d)")]


def _news_date(url: str) -> Optional[str]:
    for rx in DATE_IN_URL:
        m = rx.search(url or "")
        if m:
            return "-".join(m.groups())
    return None


NEWS_TIMEOUT_S = 3.0   # first view waits at most 3 s; the fetch finishes in the background and is cached
_news_pool = ThreadPoolExecutor(2)
_news_inflight: dict[str, Future] = {}


def _title(doc_name: Optional[str], url: str) -> str:
    """Use the document title; when it is only a domain, derive one from the URL slug."""
    if doc_name and " " in doc_name.strip():
        return doc_name.strip()
    slug = [p for p in urlparse(url).path.split("/") if p and not p.isdigit()]
    words = re.sub(r"\.(html?|php)$", "", slug[-1] if slug else "").replace("-", " ").replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else (doc_name or urlparse(url).netloc)


def _news_from(res: Optional[dict]) -> list[dict]:
    news, seen = [], set()
    for item in (res or {}).get("context", []):
        for o in item.get("origins", []):
            doc, src = o.get("document") or {}, o.get("source") or {}
            url = doc.get("url") or src.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            host = urlparse(url).netloc
            news.append({"title": _title(doc.get("name"), url), "date": _news_date(url),
                         "source": host[4:] if host.startswith("www.") else host, "url": url})
    news.sort(key=lambda n: n["date"] or "", reverse=True)
    return news[:5]


def recent_news(cala, name: str, website: Optional[str], wait: float = NEWS_TIMEOUT_S,
                cache_only: bool = False) -> list[dict]:
    """Cala knowledge_search, cached. A slow first fetch keeps running in the background
    (its result is cached for the next request) while this call returns [] after `wait` seconds.
    `cache_only` never calls Cala (used when bundling the demo)."""
    if cala is None:
        return []
    domain = normalize_domain(website)
    q = f"Latest news about the startup {name}" + (f" ({domain})" if domain else "")
    if cache_only:
        return _news_from(cala.knowledge_search(q, cache_only=True))
    fut = _news_inflight.get(q)
    if fut is None or fut.done():
        fut = _news_pool.submit(cala.knowledge_search, q)
        _news_inflight[q] = fut
    try:
        return _news_from(fut.result(timeout=wait))
    except FutureTimeout:
        return []
    except Exception:
        return []


def deal_detail(company_id: str, fund_id: Optional[str], cala=None, news_wait: float = NEWS_TIMEOUT_S,
                news_cache_only: bool = False) -> dict:
    comps = db.companies([company_id])
    if company_id not in comps:
        raise NotFound(f"company {company_id} not found")
    c = comps[company_id]
    funds, ent2fund, known = _fund_names()
    rounds = db.rounds_for_companies([company_id])
    rounds.sort(key=lambda r: (r["date"] or "", r["amount"] or 0), reverse=True)
    lp = _leads_and_participants([r["id"] for r in rounds], funds, ent2fund, known)
    out_rounds = [{"label": r["label"], "amount": _amount(r["amount"]), "currency": r["currency"], "date": r["date"],
                   "lead_investors": lp.get(r["id"], {}).get("leads", []),
                   "participants": lp.get(r["id"], {}).get("participants", []),
                   "sources": r["sources"], "conflated": is_conflated(r)} for r in rounds]

    why = []
    if fund_id and db.get_fund(fund_id):
        prof = _profile(fund_id)
        latest = next((r for r in out_rounds if r["date"] and not r["conflated"]), out_rounds[0] if out_rounds else None)
        if latest:
            for lead in latest["lead_investors"]:
                lead_companies = (prof["_portfolios"].get(lead["id"], set()) if lead["id"] in funds
                                  else db.companies_for_entity(lead["id"]))
                if lead["id"] != fund_id and not (lead_companies & prof["_portfolio"]):
                    why.append({"reason": f"Lead investor {lead['name']} has never co-invested with you"})
                    break
        if c["country"] and c["country"] not in prof["_top_countries"] and len(why) < 2:
            why.append({"reason": f"{c['country']} is outside your top countries "
                                  f"({', '.join(prof['_top_countries'])})"})
        if latest and latest["label"] and latest["label"] not in prof["_thesis_stages"] and len(why) < 2:
            why.append({"reason": f"{stage_human(latest['label'])} is outside your usual stages"})

    return {"id": company_id, "name": display(c["name"], known, company_id), "website": normalize_domain(c["website"]) or c["website"],
            "description": c["description"], "country": c["country"], "founded": c["founded"],
            "rounds": out_rounds, "why_missed": why[:2], "recent_news": recent_news(cala, c["name"], c["website"], wait=news_wait, cache_only=news_cache_only),
            "sources": c["sources"]}
