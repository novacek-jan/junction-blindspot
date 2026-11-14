"""Who counts as a VC (Blindspot is a tool for VC funds, so "investor" means a VC firm).

Cala has no investor-type field, so this is our rule, applied to round participants:
  1. role must be INVESTOR (Cala's GRANTOR and LENDER participants never count);
  2. vc_lists.ALLOW / vc_lists.BLOCK (hand-edited, by normalized name) win;
  3. a crawled fund (funds.py) is a VC;
  4. entity_type Person -> angel (not a VC);
  5. NOT-VC name patterns: grant/public bodies, banks/insurers/pension funds/asset managers, accelerators,
     universities/research institutes, family offices/holdings/syndicates/angel networks;
  6. VC name patterns: state/regional VC, growth/PE, corporate VC arms (a corporate name + ventures/capital),
     then generic VC words (ventures, venture capital, capital, partners, fund, kapital, invest, .vc, ...);
  7. a name that looks like a person's (2-3 capitalised words, no organisation words) -> angel;
  8. anything else (corporates investing directly, unknown names) is "other": NOT a VC.
VC categories: vc, state_vc, cvc, growth_pe. Review list: data/vc_check.md (backend/vc_report.py).
"""
from __future__ import annotations

import re
from typing import Optional

from matching import normalize_name
from vc_lists import ALLOW, BLOCK

VC_CATEGORIES = {"vc", "state_vc", "cvc", "growth_pe"}

NOT_VC_PATTERNS = [
    ("grant_public", r"minist|bundesministerium|\bcouncil\b|commission|\bagency\b|agentur|\bagence\b|"
                     r"business finland|vinnova|innovation norway|innovasjon|innovationsfonden|innovation fund denmark|"
                     r"\bsprind\b|british business bank|\beib\b|european investment (bank|fund)|\bkfw\b|"
                     r"government|regierung|\bcity of\b|\bstate of\b|space agency|\besa\b|horizon europe|"
                     r"forschungszentrum|\beu\b|european union"),
    ("bank_insurer_pension_am", r"\bbank\b|banque|bancorp|sparkasse|\binsurance\b|assurance|versicherung|"
                                r"\bpension|pensjon|mutual\b|asset management|investment management|blackrock|"
                                r"schroders|\bhsbc\b|nordea|danske|\bubs\b|credit suisse|j p morgan|jpmorgan|"
                                r"goldman sachs|morgan stanley|vanguard|fidelity management|allianz|\baviva\b|"
                                r"investitionsbank|forderbank|\bkommunalbank"),
    ("accelerator", r"y combinator|techstars|plug and play|entrepreneur first|accelerat|incubat|startup wise guys|"
                    r"\bantler\b"),
    ("university_research", r"universit|\bcollege\b|institut|fraunhofer|max planck|helmholtz|\bimec\b|\bvtt\b|"
                            r"\bresearch\b|hochschule|\bschool\b"),
    ("family_office_holding_syndicate", r"family office|familien|\bholdings?\b|syndicate|angel|\bclub\b|"
                                        r"business angels|\bfoundation\b|stiftung"),
]
STATE_VC = (r"high tech grunderfonds|\bhtgf\b|\btesi\b|bayern kapit|aws grunderfonds|\bbgf\b|business growth fund|"
            r"deeptech (and )?climate fund|investinor|industrifonden|seed capital denmark|\bifu\b|\bebrd\b|"
            r"saxony|sachsen|ilb|nrw bank|bpifrance investissement|finnvera|\bvaekstfonden|eifo")
GROWTH_PE = (r"insight partners|dst global|lightrock|general atlantic|tiger global|coatue|softbank|summit partners|"
             r"vitruvian|kkr|blackstone growth|warburg pincus|permira|\beqt\b|tcv|iconiq|thrive capital|"
             r"bregal|hg capital|keensight")
CORPORATES = (r"\b(bmw|salesforce|sanofi|hubspot|databricks|dell|eviny|intel|google|siemens|bosch|samsung|nvidia|"
              r"microsoft|sap|porsche|merck|novartis|roche|bayer|basf|airbus|axa|volvo|ericsson|nokia|telia|"
              r"orange|vodafone|shell|bp|equinor|statkraft|fortum|wartsila|kone|abb|maersk|novo|lego|ikea|"
              r"schneider|continental|daimler|mercedes|volkswagen|audi|lufthansa|allianz x|zalando|"
              r"amazon|nike|unilever|nestle|bertelsmann|axel springer|prosiebensat|tengelmann|otto)\b")
VC_WORDS = (r"\bventures?\b|venture partners|venture capital|\bcapital\b|\bvc\b|\bpartners\b|\bfund\b|\bfonds\b|"
            r"\bkapital\b|kapitaal|\binvest|\bequity\b|\bseed\b|\bgrowth\b|\binvestments?\b|\bsicar\b|\bgp\b")


def _norm(name: Optional[str]) -> str:
    return normalize_name(name or "").replace(" and ", " and ")


def classify(name: Optional[str], entity_type: Optional[str] = None, role: Optional[str] = "INVESTOR",
             entity_id: Optional[str] = None, crawled_fund_entities: frozenset = frozenset()) -> tuple[str, bool]:
    """(category, is_vc) for one round participant / investor."""
    if role and role != "INVESTOR":
        return ("grant_public" if role == "GRANTOR" else "lender" if role == "LENDER" else "other", False)
    n = _norm(name)
    if n in ALLOW:
        return ALLOW[n], ALLOW[n] in VC_CATEGORIES
    if n in BLOCK:
        return BLOCK[n], BLOCK[n] in VC_CATEGORIES
    if entity_id and entity_id in crawled_fund_entities:
        return "vc", True
    if entity_type == "Person":
        return "angel", False
    for cat, pat in NOT_VC_PATTERNS:
        if re.search(pat, n):
            return cat, False
    if re.search(STATE_VC, n):
        return "state_vc", True
    if re.search(GROWTH_PE, n):
        return "growth_pe", True
    if re.search(CORPORATES, n) and re.search(r"\bventures?\b|\bcapital\b|\bvc\b|\bfund\b|investments?", n):
        return "cvc", True
    if re.search(CORPORATES, n):
        return "corporate", False
    if re.search(VC_WORDS, n):
        return "vc", True
    if looks_like_person(name):
        return "angel", False      # an individual Cala typed as an organisation (e.g. Elad Gil, Nat Friedman)
    return "other", False


ORG_WORDS = re.compile(r"\b(ab|oy|as|aps|gmbh|ag|ltd|llc|inc|sa|bv|nv|group|labs?|capital|ventures?|fund|partners|"
                       r"holding|invest|global|collective|club|network|studio|systems|technologies|bank|the|of|and|"
                       r"for|vc|tech|ai|energy|health|bio|media|digital|foundation|institute|university)\b", re.I)


def looks_like_person(name: Optional[str]) -> bool:
    """Two or three capitalised words without organisation words: 'Cal Henderson', 'Ilkka Paananen'.
    Only used as the last step for names nothing else matched (both outcomes are 'not a VC')."""
    tokens = (name or "").replace("-", " ").split()
    if not 2 <= len(tokens) <= 3 or ORG_WORDS.search(name or ""):
        return False
    return all(t[:1].isupper() and t[1:].islower() and t.isalpha() for t in tokens)


class VCRule:
    """Classifier bound to the crawled funds' entity ids (from the DB), with a per-id cache."""

    def __init__(self, crawled_fund_entities):
        self.crawled = frozenset(crawled_fund_entities)
        self._cache: dict = {}

    def participant(self, p: dict) -> tuple[str, bool]:
        key = (p.get("entity_id"), p.get("role"))
        if key not in self._cache:
            self._cache[key] = classify(p.get("name"), p.get("entity_type"), p.get("role"), p.get("entity_id"),
                                        self.crawled)
        return self._cache[key]

    def is_vc(self, p: dict) -> bool:
        return self.participant(p)[1]
