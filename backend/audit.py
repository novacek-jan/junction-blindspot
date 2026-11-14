"""Deterministic Blind Spot logic (v2): fund profile and thesis, market, audit and deal detail.

Market = European companies with a qualifying round since 2022 (market.py), cut by the fund's thesis.
Every number returned by the API is computed here from the crawled Cala data; no LLM is involved.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import date
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Optional
from urllib.parse import urlparse

import db
import crm_import
import briefing
import market
import peers as peerscore
from vc import VCRule
from matching import CompanyIndex, classify, normalize_domain
from names import display, investor_display

PROFILE_FROM = market.PERIOD_FROM          # one period everywhere: since 2022-01-01
MARKET_FROM = market.PERIOD_FROM
# Thesis (hard filter): stages with at least this share of the fund's basis rounds, plus every stage in
# between; an early-stage fund therefore never sees Series C.
THESIS_STAGE_SHARE = 0.15
MAX_TOP_INVESTORS = 10
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
    return {"id": fid, "name": funds[fid]} if fid else {"id": entity_id,
                                                         "name": investor_display(name, known, entity_id)}


def _leads_and_participants(round_ids, funds, ent2fund, known=None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rid, parts in db.participants(round_ids).items():
        merged: dict[str, dict] = {}            # one entry per display name (fund vehicles merged)
        for p in parts:
            if p["role"] == "ISSUER":
                continue
            inv = _investor(p["entity_id"], p["name"], funds, ent2fund, known)
            entry = merged.setdefault(inv["name"].casefold(), {"inv": inv, "lead": False})
            entry["lead"] = entry["lead"] or bool(p["is_lead"])
        leads = [e["inv"] for e in merged.values() if e["lead"]]
        others = [e["inv"] for e in merged.values() if not e["lead"]]
        out[rid] = {"leads": leads, "participants": others}
    return out


def _amount(v):
    if v is None:
        return None
    return int(v) if float(v).is_integer() else float(v)


# ---------------------------------------------------------------- funds

MIN_SEARCH_ROUNDS = 3
# Grant bodies and public administrations are not investors to audit (Tesi and similar investment
# companies stay). Rule: a name matching NON_INVESTOR_NAME, or at least GRANT_SHARE_EXCLUDE of the
# organisation's rounds labelled GRANT.
NON_INVESTOR_NAME = re.compile(
    r"(minist|bundesministerium|ministère|department for|innovation council|\beic\b|european commission|"
    r"european union|horizon europe|\bcouncil\b|commission|agency|agentur|\bagence\b|business finland|"
    r"vinnova|innovasjon norge|innovation norway|innovationsfonden|innovation fund denmark|bpifrance|"
    r"government|regierung|\bstate of\b|\bcity of\b|\bregion\b|forschungs|research council)", re.I)
GRANT_SHARE_EXCLUDE = 0.5


SEARCH_TTL_S = 300
_search_cache: dict = {"at": 0.0, "items": None}


def search_funds(q: str) -> list[dict]:
    """Crawled funds plus every investor organisation (not persons) with at least MIN_SEARCH_ROUNDS basis
    rounds (named participant in rounds since 2022 of European companies, conflated rounds excluded).
    Each result carries basis_rounds; profile and audit use the same logic for both kinds.
    The full list is cached for SEARCH_TTL_S seconds; the query only filters it."""
    ql = (q or "").strip().casefold()
    if _search_cache["items"] is None or time.time() - _search_cache["at"] > SEARCH_TTL_S:
        # Precomputed by backend/refresh.py (hourly) when available; computed here otherwise.
        _search_cache["items"], _search_cache["at"] = (db.kv_get("search:all") or _all_investors()), time.time()
    out = list(_search_cache["items"])
    if ql:
        out = [f for f in out if ql in f["name"].casefold()]
    out.sort(key=lambda f: (not f["name"].casefold().startswith(ql) if ql else False, -f["basis_rounds"],
                            f["name"].casefold()))
    return out[:100]


def _all_investors() -> list[dict]:
    """VCs for the fund search. Entities with the same cleaned display name (fund vehicles of one firm) are one
    result; basis_rounds counts distinct rounds across them; the id is the vehicle with most rounds."""
    funds, ent2fund, known = _fund_names()
    rows = db.market_rounds(market.PERIOD_FROM)
    comps = db.companies({r["company_id"] for r in rows})
    parts = db.participants([r["id"] for r in rows])
    rule = vc_rule()
    rounds, grants, per_entity, names, types = defaultdict(set), defaultdict(set), Counter(), {}, {}
    for r in rows:
        c = comps.get(r["company_id"])
        if not c or c["country"] not in market.EUROPE_COUNTRIES or is_conflated(r):
            continue
        for p in {p["entity_id"]: p for p in parts.get(r["id"], [])
                  if p["role"] == "INVESTOR" and rule.is_vc(p)}.values():
            if p["entity_id"] in ent2fund:
                continue                                    # crawled funds are listed below
            name = investor_display(p["name"], known, p["entity_id"])
            key = name.casefold()
            rounds[key].add(r["id"])
            if r["label"] == "GRANT":
                grants[key].add(r["id"])
            per_entity[(key, p["entity_id"])] += 1
            names.setdefault(key, name)
            types.setdefault(key, p.get("entity_type"))
    out = [{"id": fid, "name": name, "basis_rounds": len(_basis_rounds_quick(fid))} for fid, name in funds.items()]
    fund_names = {n.casefold() for n in funds.values()}
    for key, rs in rounds.items():
        n = len(rs)
        if key in fund_names or n < MIN_SEARCH_ROUNDS or (types.get(key) or "") == "Person":
            continue
        if NON_INVESTOR_NAME.search(names[key] or "") or len(grants[key]) / n >= GRANT_SHARE_EXCLUDE:
            continue
        best = max((e for (k, e) in per_entity if k == key), key=lambda e: (per_entity[(key, e)], e))
        out.append({"id": best, "name": names[key], "basis_rounds": n})
    return out


def _basis_rounds_quick(fund_id: str) -> list:
    """Basis rounds of a crawled fund (same rule as the profile)."""
    portfolio = db.fund_portfolio(fund_id)
    comps = db.companies(portfolio)
    return [r for r in _basis_rounds(fund_id, portfolio)
            if comps.get(r["company_id"], {}).get("country") in market.EUROPE_COUNTRIES]


def _fund_or_404(fund_id: str) -> dict:
    """A crawled fund (funds.py) or any investor organisation found in Cala rounds/portfolios."""
    f = db.get_fund(fund_id)
    if f:
        return f
    name = db.investor_name(fund_id)
    if not name:
        raise NotFound(f"fund {fund_id} not found")
    return {"id": fund_id, "name": display(name, db.display_names(), fund_id)}


def _entity_ids(fund_id: str) -> set[str]:
    return set(db.fund_entity_ids(fund_id)) or {fund_id}


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


def _basis_rounds(fund_id: str, portfolio: set) -> list[dict]:
    """The fund's own investments since 2022: rounds where one of its entities is a named participant.
    Portfolio companies whose rounds since 2022 have no participant list in Cala contribute their first
    such round instead. Conflated rounds never count."""
    ents = _entity_ids(fund_id)
    rounds = [r for r in db.rounds_for_companies(portfolio)
              if r["date"] and r["date"] >= PROFILE_FROM and not is_conflated(r)]
    parts = db.participants([r["id"] for r in rounds])
    joined = [r for r in rounds if any(p["entity_id"] in ents and p["role"] != "ISSUER" for p in parts.get(r["id"], []))]
    joined_companies = {r["company_id"] for r in joined}
    no_list: dict[str, dict] = {}
    for r in sorted(rounds, key=lambda r: (r["date"], r["id"])):
        investors = [p for p in parts.get(r["id"], []) if p["role"] != "ISSUER"]
        if r["company_id"] not in joined_companies and not investors and r["company_id"] not in no_list:
            no_list[r["company_id"]] = r
    # Cala sometimes holds the same round twice (two entities, same company, stage and date): count it once.
    out, seen = [], set()
    for r in sorted(joined + list(no_list.values()), key=lambda r: (r["date"], r["id"])):
        key = (r["company_id"], r["label"], r["date"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _profile(fund_id: str) -> dict:
    """Thesis and profile, all over the same period (since 2022) and scope (European HQ)."""
    fund = _fund_or_404(fund_id)
    portfolios = db.all_fund_portfolios()
    if fund_id not in portfolios:            # an investor organisation that is not a crawled fund
        portfolios[fund_id] = db.investor_portfolio(fund_id)
    portfolio = portfolios.get(fund_id, set())
    comps = db.companies(portfolio)
    basis_all = _basis_rounds(fund_id, portfolio)
    basis = [r for r in basis_all if comps.get(r["company_id"], {}).get("country") in market.EUROPE_COUNTRIES]
    out_of_scope = len(basis_all) - len(basis)

    stage_counts = Counter(r["label"] for r in basis if r["label"] in STAGE_RANK)
    total = sum(stage_counts.values())
    stages = [{"label": st, "share": round(n / total, 2)}
              for st, n in sorted(stage_counts.items(), key=lambda kv: (-kv[1], STAGE_RANK[kv[0]]))] if total else []
    countries = Counter(comps[r["company_id"]]["country"] for r in basis)
    industries = Counter(i for r in basis for i in comps[r["company_id"]]["industries"])

    core = [STAGE_RANK[st] for st, n in stage_counts.items() if total and n / total >= THESIS_STAGE_SHARE]
    thesis_stages = EQUITY_STAGES[min(core):max(core) + 1] if core else ["PRE_SEED", "SEED", "SERIES_A"]
    regions = {region_of(c) for c in countries}
    thesis_countries = sorted({c for r in regions for c in REGIONS.get(r, [r])} & market.EUROPE_COUNTRIES)
    # most basis rounds first (ties by code), so the UI can show the fund's top industries
    thesis_industries = [k for k, _ in sorted(industries.items(), key=lambda kv: (-kv[1], kv[0]))]

    sources, seen = [], set()
    for r in sorted(basis, key=lambda r: r["date"], reverse=True):
        for src in r["sources"]:
            if src["url"] not in seen and len(sources) < 10:
                seen.add(src["url"])
                sources.append(src)
    return {
        "fund": fund,
        "period": {"from": PROFILE_FROM, "to": date.today().isoformat()},
        "scope": "Europe",
        "investments_since_2022": len(basis),
        "out_of_scope_deals": out_of_scope,
        "stages": stages,
        "countries": [{"name": k, "count": v} for k, v in sorted(countries.items(), key=lambda kv: (-kv[1], kv[0]))],
        "industries": [{"name": industry_human(k), "count": v}
                       for k, v in sorted(industries.items(), key=lambda kv: (-kv[1], kv[0]))],
        "thesis": {"stages": thesis_stages, "countries": thesis_countries,
                   "industries": [{"code": k, "name": industry_human(k)} for k in thesis_industries]},
        "suggested_peers": [],          # filled by profile() (thesis similarity, see peers.py); context only
        "sources": sources,
        "_portfolio": portfolio,
        "_portfolios": portfolios,
        "_basis": basis,
        "_thesis_stages": set(thesis_stages),
        "_thesis_countries": set(thesis_countries),
        "_thesis_industries": set(thesis_industries),
        "_thesis_industries_ranked": thesis_industries,
        "_top_countries": [k for k, _ in sorted(countries.items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
    }


SOURCE_RANK_ORDER = {"FILING": 0, "PRIMARY": 1, "PRESS": 2, "AGGREGATOR": 3}


def rank_sources(sources: list[dict]) -> list[dict]:
    """Strongest evidence first: FILING, PRIMARY, PRESS, AGGREGATOR, unranked; newest first within a rank."""
    return sorted(sources, key=lambda x: (SOURCE_RANK_ORDER.get(x.get("rank"), 9), "" if not x.get("date") else
                                          "".join(chr(255 - ord(ch)) for ch in x["date"]), x.get("url") or ""))


def vc_rule() -> VCRule:
    return VCRule(db.all_fund_entity_ids())


def in_thesis(company: dict, rnd: dict, prof: dict) -> bool:
    """Hard filter: stage of the round, company country, and industry (no industry in Cala = no exclusion)."""
    if rnd["label"] not in prof["_thesis_stages"]:
        return False
    if company["country"] not in prof["_thesis_countries"]:
        return False
    inds = set(company["industries"] or [])
    return not inds or not prof["_thesis_industries"] or bool(inds & prof["_thesis_industries"])


def market_companies(prof: dict, rule: Optional[VCRule] = None) -> tuple[dict, dict, dict, int]:
    """(company id -> its latest qualifying in-thesis round, companies, participants by round, n_qualifying).
    Deterministic: the latest round by (date, amount, id). rule=None: the VC rule."""
    rule = rule or vc_rule()
    rows = db.market_rounds(market.PERIOD_FROM)
    comps = db.companies({r["company_id"] for r in rows})
    parts = db.participants([r["id"] for r in rows])
    qualifying, chosen = set(), {}
    for r in rows:
        c = comps.get(r["company_id"])
        if not c or market.prefilter(c["country"], c["founded"]) != "pass":
            continue
        if not market.round_qualifies(r, parts.get(r["id"], []), is_conflated, rule.is_vc):
            continue
        qualifying.add(c["id"])
        if not in_thesis(c, r, prof):
            continue
        cur = chosen.get(c["id"])
        key = (r["date"], r["amount"] or 0, r["id"])
        if cur is None or key > (cur["date"], cur["amount"] or 0, cur["id"]):
            chosen[c["id"]] = r
    return chosen, comps, parts, len(qualifying)


# ---------------------------------------------------------------- audit

def parse_crm(text: str) -> tuple[list[dict], bool]:
    """CRM CSV text -> (normalized rows, simulated flag), using the same column detection as uploads.
    Lines starting with '#' are comments; a comment containing 'SIMULATED' marks the file as simulated."""
    table = crm_import.load_table("crm.csv", text.encode("utf-8"))
    rows = crm_import.normalize_rows(table, crm_import.resolve_mapping(table))
    return rows, table["simulated"]


def run_audit(fund_id: str, peer_ids: list[str], crm_text: str, briefing_mode: str = "generate",
              briefing_attempts: int = 1) -> dict:
    """Audit from CRM CSV text (demo builder, tests). peer_ids is ignored in v2."""
    rows, simulated = parse_crm(crm_text)
    return run_audit_rows(fund_id, peer_ids, rows, simulated, crm_text, briefing_mode, briefing_attempts)


def run_audit_rows(fund_id: str, peer_ids: list[str], crm_rows: list[dict], simulated: bool,
                   fingerprint: str, briefing_mode: str = "generate", briefing_attempts: int = 1) -> dict:
    """v2 audit (the frontend reads only v2; the v1 fields were removed).

    Market = European companies with a qualifying round since 2022 (market.py) inside the fund's thesis.
    Blind spot = market company that is neither in the CRM nor in the fund's own Cala portfolio.
    Status "seen" (no status recorded) counts as in_review. peer_ids is ignored (v2)."""
    prof = _profile(fund_id)
    funds, ent2fund, known = _fund_names()
    rule = vc_rule()
    chosen, comps, parts, n_qualifying = market_companies(prof, rule)

    index = CompanyIndex(comps[c] for c in chosen)
    status, crm_only = classify(chosen, crm_rows, index, known_invested=prof["_portfolio"])
    st = Counter(status.values())
    n_market = len(chosen)
    in_crm = n_market - st["never_seen"]
    summary = {"market_companies": n_market, "in_crm": in_crm, "invested": st["invested"], "passed": st["passed"],
               "in_review": st["in_review"], "never_seen": st["never_seen"],
               "coverage_pct": round(100.0 * in_crm / n_market, 1) if n_market else 0.0}

    def investors_of(rid):
        return investor_entries(parts.get(rid, []), funds, ent2fund, known, rule)

    never = []
    for cid, r in chosen.items():
        if status[cid] != "never_seen":
            continue
        c = comps[cid]
        never.append({
            "company_id": cid, "name": display(c["name"], known, cid),
            "website": normalize_domain(c["website"]) or c["website"], "country": c["country"],
            "industries": [industry_human(i) for i in (c["industries"] or [])],
            "round": {"id": r["id"], "label": r["label"], "amount": _amount(r["amount"]), "currency": r["currency"],
                      "date": r["date"], "date_kind": r.get("date_kind") or "announcement",
                      "investors": investors_of(r["id"]), "sources": rank_sources(r["sources"])},
        })
    sort_never_seen(never)
    never = never[:MAX_NEVER_SEEN]

    top_investors = top_investors_of(never, fund_id)
    n_never = summary["never_seen"]
    noun = "VC-backed company" if n_never == 1 else "VC-backed companies"
    v2 = {
        "audit_id": hashlib.sha1("|".join([fund_id, "v2", fingerprint]).encode()).hexdigest()[:12],
        "fund": prof["fund"],
        "simulated_crm": simulated,
        "period": {"from": market.PERIOD_FROM, "to": date.today().isoformat()},
        "thesis": {"stages": sorted(prof["_thesis_stages"], key=STAGE_RANK.get),
                   "countries": sorted(prof["_thesis_countries"]),
                   "industries": [{"code": k, "name": industry_human(k)} for k in prof["_thesis_industries_ranked"]],
                   "basis_rounds": len(prof["_basis"])},
        "headline": {"never_seen": n_never,
                     "text": f"{n_never} {noun} in your thesis raised since 2022 and never hit your CRM"},
        "summary": summary,
        "never_seen": never,
        "top_investors_in_blind_spots": top_investors,
        "breakdown": breakdown(prof, chosen, comps, status),
        "patterns": patterns(never, top_investors, n_never),
        # The CRM never reaches an AI model: coverage is deterministic; Claude words next_round/sourcing. "none": skip.
        "briefing": (None if briefing_mode == "none" else
                     briefing.build(prof["fund"], prof, never, chosen, comps, status, n_never, rule,
                                    is_conflated, generate=briefing_mode == "generate",
                                    attempts=briefing_attempts)),
        "market_coverage": db.market_coverage(n_qualifying),
    }
    return v2


def investor_entries(parts: list[dict], funds: dict, ent2fund: dict, known: Optional[dict], rule) -> list[dict]:
    """A round's named investors for the audit: one entry per display name (fund vehicles merged), leads first."""
    merged: dict[str, dict] = {}
    for p in parts:
        if p["role"] == "ISSUER":
            continue
        inv = _investor(p["entity_id"], p["name"], funds, ent2fund, known)
        e = merged.setdefault(inv["name"].casefold(), {"id": inv["id"], "name": inv["name"],
                                                      "type": p.get("entity_type"), "is_lead": False,
                                                      "is_vc": False})
        e["is_lead"] = e["is_lead"] or bool(p["is_lead"])
        e["is_vc"] = e["is_vc"] or rule.is_vc(p)
    return sorted(merged.values(), key=lambda i: (not i["is_lead"], i["name"].casefold()))


def sort_never_seen(never: list[dict]) -> None:
    never.sort(key=lambda d: (-(d["round"]["amount"] or 0), d["round"]["date"] or "", d["company_id"]))


def top_investors_of(never: list[dict], fund_id: str) -> list[dict]:
    """VCs in the most never-seen rounds (distinct companies per display name), max 10."""
    inv_companies, inv_ref = defaultdict(set), {}
    for d in never:
        for i in d["round"]["investors"]:
            if i["id"] != fund_id and i["is_vc"]:
                key = i["name"].casefold()
                inv_companies[key].add(d["company_id"])
                inv_ref.setdefault(key, i)
    return [{"id": inv_ref[k]["id"], "name": inv_ref[k]["name"], "companies": len(cs)}
            for k, cs in sorted(inv_companies.items(), key=lambda kv: (-len(kv[1]), kv[0]))][:MAX_TOP_INVESTORS]


def breakdown(prof: dict, chosen: dict, comps: dict, status: dict) -> list[dict]:
    """Every thesis country x thesis stage, with market companies and never-seen companies (zeros included)."""
    cells = Counter()
    for cid, r in chosen.items():
        cells[(comps[cid]["country"], r["label"], "market")] += 1
        cells[(comps[cid]["country"], r["label"], "never")] += status[cid] == "never_seen"
    stages = sorted(prof["_thesis_stages"], key=STAGE_RANK.get)
    return [{"country": c, "stage": st, "market": cells[(c, st, "market")], "never_seen": cells[(c, st, "never")]}
            for c in sorted(prof["_thesis_countries"]) for st in stages]


def patterns(never: list[dict], top_investors: list[dict], total: int) -> list[dict]:
    """Up to 3 deterministic findings (top VC, country, stage), each only when value >= 2. Ties: alphabetical."""
    out = []
    if top_investors and top_investors[0]["companies"] >= 2:
        t = top_investors[0]
        out.append({"kind": "top_vc", "text": f"{t['name']} backed {t['companies']} of the {total}",
                    "value": t["companies"], "total": total})
    for kind, key, fmt in (("country", lambda d: d["country"], "{v} of the {t} are in {k}"),
                           ("stage", lambda d: d["round"]["label"], "{v} of the {t} raised a {k} round")):
        counts = Counter(key(d) for d in never if key(d))
        if counts:
            k, v = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            if v >= 2:
                label = stage_human(k) if kind == "stage" else k
                out.append({"kind": kind, "text": fmt.format(v=v, t=total, k=label), "value": v, "total": total})
    return out[:3]


# ---------------------------------------------------------------- deal detail

DATE_IN_URL = [re.compile(r"/(20\d\d)/(\d\d)/(\d\d)/"), re.compile(r"(20\d\d)-(\d\d)-(\d\d)")]


def _news_date(url: str) -> Optional[str]:
    for rx in DATE_IN_URL:
        m = rx.search(url or "")
        if m:
            return "-".join(m.groups())
    return None


NEWS_TIMEOUT_S = 6.0   # a view waits at most 6 s; the fetch finishes in the background and is cached
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
    parts = db.participants([r["id"] for r in rounds])
    rule = vc_rule()
    out_rounds = [{"id": r["id"], "label": r["label"], "amount": _amount(r["amount"]), "currency": r["currency"],
                   "date": r["date"], "date_kind": r.get("date_kind") or ("announcement" if r["date"] else None),
                   "qualifying": market.round_qualifies(r, parts.get(r["id"], []), is_conflated, rule.is_vc),
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
