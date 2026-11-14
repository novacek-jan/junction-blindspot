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
os.environ.pop("ANTHROPIC_API_KEY", None)

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
    "$.suggested_peers[]": {"score", "reasons"},
    "$.sources[]": {"date"},
    "$.never_seen_deals[].sources[]": {"date"},
    "$.rounds[]": {"id", "date_kind", "qualifying"},
    "$.rounds[].sources[]": {"date"},
}
V2_MOCKS = ROOT / "docs" / "mocks"


def v2mock(name):
    return json.loads((V2_MOCKS / name).read_text())


def check_transition_shape(resp, v1, v2):
    """During the transition the response carries the v1 fields (frontend/mocks) AND the v2 fields (docs/mocks)."""
    assert set(resp) == set(v1) | set(v2), sorted(set(resp) ^ (set(v1) | set(v2)))
    assert set(resp["summary"]) == set(v1["summary"]) | set(v2["summary"])
    for mock in (v1, v2):
        part = {k: resp[k] for k in mock}
        part["summary"] = {k: resp["summary"][k] for k in mock["summary"]}
        same_shape(part, mock)


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
    assert r.status_code == 200 and r.json() == [{"id": F2, "name": "Beta Capital"}]
    same_shape(r.json(), mock("funds_search.json"))


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
    assert r.json()["peers"] == []                                              # v2: peers do not define the market
    assert r.json()["summary"]["market_companies"] >= 1


def test_audit_numbers_and_shape(client):
    r = post_audit(client)
    assert r.status_code == 200, r.text
    a = r.json()
    check_transition_shape(a, mock("audit.json"), v2mock("audit_v2.json"))
    # Market (any investor, not just peers): own1, own2, m1, m2, m3 - qualifying rounds since 2022, European,
    # in Alpha's thesis (SEED..SERIES_A, DACH + Nordics). Excluded: m1's 2021 round, us1 (Brazil),
    # nosrc (no source), cf (conflated).
    assert a["summary"] == {"market_companies": 5, "in_crm": 4, "invested": 2, "passed": 1, "in_review": 1,
                            "never_seen": 1, "coverage_pct": 80.0, "market_deals": 5, "in_pipeline": 4}
    assert a["headline"] == {"never_seen": 1, "text": "1 company in your thesis raised since 2022 and never hit your CRM"}
    assert a["period"]["from"] == "2022-01-01"
    assert a["thesis"]["stages"] == ["SEED", "SERIES_A"] and a["thesis"]["basis_rounds"] == 2
    [d] = a["never_seen"]
    assert d["name"] == "Market Three" and d["country"] == "Finland"
    assert d["round"]["label"] == "SEED" and d["round"]["date"] == "2024-09-01"
    assert d["round"]["investors"] == [
        {"id": F3, "name": "Gamma Partners", "type": None, "is_lead": True},
        {"id": "angel-1", "name": "Some Angel", "type": None, "is_lead": False}]
    assert d["round"]["sources"] and all(src["url"] and src["rank"] for src in d["round"]["sources"])
    assert a["top_investors_in_blind_spots"] == [{"id": F3, "name": "Gamma Partners", "companies": 1},
                                                 {"id": "angel-1", "name": "Some Angel", "companies": 1}]
    assert len(a["never_seen"]) == a["summary"]["never_seen"] == a["headline"]["never_seen"]
    # legacy v1 fields derived from the same set
    assert [x["name"] for x in a["never_seen_deals"]] == ["Market Three"]
    assert a["venn"] == {"pipeline_only": 1, "overlap": 4, "market_only": 1}
    assert a["top_blind_spots"] == [] and a["peers"] == []
    assert set(a["market_coverage"]) == {"european_companies_screened", "qualifying_companies",
                                         "investors_explored", "as_of"}
    assert a["simulated_crm"] is False


def test_audit_is_deterministic(client):
    assert post_audit(client).json() == post_audit(client).json()


def test_deal_detail_shape(client):
    r = client.get(f"/api/deals/m3?fund_id={F1}")
    assert r.status_code == 200
    d = r.json()
    same_shape(d, next(iter(mock("deal_details.json").values())))
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
    check_transition_shape(a, mock("audit_demo.json"), v2mock("audit_v2.json"))
    assert a["simulated_crm"] is True
    assert all(d["round"]["sources"] for d in a["never_seen"])
    assert all(d["round"]["label"] in a["thesis"]["stages"] for d in a["never_seen"])
    assert len(a["never_seen"]) == a["summary"]["never_seen"] == a["headline"]["never_seen"]


def test_demo_works_without_db(client, monkeypatch, tmp_path):
    if not (ROOT / "data" / "demo_deals.json").exists():
        pytest.skip("demo not built")
    monkeypatch.setenv("BLINDSPOT_DB", str(tmp_path / "missing.db"))
    monkeypatch.setattr(db._local, "conn", None)
    demo = json.loads((ROOT / "data" / "demo_audit.json").read_text())
    deals = json.loads((ROOT / "data" / "demo_deals.json").read_text())
    assert client.get("/api/audit/demo").status_code == 200
    for d in demo["never_seen"]:
        assert d["company_id"] in deals, f"no precomputed detail for {d['name']}"
        r = client.get(f"/api/deals/{d['company_id']}?fund_id={demo['fund']['id']}")
        assert r.status_code == 200
    assert client.get(f"/api/funds/{demo['fund']['id']}/profile").status_code == 200
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


def test_peers_without_market_companies_are_not_listed(client):
    import db as dbm
    dbm.ALLOW_CREATE = True
    dbm.upsert_fund("f4000000-0000-0000-0000-000000000004", "Empty Fund", [("f4000000-0000-0000-0000-000000000004", "Empty Fund")])
    dbm.ALLOW_CREATE = False
    r = post_audit(client, peers=f"{F2},{F3},f4000000-0000-0000-0000-000000000004")
    assert r.status_code == 200
    assert "Empty Fund" not in [p["name"] for p in r.json()["peers"]]


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
