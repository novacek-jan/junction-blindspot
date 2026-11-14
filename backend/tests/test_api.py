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
                           "total_funding_currency": "EUR", "industries": json.dumps(["SOFTWARE_AND_SERVICES"]),
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
    "$.never_seen[].round.investors[]": {"is_vc"},
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
    assert post_audit(client).json() == post_audit(client).json()


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
    assert r1.content == r2.content
    a = r1.json()
    check_v2_shape(a, mock("audit_demo.json"))
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
    import db as dbm
    dbm.ALLOW_CREATE = True
    rows = [("bs-1", "Patent AI Oy", "AI for patent search", "SEED", ["new-vc"], 2),
            ("bs-2", "Contract AI Oy", "AI for legal contracts", "SEED", ["new-vc"], 1),
            ("bs-3", "Compliance AI Oy", "AI for compliance checks", "SEED", ["new-vc", "other-vc"], 2),
            ("bs-4", "Boat Parts Oy", "Marine spare parts marketplace", "SEED", ["other-vc"], 1)]
    for cid, name, desc, label, vcs, n_rounds in rows:
        dbm.upsert_company({"id": cid, "name": name, "website": f"https://{cid}.fi", "description": desc,
                            "country": "Finland", "founded": "2021", "funding_stage": label, "total_funding": 2e6,
                            "total_funding_currency": "EUR", "industries": json.dumps(["SOFTWARE_AND_SERVICES"]),
                            "sources": json.dumps(SRC), "fetched_at": 0})
        for k in range(n_rounds):
            dbm.upsert_round({"id": f"r-{cid}-{k}", "company_id": cid, "label": label, "amount": 1e6 + k,
                              "currency": "EUR", "date": f"202{4 + k}-03-01", "conflated": 0, "conflation_reason": "",
                              "sources": json.dumps(SRC)},
                             [{"entity_id": cid, "name": name, "role": "ISSUER"}] +
                             [{"entity_id": v, "name": {"new-vc": "Nordic Seed Capital Oy",
                                                       "other-vc": "BVF Venture Fund IV AB"}[v],
                               "entity_type": "Organization", "role": "INVESTOR", "is_lead": True} for v in vcs])
    dbm.ALLOW_CREATE = False


def test_briefing_facts_and_fallback_without_key(client):
    _seed_briefing_data()
    a = post_audit(client).json()
    b = a["briefing"]
    assert b and b["model"] == "template"                      # no API key in tests: template text
    kinds = [i["kind"] for i in b["insights"]]
    assert kinds == [k for k in ("sourcing", "theme", "momentum") if k in kinds] and "theme" not in kinds
    src = next(i for i in b["insights"] if i["kind"] == "sourcing")
    never_ids = {d["company_id"] for d in a["never_seen"]}
    assert set(src["company_ids"]) <= never_ids and src["value"] == len(src["company_ids"]) >= 2
    assert "Nordic Seed Capital" in src["investor_names"]      # "Nordic Seed Capital Oy": legal suffix removed
    boat = next(d for d in a["never_seen"] if d["company_id"] == "bs-4")
    assert [i["name"] for i in boat["round"]["investors"]] == ["Butterfly Ventures"]   # "BVF Venture Fund IV AB"
    mom = next(i for i in b["insights"] if i["kind"] == "momentum")
    assert set(mom["company_ids"]) == {"bs-1", "bs-3"} and mom["value"] == 2   # raised again since 2022
    for i in b["insights"]:
        assert i["total"] == a["summary"]["never_seen"] and i["value"] >= 2


def test_briefing_uses_model_text_only_when_valid(client, monkeypatch):
    import briefing
    _seed_briefing_data()
    seen_payloads = []

    def fake(payload):
        seen_payloads.append(payload)
        v = payload["insights"]["sourcing"]["value"]
        return {"sourcing": {"title": "Seed funds you never meet", "line": f"They backed {v} of them before you looked."},
                "theme": {"company_ids": ["bs-1", "bs-2", "bs-3", "not-a-real-id"], "title": "Vertical AI for experts",
                          "line": "AI tools for patents, contracts and compliance work."},
                "momentum": {"title": "They raised again", "line": "They closed 99 rounds already."}}  # 99: invalid
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(briefing, "_call_model", fake)
    monkeypatch.setattr(briefing.db, "kv_get", lambda k: None)
    monkeypatch.setattr(briefing.db, "kv_put", lambda k, v: None)
    a = post_audit(client).json()
    ins = {i["kind"]: i for i in a["briefing"]["insights"]}
    assert [i["kind"] for i in a["briefing"]["insights"]] == ["sourcing", "theme", "momentum"]
    assert ins["sourcing"]["title"] == "Seed funds you never meet"              # valid model text kept
    assert ins["theme"]["company_ids"] == ["bs-1", "bs-2", "bs-3"] and ins["theme"]["value"] == 3   # fake id dropped
    assert ins["momentum"]["title"] == "They already raised again"             # invalid -> template
    assert a["briefing"]["model"] == briefing.MODEL
    # the CRM never reaches the model: no CRM-only company names in the payload
    assert "Unrelated Startup" not in json.dumps(seen_payloads)


def test_briefing_text_rules():
    import briefing
    assert briefing.text_ok("Seed funds got there first", "They backed 6 of the 16 before you.", 6, 16)
    assert not briefing.text_ok("Two seed funds got there", "They backed 6 of the 16.", 6, 16)     # "two"
    assert not briefing.text_ok("Seed funds", "They backed 7 of them.", 6, 16)                      # 7
    assert not briefing.text_ok("A title that is far too long here", "Fine.", 6, 16)                # > 6 words
    assert briefing.text_ok("20VC got there first", "20VC backed 6 of them.", 6, 16, names=("20VC",))


def test_briefing_templates_respect_word_limits():
    import briefing
    long_names = {"kind": "sourcing", "value": 4, "investor_names": ["Icebreaker.vc", "Ugly Duckling Ventures"]}
    for fact in (long_names, {"kind": "momentum", "value": 6, "investor_names": []}):
        title, line = briefing.fallback_text(fact)
        assert briefing.text_ok(title, line, fact["value"], 19, names=tuple(fact["investor_names"]))
