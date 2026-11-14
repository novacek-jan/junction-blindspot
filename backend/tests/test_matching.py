import os
import sys
from pathlib import Path

os.environ["BLINDSPOT_BACKEND"] = "sqlite"   # tests never touch Postgres
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from audit import parse_crm  # noqa: E402
from matching import CompanyIndex, classify, normalize_domain, normalize_name  # noqa: E402


@pytest.mark.parametrize("raw,expected", [
    ("https://www.Vayu-Robotics.se/about?x=1", "vayu-robotics.se"),
    ("http://vayu-robotics.se", "vayu-robotics.se"),
    ("vayu-robotics.se/", "vayu-robotics.se"),
    ("WWW.Example.COM:8080/path", "example.com"),
    ("app.example.io", "app.example.io"),
    ("", ""),
    (None, ""),
    ("not a domain", ""),
])
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Vayu Robotics GmbH", "vayu robotics"),
    ("Marvel Fusion GmbH", "marvel fusion"),
    ("AIVEN OY", "aiven"),
    ("Cherry Ventures UG (haftungsbeschränkt) & Co. KG", "cherry ventures"),
    ("Pipedrive Inc.", "pipedrive"),
    ("Zürich Analytics AG", "zurich analytics"),
    ("nexos.ai", "nexos ai"),
    ("Ltd", ""),
    (None, ""),
])
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


COMPANIES = [
    {"id": "c1", "name": "Vayu Robotics GmbH", "website": "https://vayu-robotics.se"},
    {"id": "c2", "name": "Nexos AI", "website": None},
    {"id": "c3", "name": "Other Co", "website": "other.com"},
    {"id": "c4", "name": "Fourth", "website": "fourth.io"},
]


def test_match_by_domain_beats_name():
    idx = CompanyIndex(COMPANIES)
    assert idx.match("Totally different name", "www.vayu-robotics.se/team") == {"c1"}


def test_match_by_name_when_no_website():
    idx = CompanyIndex(COMPANIES)
    assert idx.match("nexos.ai", "") == {"c2"}
    assert idx.match("NEXOS AI Ltd", None) == {"c2"}


def test_no_match():
    idx = CompanyIndex(COMPANIES)
    assert idx.match("Unknown Startup", "unknown.example") == set()
    assert idx.match("", "") == set()


def test_classify_statuses_and_pipeline_only():
    idx = CompanyIndex(COMPANIES)
    crm = [
        {"company": "Vayu Robotics", "website": "vayu-robotics.se", "status": "passed"},
        {"company": "Vayu Robotics", "website": "", "status": "in_review"},   # stronger status wins
        {"company": "Nexos AI", "website": "", "status": "PASSED"},          # case-insensitive
        {"company": "Not in market", "website": "nope.com", "status": "passed"},
        {"company": "Other Co", "website": "other.com", "status": "weird"},  # unknown status -> in_review
    ]
    status, pipeline_only = classify(["c1", "c2", "c3", "c4"], crm, idx)
    assert status == {"c1": "in_review", "c2": "passed", "c3": "in_review", "c4": "never_seen"}
    assert pipeline_only == 1


def test_classify_own_portfolio_counts_as_invested():
    idx = CompanyIndex(COMPANIES)
    status, _ = classify(["c1", "c4"], [{"company": "Vayu", "website": "vayu-robotics.se", "status": "passed"}],
                         idx, known_invested=["c4", "c1"])
    assert status == {"c1": "invested", "c4": "invested"}


def test_classify_ignores_matches_outside_market():
    idx = CompanyIndex(COMPANIES)
    status, pipeline_only = classify(["c4"], [{"company": "Other Co", "website": "other.com", "status": "passed"}], idx)
    assert status == {"c4": "never_seen"} and pipeline_only == 1


def test_parse_crm_comments_and_simulated_flag():
    text = "# SIMULATED CRM export\ncompany,website,status,date\nVayu,vayu.se,passed,2024-01-01\n,,,\n"
    rows, simulated = parse_crm(text)
    assert simulated is True
    assert rows == [{"company": "Vayu", "website": "vayu.se", "status": "passed", "raw_status": "passed",
                     "date": "2024-01-01"}]
    assert parse_crm("Company,Website,Status,Date\nA,a.com,invested,2024-01-01\n")[1] is False


def test_implausible_round_sizes_count_as_conflated():
    from audit import is_conflated
    assert is_conflated({"label": "SERIES_B", "amount": 3e9, "conflated": 0})       # valuation stored as round
    assert not is_conflated({"label": "SERIES_B", "amount": 150e6, "conflated": 0})
    assert is_conflated({"label": "SEED", "amount": 12e6, "conflated": 0})
    assert is_conflated({"label": "SEED", "amount": 1e6, "conflated": 1})           # crawler flag kept
    assert not is_conflated({"label": "GRANT", "amount": 5e9, "conflated": 0})       # no cap defined


def test_sources_of_accepts_string_and_object_documents():
    from cala_client import sources_of
    ent = {"properties": {"name": {"value": "X", "sources": [
        {"name": "tech.eu", "document": "https://tech.eu/a", "source_rank": "PRESS"},
        {"name": "GLEIF", "document": {"endpoint": "https://api.gleif.org/x", "params": {}}},
        {"name": "dup", "document": "https://tech.eu/a"},
        {"name": "empty", "document": {}}]}}}
    assert sources_of(ent, ["name"]) == [
        {"name": "tech.eu", "url": "https://tech.eu/a", "rank": "PRESS", "date": None},
        {"name": "GLEIF", "url": "https://api.gleif.org/x", "rank": None, "date": None}]


def test_brand_names():
    from names import brand_name
    assert brand_name("FIRSTMINUTE CAPITAL LLP", ["BRENT CAPITAL LLP", "Firstminute Capital", "Firstminute"]) == "Firstminute Capital"
    assert brand_name("SLACK TECHNOLOGIES, INC.", ["Tiny Speck", "Slack Technologies, LLC", "Slack Technologies"]) == "Slack Technologies"
    assert brand_name("NEXOS AI LTD") == "Nexos AI"
    assert brand_name("11X LIMITED") == "11X"
    assert brand_name("Marvel Fusion GmbH") == "Marvel Fusion GmbH"      # mixed case is left alone


def test_peer_score_overlap_weights_and_reasons():
    import peers
    a = {"country": {"Germany": 1.0}, "region": {"DACH": 1.0}, "stage": {"SEED": 0.5, "SERIES_A": 0.5},
         "sector": {"SOFTWARE": 1.0}}
    same = peers.score(a, a, peers.COINVEST_CAP)[0]
    assert same == 100.0                                           # identical thesis + full co-invest bonus
    b = {"country": {"Austria": 1.0}, "region": {"DACH": 1.0}, "stage": {"SEED": 1.0}, "sector": {"FINTECH": 1.0}}
    sc, parts = peers.score(a, b, 0)
    assert parts == {"geography": 0.5, "stage": 0.5, "sector": 0.0, "coinvest": 0.0}
    assert sc == round(100 * (peers.W_GEOGRAPHY * 0.5 + peers.W_STAGE * 0.5), 1)
    empty = {"country": {}, "region": {}, "stage": {}, "sector": {}}
    assert peers.score(a, empty, 0)[0] == 0.0
    rs = peers.reasons(a, b, parts, 2, lambda s: s.lower(), lambda s: s.title(), lambda r: r)
    assert rs[0].startswith("DACH focus: 100% of your deals, 100% of theirs")
    assert "2 portfolio companies in common" in rs
    assert abs(peers.W_GEOGRAPHY + peers.W_STAGE + peers.W_SECTOR + peers.W_COINVEST - 1.0) < 1e-9


def test_acronyms_survive_title_case():
    from names import brand_name
    assert brand_name("NEA") == "NEA"
    assert brand_name("HV HOLDING GMBH") == "HV Holding"
    assert brand_name("THE BIO LAB LTD") == "The Bio Lab"


def test_reworded_insight_must_keep_the_verb(monkeypatch, tmp_path):
    import insights
    fact = {"title": "Nordic seed", "detail": "You never saw 3 of 4 Nordic seed rounds your peers did since 2023.",
            "keep": ["Nordic", "seed"], "verbs": ["did", "closed"]}
    good = {"title": "Nordic seed gap", "detail": "Peers closed 3 of 4 Nordic seed rounds since 2023 you never saw."}
    bad = {"title": "Nordic seed gap", "detail": "Peers reviewed 3 of 4 Nordic seed rounds since 2023 you never saw."}
    for out, expected in ((good, good), (bad, {"title": fact["title"], "detail": fact["detail"]})):
        monkeypatch.setattr(insights, "_call_model", lambda facts, o=out: [o])
        monkeypatch.setattr(insights.db, "kv_get", lambda k: None)
        monkeypatch.setattr(insights.db, "kv_put", lambda k, v: None)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        assert insights.phrase([fact]) == [expected]


@pytest.mark.parametrize("name,etype,role,expected", [
    ("Lifeline Ventures", "Organization", "INVESTOR", ("vc", True)),
    ("Seedcamp Limited", "Organization", "INVESTOR", ("vc", True)),
    ("Kima Ventures", "Organization", "INVESTOR", ("vc", True)),
    ("High-Tech Gründerfonds", "Organization", "INVESTOR", ("state_vc", True)),
    ("Tesi", "Organization", "INVESTOR", ("state_vc", True)),
    ("BMW i Ventures", "Company", "INVESTOR", ("cvc", True)),
    ("Salesforce Ventures", "Company", "INVESTOR", ("cvc", True)),
    ("Insight Partners", "Company", "INVESTOR", ("growth_pe", True)),
    ("Jane Angel", "Person", "INVESTOR", ("angel", False)),
    ("Business Finland", "Organization", "INVESTOR", ("grant_public", False)),
    ("European Innovation Council", "Organization", "GRANTOR", ("grant_public", False)),
    ("Bpifrance", "Organization", "INVESTOR", ("grant_public", False)),
    ("Varma Mutual Pension Insurance Company", "Organization", "INVESTOR", ("bank_insurer_pension_am", False)),
    ("Danske Bank A/S", "Organization", "LENDER", ("lender", False)),
    ("Y Combinator", "Company", "INVESTOR", ("accelerator", False)),
    ("University of Helsinki", "Organization", "INVESTOR", ("university_research", False)),
    ("Tencent Holdings", "Organization", "INVESTOR", ("corporate", False)),
    ("Eli Lilly and Company", "Company", "INVESTOR", ("corporate", False)),
    ("Daniel Gross", "Organization", "INVESTOR", ("other", False)),
])
def test_vc_rule(name, etype, role, expected):
    from vc import classify
    assert classify(name, etype, role) == expected
