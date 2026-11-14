"""Live Cala check for every audit (docs/api-contract.md, audit.live_check).

During POST /api/audit and GET /api/audit/demo the funding rounds of every never_seen company are re-fetched from
Cala (entity_retrieval, PARTICIPATES_IN_FUNDING_ROUND, no crawl cache), at most 6 in parallel, overall budget 3 s (3 s per HTTP request).
A new qualifying round with a thesis stage that is newer than the row's round replaces it. Companies are never added
or dropped; a failed call keeps the stored row. Each company's result is cached in memory for 10 minutes.
The audit never fails because of Cala: any error ends in status "partial" or "offline". After a refusal
(401/402/403) or an offline result (e.g. every call timed out), no calls are made for 60 s.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Callable, Optional

import market
from cala_client import Cala, PaymentRequired, sources_of, val

BUDGET_S = 3.0
WORKERS = 6
TTL_S = 600
HTTP_TIMEOUT_S = 3.0
MIN_INTERVAL_S = 0.05                 # own throttle (the crawler's client is not shared)
PAUSE_S = 60                          # after 401/402/403 or an offline result: no calls for a minute
ROUND_FIELDS = ["round_label", "transaction_value", "transaction_value_units", "announcement_date", "event_date"]
ROUND_FIELDS_V1 = ["round_label", "transaction_value", "transaction_value_units", "announcement_date"]
COMPANY_FIELDS = ["total_funding", "total_funding_units"]

_cache: dict[str, tuple[float, list[dict]]] = {}     # company id -> (checked at, its rounds as Cala lists them now)
_lock = threading.Lock()
_client: Optional[Cala] = None
_paused_until = 0.0


def client() -> Cala:
    global _client
    with _lock:
        if _client is None:
            _client = Cala(max_attempts=1, http_timeout=HTTP_TIMEOUT_S, min_interval=MIN_INTERVAL_S)
        return _client


def reset() -> None:
    """Tests: forget cached results and the pause."""
    global _paused_until, _client
    with _lock:
        _cache.clear()
        _paused_until = 0.0
        _client = None


def paused() -> bool:
    """True while Cala refused or was unreachable within the last PAUSE_S seconds (also used by deal news)."""
    return time.time() < _paused_until


def _pause() -> None:
    global _paused_until
    with _lock:
        _paused_until = time.time() + PAUSE_S


def _round_record(rnd: dict, company: dict) -> dict:
    from crawler import conflation
    label, amount, cur = val(rnd, "round_label"), val(rnd, "transaction_value"), val(rnd, "transaction_value_units")
    ann, ev = val(rnd, "announcement_date"), val(rnd, "event_date")
    parts = [{"entity_id": p["id"], "name": p.get("name"), "entity_type": p.get("entity_type"),
              "role": (p.get("properties") or {}).get("role"), "is_lead": (p.get("properties") or {}).get("is_lead")}
             for p in rnd["_rels"].get("incoming:PARTICIPATES_IN_FUNDING_ROUND", [])]
    reason = conflation(label, amount, val(company, "total_funding"),
                        cur is not None and cur == val(company, "total_funding_units"))
    return {"id": rnd["id"], "label": label, "amount": amount, "currency": cur,
            "date": str(ann or ev)[:10] if (ann or ev) else None, "date_kind": "announcement" if ann else "event",
            "conflated": int(bool(reason)), "sources": sources_of(rnd, ["transaction_value", "round_label",
                                                                       "announcement_date"]),
            "participants": parts}


def fetch_company(cala: Cala, company_id: str, known_round_ids: set) -> list[dict]:
    """The company's rounds that are not in the stored data, fresh from Cala. Raises on failure."""
    c = cala.retrieve(company_id, COMPANY_FIELDS, out=["PARTICIPATES_IN_FUNDING_ROUND"], cache=False)
    if not c.get("_ok"):
        raise RuntimeError("company retrieval failed")
    new = []
    for it in c["_rels"].get("outgoing:PARTICIPATES_IN_FUNDING_ROUND", []):
        if (it.get("properties") or {}).get("role") not in ("ISSUER", None) or it["id"] in known_round_ids:
            continue
        r = cala.retrieve(it["id"], ROUND_FIELDS, inc=["PARTICIPATES_IN_FUNDING_ROUND"], cache=False)
        if not r.get("_ok"):
            r = cala.retrieve(it["id"], ROUND_FIELDS_V1, inc=["PARTICIPATES_IN_FUNDING_ROUND"], cache=False)
        if not r.get("_ok"):
            raise RuntimeError(f"round {it['id']} retrieval failed")
        new.append(_round_record(r, c))
    return new


def check(company_ids: list[str], known_round_ids: dict, budget: Optional[float] = None) -> tuple[dict, dict]:
    """({company id -> new rounds} for the companies checked, live_check without `updated`)."""
    budget = BUDGET_S if budget is None else budget
    started = time.time()
    now = started
    results: dict[str, list[dict]] = {}
    checked_at: dict[str, float] = {}
    todo = []
    with _lock:
        for cid in company_ids:
            hit = _cache.get(cid)
            if hit and now - hit[0] < TTL_S:
                checked_at[cid], results[cid] = hit
            else:
                todo.append(cid)
    cala = client()
    refused = threading.Event()
    if todo and (not cala.has_key or paused()):
        refused.set()

    def one(cid: str) -> None:
        if refused.is_set() or time.time() - started > budget:
            return
        try:
            rounds = fetch_company(cala, cid, known_round_ids.get(cid, set()))
        except PaymentRequired:
            refused.set()
            _pause()
            return
        except Exception:
            return
        t = time.time()
        with _lock:
            _cache[cid] = (t, rounds)       # also when it lands after the budget: the next load uses it
        checked_at[cid], results[cid] = t, rounds

    if todo and not refused.is_set():
        pool = ThreadPoolExecutor(WORKERS)
        futures = [pool.submit(one, cid) for cid in todo]
        wait(futures, timeout=max(0.0, budget - (time.time() - started)))
        pool.shutdown(wait=False, cancel_futures=True)
    done = {cid: results[cid] for cid in company_ids if cid in results}     # snapshot: late threads may still write
    n = len(done)
    status = "ok" if n == len(company_ids) else ("offline" if n == 0 else "partial")
    if status == "offline" and todo and cala.has_key and not paused():
        _pause()                    # unreachable or timing out: treat like a refusal, skip checks for a minute
    oldest = min((checked_at[c] for c in done), default=time.time())
    return done, {"companies": n, "updated": 0, "updated_company_ids": [], "seconds": round(time.time() - started, 2),
                  "checked_at": datetime.fromtimestamp(oldest, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "status": status}


def apply(result: dict, known_round_ids: dict, rule, investors: Callable[[list[dict]], list[dict]],
          budget: Optional[float] = None) -> dict:
    """Run the live check for an audit result (v2 dict) and merge it in place. Never raises."""
    import audit
    never = result.get("never_seen") or []
    try:
        fresh, live = check([d["company_id"] for d in never], known_round_ids, budget)
    except Exception:          # the audit must never fail because of Cala
        result["live_check"] = {"companies": 0, "updated": 0, "updated_company_ids": [], "seconds": 0.0,
                                "status": "offline",
                                "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        return result
    stages = set((result.get("thesis") or {}).get("stages") or [])
    moved = []                 # (country, old label, new label) for the breakdown
    for d in never:
        new = [r for r in fresh.get(d["company_id"], [])
               if market.round_qualifies(r, r["participants"], audit.is_conflated, rule.is_vc)]
        if not new:
            continue
        live["updated"] += 1
        live["updated_company_ids"].append(d["company_id"])
        cur = d["round"]
        best = max((r for r in new if r["label"] in stages),
                   key=lambda r: (r["date"], r["amount"] or 0, r["id"]), default=None)
        if best is None or (cur.get("date") and best["date"] <= cur["date"]):
            continue
        moved.append((d["country"], cur["label"], best["label"]))
        d["round"] = {"id": best["id"], "label": best["label"], "amount": audit._amount(best["amount"]),
                      "currency": best["currency"], "date": best["date"], "date_kind": best["date_kind"],
                      "investors": investors(best["participants"]), "sources": audit.rank_sources(best["sources"])}
    if moved:
        audit.sort_never_seen(never)
        fund_id = (result.get("fund") or {}).get("id")
        result["top_investors_in_blind_spots"] = audit.top_investors_of(never, fund_id)
        result["patterns"] = audit.patterns(never, result["top_investors_in_blind_spots"],
                                            (result.get("summary") or {}).get("never_seen", len(never)))
        cells = {(b["country"], b["stage"]): b for b in result.get("breakdown") or []}
        for country, old, new_label in moved:
            if old != new_label and (country, old) in cells and (country, new_label) in cells:
                for key, step in (((country, old), -1), ((country, new_label), 1)):
                    cells[key]["market"] += step
                    cells[key]["never_seen"] += step
    result["live_check"] = live
    return result
