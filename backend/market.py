"""The market definition, shared by the snowball crawler and the audit (one source of truth).

A company is in the market when
  1. its headquarters is in Europe (EUROPE_COUNTRIES), and
  2. it has a *qualifying round*: closed since PERIOD_FROM (announcement date, else event date),
     with at least one named non-issuer participant (any investor type), at least one Cala
     source, and not flagged as merged/implausible (see audit.is_conflated).
Crawler prefilter (cheap, before any round is fetched): Europe HQ and founded >= FOUNDED_FROM
(or founding year unknown).
"""
from __future__ import annotations

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


def prefilter(country: Optional[str], founded: Optional[str]) -> str:
    """'pass' | 'no_hq' | 'out_of_europe' | 'too_old'."""
    if not country:
        return "no_hq"
    if country not in EUROPE_COUNTRIES:
        return "out_of_europe"
    if founded and str(founded)[:4] < FOUNDED_FROM:
        return "too_old"
    return "pass"


def round_qualifies(rnd: dict, participants: Iterable[dict], is_conflated) -> bool:
    """rnd: a stored round row (date, sources, label, amount, conflated); participants: its rows."""
    if not rnd.get("date") or str(rnd["date"]) < PERIOD_FROM:
        return False
    if not rnd.get("sources"):
        return False
    if is_conflated(rnd):
        return False
    return any(p.get("role") != "ISSUER" for p in participants)
