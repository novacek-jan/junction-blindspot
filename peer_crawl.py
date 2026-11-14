#!/usr/bin/env python3
"""Peer crawl for Blind Spot Audit.

For a list of peer VC funds, walk the Cala investor graph:
  fund -> INVESTED_IN companies + PARTICIPATES_IN_FUNDING_ROUND rounds (-> ISSUER company)
  company -> name, website, HQ country, funding_stage, total_funding, ISSUER rounds
  round -> round_label, transaction_value (+currency), announcement_date, lead investors (is_lead)

Every API response is cached in SQLite (cala_cache.db), so re-runs never refetch.
Relationship items are followed by their top-level `id` (the entity id), never by
`properties.id` (the edge id, which 404s).

Usage:  python peer_crawl.py            (reads CALA_API_KEY from ./.env)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MCP_URL = "https://api.cala.ai/mcp/"
DB_PATH = ROOT / "cala_cache.db"
SUMMARY_PATH = ROOT / "crawl_summary.md"
PAGE = 100
WORKERS = 4
MIN_INTERVAL = 0.25   # seconds between request starts, shared by all workers
MAX_ATTEMPTS = 8
MIN_DATE = "2024-01-01"

# Fund -> Cala entity ids that belong to it. A fund is split across a brand entity,
# management companies and fund vehicles, and entity_search also returns unrelated
# namesakes (restaurants, Norwegian 'HV CAPITAL AS', 'ATOMICO ELECTRICAL LLP', ...),
# so the ids were checked by hand against the search descriptions.
FUNDS: dict[str, list[str]] = {
    "Earlybird Venture Capital": [
        "7de3d7d6-af8f-4e95-a949-2befc86938a0",  # Earlybird Venture Capital
        "3e6f7bca-a0f3-418f-8d09-48d69ebbd09a",  # Earlybird Venture Capital GmbH & Co. KG
        "a95347dd-65ea-4e8a-80f4-02e478c16584",  # Earlybird Vision Lab GmbH & Co. KG
        "c5d7b929-178f-4bf3-bdc9-29f688bb9f50",  # Earlybird VC Management GmbH & Co. KG
    ],
    "Cherry Ventures": [
        "dd4f5ab1-c3b5-47e8-aeb5-7995976746eb",  # Cherry Ventures Limited
        "c06adc97-e2d8-4590-a329-4462750ee4e6",  # Cherry Ventures
        "fa19b3c0-1187-47dd-a0ba-9bc59319bee5",  # Cherry Ventures UG (haftungsbeschränkt) & Co. KG
        "c1d537b4-a826-4ef5-8264-34f893157b53",  # Cherry Ventures Management GmbH
        "a3e6d2ff-8359-4be4-aca6-c50ec55d06fa",  # CHERRY VENTURES ADVISORS UK LTD
        "899cd68c-5668-4c31-9d85-1b86803b893b",  # Cherry Ventures Select V GmbH & Co. KG
        "f35dfa9a-4d5a-4f28-a5de-b023b1eef629",  # Cherry Ventures Opportunities II GmbH & Co. KG
        "d3fde5ee-3628-439c-94b5-6460d3c02fb6",  # Cherry Ventures Fund II GmbH & Co. KG
        "639f5276-087b-471b-839b-0c3c184654b5",  # Cherry Ventures Opportunities VIII GmbH & Co. KG
        "9dd76956-8278-4073-a6b9-820c7d15941b",  # Cherry Ventures Fund III GmbH & Co. KG
        "5c2a96aa-d4e9-4be1-b0a5-4e51ef2f5778",  # Cherry Ventures Opportunities XI GmbH & Co. KG
        "d6856dfe-838c-48c9-a649-c80a3616cb20",  # Cherry Ventures Opportunities VII GmbH & Co. KG
        "1944891d-efb9-4870-a250-7db5d756d7d6",  # Cherry Ventures Opportunities IX GmbH & Co. KG
        "3935adac-ce6a-477c-8deb-11385329b64f",  # Cherry Ventures Fund V GmbH & Co. KG
        "ab8aaf8a-63d2-4c79-956b-d76febdfbff8",  # Cherry Ventures Fund IV GmbH & Co KG
        "328d7688-a6b1-4572-8910-8098a24459b9",  # Cherry Ventures Opportunities IV GmbH & Co. KG
        "5b11e8a2-c069-4308-a2f8-23fbf27112d7",  # Cherry Ventures Opportunities VI GmbH & Co. KG
        "3247ef39-c014-4ef6-a4b9-882e371d8a33",  # Cherry Ventures Opportunities V GmbH & Co. KG
        "0a1b4076-cebd-4fa1-bccc-6fc06fda5ac1",  # Cherry Ventures Opportunities X GmbH & Co. KG
    ],
    "Project A Ventures": [
        "14114b32-b79d-4dba-8f6f-356113a4c696",  # Project A Ventures
        "7b1b7e16-c539-429d-8af0-883594236fdb",  # Project A Ventures GmbH & Co. KG
        "da41acc4-742b-47b1-86bc-d2f65a8fff31",  # PROJECT A VENTURES  MANAGEMENT UK LIMITED
        "4bfb1267-24fe-461e-9b64-6469a6e59bd3",  # Project A Ventures Management GmbH
        "1780e85e-cf18-4279-a833-12622a3c1b7e",  # Project A Ventures V GmbH & Co. geschlossene Investment KG
        "f800d455-1821-4209-a296-48d4f0b5a747",  # Project A Ventures III GmbH & Co. geschlossene Investment KG
        "0146afa4-5955-4354-bf72-243da42490af",  # Project A Ventures II GmbH und Co. geschlossene Investment KG
        "bd3122dd-bd7b-4561-a47f-21a0c4d3d19c",  # Project A Ventures IV GmbH & Co. geschlossene Investment KG
        "4456c0c0-086b-4a90-9a58-e3d7140a3343",  # Project A Ventures IV Blocker GmbH & Co. geschlossene Investment KG
        "0e96c377-9914-4701-b082-10c178922207",  # Project A Ventures IV Feeder GmbH & Co. geschlossene Investment KG
        "d05cecb9-b3e9-467c-9dbb-4d0beeb991b0",  # Project A Ventures IV Feeder GmbH & Co. geschlossene Investment KG
    ],
    "HV Capital": [
        "8774eb35-b3d0-4d71-8135-a4fe1187a3b6",  # HV Capital
        "1867dfbe-51ab-4e7e-a071-5ef25b8f8329",  # HV Capital Manager GmbH
        "bcbe0d48-b849-4dd9-814c-b31ec7895008",  # HV Capital Fund X Growth GmbH & Co. geschlossene Investment KG
        "0cbd1007-16ea-44a0-b582-c1a208c83703",  # HV Capital Fund 7 COIF GmbH & Co. geschlossene Investment KG
        "3b3ec99f-3906-4f3a-b720-c76551a8a553",  # HV Capital Fund IX Growth GmbH & Co. geschlossene Investment KG
        "915c9d08-4357-4bdd-9c7c-111a502fad1c",  # HV Capital Fund X Ventures GmbH & Co. geschlossene Investment KG
    ],
    "Point Nine": [
        "c934f7e3-6ee3-4983-b0e1-f7827df567f9",  # Point Nine Capital
        "46df2a7c-c4cd-4f6f-82ab-278771599885",  # Point Nine Management GmbH
        "fe1dbe57-8cfc-4ff2-91e5-35bf8d853f4b",  # Point Nine Verwaltungs GmbH
        "edd2367c-8c79-4f7b-9f30-20aaa954ad7b",  # Point Nine Team VII eGbR
        "79ed6f21-723d-4774-8485-aee8e0f1d8cb",  # Point Nine Verwaltungs II GmbH
        "6bb69c1b-45a3-4a9f-8812-eee180a37a96",  # Point Nine Management II GmbH
        "2e8ba5a0-64b0-4378-add0-5c842f223212",  # Point Nine Holding GmbH & Co. KG
    ],
    "Speedinvest": [
        "94e0ca6a-4e39-4181-bd84-11f264d0aa62",  # Speedinvest GmbH
        "3462acb6-9dc2-4d18-b5ab-0f4ba5addedd",  # SPEEDINVEST LIMITED
        "a2b296da-4357-53ab-819a-31900e89abae",  # SPEEDINVEST FRANCE
        "e8d0f18a-56bf-5325-823b-916ac2df6bae",  # Speedinvest Ii International Gmbh
        "8c2e081e-0ec8-5eb4-ad86-32ccdf138080",  # Speedinvest Iv Euveca Gmbh & Co Kg
        "03236055-ee50-46b4-bcb6-895915894180",  # SpeedInvest Africa & Middle East Fund
        "b8e0c2e7-9e4c-48ae-958b-3bf9a950026e",  # Speedinvest Continuation II GmbH & Co KG
        "a1280bb7-9456-4d7b-aeab-fa48c11b2165",  # Speedinvest Continuation I GmbH & Co KG
        "e3c3af32-b8a9-4dce-9e41-cab38e9f3c50",  # Speedinvest F EuVECA GmbH & Co KG
        "418a5138-8250-4f88-a339-22bea29891f2",  # Speedinvest Co-Invest UVG GmbH & Co KG
    ],
    "Creandum": [
        "8daff491-270c-489b-a9ab-a3949f282c49",  # Creandum Kommanditbolag
        "7d4ebd18-3539-4f19-a2e0-93bebb838554",  # Creandum Fund
        "6ba00a20-2cb4-4559-8fe2-f39484a9e5f6",  # Creandum
        "d511355c-2c55-4b91-bf0f-bb444e2db854",  # CREANDUM ADVISOR LLP
        "dced699e-9f7f-465f-8f27-2f2c251a33cc",  # Creandum III, L.P.
        "62a411ef-7d78-42fd-a9d0-2913a6e93381",  # Creandum Advisor AB
        "7b88a753-db0f-44bb-aaaf-13ec11451e48",  # Creandum GovCo AB
        "b5ae192f-6f7e-47cb-afc5-a04ee5cd714d",  # Creandum II L.P.
        "053b55ec-942f-4887-9f77-516ef7899181",  # Creandum V, L.P.
        "84ae9b54-4130-4fa4-8eb7-4e21ddf625ad",  # CREANDUM ADVISOR UK LIMITED
        "c24969af-27c9-4b41-b3be-3d8bff624663",  # Creandum II Kommanditbolag
        "f5fd883c-12f0-494c-94d4-7f687e3defb3",  # Creandum VII (D) AB
        "65ae144a-72c7-4d7c-9ed8-825979b61fbe",  # Creandum Fund Manager AB
        "36123e65-3896-461c-9b41-50059fc02205",  # Creandum VI Holding AB
        "babee61b-6ca2-4df6-b253-721d248f16c4",  # Creandum VI (D) AB
        "7498c01f-0f64-4723-b202-ef6dc3e6bd0e",  # Creandum VII (E) AB
        "623bc52d-6cd2-4920-863f-861c9bbf0d02",  # Creandum VI TopCo AB
        "37212c2d-5c22-4323-8fae-b0ad7066cb61",  # CREANDUM ADVISOR UK II LIMITED
        "5b571f0d-ba6f-4320-8054-e811a6854f32",  # Creandum Select Fund Manager AB
        "bc861019-6feb-438e-9632-3e109adb135f",  # Creandum I Annex Fund AB
    ],
    "Lakestar": [
        "16bdbb1a-6658-4fa2-9b04-0a48011841d2",  # Lakestar
        "20fbfb4a-07ec-498e-bedc-4837db4c66f2",  # Lakestar Advisors GmbH
        "a0362d06-71ba-4f92-b424-13e641dd8ada",  # LAKESTAR RESILIENCE I LP
        "c485e50f-666d-48f3-9078-c8474b08f16f",  # Lakestar Growth II SCSp
        "50d4f3a8-4d56-4a65-91e5-8a61e69d36c0",  # LAKESTAR GROWTH I S.À R.L.
        "5c6a1045-ccb8-4d19-badb-95ee336af794",  # LAKESTAR III LP
        "bf487a7e-9aa6-408b-91a4-4660407691ab",  # LAKESTAR RESILIENCE I (G.P.) LIMITED
        "49f3bca5-fe4c-4dab-bfde-c3e297f22aab",  # LAKESTAR ADVISORS UK LLP
        "680f8684-8616-493a-9c9f-515d0a934913",  # LAKESTAR II LP
        "b4691eb5-4225-427b-b305-31ca96589131",  # LAKESTAR I LP
        "051cd46f-03cb-582c-bde6-c8d856935786",  # Lakestar Scout Fund
        "629b77f3-6b57-48b2-9515-83f91a70e1ce",  # LAKESTAR GROWTH I LP
        "97a6236f-8d9d-46ae-b7d4-24bbb7a4c912",  # LAKESTAR GROWTH II LP
        "5cf0c299-1976-4127-aaef-b5042510d600",  # LAKESTAR EARLY IV LP
    ],
    "La Famiglia": [
        "955ecf27-7599-4bd4-a2ff-f66265cc6108",  # La Famiglia
        "d8f25d35-ccae-461e-ad17-f7bb263cf775",  # La Famiglia Boajé AB
        "11bc8fbe-1913-4a53-8884-d8e65b69cd00",  # La Famiglia GmbH
    ],
    "Atomico": [
        "d4640009-5578-485e-9f77-3ab64881cddd",  # ATOMICO (UK) LIMITED
        "8f929584-4c5e-409e-9140-d820fe57b6df",  # ATOMICO MANAGEMENT, LTD.
        "32e27d54-3922-407f-aa07-2747d94b210c",  # Atomico
        "e4c54019-482d-40ee-acfb-5ce43e713ab2",  # ATOMICO (UK) PARTNERS LLP
        "9389170b-144d-4b10-b01a-813862fcc9bd",  # Atomico V SCSp
        "15dbd1a0-1e58-42d7-8056-02fecf391bdf",  # Atomico IV, L.P.
        "4e2fd6fb-033d-48fa-8a82-9cf8801fc47c",  # Atomico Angel Programme
        "2d6251db-e061-4a00-a0fd-ff6d455b2124",  # Atomico III, L.P.
        "a48b5f27-b899-4268-9c5c-3667e761b9fb",  # Atomico Scouts
        "a0eafb19-263c-58c1-a809-d1366816ccd0",  # ATOMICO (FRANCE) SAS
        "a36f9db0-0fa3-4f71-b212-8d94123a1625",  # ATOMICO IV, L.P.
        "1a5d508e-a5c9-4b3e-a881-f12eefb10a9e",  # ATOMICO 2010 (UK) LIMITED
        "57c3d2ef-4d9d-4124-85cf-bf07fe3e330c",  # ATOMICO V COINVEST LIMITED
        "e2d7627f-42b6-4bc4-9ce1-13c07acaa934",  # ATOMICO VI COINVEST LIMITED
        "2454e348-ed05-4f49-808f-e18af2ff174b",  # Atomico V, L.P.
        "83fc5496-bc67-4fdf-bd8f-93772a92e489",  # Atomico Growth VI SCSp
        "ca65fd64-5856-4586-b3ae-ac5824fb50a8",  # Atomico Venture VI SCSp
        "dc1149b2-e447-46a8-83ed-2ada11f427fb",  # ATOMICO IV (GUERNSEY), L.P.
    ],
}
FUND_ENTITY_TYPES = ["Organization", "Company"]

# Round sizes above these look like several rounds merged into one entity.
CONFLATION_THRESHOLDS = {"PRE_SEED": 5_000_000, "SEED": 10_000_000, "SERIES_A": 75_000_000}


# --------------------------------------------------------------------------- env

def load_api_key() -> str:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    key = os.environ.get("CALA_API_KEY")
    if not key:
        sys.exit("CALA_API_KEY missing: put it in .env (see .env.example)")
    return key


# ------------------------------------------------------------------------- client

class Cala:
    """Minimal MCP-over-HTTP client with a SQLite response cache."""

    def __init__(self, api_key: str, db_path: Path):
        self._key = api_key
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, tool TEXT, response TEXT, fetched_at REAL)")
        self._db.commit()
        self._lock = threading.Lock()
        self.api_calls = 0
        self.cache_hits = 0
        self.errors: list[str] = []
        self._rid = 0
        self._next_slot = 0.0      # global throttle / back-off clock
        self.rate_limited = 0

    def call(self, tool: str, args: dict) -> dict | None:
        key = tool + ":" + json.dumps(args, sort_keys=True)
        with self._lock:
            row = self._db.execute("SELECT response FROM cache WHERE key=?", (key,)).fetchone()
            if row:
                self.cache_hits += 1
                return json.loads(row[0])
            self._rid += 1
            rid = self._rid
        result = self._post(tool, args, rid)
        if result is None:
            return None
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (key, tool, json.dumps(result), time.time()))
            self._db.commit()
        return result

    def _post(self, tool: str, args: dict, rid: int) -> dict | None:
        body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                           "params": {"name": tool, "arguments": args}}).encode()
        headers = {"X-API-KEY": self._key, "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        for attempt in range(MAX_ATTEMPTS):
            self._wait_turn()
            with self._lock:
                self.api_calls += 1
            try:
                req = urllib.request.Request(MCP_URL, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=90) as resp:
                    raw = resp.read().decode()
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    self._backoff(attempt)
                    continue
                self._err(f"{tool} {args.get('entity_id', args.get('name'))}: HTTP {e.code}")
                return None
            except (urllib.error.URLError, TimeoutError) as e:
                self._backoff(attempt)
                continue
            msg = None
            for line in raw.splitlines():
                if line.startswith("data: "):
                    msg = json.loads(line[6:])
            if msg is None and raw.strip().startswith("{"):
                msg = json.loads(raw)
            if not msg or "error" in msg:
                self._err(f"{tool}: {(msg or {}).get('error', 'empty response')}")
                return None
            res = msg["result"]
            if res.get("isError"):
                text = " ".join(c.get("text", "") for c in res.get("content", []))[:200]
                if ("429" in text or "rate limit" in text.lower()) and attempt < MAX_ATTEMPTS - 1:
                    self._backoff(attempt)
                    continue
                self._err(f"{tool} {args.get('entity_id', args.get('name'))}: {text}")
                return None
            if res.get("structuredContent") is not None:
                return res["structuredContent"]
            return json.loads(res["content"][0]["text"])
        self._err(f"{tool} {args.get('entity_id', args.get('name'))}: gave up after retries")
        return None

    def _wait_turn(self) -> None:
        with self._lock:
            now = time.time()
            start = max(now, self._next_slot)
            self._next_slot = start + MIN_INTERVAL
        time.sleep(max(0.0, start - now))

    def _backoff(self, attempt: int) -> None:
        """Rate limited: pause *all* workers, growing up to 60 s."""
        delay = min(60.0, 5.0 * 2 ** attempt)
        with self._lock:
            self.rate_limited += 1
            self._next_slot = max(self._next_slot, time.time() + delay)
        time.sleep(delay)

    def _err(self, msg: str) -> None:
        with self._lock:
            self.errors.append(msg)

    # -- helpers

    def search(self, name: str, types: list[str]) -> list[dict]:
        res = self.call("entity_search", {"name": name, "entity_types": types, "limit": 20})
        return (res or {}).get("entities", [])

    def retrieve(self, entity_id: str, properties: list[str], out: list[str] = (), inc: list[str] = ()) -> dict:
        """Retrieve properties plus *all* items of the given relationships (paged)."""
        base = {"entity_id": entity_id, "properties": list(properties)}
        rels = {("outgoing", r): [] for r in out} | {("incoming", r): [] for r in inc}
        offset, entity, pending = 0, None, set(rels)
        while True:
            args = dict(base)
            if offset:  # properties only needed on the first page
                args["properties"] = []
            args["relationships"] = {
                "outgoing": {r: {"limit": PAGE, "offset": offset} for d, r in pending if d == "outgoing"},
                "incoming": {r: {"limit": PAGE, "offset": offset} for d, r in pending if d == "incoming"},
            }
            res = self.call("entity_retrieval", args)
            if res is None:
                break
            if entity is None:
                entity = res
            got_full = set()
            for d, r in pending:
                items = ((res.get("relationships") or {}).get(d) or {}).get(r) or []
                rels[(d, r)].extend(items)
                if len(items) >= PAGE:
                    got_full.add((d, r))
            pending = got_full
            if not pending:
                break
            offset += PAGE
        entity = entity or {"id": entity_id, "properties": {}}
        entity["_rels"] = {f"{d}:{r}": items for (d, r), items in rels.items()}
        return entity


def val(entity: dict, prop: str):
    p = (entity.get("properties") or {}).get(prop)
    return p.get("value") if isinstance(p, dict) else None


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).strip()


# -------------------------------------------------------------------------- crawl

def main() -> None:
    t0 = time.time()
    cala = Cala(load_api_key(), DB_PATH)
    pool = ThreadPoolExecutor(WORKERS)

    # 1. Funds -> entity ids: entity_search, then keep only the vetted ids
    fund_entities: dict[str, list[dict]] = {}
    for fund, allowed in FUNDS.items():
        hits = cala.search(fund, FUND_ENTITY_TYPES)
        kept = [e for e in hits if e["id"] in allowed]
        missing = set(allowed) - {e["id"] for e in kept}
        kept += [{"id": i, "name": i} for i in sorted(missing)]  # vetted but not in this search page
        fund_entities[fund] = kept
        dropped = [e["name"] for e in hits if e["id"] not in allowed]
        print(f"[fund] {fund}: {len(kept)} entities kept, {len(dropped)} search hits dropped")

    # 2. Fund entities -> portfolio companies and rounds
    flat = [(f, e) for f, es in fund_entities.items() for e in es]
    fund_data = list(pool.map(lambda fe: (fe[0], cala.retrieve(fe[1]["id"], ["name"],
                              out=["INVESTED_IN", "PARTICIPATES_IN_FUNDING_ROUND"])), flat))
    company_funds: dict[str, set[str]] = {}
    fund_round_ids: dict[str, set[str]] = {}
    per_fund_counts: Counter = Counter()
    for fund, ent in fund_data:
        for it in ent["_rels"].get("outgoing:INVESTED_IN", []):
            company_funds.setdefault(it["id"], set()).add(fund)  # top-level id = entity id
        for it in ent["_rels"].get("outgoing:PARTICIPATES_IN_FUNDING_ROUND", []):
            fund_round_ids.setdefault(it["id"], set()).add(fund)
        per_fund_counts[fund + "|invested_in"] += len(ent["_rels"].get("outgoing:INVESTED_IN", []))
        per_fund_counts[fund + "|rounds"] += len(ent["_rels"].get("outgoing:PARTICIPATES_IN_FUNDING_ROUND", []))
    print(f"[graph] {len(company_funds)} companies via INVESTED_IN, {len(fund_round_ids)} rounds via PARTICIPATES_IN_FUNDING_ROUND")

    round_fields = ["round_label", "transaction_value", "transaction_value_units", "announcement_date"]

    def get_round(rid: str) -> dict:
        return cala.retrieve(rid, round_fields, inc=["PARTICIPATES_IN_FUNDING_ROUND"])

    # Rounds the funds joined directly -> add their issuers to the portfolio
    for rid, rnd in zip(fund_round_ids, pool.map(get_round, fund_round_ids)):
        for p in rnd["_rels"].get("incoming:PARTICIPATES_IN_FUNDING_ROUND", []):
            if (p.get("properties") or {}).get("role") == "ISSUER":
                company_funds.setdefault(p["id"], set()).update(fund_round_ids[rid])
    print(f"[graph] {len(company_funds)} unique portfolio entities after adding round issuers")

    # 3. Companies
    company_fields = ["name", "website", "funding_stage", "total_funding", "total_funding_units"]
    cids = list(company_funds)
    companies = dict(zip(cids, pool.map(
        lambda cid: cala.retrieve(cid, company_fields, out=["HAS_HEADQUARTERS_IN", "PARTICIPATES_IN_FUNDING_ROUND"]), cids)))
    print(f"[companies] retrieved {len(companies)}")

    # 4. ISSUER rounds of every company
    company_rounds: dict[str, list[str]] = {}
    for cid, c in companies.items():
        company_rounds[cid] = [it["id"] for it in c["_rels"].get("outgoing:PARTICIPATES_IN_FUNDING_ROUND", [])
                               if (it.get("properties") or {}).get("role") in ("ISSUER", None)]
    all_rids = sorted({r for rs in company_rounds.values() for r in rs})
    rounds = dict(zip(all_rids, pool.map(get_round, all_rids)))
    print(f"[rounds] retrieved {len(rounds)}")

    # 5. Assemble
    def hq_country(c: dict) -> str:
        hqs = c["_rels"].get("outgoing:HAS_HEADQUARTERS_IN", [])
        for h in hqs:
            if h.get("entity_type") == "Country":
                return h["name"]
        return hqs[0]["name"] if hqs else "Unknown"

    comp_rows, round_rows = [], []
    dropped_old = dropped_nodate = 0
    for cid, c in companies.items():
        comp_rows.append({
            "id": cid, "name": val(c, "name") or c.get("name"), "entity_type": c.get("entity_type"),
            "website": val(c, "website"), "hq_country": hq_country(c),
            "funding_stage": val(c, "funding_stage"), "total_funding": val(c, "total_funding"),
            "total_funding_currency": val(c, "total_funding_units"),
            "peer_funds": ", ".join(sorted(company_funds[cid])),
        })
        for rid in company_rounds[cid]:
            r = rounds.get(rid) or {}
            date = val(r, "announcement_date")
            if not date:
                dropped_nodate += 1
                continue
            if str(date) < MIN_DATE:
                dropped_old += 1
                continue
            label, amount = val(r, "round_label"), val(r, "transaction_value")
            parts = r.get("_rels", {}).get("incoming:PARTICIPATES_IN_FUNDING_ROUND", [])
            leads = sorted({p["name"] for p in parts if (p.get("properties") or {}).get("is_lead")})
            flags = []
            thr = CONFLATION_THRESHOLDS.get(label or "")
            if thr and isinstance(amount, (int, float)) and amount > thr:
                flags.append(f"{label} above {thr / 1e6:.0f}M")
            tf = val(c, "total_funding")
            if isinstance(amount, (int, float)) and isinstance(tf, (int, float)) and amount > tf * 1.05 \
                    and val(r, "transaction_value_units") == val(c, "total_funding_units"):
                flags.append("round larger than company total_funding")
            round_rows.append({
                "id": rid, "company_id": cid, "company": comp_rows[-1]["name"], "hq_country": comp_rows[-1]["hq_country"],
                "round_label": label or "UNLABELLED", "transaction_value": amount,
                "currency": val(r, "transaction_value_units"), "announcement_date": date,
                "lead_investors": "; ".join(leads), "conflation_flag": "; ".join(flags),
            })

    # 6. Persist results next to the cache
    db = sqlite3.connect(DB_PATH)
    for table, rows in (("companies", comp_rows), ("rounds", round_rows)):
        db.execute(f"DROP TABLE IF EXISTS {table}")
        if rows:
            cols = list(rows[0])
            db.execute(f"CREATE TABLE {table} ({', '.join(cols)})")
            db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(cols))})",
                           [tuple(r[k] for k in cols) for r in rows])
    db.commit()

    # 7. Summary
    elapsed = time.time() - t0
    cached_total = db.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
    active = {r["company_id"] for r in round_rows}
    by_country = Counter(c["hq_country"] for c in comp_rows)
    by_country_active = Counter(c["hq_country"] for c in comp_rows if c["id"] in active)
    by_label = Counter(r["round_label"] for r in round_rows)
    flagged = [r for r in round_rows if r["conflation_flag"]]
    dup_names = sum(n - 1 for n in Counter(norm(c["name"]) for c in comp_rows).values() if n > 1)

    md = ["# Peer crawl summary", "",
          f"Peer funds: {', '.join(FUNDS)}. Rounds kept: announced on or after {MIN_DATE}.", "",
          "| Metric | Value |", "|---|---|",
          f"| Unique portfolio entities (by Cala entity id) | {len(comp_rows)} |",
          f"| ...of which name duplicates (same name, different id) | {dup_names} |",
          f"| Companies with at least one round since 2024 | {len(active)} |",
          f"| Funding rounds since 2024 | {len(round_rows)} |",
          f"| Rounds dropped: announced before 2024 | {dropped_old} |",
          f"| Rounds dropped: no announcement_date | {dropped_nodate} |",
          f"| Rounds flagged as possibly conflated | {len(flagged)} |",
          f"| API calls this run (incl. retries) | {cala.api_calls} |",
          f"| ...of which rate-limited (429) and retried | {cala.rate_limited} |",
          f"| Cache hits this run (fetched by an earlier run) | {cala.cache_hits} |",
          f"| Distinct API responses in cache (calls needed for a full crawl) | {cached_total} |",
          f"| API errors | {len(cala.errors)} |",
          f"| Run time | {elapsed:.0f} s |", "",
          "## Fund entities used", "", "| Fund | Cala entities | INVESTED_IN links | Round links |", "|---|---|---|---|"]
    for fund, es in fund_entities.items():
        md.append(f"| {fund} | {'; '.join(e['name'] for e in es) or '**not found**'} | "
                  f"{per_fund_counts[fund + '|invested_in']} | {per_fund_counts[fund + '|rounds']} |")
    md += ["", "## By HQ country", "", "| HQ country | Companies (all) | Companies with 2024+ round |", "|---|---|---|"]
    for k, n in by_country.most_common():
        md.append(f"| {k} | {n} | {by_country_active.get(k, 0)} |")
    md += ["", "## Rounds since 2024 by round_label", "", "| round_label | Rounds |", "|---|---|"]
    for k, n in by_label.most_common():
        md.append(f"| {k} | {n} |")
    md += ["", "## Possibly conflated rounds", "",
           "Flagged when the amount is implausible for the label "
           f"({', '.join(f'{k} > {v / 1e6:.0f}M' for k, v in CONFLATION_THRESHOLDS.items())}, any currency) "
           "or the round is larger than the company's total funding.", ""]
    if flagged:
        md += ["| Company | Label | Amount | Date | Flag |", "|---|---|---|---|---|"]
        for r in sorted(flagged, key=lambda r: -(r["transaction_value"] or 0)):
            md.append(f"| {r['company']} | {r['round_label']} | {r['transaction_value']:,} {r['currency'] or ''} | "
                      f"{r['announcement_date']} | {r['conflation_flag']} |")
    else:
        md.append("None.")
    if cala.errors:
        md += ["", "## API errors (first 20)", ""] + [f"- {e}" for e in cala.errors[:20]]
    md += ["", "Full results are in `cala_cache.db` (tables `companies`, `rounds`; raw responses in `cache`)."]
    SUMMARY_PATH.write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
