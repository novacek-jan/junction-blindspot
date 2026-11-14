"""Match CRM rows to Cala companies by website domain or normalized name."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional

LEGAL_SUFFIXES = {
    "gmbh", "mbh", "ag", "se", "kg", "ug", "co", "ltd", "limited", "inc", "incorporated", "llc", "llp", "lp", "plc",
    "corp", "corporation", "sa", "sas", "sasu", "sarl", "srl", "spa", "bv", "nv", "oy", "oyj", "ab", "as", "asa",
    "aps", "a/s", "oü", "ou", "uab", "sro", "s.r.o", "kft", "zrt", "doo", "sp", "zoo", "haftungsbeschrankt",
    "and",  # left over from "& Co. KG"
}
STATUS_PRIORITY = {"invested": 3, "in_review": 2, "passed": 1}


def normalize_domain(url: Optional[str]) -> str:
    """'https://www.Vayu-Robotics.se/about?x=1' -> 'vayu-robotics.se'."""
    if not url:
        return ""
    s = url.strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
    s = s.split("@")[-1]
    if s.startswith("www."):
        s = s[4:]
    s = s.strip(".")
    return s if "." in s else ""


def normalize_name(name: Optional[str]) -> str:
    """'Vayu Robotics GmbH' -> 'vayu robotics'; strips accents, punctuation and legal suffixes."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    tokens = s.split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


class CompanyIndex:
    """Lookup of company ids by normalized domain and name."""

    def __init__(self, companies: Iterable[dict]):
        self.by_domain: dict[str, set[str]] = {}
        self.by_name: dict[str, set[str]] = {}
        for c in companies:
            d = normalize_domain(c.get("website"))
            n = normalize_name(c.get("name"))
            if d:
                self.by_domain.setdefault(d, set()).add(c["id"])
            if n:
                self.by_name.setdefault(n, set()).add(c["id"])

    def match(self, name: Optional[str], website: Optional[str]) -> set[str]:
        d = normalize_domain(website)
        if d and d in self.by_domain:
            return set(self.by_domain[d])
        n = normalize_name(name)
        return set(self.by_name.get(n, set())) if n else set()


def classify(market_ids: Iterable[str], crm_rows: list[dict], index: CompanyIndex,
             known_invested: Iterable[str] = ()) -> tuple[dict[str, str], int]:
    """Status per market company: invested | in_review | passed | never_seen.

    A company matched by several CRM rows takes the strongest status
    (invested > in_review > passed). `known_invested` (the fund's own Cala
    portfolio) counts as invested even when missing from the CRM.
    Returns (status by company id, number of CRM rows matching nothing in the market).
    """
    market = set(market_ids)
    status: dict[str, str] = {cid: "never_seen" for cid in market}
    for cid in set(known_invested) & market:
        status[cid] = "invested"
    pipeline_only = 0
    for row in crm_rows:
        st = (row.get("status") or "").strip().lower()
        if st not in STATUS_PRIORITY:
            st = "in_review"
        hits = index.match(row.get("company"), row.get("website")) & market
        if not hits:
            pipeline_only += 1
            continue
        for cid in hits:
            cur = status[cid]
            if cur == "never_seen" or STATUS_PRIORITY[st] > STATUS_PRIORITY[cur]:
                status[cid] = st
    return status, pipeline_only
