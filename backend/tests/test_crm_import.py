"""CRM import: column detection on real-world export layouts, status mapping, file safety."""
import io
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

os.environ["BLINDSPOT_BACKEND"] = "sqlite"   # tests never touch Postgres
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl  # noqa: E402
import pytest  # noqa: E402

import crm_import as ci  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


def load(name):
    t = ci.load_table(name, (FIX / name).read_bytes())
    m = ci.resolve_mapping(t)
    return t, m, ci.normalize_rows(t, m)


@pytest.mark.parametrize("name,expected", [
    ("affinity_export.csv", {"company": "Organization Name", "website": "Organization Website",
                             "status": "Status", "date": "Date Added"}),
    ("hubspot_deals.xlsx", {"company": "Associated Company", "website": "Company Domain Name",
                            "status": "Deal Stage", "date": "Create Date"}),
    ("pipedrive_deals.csv", {"company": "Organization - Name", "website": None,
                             "status": "Deal - Status", "date": "Deal - Deal created"}),
    ("excel_tracker_no_status.xlsx", {"company": "Startup", "website": "URL", "status": None, "date": "First contact"}),
    ("salesforce_report.csv", {"company": "Account Name", "website": "Website", "status": "Stage",
                               "date": "Created Date"}),
    ("attio_list.csv", {"company": "Name", "website": "Domains", "status": "List status", "date": "Added at"}),
])
def test_detects_columns(name, expected):
    _, mapping, _ = load(name)
    assert mapping == expected


def test_affinity_rows_statuses_and_dates():
    t, _, rows = load("affinity_export.csv")
    assert t["kind"] == "csv"
    assert [(r["company"], r["website"], r["status"], r["date"]) for r in rows] == [
        ("Market One GmbH", "market-one.de", "invested", "2024-05-01"),
        ("Market Two", "", "passed", "2024-12-01"),
        ("Unrelated Startup", "unrelated.io", "in_review", "2024-01-15"),
        ("Lumen Labs", "lumenlabs.ai", "seen", "2024-02-02"),          # empty status = seen
    ]                                                                    # blank row skipped


def test_xlsx_with_title_rows_and_no_status_column():
    t, _, rows = load("excel_tracker_no_status.xlsx")
    assert t["kind"] == "xlsx" and t["headers"][:2] == ["Startup", "URL"]
    assert {r["status"] for r in rows} == {"seen"}
    assert rows[0]["website"] == "market-one.de" and rows[0]["date"] == "2024-07-01"


def test_pipedrive_semicolon_cp1252_and_day_first_dates():
    _, _, rows = load("pipedrive_deals.csv")
    assert [r["status"] for r in rows] == ["passed", "invested", "in_review"]   # lost / won / open
    assert rows[2]["company"] == "Zürich Robotics AG"
    assert [r["date"] for r in rows] == ["2024-08-15", "2024-12-03", "2025-02-02"]


def test_salesforce_month_first_dates_and_closed_stages():
    _, _, rows = load("salesforce_report.csv")
    assert [r["date"] for r in rows] == ["2024-05-14", "2024-09-02", "2024-01-20"]
    assert [r["status"] for r in rows] == ["in_review", "invested", "passed"]


@pytest.mark.parametrize("raw,expected", [
    ("Portfolio", "invested"), ("Invested", "invested"), ("Closed Won", "invested"), ("won", "invested"),
    ("Pass", "passed"), ("Passed - too early", "passed"), ("Declined", "passed"), ("Lost", "passed"),
    ("Rejected", "passed"), ("Closed Lost", "passed"), ("Not invested", "passed"), ("Not a fit", "passed"),
    ("Due Diligence", "in_review"), ("Term Sheet", "in_review"), ("IC", "in_review"), ("Lead In", "in_review"),
    ("", "seen"), (None, "seen"), ("   ", "seen"),
])
def test_status_synonyms(raw, expected):
    assert ci.map_status(raw) == expected


def test_mapping_override_and_validation():
    t = ci.load_table("hubspot_deals.xlsx", (FIX / "hubspot_deals.xlsx").read_bytes())
    m = ci.resolve_mapping(t, {"company": "Deal Name", "status": None})
    assert m["company"] == "Deal Name" and m["status"] is None
    rows = ci.normalize_rows(t, m)
    assert rows[0]["company"] == "Market One - Seed" and rows[0]["status"] == "seen"
    with pytest.raises(ci.ImportError_) as e:
        ci.resolve_mapping(t, {"company": "No Such Column"})
    assert e.value.status == 422
    with pytest.raises(ci.ImportError_):
        ci.resolve_mapping(t, {"ceo": "Deal Name"})


def test_requires_company_or_website():
    with pytest.raises(ci.ImportError_) as e:
        t = ci.load_table("x.csv", b"Amount,Probability\n100,0.5\n200,0.1\n")
        ci.resolve_mapping(t)
    assert e.value.code == "no_company_column"
    t = ci.load_table("x.csv", b"Domain\nfoo.com\nbar.io\n")      # website alone is enough
    assert ci.resolve_mapping(t)["website"] == "Domain"


# ---------------------------------------------------------------- file safety

def _xlsx(build) -> bytes:
    wb = openpyxl.Workbook()
    build(wb.active)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_formulas_are_never_evaluated():
    raw = _xlsx(lambda ws: [ws.append(["Company", "Website"]), ws.append(["=1+1", "a.com"]),
                            ws.append(['=HYPERLINK("http://evil.example","x")', "b.com"]), ws.append(["Real Co", "c.com"])])
    t = ci.load_table("f.xlsx", raw)
    rows = ci.normalize_rows(t, ci.resolve_mapping(t))
    # data_only=True returns cached values; openpyxl-written formulas have none, so nothing is computed
    assert [r["company"] for r in rows] == ["", "", "Real Co"]
    assert all("=" not in r["company"] for r in rows)


@pytest.mark.parametrize("name,raw", [
    ("legacy.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100),
    ("macro.xlsm", b"PK\x03\x04" + b"\x00" * 100),
    ("report.pdf", b"%PDF-1.7 ..."),
    ("binary.csv", b"\x00\x01\x02 not text"),
    ("fake.xlsx", b"company,website\nA,a.com\n"),
])
def test_rejects_other_file_types(name, raw):
    with pytest.raises(ci.ImportError_) as e:
        ci.load_table(name, raw)
    assert e.value.status == 415


def test_rejects_xlsx_with_macros():
    raw = _xlsx(lambda ws: ws.append(["Company"]))
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr("xl/vbaProject.bin", b"\x00" * 10)
    with pytest.raises(ci.ImportError_) as e:
        ci.load_table("sneaky.xlsx", buf.getvalue())
    assert e.value.status == 415


def test_rejects_zip_bomb():
    raw = _xlsx(lambda ws: ws.append(["Company"]))
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr("xl/padding.bin", b"\x00" * (65 * 1024 * 1024))   # compresses to ~64 KB
    assert len(buf.getvalue()) < 2 * 1024 * 1024
    with pytest.raises(ci.ImportError_) as e:
        ci.load_table("bomb.xlsx", buf.getvalue())
    assert e.value.status == 413


def test_row_limit_xlsx():
    raw = _xlsx(lambda ws: [ws.append(["Company"])] + [ws.append([f"C{i}"]) for i in range(5001)])
    with pytest.raises(ci.ImportError_) as e:
        ci.load_table("big.xlsx", raw)
    assert e.value.code == "too_many_rows"


def test_excel_dates_and_serials():
    raw = _xlsx(lambda ws: [ws.append(["Company", "Created"]), ws.append(["A", datetime(2024, 3, 5, 14, 0)])])
    t = ci.load_table("d.xlsx", raw)
    assert ci.normalize_rows(t, ci.resolve_mapping(t))[0]["date"] == "2024-03-05"
    assert ci.parse_date("45356") == "2024-03-05"          # serial number from a CSV re-export


def test_utf16_tab_separated_export():
    raw = "Company\tWebsite\tStatus\nZürich Robotics\tzr.ch\tPassed\n".encode("utf-16")
    t = ci.load_table("export.csv", raw)
    rows = ci.normalize_rows(t, ci.resolve_mapping(t))
    assert rows == [{"company": "Zürich Robotics", "website": "zr.ch", "status": "passed",
                     "raw_status": "Passed", "date": None}]
