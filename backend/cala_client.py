"""Throttled, cached client for the Cala MCP endpoint (JSON-RPC over HTTP).

Every successful response is cached via db.cache_* so nothing is fetched twice.
Relationship items must be followed by their top-level `id` (entity id), never by
`properties.id` (the edge id, which returns 404).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

import db
from settings import load_env

MCP_URL = "https://api.cala.ai/mcp/"
PAGE = 100
MIN_INTERVAL = 0.25   # seconds between request starts, shared by all threads
MAX_ATTEMPTS = 8


class PaymentRequired(Exception):
    """Cala refused service: HTTP 402 (insufficient balance), 403 (forbidden / blocked) or 401 (bad key).
    Retrying cannot help: callers must stop (the crawler stops cleanly; --resume continues later)."""


class Cala:
    def __init__(self, api_key: Optional[str] = None):
        load_env()
        self._key = api_key or os.environ.get("CALA_API_KEY")
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self._rid = 0
        self.api_calls = self.cache_hits = self.rate_limited = 0
        self.errors: list[str] = []

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    # -- core

    def call(self, tool: str, args: dict, cache: bool = True, cache_only: bool = False) -> Optional[dict]:
        key = tool + ":" + json.dumps(args, sort_keys=True)
        if cache:
            hit = db.cache_get(key)
            if hit is not None:
                with self._lock:
                    self.cache_hits += 1
                return hit
        if cache_only:
            return None
        if not self._key:
            self._err(f"{tool}: CALA_API_KEY missing")
            return None
        result = self._post(tool, args)
        if result is not None and cache:
            db.cache_put(key, tool, result)
        return result

    def _post(self, tool: str, args: dict) -> Optional[dict]:
        with self._lock:
            self._rid += 1
            rid = self._rid
        body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                           "params": {"name": tool, "arguments": args}}).encode()
        headers = {"X-API-KEY": self._key, "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        what = args.get("entity_id") or args.get("name") or args.get("input", "")[:40]
        for attempt in range(MAX_ATTEMPTS):
            self._wait_turn()
            with self._lock:
                self.api_calls += 1
            try:
                req = urllib.request.Request(MCP_URL, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read().decode()
            except urllib.error.HTTPError as e:
                if e.code in (401, 402, 403):
                    reason = {401: "Unauthorized (API key)", 402: "Payment Required (insufficient balance)",
                              403: "Forbidden (access blocked or plan limit)"}[e.code]
                    self._err(f"{tool} {what}: HTTP {e.code} {reason}")
                    raise PaymentRequired(f"Cala returned {e.code} {reason}")
                if e.code in (429, 500, 502, 503, 504):
                    self._backoff(attempt)
                    continue
                self._err(f"{tool} {what}: HTTP {e.code}")
                return None
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                self._backoff(attempt)
                continue
            msg = None
            for line in raw.splitlines():
                if line.startswith("data: "):
                    msg = json.loads(line[6:])
            if msg is None and raw.strip().startswith("{"):
                msg = json.loads(raw)
            if not msg or "error" in msg:
                self._err(f"{tool} {what}: {(msg or {}).get('error', 'empty response')}")
                return None
            res = msg["result"]
            if res.get("isError"):
                text = " ".join(c.get("text", "") for c in res.get("content", []))[:300]
                if "402" in text or "Payment Required" in text or "Insufficient bala" in text:
                    self._err(f"{tool} {what}: HTTP 402 Payment Required")
                    raise PaymentRequired("Cala returned 402 Payment Required (insufficient balance)")
                if ("429" in text or "rate limit" in text.lower()) and attempt < MAX_ATTEMPTS - 1:
                    self._backoff(attempt)
                    continue
                self._err(f"{tool} {what}: {text[:200]}")
                return None
            if res.get("structuredContent") is not None:
                return res["structuredContent"]
            return json.loads(res["content"][0]["text"])
        self._err(f"{tool} {what}: gave up after {MAX_ATTEMPTS} attempts")
        return None

    def _wait_turn(self) -> None:
        with self._lock:
            now = time.time()
            start = max(now, self._next_slot)
            self._next_slot = start + MIN_INTERVAL
        time.sleep(max(0.0, start - now))

    def _backoff(self, attempt: int) -> None:
        """Rate limited: pause *all* threads, growing up to 60 s."""
        delay = min(60.0, 5.0 * 2 ** attempt)
        with self._lock:
            self.rate_limited += 1
            self._next_slot = max(self._next_slot, time.time() + delay)
        time.sleep(delay)

    def _err(self, msg: str) -> None:
        with self._lock:
            self.errors.append(msg)

    # -- helpers

    def search(self, name: str, types: list[str], limit: int = 20) -> list[dict]:
        res = self.call("entity_search", {"name": name, "entity_types": types, "limit": limit})
        return (res or {}).get("entities", [])

    def knowledge_search(self, question: str, cache_only: bool = False) -> Optional[dict]:
        return self.call("knowledge_search", {"input": question}, cache_only=cache_only)

    def retrieve(self, entity_id: str, properties: list[str], out: list[str] = (), inc: list[str] = ()) -> dict:
        """Retrieve properties plus *all* items of the given relationships (paged with limit/offset)."""
        rels = {("outgoing", r): [] for r in out}
        rels.update({("incoming", r): [] for r in inc})
        offset, entity, pending = 0, None, set(rels)
        while True:
            args = {"entity_id": entity_id, "properties": list(properties) if not offset else []}
            args["relationships"] = {
                "outgoing": {r: {"limit": PAGE, "offset": offset} for d, r in pending if d == "outgoing"},
                "incoming": {r: {"limit": PAGE, "offset": offset} for d, r in pending if d == "incoming"},
            }
            res = self.call("entity_retrieval", args)
            if res is None:
                break
            if entity is None:
                entity = res
            full = set()
            for d, r in pending:
                items = ((res.get("relationships") or {}).get(d) or {}).get(r) or []
                rels[(d, r)].extend(items)
                if len(items) >= PAGE:
                    full.add((d, r))
            pending = full
            if not pending:
                break
            offset += PAGE
        ok = entity is not None
        entity = entity or {"id": entity_id, "properties": {}}
        entity["_ok"] = ok
        entity["_rels"] = {f"{d}:{r}": items for (d, r), items in rels.items()}
        return entity


def val(entity: dict, prop: str):
    p = (entity.get("properties") or {}).get(prop)
    return p.get("value") if isinstance(p, dict) else None


def sources_of(entity: dict, props: list[str]) -> list[dict]:
    """Deduplicated contract-shaped sources for the given properties."""
    seen, out = set(), []
    for prop in props:
        p = (entity.get("properties") or {}).get(prop)
        for s in (p or {}).get("sources", []) if isinstance(p, dict) else []:
            doc = s.get("document") or ""
            if isinstance(doc, dict):          # API-sourced records (e.g. GLEIF) give a request object
                doc = doc.get("url") or doc.get("endpoint") or ""
            url = doc if isinstance(doc, str) else ""
            if url and url not in seen:
                seen.add(url)
                out.append({"name": s.get("name") or "", "url": url, "rank": s.get("source_rank"),
                            "date": (str(s.get("date"))[:10] if s.get("date") else None)})
    return out
