"""Display names: show brands instead of upper-case legal names.

Cala names many entities by their registry name ("FIRSTMINUTE CAPITAL LLP", "SLACK TECHNOLOGIES, INC.").
Its `aliases` usually contain the brand ("Firstminute Capital", "Slack Technologies"), but also old
names ("BRENT CAPITAL LLP", "Tiny Speck"). The brand is the mixed-case alias that normalizes to the
same name as the legal name (legal suffix removed). Without one, the legal name is title-cased.
Mixed-case names are already brand-like and are left alone.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from matching import LEGAL_SUFFIXES, normalize_name

ACRONYMS = {"AI", "VC", "UK", "US", "USA", "EU", "IT", "HR", "AR", "VR", "XR", "ML", "IO", "IOT", "API", "SAAS",
            "B2B", "B2C", "3D", "TV", "CEO", "GP", "LP", "NYC", "SF", "BCG", "IBM", "SAP", "AWS"}
SHORT_WORDS = {"THE", "AND", "OF", "FOR", "TO", "IN", "ON", "AT", "BY", "DE", "LA", "LE", "DU", "DER", "DIE",
               "DAS", "VON", "UND", "ET", "Y", "A", "AN", "MY", "OUR", "NEW", "BIG", "ONE", "TWO", "BIO", "LAB"}
_TRAILING = re.compile(r"[\s,.;:&-]+$")


def is_shouting(name: Optional[str]) -> bool:
    """True for names written entirely in upper case (registry style)."""
    return bool(name) and any(ch.isalpha() for ch in name) and name == name.upper()


def strip_legal_suffix(name: str) -> str:
    """'SLACK TECHNOLOGIES, INC.' -> 'SLACK TECHNOLOGIES'; keeps the original casing."""
    tokens = name.split()
    while tokens:
        bare = re.sub(r"[^a-z/]", "", tokens[-1].lower())
        if bare in LEGAL_SUFFIXES or tokens[-1] in ("&", "-", ","):
            tokens.pop()
        else:
            break
    out = _TRAILING.sub("", " ".join(tokens))
    return re.sub(r"\(.*?\)\s*$", "", out).strip() or name


def title_case(name: str) -> str:
    def word(w: str) -> str:
        core = re.sub(r"[^A-Za-z0-9]", "", w)
        if not core or any(ch.isdigit() for ch in core) or core.upper() in ACRONYMS:
            return w
        if len(core) <= 3 and core.isalpha() and core.upper() not in SHORT_WORDS:
            return w                                   # NEA, HV, BNP: short all-caps tokens are acronyms
        return "-".join(part[:1].upper() + part[1:].lower() for part in w.split("-"))
    return " ".join(word(w) for w in name.split())


def brand_name(name: Optional[str], aliases: Iterable[str] = ()) -> Optional[str]:
    if not name or not is_shouting(name):
        return name
    base = normalize_name(name)
    candidates = [a for a in aliases if a and not is_shouting(a) and normalize_name(a) == base]
    if candidates:
        # Prefer an alias without a legal suffix, then the shortest.
        candidates.sort(key=lambda a: (strip_legal_suffix(a) != a, len(a), a))
        return strip_legal_suffix(candidates[0])
    return title_case(strip_legal_suffix(name))


def display(name: Optional[str], known: Optional[dict] = None, entity_id: Optional[str] = None) -> Optional[str]:
    """Brand from the stored alias lookup when available, else the rule-based fallback."""
    if known and entity_id and entity_id in known:
        return known[entity_id]
    return brand_name(name)
