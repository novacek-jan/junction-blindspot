"""Peer selection by thesis similarity.

Every fund gets a thesis profile: the share of its deals per geography, stage and sector.
Two funds' similarity per dimension is the overlap of those shares (histogram intersection:
sum of min(share_a, share_b), 0 = nothing in common, 1 = identical mix). The peer score is

    score = 100 * ( W_GEOGRAPHY * geo_overlap + W_STAGE * stage_overlap
                    + W_SECTOR * sector_overlap + W_COINVEST * min(1, co_investments / COINVEST_CAP) )

  geo_overlap  = 0.5 * country overlap + 0.5 * region overlap (DACH, Nordics, UK & Ireland, ...),
                 so Berlin and Vienna funds count as close even when their countries differ.
  deals        = rounds of the fund's portfolio companies announced since THESIS_FROM (2022), excluding
                 conflated rounds. A company in several sectors splits its weight across them.
  fallback     = a fund with fewer than MIN_DEALS deals since THESIS_FROM (2022) uses all its dated deals;
                 if those are still fewer than MIN_DEALS, its portfolio companies (one each) define
                 geography and sector. Funds with no data score at most the co-investment bonus.

Default peers: the PEER_COUNT highest scores at or above MIN_PEER_SCORE (env PEER_COUNT overrides N).
"""
from __future__ import annotations

import os
from collections import Counter

W_GEOGRAPHY = 0.35
W_STAGE = 0.25
W_SECTOR = 0.25
W_COINVEST = 0.15
COINVEST_CAP = 5            # co-investments that earn the full bonus
THESIS_FROM = "2022-01-01"   # same period as the market (market.PERIOD_FROM)
MIN_DEALS = 5
MIN_PEER_SCORE = 25.0       # out of 100
DEFAULT_PEER_COUNT = 10


def peer_count() -> int:
    try:
        return max(1, int(os.environ.get("PEER_COUNT", DEFAULT_PEER_COUNT)))
    except ValueError:
        return DEFAULT_PEER_COUNT


def _share(counter: Counter) -> dict:
    total = sum(counter.values())
    return {k: v / total for k, v in counter.items()} if total else {}


def overlap(a: dict, b: dict) -> float:
    return sum(min(v, b.get(k, 0.0)) for k, v in a.items())


def thesis(portfolio: set, comps: dict, rounds_by_company: dict, region_of, equity_stages: set,
           is_conflated) -> dict:
    """Shares per dimension for one fund, plus how many deals they rest on."""
    def deals(since):
        return [r for cid in portfolio for r in rounds_by_company.get(cid, [])
                if r["date"] and (since is None or r["date"] >= since) and not is_conflated(r)]

    ds, basis = deals(THESIS_FROM), "deals since 2022"
    if len(ds) < MIN_DEALS:
        ds, basis = deals(None), "all dated deals"
    country, region, stage, sector = Counter(), Counter(), Counter(), Counter()
    units = [(r["company_id"], r["label"]) for r in ds]
    if len(ds) < MIN_DEALS:
        units += [(cid, None) for cid in portfolio]
        basis = "portfolio companies"
    for cid, label in units:
        c = comps.get(cid)
        if not c:
            continue
        if c["country"]:
            country[c["country"]] += 1
            region[region_of(c["country"])] += 1
        if label in equity_stages:
            stage[label] += 1
        inds = c["industries"] or []
        for ind in inds:
            sector[ind] += 1 / len(inds)
    return {"country": _share(country), "region": _share(region), "stage": _share(stage),
            "sector": _share(sector), "deals": len(ds), "basis": basis}


def score(a: dict, b: dict, co_investments: int) -> tuple[float, dict]:
    parts = {
        "geography": 0.5 * overlap(a["country"], b["country"]) + 0.5 * overlap(a["region"], b["region"]),
        "stage": overlap(a["stage"], b["stage"]),
        "sector": overlap(a["sector"], b["sector"]),
        "coinvest": min(1.0, co_investments / COINVEST_CAP),
    }
    total = 100 * (W_GEOGRAPHY * parts["geography"] + W_STAGE * parts["stage"]
                   + W_SECTOR * parts["sector"] + W_COINVEST * parts["coinvest"])
    return round(total, 1), parts


def reasons(a: dict, b: dict, parts: dict, co_investments: int, human_stage, human_sector, region_adj) -> list[str]:
    """Up to 3 human-readable reasons, strongest weighted contribution first."""
    def top_shared(dim, fmt):
        common = sorted(((min(v, b[dim].get(k, 0)), k) for k, v in a[dim].items() if b[dim].get(k)),
                        reverse=True)
        if not common:
            return None
        k = common[0][1]
        return f"{fmt(k)}: {a[dim][k]:.0%} of your deals, {b[dim][k]:.0%} of theirs"

    candidates = []
    geo = top_shared("region", lambda r: f"{region_adj(r)} focus")
    if geo:
        candidates.append((W_GEOGRAPHY * parts["geography"], geo))
    stg = top_shared("stage", lambda s: f"{human_stage(s)} rounds")
    if stg:
        candidates.append((W_STAGE * parts["stage"], stg))
    sec = top_shared("sector", human_sector)
    if sec:
        candidates.append((W_SECTOR * parts["sector"], sec))
    if co_investments:
        noun = "company" if co_investments == 1 else "companies"
        candidates.append((W_COINVEST * parts["coinvest"], f"{co_investments} portfolio {noun} in common"))
    candidates.sort(key=lambda x: -x[0])
    return [text[:1].upper() + text[1:] for _, text in candidates[:3]]
