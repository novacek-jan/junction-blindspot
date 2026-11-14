"""Endpoint tests: contract shapes (vs frontend/mocks), security limits, demo speed and determinism.

Runs against a small synthetic SQLite DB (no network: Cala and Anthropic are never called).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
MOCKS = ROOT / "frontend" / "mocks"
os.environ["BLINDSPOT_BACKEND"] = "sqlite"   # tests never touch Postgres
sys.path.insert(0, str(BACKEND))

os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000,https://blindspot-test.vercel.app"
os.environ["AUDIT_ACCESS_CODE"] = "test-code"
os.environ["AUDIT_RATE_LIMIT"] = "1000"
os.environ["ANTHROPIC_API_KEY"] = ""   # never call Claude in tests (load_env does not override)

import db  # noqa: E402

F1, F2, F3 = "f1000000-0000-0000-0000-000000000001", "f2000000-0000-0000-0000-000000000002", "f3000000-0000-0000-0000-000000000003"
LEAD = {"own1": F1, "own2": "e1-legal", "m3": F3}   # own rounds led by Alpha (incl. its legal entity)
# own1 adds a second industry: Alpha's thesis is SOFTWARE_AND_SERVICES (2 basis rounds) before ADVERTISING (1)
INDUSTRIES = {"own1": ["ADVERTISING", "SOFTWARE_AND_SERVICES"]}
SRC = [{"name": "tech.eu", "url": "https://tech.eu/x", "rank": "PRESS"}]


def _seed(path: Path) -> None:
    os.environ["BLINDSPOT_DB"] = str(path)
    db._local.conn = None
    db.ALLOW_CREATE = True
    db.upsert_fund(F1, "Alpha Ventures", [(F1, "Alpha Ventures"), ("e1-legal", "Alpha Ventures GmbH")])
    db.upsert_fund(F2, "Beta Capital", [(F2, "Beta Capital")])
    db.upsert_fund(F3, "Gamma Partners", [(F3, "Gamma Partners")])
    comps = [("own1", "Own One", "own1.de", "Germany"), ("own2", "Own Two", "own2.se", "Sweden"),
             ("m1", "Market One GmbH", "market-one.de", "Germany"), ("m2", "Market Two", "market-two.se", "Sweden"),
             ("m3", "Market Three", "m3.fi", "Finland"), ("cf", "Conflated Co", "conflated.de", "Germany"),
             ("us1", "Faraway Inc", "faraway.com", "Brazil"), ("nosrc", "No Source", "nosrc.de", "Germany")]
    for cid, name, web, country in comps:
        db.upsert_company({"id": cid, "name": name, "website": "https://" + web, "description": f"{name} does things",
                           "country": country, "founded": "2021", "funding_stage": "SEED", "total_funding": 5e6,
                           "total_funding_currency": "EUR", "industries": json.dumps(INDUSTRIES.get(cid, ["SOFTWARE_AND_SERVICES"])),
                           "sources": json.dumps(SRC), "fetched_at": 0})
    db.add_portfolio(F1, [("own1", "INVESTED_IN", None), ("own2", "INVESTED_IN", None)])
    db.add_portfolio(F2, [("m1", "INVESTED_IN", None), ("m2", "INVESTED_IN", None), ("cf", "INVESTED_IN", None),
                          ("own1", "INVESTED_IN", None), ("nosrc", "INVESTED_IN", None)])
    db.add_portfolio(F3, [("m3", "INVESTED_IN", None), ("us1", "INVESTED_IN", None)])
    rounds = [("r-own1", "own1", "SEED", 3e6, "2023-05-01", 0, SRC), ("r-own2", "own2", "SERIES_A", 9e6, "2024-02-01", 0, SRC),
              ("r-m1", "m1", "SEED", 4e6, "2024-06-14", 0, SRC), ("r-m1-old", "m1", "SEED", 1e6, "2021-01-01", 0, SRC),
              ("r-m2", "m2", "SERIES_A", 12e6, "2025-01-10", 0, SRC), ("r-m3", "m3", "SEED", 2e6, "2024-09-01", 0, SRC),
              ("r-cf", "cf", "SEED", 40e6, "2025-03-01", 1, SRC), ("r-us1", "us1", "SEED", 2e6, "2024-01-01", 0, SRC),
              ("r-nosrc", "nosrc", "SEED", 2e6, "2024-01-01", 0, [])]
    for rid, cid, label, amt, date, conf, src in rounds:
        db.upsert_round({"id": rid, "company_id": cid, "label": label, "amount": amt, "currency": "EUR", "date": date,
                         "conflated": conf, "conflation_reason": "SEED above 10M" if conf else "",
                         "sources": json.dumps(src)},
                        [{"entity_id": cid, "name": cid, "role": "ISSUER"},
                         {"entity_id": LEAD.get(cid, F2), "name": "lead", "role": "INVESTOR", "is_lead": True},
                         {"entity_id": "angel-1", "name": "Some Angel", "role": "INVESTOR", "is_lead": False}])
    db.ALLOW_CREATE = False


class FakeCala:
    """Stands in for Cala in the live check: no network. rounds: company id -> new round entities (Cala shape);
    fail: company ids whose retrieval fails; delay: seconds per call; refuse: raise PaymentRequired."""

    def __init__(self, rounds=None, fail=(), delay=0.0, refuse=False):
        self.rounds, self.fail, self.delay, self.refuse = rounds or {}, set(fail), delay, refuse
        self.has_key = True
        self.calls = []

    def retrieve(self, entity_id, properties, out=(), inc=(), cache=True):
        import cala_client
        assert cache is False                            # the live check always bypasses the crawl cache
        self.calls.append(entity_id)
        if self.delay:
            time.sleep(self.delay)
        if self.refuse:
            raise cala_client.PaymentRequired("Cala returned 402")
        if entity_id in self.fail:
            return {"id": entity_id, "properties": {}, "_ok": False, "_rels": {}}
        for cid, rounds in self.rounds.items():
            for r in rounds:
                if r["id"] == entity_id:
                    return {**r, "_ok": True}
        items = [{"id": r["id"], "properties": {"role": "ISSUER"}} for r in self.rounds.get(entity_id, [])]
        return {"id": entity_id, "properties": {}, "_ok": True,
                "_rels": {"outgoing:PARTICIPATES_IN_FUNDING_ROUND": items}}


def cala_round(rid, label, amount, day, investors):
    """A round entity as Cala's entity_retrieval returns it (with participants)."""
    def prop(v):
        return {"value": v, "sources": [{"name": "tech.eu", "document": f"https://tech.eu/{rid}",
                                         "source_rank": "PRESS"}]}
    return {"id": rid, "properties": {"round_label": prop(label), "transaction_value": prop(amount),
                                      "transaction_value_units": prop("EUR"), "announcement_date": prop(day)},
            "_rels": {"incoming:PARTICIPATES_IN_FUNDING_ROUND": [
                {"id": eid, "name": name, "entity_type": "Organization",
                 "properties": {"role": "INVESTOR", "is_lead": True}} for eid, name in investors]}}


@pytest.fixture(autouse=True)
def fake_cala(monkeypatch):
    """Every test: the live check talks to a fake Cala (no network) with no new rounds, and starts uncached."""
    import live_check
    live_check.reset()
    fake = FakeCala()
    monkeypatch.setattr(live_check, "client", lambda: fake)
    return fake


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    _seed(tmp_path_factory.mktemp("db") / "test.db")
    from fastapi.testclient import TestClient
    import app as app_module
    app_module._cala = None            # no network in tests
    return TestClient(app_module.app)


# Fields added to the contract after the frontend mocks were written (documented in docs/api-contract.md).
ADDED_FIELDS = {
    "$": {"breakdown", "patterns", "briefing"},
    "$.briefing.insights[]": {"best_pct", "worst_pct", "best_industry", "worst_industry"},
    "$.never_seen[].round.investors[]": {"is_vc"},
    "$.live_check": {"checked_at"},                 # frontend mock has no checked_at
    "$.market_coverage": {"region", "region_countries", "region_qualifying_companies", "priority_country",
                          "priority_country_qualifying_companies"},
    "$[]": {"basis_rounds"},
    "$.suggested_peers[]": {"score", "reasons"},
    "$.sources[]": {"date"},
    "$.never_seen_deals[].sources[]": {"date"},
    "$.rounds[]": {"id", "date_kind", "qualifying"},
    "$.rounds[].sources[]": {"date"},
}
V2_MOCKS = ROOT / "docs" / "mocks"


def v2mock(name):
    return json.loads((V2_MOCKS / name).read_text())


def check_v2_shape(resp, frontend_mock):
    """v2 only (the v1 fields are gone): same shape as docs/mocks/audit_v2.json and the frontend's mock."""
    same_shape(resp, v2mock("audit_v2.json"))
    same_shape(resp, frontend_mock)


def same_shape(resp, mock, path="$"):
    """Same keys at every level as the frontend mock; list items compared against the mock's first item."""
    if isinstance(mock, dict):
        assert isinstance(resp, dict), f"{path}: expected object"
        extra = ADDED_FIELDS.get(re.sub(r"\[\d+\]", "[]", path), set()) - set(mock)
        assert set(resp) - extra == set(mock), f"{path}: keys {sorted((set(resp) - extra) ^ set(mock))} differ"
        for k in mock:
            if resp[k] is not None and mock[k] is not None:
                same_shape(resp[k], mock[k], f"{path}.{k}")
    elif isinstance(mock, list):
        assert isinstance(resp, list), f"{path}: expected array"
        if mock and resp:
            for i, item in enumerate(resp):
                same_shape(item, mock[0], f"{path}[{i}]")
    elif isinstance(mock, bool):
        assert isinstance(resp, bool), f"{path}: expected bool"
    elif isinstance(mock, (int, float)):
        assert isinstance(resp, (int, float)) and not isinstance(resp, bool), f"{path}: expected number"
    elif isinstance(mock, str):
        assert isinstance(resp, str), f"{path}: expected string"


def mock(name):
    return json.loads((MOCKS / name).read_text())


CSV = ("company,website,status,date\n"
       "Market One,https://www.market-one.de,passed,2024-05-01\n"   # domain match
       "Market Two,,in_review,2024-12-01\n"                          # name match
       "Unrelated Startup,unrelated.io,passed,2024-01-01\n")          # pipeline only


def post_audit(client, csv=CSV, code="test-code", ctype="text/csv", fund=F1, peers=f"{F2},{F3}"):
    headers = {"X-Access-Code": code} if code is not None else {}
    return client.post("/api/audit", data={"fund_id": fund, "peer_ids": peers},
                       files={"crm_csv": ("crm.csv", csv, ctype)}, headers=headers)


# ---------------------------------------------------------------- contract shapes

def test_funds_search(client):
    r = client.get("/api/funds/search?q=bet")
    # Beta's basis: its own rounds since 2022 of European companies (m1, m2, nosrc); cf is conflated, us1 in Brazil
    assert r.status_code == 200 and r.json() == [{"id": F2, "name": "Beta Capital", "basis_rounds": 3}]
    same_shape(r.json(), v2mock("funds_search_v2.json"))
    same_shape(r.json(), mock("funds_search.json"))
    everyone = client.get("/api/funds/search?q=").json()
    assert not [f for f in everyone if f["id"] == "angel-1"]    # an angel (not a VC) is never returned
    assert {f["id"] for f in everyone} >= {F1, F2, F3}


def test_profile_shape_and_values(client):
    r = client.get(f"/api/funds/{F1}/profile")
    assert r.status_code == 200
    body = r.json()
    same_shape(body, v2mock("profile_v2.json"))
    v1 = mock("fund_profile.json")
    same_shape({k: body[k] for k in v1}, v1)
    # basis: Alpha's own rounds since 2022 (own1 SEED 2023, own2 SERIES_A 2024), both European
    assert body["investments_since_2022"] == 2 and body["out_of_scope_deals"] == 0
    assert body["period"]["from"] == "2022-01-01" and body["scope"] == "Europe"
    assert {s["label"] for s in body["stages"]} == {"SEED", "SERIES_A"}
    assert body["thesis"]["stages"] == ["SEED", "SERIES_A"]
    assert {"Germany", "Austria", "Switzerland", "Sweden", "Finland"} <= set(body["thesis"]["countries"])
    assert "United States" not in body["thesis"]["countries"]
    # thesis industries ranked by basis rounds (most first), not alphabetically
    assert [i["code"] for i in body["thesis"]["industries"]] == ["SOFTWARE_AND_SERVICES", "ADVERTISING"]
    assert sum(c["count"] for c in body["countries"]) == body["investments_since_2022"]
    top = body["suggested_peers"][0]
    assert (top["id"], top["co_investments"]) == (F2, 1)
    assert set(top) == {"id", "name", "co_investments", "score", "reasons"}


def test_default_peers_by_thesis_when_none_sent(client):
    r = post_audit(client, peers="")
    assert r.status_code == 200
    profile_peers = [p["id"] for p in client.get(f"/api/funds/{F1}/profile").json()["suggested_peers"]]
    assert "peers" not in r.json()                                              # v2: peers do not define the market
    assert r.json()["summary"]["market_companies"] >= 1


def test_audit_numbers_and_shape(client):
    r = post_audit(client)
    assert r.status_code == 200, r.text
    a = r.json()
    check_v2_shape(a, mock("audit.json"))
    # Market (any investor, not just peers): own1, own2, m1, m2, m3 - qualifying rounds since 2022, European,
    # in Alpha's thesis (SEED..SERIES_A, DACH + Nordics). Excluded: m1's 2021 round, us1 (Brazil),
    # nosrc (no source), cf (conflated).
    assert a["summary"] == {"market_companies": 5, "in_crm": 4, "invested": 2, "passed": 1, "in_review": 1,
                            "never_seen": 1, "coverage_pct": 80.0}
    assert a["headline"] == {"never_seen": 1,
                             "text": "1 VC-backed company in your thesis raised since 2022 and never hit your CRM"}
    assert a["period"]["from"] == "2022-01-01"
    assert a["thesis"]["stages"] == ["SEED", "SERIES_A"] and a["thesis"]["basis_rounds"] == 2
    assert [i["code"] for i in a["thesis"]["industries"]] == ["SOFTWARE_AND_SERVICES", "ADVERTISING"]
    [d] = a["never_seen"]
    assert d["name"] == "Market Three" and d["country"] == "Finland"
    assert d["round"]["label"] == "SEED" and d["round"]["date"] == "2024-09-01"
    assert d["round"]["investors"] == [
        {"id": F3, "name": "Gamma Partners", "type": None, "is_lead": True, "is_vc": True},
        {"id": "angel-1", "name": "Some Angel", "type": None, "is_lead": False, "is_vc": False}]
    assert d["round"]["sources"] and all(src["url"] and src["rank"] for src in d["round"]["sources"])
    assert a["top_investors_in_blind_spots"] == [{"id": F3, "name": "Gamma Partners", "companies": 1}]  # VCs only
    # breakdown: every thesis country x stage; sums match the summary
    assert sum(b["market"] for b in a["breakdown"]) == a["summary"]["market_companies"]
    assert sum(b["never_seen"] for b in a["breakdown"]) == a["summary"]["never_seen"]
    assert {(b["country"], b["stage"]) for b in a["breakdown"] if b["never_seen"]} == {("Finland", "SEED")}
    assert len(a["breakdown"]) == len(a["thesis"]["countries"]) * len(a["thesis"]["stages"])
    assert a["patterns"] == []                                   # one blind spot: no pattern reaches 2
    assert len(a["never_seen"]) == a["summary"]["never_seen"] == a["headline"]["never_seen"]
    for legacy in ("peers", "venn", "heatmap", "top_blind_spots", "never_seen_deals", "top_missed_leads"):
        assert legacy not in a
    assert a["market_coverage"]["region"] == "nordics"
    assert set(a["market_coverage"]["region_countries"]) == {"Finland", "Sweden", "Norway", "Denmark", "Iceland"}
    assert a["simulated_crm"] is False


def test_audit_is_deterministic(client):
    a, b = post_audit(client).json(), post_audit(client).json()
    for x in (a, b):
        x["live_check"].pop("seconds"), x["live_check"].pop("checked_at")
    assert a == b


def test_deal_detail_shape(client):
    r = client.get(f"/api/deals/m3?fund_id={F1}")
    assert r.status_code == 200
    d = r.json()
    same_shape(d, v2mock("deal_v2.json"))
    assert all(set(r) >= {"id", "date_kind", "qualifying"} for r in d["rounds"])
    assert d["rounds"][0]["lead_investors"] == [{"id": F3, "name": "Gamma Partners"}]
    assert d["rounds"][0]["participants"] == [{"id": "angel-1", "name": "Some Angel"}]
    assert len(d["why_missed"]) <= 2
    assert d["why_missed"][0]["reason"] == "Lead investor Gamma Partners has never co-invested with you"


# ---------------------------------------------------------------- protection of POST /api/audit

def test_audit_requires_access_code(client):
    assert post_audit(client, code=None).status_code == 401
    assert post_audit(client, code="wrong").status_code == 401


def test_audit_rejects_non_csv(client):
    r = post_audit(client, ctype="application/json")
    assert r.status_code == 415 and r.json()["error"] == "unsupported_media_type"


def test_audit_rejects_large_file(client):
    big = "company,website,status,date\n" + ("x" * 100 + ",a.com,passed,2024-01-01\n") * 25_000
    assert len(big) > 2 * 1024 * 1024
    r = post_audit(client, csv=big)
    assert r.status_code == 413


def test_audit_rejects_too_many_rows(client):
    rows = "company,website,status,date\n" + "".join(f"C{i},c{i}.com,passed,2024-01-01\n" for i in range(5001))
    r = post_audit(client, csv=rows)
    assert r.status_code == 413 and r.json()["error"] == "too_many_rows"


def test_audit_rate_limit(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "RATE_LIMIT", 2)
    app_module._hits.clear()
    codes = [post_audit(client).status_code for _ in range(3)]
    app_module._hits.clear()
    assert codes == [200, 200, 429]


def test_audit_disabled_without_code_configured(client, monkeypatch):
    monkeypatch.delenv("AUDIT_ACCESS_CODE")
    assert post_audit(client).status_code == 503


# ---------------------------------------------------------------- errors, CORS

def test_errors_are_clean_json(client):
    for url in ["/api/funds/nope/profile", "/api/deals/nope"]:
        r = client.get(url)
        assert r.status_code == 404
        assert set(r.json()) == {"error", "detail"}
        assert "Traceback" not in r.text and "/Users/" not in r.text and ".py" not in r.text
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_cors(client):
    ok = client.get("/api/health", headers={"Origin": "https://blindspot-test.vercel.app"})
    assert ok.headers.get("access-control-allow-origin") == "https://blindspot-test.vercel.app"
    bad = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


# ---------------------------------------------------------------- demo (committed precomputed JSON)

def test_demo_shape_speed_determinism(client):
    if not (ROOT / "data" / "demo_audit.json").exists():
        pytest.skip("demo not built")
    t0 = time.perf_counter()
    r1 = client.get("/api/audit/demo")
    elapsed = time.perf_counter() - t0
    r2 = client.get("/api/audit/demo")
    assert r1.status_code == 200 and elapsed < 1.0
    a, b = r1.json(), r2.json()
    assert a["live_check"]["status"] == "ok" and a["live_check"]["companies"] == len(a["never_seen"])
    check_v2_shape(a, mock("audit_demo.json"))
    for x in (a, b):
        x["live_check"].pop("seconds"), x["live_check"].pop("checked_at")
    assert a == b
    assert a["simulated_crm"] is True
    assert all(d["round"]["sources"] for d in a["never_seen"])
    assert all(d["round"]["label"] in a["thesis"]["stages"] for d in a["never_seen"])
    assert len(a["never_seen"]) == a["summary"]["never_seen"] == a["headline"]["never_seen"]


def test_demo_works_without_db(client, monkeypatch, tmp_path):
    if not (ROOT / "data" / "demo_deals.json").exists():
        pytest.skip("demo not built")
    monkeypatch.setenv("BLINDSPOT_DB", str(tmp_path / "missing.db"))
    monkeypatch.setattr(db._local, "conn", None)
    demos = client.get("/api/audit/demos").json()
    same_shape(demos, v2mock("demos_v2.json"))
    assert sum(d["default"] for d in demos) == 1
    for entry in demos:
        fid = entry["fund"]["id"]
        demo = client.get(f"/api/audit/demo?fund_id={fid}").json()
        assert demo["fund"]["id"] == fid and demo["simulated_crm"] is True
        for d in demo["never_seen"]:
            r = client.get(f"/api/deals/{d['company_id']}?fund_id={fid}")
            assert r.status_code == 200, f"no precomputed detail for {d['name']}"
        assert client.get(f"/api/funds/{fid}/profile").status_code == 200
    assert client.get("/api/audit/demo").json()["fund"]["id"] == next(d["fund"]["id"] for d in demos if d["default"])
    assert client.get("/api/funds/search?q=").json()
    assert post_audit(client).status_code == 503
    assert not (tmp_path / "missing.db").exists(), "API must not create an empty DB"


# ---------------------------------------------------------------- client IP behind proxies

class _Req:
    def __init__(self, xff, peer="10.0.0.9"):
        self.headers = {"x-forwarded-for": xff} if xff is not None else {}
        self.client = type("C", (), {"host": peer})()


@pytest.mark.parametrize("hops,xff,expected", [
    ("0", "1.1.1.1, 2.2.2.2", "10.0.0.9"),            # default: header ignored
    ("1", "6.6.6.6, 1.1.1.1", "1.1.1.1"),             # one proxy appended the real client
    ("2", "6.6.6.6, 1.1.1.1, 3.3.3.3", "1.1.1.1"),    # two proxies; spoofed left entry ignored
    ("3", "1.1.1.1", "1.1.1.1"),                       # fewer entries than hops: leftmost
    ("1", None, "10.0.0.9"),                           # no header: peer
    ("abc", "1.1.1.1", "10.0.0.9"),                    # invalid setting: treated as 0
])
def test_client_ip(monkeypatch, hops, xff, expected):
    import app as app_module
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", hops)
    assert app_module.client_ip(_Req(xff)) == expected


def test_deal_detail_uses_brand_names(client):
    import db as dbm
    dbm.ALLOW_CREATE = True
    dbm.upsert_round({"id": "r-m3b", "company_id": "m3", "label": "SEED", "amount": 1e6, "currency": "EUR",
                      "date": None, "conflated": 0, "conflation_reason": "", "sources": json.dumps(SRC)},
                     [{"entity_id": "m3", "name": "m3", "role": "ISSUER"},
                      {"entity_id": "fm", "name": "FIRSTMINUTE CAPITAL LLP", "role": "INVESTOR", "is_lead": True},
                      {"entity_id": "sl", "name": "SLACK TECHNOLOGIES, INC.", "role": "INVESTOR"}])
    dbm.upsert_display_names([("sl", "SLACK TECHNOLOGIES, INC.", "Slack Technologies", "cala_alias")])
    dbm.ALLOW_CREATE = False
    d = client.get(f"/api/deals/m3?fund_id={F1}").json()
    undated = next(r for r in d["rounds"] if r["date"] is None)        # EU grants etc. have no date
    assert undated["lead_investors"] == [{"id": "fm", "name": "Firstminute Capital"}]   # title-case fallback
    assert {"id": "sl", "name": "Slack Technologies"} in undated["participants"]       # Cala alias


# ---------------------------------------------------------------- any CRM export: preview + audit

FIXTURES = Path(__file__).resolve().parent / "fixtures"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(client, path, name=None, ctype=None, url="/api/audit/preview", mapping=None, code="test-code"):
    name = name or path.name
    ctype = ctype or (XLSX if name.endswith(".xlsx") else "text/csv")
    data = {"fund_id": F1, "peer_ids": f"{F2},{F3}"}
    if mapping is not None:
        data["mapping"] = json.dumps(mapping)
    return client.post(url, data=data, files={"crm_csv": (name, path.read_bytes(), ctype)},
                       headers={"X-Access-Code": code} if code else {})


@pytest.mark.parametrize("fixture,rows,matched", [
    ("affinity_export.csv", 4, 2), ("hubspot_deals.xlsx", 4, 4), ("pipedrive_deals.csv", 3, 2),
    ("excel_tracker_no_status.xlsx", 3, 2), ("salesforce_report.csv", 3, 3), ("attio_list.csv", 3, 2),
])
def test_preview_every_export(client, fixture, rows, matched):
    r = upload(client, FIXTURES / fixture)
    assert r.status_code == 200, r.text
    p = r.json()
    assert set(p) == {"file_type", "columns", "mapping", "row_count", "skipped_rows", "matched_rows",
                      "status_counts", "sample_rows", "warnings"}
    assert p["row_count"] == rows and p["matched_rows"] == matched
    assert len(p["sample_rows"]) == min(5, rows)
    assert set(p["mapping"]) == {"company", "website", "status", "date"}
    assert sum(p["status_counts"].values()) == rows


def test_preview_warns_when_status_missing(client):
    p = upload(client, FIXTURES / "excel_tracker_no_status.xlsx").json()
    assert p["status_counts"]["seen"] == 3
    assert any("no status column" in w for w in p["warnings"])


def test_audit_accepts_xlsx_and_mapping_override(client):
    r = upload(client, FIXTURES / "hubspot_deals.xlsx", url="/api/audit")
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    # market own1, own2, m1, m2, m3: m1 invested (Closed won), m2 passed (Closed lost), m3 in_review (DD),
    # own1 + own2 invested (own portfolio)
    assert {k: s[k] for k in ("market_companies", "in_crm", "invested", "passed", "in_review", "never_seen")} == \
        {"market_companies": 5, "in_crm": 5, "invested": 3, "passed": 1, "in_review": 1, "never_seen": 0}
    # Override: match on the deal title column instead, which matches nothing -> m1, m2, m3 never seen
    r2 = upload(client, FIXTURES / "hubspot_deals.xlsx", url="/api/audit",
                mapping={"company": "Deal Name", "website": None})
    assert r2.status_code == 200 and r2.json()["summary"]["never_seen"] == 3


def test_upload_errors(client, tmp_path):
    bad = tmp_path / "legacy.xls"
    bad.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 64)
    assert upload(client, bad, ctype="application/vnd.ms-excel").status_code == 415
    assert upload(client, FIXTURES / "attio_list.csv", ctype="application/pdf").status_code == 415
    nocol = tmp_path / "numbers.csv"
    nocol.write_text("Amount,Probability\n1,2\n")
    r = upload(client, nocol)
    assert r.status_code == 422 and r.json()["error"] == "no_company_column"
    r = upload(client, FIXTURES / "attio_list.csv", mapping={"company": "Nope"})
    assert r.status_code == 422 and r.json()["error"] == "invalid_mapping"
    assert upload(client, FIXTURES / "attio_list.csv", code=None).status_code == 401


def test_vc_rule_market_and_patterns(client):
    """Angel-only, grant and loan rounds do not qualify; patterns appear from value 2."""
    import db as dbm
    dbm.ALLOW_CREATE = True
    for cid, name, label, parts in [
        ("angel-only", "Angel Only Oy", "SEED", [("p1", "Jane Angel", "Person", "INVESTOR")]),
        ("grant-only", "Grant Only Oy", "GRANT", [("g1", "Business Finland", "Organization", "GRANTOR")]),
        ("vc-a", "VC Backed A Oy", "SEED", [(F3, "Gamma Partners", "Organization", "INVESTOR")]),
        ("vc-b", "VC Backed B Oy", "SEED", [(F3, "Gamma Partners", "Organization", "INVESTOR"),
                                            ("u1", "University of Helsinki", "Organization", "INVESTOR")]),
    ]:
        dbm.upsert_company({"id": cid, "name": name, "website": f"https://{cid}.fi", "description": "", "country": "Finland",
                            "founded": "2020", "funding_stage": label, "total_funding": 1e6, "total_funding_currency": "EUR",
                            "industries": json.dumps(["SOFTWARE_AND_SERVICES"]), "sources": json.dumps(SRC), "fetched_at": 0})
        dbm.upsert_round({"id": f"r-{cid}", "company_id": cid, "label": label, "amount": 1e6, "currency": "EUR",
                          "date": "2025-01-01", "conflated": 0, "conflation_reason": "", "sources": json.dumps(SRC)},
                         [{"entity_id": cid, "name": name, "role": "ISSUER"}] +
                         [{"entity_id": e, "name": n, "entity_type": t, "role": r} for e, n, t, r in parts])
    dbm.ALLOW_CREATE = False
    a = post_audit(client).json()
    names = {d["name"] for d in a["never_seen"]}
    assert {"VC Backed A Oy", "VC Backed B Oy"} <= names
    assert not names & {"Angel Only Oy", "Grant Only Oy"}
    kinds = {p["kind"]: p for p in a["patterns"]}
    assert kinds["top_vc"]["text"].startswith("Gamma Partners backed 3 of the")
    assert kinds["country"]["text"] == f"{kinds['country']['value']} of the {a['summary']['never_seen']} are in Finland"
    assert all(p["value"] >= 2 for p in a["patterns"]) and len(a["patterns"]) <= 3


# ---------------------------------------------------------------- briefing ("Why they slipped through")

def _seed_briefing_data():
    """Four never-seen Finnish seed companies. bs-1..bs-3 are also in ADVERTISING (own1's second industry), so
    the thesis has two industries with >= 3 market companies: software (9 market, 4 in CRM: 44%) and
    advertising (own1 invested + bs-1..bs-3: 25%)."""
    import db as dbm
    dbm.ALLOW_CREATE = True
    rows = [("bs-1", "Patent AI Oy", "AI for patent search", "SEED", ["new-vc"], 2),
            ("bs-2", "Contract AI Oy", "AI for legal contracts", "SEED", ["new-vc"], 1),
            ("bs-3", "Compliance AI Oy", "AI for compliance checks", "SEED", ["new-vc", "other-vc"], 2),
            ("bs-4", "Boat Parts Oy", "Marine spare parts marketplace", "SEED", ["other-vc"], 1)]
    for cid, name, desc, label, vcs, n_rounds in rows:
        inds = ["SOFTWARE_AND_SERVICES"] + (["ADVERTISING"] if cid != "bs-4" else [])
        dbm.upsert_company({"id": cid, "name": name, "website": f"https://{cid}.fi", "description": desc,
                            "country": "Finland", "founded": "2021", "funding_stage": label, "total_funding": 2e6,
                            "total_funding_currency": "EUR", "industries": json.dumps(inds),
                            "sources": json.dumps(SRC), "fetched_at": 0})
        for k in range(n_rounds):
            dbm.upsert_round({"id": f"r-{cid}-{k}", "company_id": cid, "label": label, "amount": 1e6 + k,
                              "currency": "EUR", "date": f"202{4 + k}-03-0{1 + int(cid[-1])}", "conflated": 0,
                              "conflation_reason": "", "sources": json.dumps(SRC)},
                             [{"entity_id": cid, "name": name, "role": "ISSUER"}] +
                             [{"entity_id": v, "name": {"new-vc": "Nordic Seed Capital Oy",
                                                       "other-vc": "BVF Venture Fund IV AB"}[v],
                               "entity_type": "Organization", "role": "INVESTOR", "is_lead": True} for v in vcs])
    dbm.ALLOW_CREATE = False


@pytest.fixture
def audit_day(monkeypatch):
    """Audit date 2026-02-10: the next_round window is 2024-02-10..2025-02-10, so the companies whose latest
    round is 2024-03-0x (bs-2, bs-4) are due; bs-1/bs-3 raised again in 2025-03."""
    import briefing
    from datetime import date
    monkeypatch.setattr(briefing, "_today", lambda: date(2026, 2, 10))


def test_briefing_facts_and_fallback_without_key(client, audit_day):
    _seed_briefing_data()
    a = post_audit(client).json()
    b = a["briefing"]
    assert b and b["model"] == "template"                      # no API key in tests: template text
    assert [i["kind"] for i in b["insights"]] == ["coverage", "next_round", "sourcing"]
    ins = {i["kind"]: i for i in b["insights"]}
    never_ids = {d["company_id"] for d in a["never_seen"]}
    for i in b["insights"]:
        assert set(i) == {"kind", "value", "total", "title", "line", "company_ids", "investor_names",
                          "best_pct", "worst_pct", "best_industry", "worst_industry"}
        assert i["value"] >= 2 and set(i["company_ids"]) <= never_ids
        assert len(i["title"].split()) <= 6 and len(i["line"].split()) <= 14
    cov = ins["coverage"]
    # software coverage depends on rows other tests add (44% on the base fixture); advertising is fixed.
    # Short sector labels: "Software and services" -> "software"; unlisted ADVERTISING -> "advertising".
    assert (cov["best_industry"], cov["worst_industry"], cov["worst_pct"]) == ("software", "advertising", 25)
    assert cov["best_pct"] > 25
    assert (cov["value"], cov["total"]) == (3, 4) and cov["company_ids"] == ["bs-3", "bs-1", "bs-2"]   # newest round first
    assert cov["title"] == "Advertising coverage lags software"
    assert cov["line"] == f"You see {cov['best_pct']}% of software deals but only 25% of advertising deals."
    nxt = ins["next_round"]
    # bs-4 / bs-2 last raised 2024-03 (in the window); bs-1 / bs-3 raised again in 2025-03 (too recent)
    assert {"bs-4", "bs-2"} <= set(nxt["company_ids"]) and not {"bs-1", "bs-3"} & set(nxt["company_ids"])
    assert nxt["company_ids"].index("bs-4") < nxt["company_ids"].index("bs-2")   # newest first
    assert nxt["value"] == len(nxt["company_ids"])
    assert nxt["total"] == a["summary"]["never_seen"] and nxt["best_pct"] is None
    src = ins["sourcing"]
    assert src["value"] == len(src["company_ids"]) >= 2 and src["total"] == a["summary"]["never_seen"]
    assert "Nordic Seed Capital" in src["investor_names"]      # "Nordic Seed Capital Oy": legal suffix removed
    boat = next(d for d in a["never_seen"] if d["company_id"] == "bs-4")
    assert [i["name"] for i in boat["round"]["investors"]] == ["Butterfly Ventures"]   # "BVF Venture Fund IV AB"


def _fake_model(monkeypatch, reply):
    import briefing
    calls = []

    def fake(payload):
        calls.append(payload)
        return reply(payload)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(briefing, "_call_model", fake)
    monkeypatch.setattr(briefing.db, "kv_get", lambda k: None)
    monkeypatch.setattr(briefing.db, "kv_put", lambda k, v: None)
    return calls


def test_briefing_uses_model_text_only_when_valid(client, monkeypatch, audit_day):
    import briefing
    _seed_briefing_data()
    calls = _fake_model(monkeypatch, lambda p: {
        "coverage": {"title": "Model coverage title", "line": "Model coverage line."},   # never used
        "next_round": {"title": "Due again soon", "line": "They raised 18 months ago."},   # 18: invalid
        "sourcing": {"title": "Seed funds you never meet", "line": "They backed most of them before you."}})
    a = post_audit(client).json()
    ins = {i["kind"]: i for i in a["briefing"]["insights"]}
    assert [i["kind"] for i in a["briefing"]["insights"]] == ["coverage", "next_round", "sourcing"]
    assert ins["coverage"]["title"] == "Advertising coverage lags software"        # deterministic, never the model
    assert ins["next_round"]["title"] == "Due for their next round"               # invalid -> template
    assert ins["sourcing"]["title"] == "Seed funds you never meet"                # valid model text kept
    assert a["briefing"]["model"] == briefing.MODEL
    # the CRM never reaches the model: no coverage facts, no CRM rows, no company names or ids
    assert [set(p["insights"]) for p in calls] == [{"next_round", "sourcing"}]
    sent = json.dumps(calls)
    for leak in ("coverage", "pct", "advertising", "Unrelated Startup", "Market One", "Patent AI", "bs-1",
                 "market-one.de"):
        assert leak.lower() not in sent.lower()


def test_briefing_coverage_alone_makes_no_api_call(client, monkeypatch, audit_day):
    """Coverage is computed from the CRM: with only a coverage insight there is no model call at all."""
    import briefing
    _seed_briefing_data()
    calls = _fake_model(monkeypatch, lambda p: {})
    monkeypatch.setattr(briefing, "next_round_fact", lambda *a, **k: None)
    monkeypatch.setattr(briefing, "sourcing_fact", lambda *a, **k: None)
    b = post_audit(client).json()["briefing"]
    assert calls == []
    assert [i["kind"] for i in b["insights"]] == ["coverage"] and b["model"] == "template"
    assert b["insights"][0]["title"] == "Advertising coverage lags software"


def test_briefing_text_rules():
    import briefing
    assert briefing.text_ok("Seed funds got there first", "They backed 6 of the 16 before you.", 6, 16)
    assert not briefing.text_ok("Two seed funds got there", "They backed 6 of the 16.", 6, 16)     # "two"
    assert not briefing.text_ok("Seed funds", "They backed 7 of them.", 6, 16)                      # 7
    assert not briefing.text_ok("Seed funds", "Under half of them.", 6, 16)                         # "half"
    assert not briefing.text_ok("A title that is far too long here", "Fine.", 6, 16)                # > 6 words
    assert briefing.text_ok("20VC got there first", "20VC backed 6 of them.", 6, 16, names=("20VC",))


def test_briefing_templates_respect_word_limits():
    import briefing
    assert all(len(v.split()) <= 2 for v in briefing.SECTOR_SHORT.values())
    assert briefing.sector_short("SOFTWARE_AND_SERVICES") == "software"
    assert briefing.sector_short("RENEWABLE_ENERGY") == "energy"
    assert briefing.sector_short("INTERNET_AND_WEB_SERVICES") == "internet"
    assert briefing.sector_short("BIOTECHNOLOGY") == "biotech"
    assert briefing.sector_short("SPACE_AND_SATELLITES") == "space"                    # unlisted code
    facts = [{"kind": "sourcing", "value": 4, "total": 19, "investor_names": ["Icebreaker.vc", "Ugly Duckling Ventures"]},
             {"kind": "next_round", "value": 6, "total": 19, "investor_names": []}]
    for fact in facts:
        title, line = briefing.fallback_text(fact)
        assert briefing.text_ok(title, line, fact["value"], fact["total"], tuple(fact["investor_names"])), (title, line)
    title, line = briefing.fallback_text({"kind": "coverage", "value": 9, "total": 14, "investor_names": [],
                                          "best_pct": 100, "worst_pct": 7, "best_industry": "venture capital",
                                          "worst_industry": "asset management"})
    assert title == "Asset management coverage lags venture capital" and len(title.split()) <= 6
    assert line == "You see 100% of venture capital deals but only 7% of asset management deals."
    assert len(line.split()) <= 14


def test_months_before():
    import briefing
    from datetime import date
    assert briefing._months_before(date(2026, 11, 14), 12) == date(2025, 11, 14)
    assert briefing._months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert briefing._months_before(date(2026, 1, 15), 24) == date(2024, 1, 15)


# ---------------------------------------------------------------- live Cala check (audit.live_check)

def test_live_check_newer_round_updates_row(client, fake_cala):
    # m3 (never seen) raised a new SEED round led by Beta Capital (a crawled fund, so a VC) in 2026
    fake_cala.rounds = {"m3": [cala_round("r-m3-live", "SEED", 3e6, "2026-10-01", [(F2, "Beta Capital")])]}
    a = post_audit(client).json()
    assert a["live_check"]["status"] == "ok"
    assert a["live_check"]["updated"] == 1 and a["live_check"]["companies"] == len(a["never_seen"])
    assert a["live_check"]["updated_company_ids"] == ["m3"]
    m3 = next(d for d in a["never_seen"] if d["company_id"] == "m3")
    assert (m3["round"]["id"], m3["round"]["date"], m3["round"]["amount"]) == ("r-m3-live", "2026-10-01", 3e6)
    assert m3["round"]["investors"] == [{"id": F2, "name": "Beta Capital", "type": "Organization",
                                         "is_lead": True, "is_vc": True}]
    assert m3["round"]["sources"][0]["url"] == "https://tech.eu/r-m3-live"
    assert any(t["id"] == F2 for t in a["top_investors_in_blind_spots"])        # recomputed
    assert a["summary"]["never_seen"] == len(a["never_seen"])                     # nobody added or dropped
    assert sum(b["never_seen"] for b in a["breakdown"]) == a["summary"]["never_seen"]
    # stored rounds are known: only the company and the one new round were fetched
    assert fake_cala.calls.count("r-m3-live") == 1 and "r-m3" not in fake_cala.calls


def test_live_check_ignores_old_and_non_qualifying_rounds(client, fake_cala):
    fake_cala.rounds = {"m3": [cala_round("r-m3-old", "SEED", 1e6, "2023-01-01", [(F2, "Beta Capital")]),    # older
                               cala_round("r-m3-angel", "SEED", 1e6, "2026-10-01", [("p1", "Jane Doe")])]}  # no VC
    a = post_audit(client).json()
    m3 = next(d for d in a["never_seen"] if d["company_id"] == "m3")
    assert m3["round"]["id"] == "r-m3" and a["live_check"]["updated"] == 1       # a new qualifying round, but older


def test_live_check_cached_for_ten_minutes(client, fake_cala):
    post_audit(client)
    n = len(fake_cala.calls)
    assert n >= 1
    a = post_audit(client).json()
    assert len(fake_cala.calls) == n and a["live_check"]["status"] == "ok"       # served from the 10-minute cache
    import live_check
    for cid in list(live_check._cache):
        t, rounds = live_check._cache[cid]
        live_check._cache[cid] = (t - live_check.TTL_S - 1, rounds)              # expired
    post_audit(client)
    assert len(fake_cala.calls) > n


def test_live_check_refused_is_offline_and_audit_still_works(client, fake_cala):
    fake_cala.refuse = True                     # 401/402/403
    r = post_audit(client)
    assert r.status_code == 200
    a = r.json()
    assert a["live_check"]["status"] == "offline" and a["live_check"]["companies"] == 0
    assert next(d for d in a["never_seen"] if d["company_id"] == "m3")["round"]["id"] == "r-m3"
    n = len(fake_cala.calls)
    post_audit(client)
    assert len(fake_cala.calls) == n            # no further calls while Cala refuses (pause)


def test_live_check_partial_and_timeout(client, fake_cala, monkeypatch):
    import live_check
    _seed_briefing_data()                       # more never-seen companies (bs-1..bs-4 and m3)
    fake_cala.fail = {"bs-1"}
    a = post_audit(client).json()
    lc = a["live_check"]
    assert lc["status"] == "partial" and lc["companies"] == len(a["never_seen"]) - 1
    # timeout: every call is slower than the budget -> offline, fast, stored rows kept
    live_check.reset()
    monkeypatch.setattr(live_check, "client", lambda: fake_cala)
    monkeypatch.setattr(live_check, "BUDGET_S", 0.2)
    fake_cala.fail, fake_cala.delay = set(), 1.0
    t0 = time.perf_counter()
    a = post_audit(client).json()
    assert time.perf_counter() - t0 < 1.0
    assert a["live_check"]["status"] == "offline" and a["live_check"]["companies"] == 0
    assert len(a["never_seen"]) == a["summary"]["never_seen"]


def test_live_check_no_key_is_offline(client, fake_cala):
    fake_cala.has_key = False
    a = post_audit(client).json()
    assert a["live_check"]["status"] == "offline" and fake_cala.calls == []


def test_live_cala_client_fails_fast_on_429(monkeypatch):
    """max_attempts=1: a 429 fails the call at once (no backoff sleep)."""
    import io
    import urllib.error
    import cala_client
    c = cala_client.Cala(api_key="k", max_attempts=1, http_timeout=1, min_interval=0)

    def boom(*a, **k):
        raise urllib.error.HTTPError(cala_client.MCP_URL, 429, "Too Many Requests", {}, io.BytesIO(b""))
    monkeypatch.setattr(cala_client, "open_url", boom)
    t0 = time.perf_counter()
    assert c.call("entity_retrieval", {"entity_id": "x"}, cache=False) is None
    assert time.perf_counter() - t0 < 0.5


def test_deal_news_capped_and_empty_on_failure():
    import audit

    class Slow:
        def knowledge_search(self, q, cache_only=False):
            time.sleep(1.0)
            return {"context": [{"origins": [{"document": {"url": "https://x.com/a", "name": "A b"}}]}]}

    class Broken:
        def knowledge_search(self, q, cache_only=False):
            raise RuntimeError("Cala down")
    assert audit.NEWS_TIMEOUT_S == 6.0
    t0 = time.perf_counter()
    assert audit.recent_news(Slow(), "Slow Co", None, wait=0.1) == []
    assert time.perf_counter() - t0 < 0.5
    assert audit.recent_news(Broken(), "Broken Co", None) == []


def test_live_check_offline_pauses_for_a_minute(client, fake_cala, monkeypatch):
    """Cala hangs: the first audit stops at the budget (offline); the next ones skip the check for 60 s."""
    import live_check
    monkeypatch.setattr(live_check, "BUDGET_S", 0.2)
    fake_cala.delay = 0.5
    a = post_audit(client).json()
    assert a["live_check"]["status"] == "offline" and live_check.paused()
    n = len(fake_cala.calls)
    t0 = time.perf_counter()
    a = post_audit(client).json()
    assert time.perf_counter() - t0 < 0.5 and len(fake_cala.calls) == n          # no calls while paused
    assert a["live_check"]["status"] == "offline" and a["live_check"]["seconds"] < 0.1
    live_check._paused_until = 0.0                                               # a minute later
    fake_cala.delay = 0.0
    assert post_audit(client).json()["live_check"]["status"] == "ok"


def test_demo_fast_when_cala_hangs(client, fake_cala):
    """Default budget (3 s): the demo answers in under 4 s even when every Cala call hangs."""
    if not (ROOT / "data" / "demo_audit.json").exists():
        pytest.skip("demo not built")
    import live_check
    assert live_check.BUDGET_S == 3.0 and live_check.HTTP_TIMEOUT_S == 3.0
    fake_cala.delay = 4.0
    t0 = time.perf_counter()
    r = client.get("/api/audit/demo")
    assert r.status_code == 200 and time.perf_counter() - t0 < 4.0
    assert r.json()["live_check"]["status"] == "offline"
    t0 = time.perf_counter()
    client.get("/api/audit/demo")
    assert time.perf_counter() - t0 < 0.5                                       # paused: no wait at all


# ---------------------------------------------------------------- GET /api/health?cala=1

@pytest.fixture
def probe_env(monkeypatch):
    import cala_probe
    monkeypatch.setattr(cala_probe, "_last", (0.0, None))
    monkeypatch.setenv("CALA_API_KEY", "secret-key-123")
    return cala_probe


def test_health_without_cala_param_makes_no_call(client, probe_env, monkeypatch):
    monkeypatch.setattr(probe_env, "run", lambda: pytest.fail("probe must not run"))
    assert "cala" not in client.get("/api/health").json()


def test_health_cala_dns_failure(client, probe_env, monkeypatch):
    import socket

    def no_dns(*a, **k):
        raise socket.gaierror("Name or service not known")
    monkeypatch.setattr(probe_env.socket, "getaddrinfo", no_dns)
    r = client.get("/api/health?cala=1")
    c = r.json()["cala"]
    assert c["key_set"] is True and c["dns_resolves"] is False and c["failed_step"] == "dns"
    assert c["error_type"] == "gaierror" and c["reachable"] is False
    assert "secret-key-123" not in r.text


def test_health_cala_tcp_timeout(client, probe_env, monkeypatch):
    import socket
    monkeypatch.setattr(probe_env.socket, "getaddrinfo",
                        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("16.170.186.71", 443))])

    def hang(*a, **k):
        raise socket.timeout("timed out")
    monkeypatch.setattr(probe_env.socket, "create_connection", hang)
    c = client.get("/api/health?cala=1").json()["cala"]
    assert c["dns_resolves"] and c["ipv4"] == 1 and not c["tcp_connect"]
    assert (c["failed_step"], c["error_type"]) == ("tcp", "timeout")


def test_health_cala_http_answer_counts_as_reachable(client, probe_env, monkeypatch):
    import io
    import socket
    import urllib.error

    class Sock:
        def close(self):
            pass

    class Tls:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def settimeout(self, t):
            pass

    class Ctx:
        def wrap_socket(self, s, server_hostname=None):
            return Tls()
    seen = {}

    def answer(req, timeout=None):
        seen["timeout"] = timeout
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b""))
    monkeypatch.setattr(probe_env.socket, "getaddrinfo",
                        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("16.170.186.71", 443))])
    monkeypatch.setattr(probe_env.socket, "create_connection", lambda *a, **k: Sock())
    monkeypatch.setattr(probe_env.ssl, "create_default_context", lambda: Ctx())
    monkeypatch.setattr(probe_env, "open_url", answer)
    r = client.get("/api/health?cala=1")
    c = r.json()["cala"]
    assert c["tcp_connect"] and c["tls"] and c["reachable"] and c["http_status"] == 403
    assert seen["timeout"] == 3.0 and c["cached"] is False
    assert c["ip_family"] == "ipv4" and set(c["steps_ms"]) == {"dns", "tcp", "tls", "http"}
    assert all(isinstance(v, int) for v in c["steps_ms"].values()) and c["total_ms"] >= c["steps_ms"]["http"]
    assert client.get("/api/health?cala=1").json()["cala"]["cached"] is True     # at most once per 30 s
    assert "secret-key-123" not in r.text


# ---------------------------------------------------------------- IPv4-only Cala HTTPS

def test_cala_connections_resolve_ipv4_only(monkeypatch):
    import socket
    import cala_client
    asked = []

    class FakeSock:
        def __init__(self, *a):
            self.family = a[0]

        def settimeout(self, t):
            self.timeout = t

        def connect(self, addr):
            self.addr = addr

    def getaddrinfo(host, port, family=0, type=0, *a):
        asked.append(family)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("16.170.186.71", port))]
    monkeypatch.setattr(cala_client.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(cala_client.socket, "socket", FakeSock)
    sock = cala_client.ipv4_create_connection(("api.cala.ai", 443), 3.0)
    assert asked == [socket.AF_INET] and sock.addr == ("16.170.186.71", 443) and sock.timeout == 3.0


def test_cala_https_keeps_sni_and_certificate_checks(monkeypatch):
    import ssl
    import cala_client
    wrapped = {}

    class Ctx:
        check_hostname, verify_mode = True, ssl.CERT_REQUIRED

        def wrap_socket(self, sock, server_hostname=None):
            wrapped["server_hostname"] = server_hostname
            return sock

    class Sock:
        def setsockopt(self, *a):
            pass
    monkeypatch.setattr(cala_client, "ipv4_create_connection", lambda addr, timeout, src: Sock())
    conn = cala_client.IPv4HTTPSConnection("api.cala.ai", 443, timeout=3, context=Ctx())
    conn.connect()
    assert wrapped["server_hostname"] == "api.cala.ai"                 # SNI is the host name, not the IP
    default = cala_client.IPv4HTTPSConnection("api.cala.ai", 443)._context
    assert default.check_hostname and default.verify_mode == ssl.CERT_REQUIRED   # verification stays on
    # every Cala call goes through the IPv4 opener
    handlers = [type(h).__name__ for h in cala_client._opener.handlers]
    assert "_IPv4HTTPSHandler" in handlers and "HTTPSHandler" not in handlers
