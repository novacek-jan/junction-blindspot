#!/usr/bin/env python3
"""Generate the CRM export fixtures (run once; the outputs are committed).

    backend/.venv/bin/python backend/tests/fixtures/make_fixtures.py
Company names/websites match the synthetic test DB in tests/test_api.py.
"""
from datetime import datetime
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent

# 1. Affinity list export: "Organization Name", website, Status, Date Added (+ an owner column)
(HERE / "affinity_export.csv").write_text(
    "Organization Name,Organization Website,Status,Date Added,Owner\n"
    "Market One GmbH,https://www.market-one.de,Portfolio,2024-05-01 10:12:00,Anna Example\n"
    "Market Two,,Passed,2024-12-01 09:00:00,Ben Example\n"
    "Unrelated Startup,unrelated.io,Diligence,2024-01-15 08:30:00,Anna Example\n"
    ",,,,\n"
    "Lumen Labs,lumenlabs.ai,,2024-02-02 12:00:00,Ben Example\n", encoding="utf-8")

# 2. HubSpot deals export (xlsx): deal name AND associated company; real datetime cells
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Deals"
ws.append(["Deal Name", "Associated Company", "Company Domain Name", "Deal Stage", "Create Date", "Deal owner"])
ws.append(["Market One - Seed", "Market One GmbH", "market-one.de", "Closed won", datetime(2024, 4, 2, 9, 30), "Anna"])
ws.append(["Market Two - Series A", "Market Two", "market-two.se", "Closed lost", datetime(2024, 11, 20), "Ben"])
ws.append(["Market Three - Seed", "Market Three", "m3.fi", "Due Diligence", datetime(2024, 8, 1), "Anna"])
ws.append(["Faraway - Seed", "Faraway Inc", "faraway.com", "Appointment scheduled", datetime(2024, 1, 5), "Ben"])
wb.save(HERE / "hubspot_deals.xlsx")

# 3. Pipedrive deals export: semicolon separated, cp1252, both "Deal - Stage" and "Deal - Status"
(HERE / "pipedrive_deals.csv").write_bytes(
    ("Deal - Title;Organization - Name;Deal - Stage;Deal - Status;Deal - Deal created;Person - Name\n"
     "Seed round;Market Three;Proposal Made;lost;15.08.2024;Jörg Müller\n"
     "Series A;Market Two;Negotiations Started;won;03.12.2024;Sara Svensson\n"
     "Pre-seed;Zürich Robotics AG;Lead In;open;02.02.2025;Lukas Meier\n").encode("cp1252"))

# 4. Plain Excel tracker (xlsx): title rows above the header, no status column
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Tracker"
ws.append(["Dealflow tracker Q3 2024"])
ws.append([])
ws.append(["Startup", "URL", "Sector", "First contact", "Notes"])
ws.append(["Market One", "http://market-one.de/about", "SaaS", datetime(2024, 7, 1), "warm intro"])
ws.append(["Own Two", "own2.se", "Fintech", datetime(2024, 7, 9), "portfolio follow-on"])
ws.append(["Nobody Knows Ltd", "", "Health", datetime(2024, 8, 12), ""])
wb.save(HERE / "excel_tracker_no_status.xlsx")

# 5. Salesforce opportunity report: US dates, Closed Won / Closed Lost, owner column
(HERE / "salesforce_report.csv").write_text(
    '"Account Name","Website","Stage","Created Date","Opportunity Owner"\n'
    '"Market One GmbH","market-one.de","Qualification","5/14/2024","Anna Example"\n'
    '"Market Three","www.m3.fi","Closed Won","9/2/2024","Ben Example"\n'
    '"Own One","own1.de","Closed Lost","1/20/2024","Anna Example"\n', encoding="utf-8")

# 6. Attio list export: "Name", "Domains", "List status", "Added at"
(HERE / "attio_list.csv").write_text(
    "Record ID,Name,Domains,List status,Added at\n"
    "a1,Market Two,market-two.se,Rejected,2025-01-11T10:00:00Z\n"
    "a2,Market One GmbH,market-one.de,Invested,2024-03-03T08:00:00Z\n"
    "a3,Open Source Co,opensource.dev,Screening,2025-02-20T15:30:00Z\n", encoding="utf-8")
print("fixtures written to", HERE)
