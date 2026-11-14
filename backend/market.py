"""The market definition, shared by the snowball crawler and the audit (one source of truth).

A company is in the market when
  1. its headquarters is in Europe (EUROPE_COUNTRIES), and
  2. it has a *qualifying (VC-backed) round*: closed since PERIOD_FROM (announcement date, else event
     date), not a grant or loan, with at least one VC participant (vc.py), at least one Cala source,
     and not flagged as merged/implausible (see audit.is_conflated).
Crawler prefilter (cheap, before any round is fetched): Europe HQ and founded >= FOUNDED_FROM
(or founding year unknown).
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

PERIOD_FROM = "2022-01-01"
FOUNDED_FROM = "2015"

EUROPE_COUNTRIES = {
    # Nordics, DACH, UK & Ireland, France, Benelux, Southern Europe, CEE, Türkiye (as in audit.REGIONS)
    "Sweden", "Denmark", "Norway", "Finland", "Iceland", "Germany", "Austria", "Switzerland", "Liechtenstein",
    "United Kingdom", "Ireland", "France", "Monaco", "Netherlands", "Belgium", "Luxembourg", "Spain", "Italy",
    "Portugal", "Greece", "Malta", "Cyprus", "Poland", "Czechia", "Slovakia", "Hungary", "Romania", "Bulgaria",
    "Croatia", "Slovenia", "Serbia", "Ukraine", "Estonia", "Latvia", "Lithuania", "Türkiye", "Turkey",
}


# Crawl focus. The snowball crawler only spends budget on companies headquartered in MARKET_REGION; data
# already crawled elsewhere in Europe stays in the DB and still counts for the (Europe-wide) market.
# Expanding later = change the default (or set the MARKET_REGION env var), e.g. to "europe".
REGIONS = {
    "nordics": ["Finland", "Sweden", "Norway", "Denmark", "Iceland"],
    "europe": sorted(EUROPE_COUNTRIES),
}
MARKET_REGION = os.environ.get("MARKET_REGION", "nordics").strip().lower()
REGION_COUNTRIES = set(REGIONS.get(MARKET_REGION, REGIONS["nordics"]))
PRIORITY_COUNTRY = "Finland"     # screened first within the region


def crawl_prefilter(country: Optional[str], founded: Optional[str]) -> str:
    """The crawler's prefilter: 'pass' | 'no_hq' | 'out_of_region' | 'out_of_europe' | 'too_old'."""
    pf = prefilter(country, founded)
    if pf == "pass" and country not in REGION_COUNTRIES:
        return "out_of_region"
    return pf


def prefilter(country: Optional[str], founded: Optional[str]) -> str:
    """'pass' | 'no_hq' | 'out_of_europe' | 'too_old'."""
    if not country:
        return "no_hq"
    if country not in EUROPE_COUNTRIES:
        return "out_of_europe"
    if founded and str(founded)[:4] < FOUNDED_FROM:
        return "too_old"
    return "pass"


NON_EQUITY_LABEL_WORDS = ("GRANT", "DEBT", "LOAN")   # grants and loans never qualify a company


def round_qualifies(rnd: dict, participants: Iterable[dict], is_conflated, is_vc) -> bool:
    """A VC-backed round: rnd is a stored round row (date, sources, label, amount, conflated), participants its
    rows, is_vc the VC rule (vc.VCRule.is_vc). Closed since PERIOD_FROM, not a grant/loan, sourced, plausible,
    and at least one VC participant (angel-only rounds do not qualify)."""
    if not rnd.get("date") or str(rnd["date"]) < PERIOD_FROM:
        return False
    if any(w in (rnd.get("label") or "") for w in NON_EQUITY_LABEL_WORDS):
        return False
    if not rnd.get("sources"):
        return False
    if is_conflated(rnd):
        return False
    return any(p.get("role") != "ISSUER" and is_vc(p) for p in participants)


CONFLATION_THRESHOLDS = {"PRE_SEED": 5e6, "SEED": 10e6, "SERIES_A": 75e6, "SERIES_B": 250e6,
                         "SERIES_C": 600e6, "SERIES_D": 1.5e9, "SERIES_E": 2e9, "SERIES_F": 3e9}  # = audit.MAX_PLAUSIBLE_ROUND


def conflation(label, amount, company_total, same_currency) -> str:
    """Why a stored round looks merged or implausible ("" = fine). Used by the crawler and the live check."""
    reasons = []
    thr = CONFLATION_THRESHOLDS.get(label or "")
    if thr and isinstance(amount, (int, float)) and amount > thr:
        reasons.append(f"{label} above {thr / 1e6:.0f}M")  # noqa
    if isinstance(amount, (int, float)) and isinstance(company_total, (int, float)) and same_currency \
            and amount > company_total * 1.05:
        reasons.append("round larger than company total_funding")
    return "; ".join(reasons)
