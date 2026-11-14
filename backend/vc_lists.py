"""Hand-editable VC allowlist / blocklist (see vc.py for the rule and data/vc_check.md for the review list).

Keys are normalized names (lower case, legal suffix removed: matching.normalize_name). Values are categories:
  VC (counts):     "vc", "state_vc", "cvc", "growth_pe"
  not VC:          "angel", "grant_public", "corporate", "bank_insurer_pension_am", "accelerator",
                   "university_research", "family_office_holding_syndicate"
An entry here always wins over the name patterns.
"""

ALLOW = {
    # independent VCs whose names carry no VC keyword
    "accel": "vc", "atomico": "vc", "creandum": "vc", "northzone": "vc", "index ventures": "vc", "lakestar": "vc",
    "balderton capital": "vc", "localglobe": "vc", "seedcamp": "vc", "b2venture": "vc", "headline": "vc",
    "headline services us": "vc", "ventech": "vc", "sequoia capital": "vc", "andreessen horowitz": "vc",
    "general catalyst": "vc", "kima ventures": "vc", "bond": "vc", "cyberstarts": "vc", "fj labs": "vc",
    "golden egg check capital": "vc", "world innovation lab wil": "vc", "world innovation lab": "vc",
    "highland europe": "vc", "redalpine venture partners": "vc", "sofinnova partners": "vc", "molten ventures": "vc",
    "plural platform": "vc", "plural": "vc", "visionaries club": "vc", "picus capital": "vc", "468 capital": "vc",
    "firstminute capital": "vc", "frontline ventures": "vc", "j12 ventures": "vc", "maki vc": "vc",
    "icebreaker vc": "vc", "byfounders": "vc", "byfounders collective": "vc", "wave ventures": "vc", "gg1": "vc",
    "blockwall management": "vc", "tiny vc": "vc", "lifeline ventures": "vc", "lifeline ventures ab": "vc",
    "idekapital": "vc", "innovestor": "vc", "10x founders": "vc", "new enterprise associates": "vc", "nea": "vc",
    "42cap": "vc", "benchmark": "vc", "curiosity cap": "vc", "founderful": "vc", "innovation endeavors": "vc",
    "ivp": "vc", "lumo labs": "vc", "redalpine": "vc", "samsara biocapital": "vc", "singular": "vc", "xange": "vc",
    "isai": "vc", "illuminate financial management": "vc", "operator collective": "vc", "pi labs manager": "vc",
    "20vc": "vc", "83north": "vc", "8vc": "vc", "a16z speedrun": "vc", "atlantic labs 1": "vc", "boxgroup": "vc",
    "crv": "vc", "daphni": "vc", "compound": "vc", "squareone": "vc", "visionaries tomorrow": "vc",
    "corundum open innovation": "vc", "anthemis group": "vc", "xdeck management": "vc",
    "capitalg": "cvc", "nventures": "cvc",
    # state / regional VC
    "high tech grunderfonds": "state_vc", "htgf": "state_vc", "tesi": "state_vc", "tesi s p a": "state_vc",
    "bayern kapital": "state_vc", "bayern kapit": "state_vc", "aws grunderfonds": "state_vc", "bgf": "state_vc",
    "business growth fund": "state_vc", "deeptech and climate fund": "state_vc", "investinor": "state_vc",
    "industrifonden": "state_vc", "stiftelsen industrifonden": "state_vc", "seed capital denmark": "state_vc",
    # growth / PE investors
    "insight partners": "growth_pe", "dst global": "growth_pe", "lightrock": "growth_pe",
    "general atlantic": "growth_pe", "tiger global management": "growth_pe", "tiger global": "growth_pe",
    "coatue management": "growth_pe", "coatue": "growth_pe", "softbank vision fund": "growth_pe",
    "smash capital advisors": "growth_pe", "summit partners": "growth_pe", "vitruvian partners": "growth_pe",
    "eqt": "growth_pe", "eqt ventures": "vc",
}

BLOCK = {
    # grant and public bodies
    "european innovation council": "grant_public", "european innovation council fund": "grant_public",
    "eic fund": "grant_public", "european commission": "grant_public", "business finland": "grant_public",
    "sprind": "grant_public", "bpifrance": "grant_public", "british business bank": "grant_public",
    "european space agency esa": "grant_public", "european space agency": "grant_public",
    "bioinnovation institute": "university_research",
    # corporates investing directly, holdings
    "eli lilly and company": "corporate", "tencent holdings": "corporate", "deutsche telekom": "corporate",
    "news corp": "corporate", "prosus": "corporate", "sofina": "family_office_holding_syndicate",
    # accelerators (Antler and Entrepreneur First are company builders / accelerators)
    "antler": "accelerator", "entrepreneur first": "accelerator", "y combinator": "accelerator",
    "techstars": "accelerator", "plug and play": "accelerator", "entrepreneurs first": "accelerator",
    "eit food": "grant_public", "eit": "grant_public",
    # syndicates
    "central trust syndicate number one": "family_office_holding_syndicate",
}
