"""Read any CRM export (CSV or XLSX) and map it to company / website / status / date.

Deterministic rules only: no LLM ever sees the file. Nothing from the file is executed or
evaluated: CSV is parsed as text, and XLSX is read with openpyxl in read-only, data_only mode
(cached cell values only; formulas are never calculated, macros never run). XML parsing goes
through defusedxml, and the zip is checked for decompression bombs first. The file stays in
memory and is never written to disk.

Supported layouts include exports from Affinity, HubSpot, Attio, Salesforce, Pipedrive, DealCloud
and plain Excel trackers (title rows above the header, ; or tab separators, Excel dates).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from typing import Optional

from matching import normalize_domain

MAX_ROWS = 5000
MAX_COLS = 200
MAX_XLSX_UNCOMPRESSED = 64 * 1024 * 1024   # zip bomb guard for a <= 2 MB upload
HEADER_SCAN_ROWS = 15
FIELDS = ("company", "website", "status", "date")


class ImportError_(Exception):
    """A user-facing import problem: (http status, error code, message)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ------------------------------------------------------------------ header synonyms (normalized)

HEADER_SYNONYMS = {
    "company": [
        "company", "company name", "companies", "organization", "organization name", "organisation",
        "organisation name", "org", "org name", "account", "account name", "startup", "startup name",
        "portfolio company", "target", "target company", "business", "business name", "entity", "name",
        "deal organization", "deal organization name", "associated company", "company associated",
        "deal name", "opportunity name", "deal", "title",
    ],
    "website": [
        "website", "web site", "domain", "domains", "url", "urls", "web", "homepage", "home page",
        "company domain", "company domain name", "company website", "organization website",
        "organization domain", "website url", "company url", "primary domain", "site",
    ],
    "status": [
        "status", "stage", "deal stage", "pipeline stage", "stage name", "deal status", "list status",
        "outcome", "decision", "state", "pipeline status", "funnel stage", "status of deal", "result",
    ],
    "date": [
        "date", "date added", "added", "added on", "created", "created at", "created on", "create date",
        "created date", "creation date", "date created", "first contact", "date of first contact",
        "first contacted", "first seen", "sourced date", "date sourced", "received", "date received",
        "entry date", "opened", "close date", "last updated", "updated", "modified",
    ],
}
# Exact-match bonus ranks: earlier synonyms are more typical for the field.
_HEADER_RANK = {f: {s: i for i, s in enumerate(syns)} for f, syns in HEADER_SYNONYMS.items()}
# Columns that look like a name but describe a person or an owner, never the company.
PERSON_HEADER = re.compile(r"\b(first|last|full|contact|owner|person|founder|ceo|email|e mail|phone|"
                           r"assignee|user|created by|lead owner|partner|associate|analyst)\b")
DEAL_TITLE_HEADERS = {"deal name", "opportunity name", "deal", "title"}

# ------------------------------------------------------------------ status synonyms (documented in the contract)

PASSED_TERMS = [
    "pass", "passed", "declined", "decline", "lost", "closed lost", "rejected", "reject", "dead", "killed",
    "no go", "nogo", "turned down", "not interested", "not a fit", "no fit", "dropped", "not invested",
    "no investment", "abandoned", "dismissed",
]
INVESTED_TERMS = [
    "portfolio", "portfolio company", "portco", "invested", "investment made", "closed won", "won",
    "funded", "signed", "closed deal",
]


def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _has_term(text: str, terms: list[str]) -> bool:
    return any(re.search(rf"(^| ){re.escape(t)}( |$)", text) for t in terms)


def map_status(raw: Optional[str]) -> str:
    """invested | passed | in_review | seen.

    Passed terms are checked first, so "Not invested" or "Closed Lost" never count as invested.
    An empty cell (or no status column) means the company was only seen: "seen".
    Everything else (Due Diligence, IC, Term Sheet, Contacted, Lead...) is in_review.
    """
    text = _norm_text(raw or "")
    if not text:
        return "seen"
    if _has_term(text, PASSED_TERMS):
        return "passed"
    if _has_term(text, INVESTED_TERMS):
        return "invested"
    return "in_review"


# ------------------------------------------------------------------ cell values

DOMAIN_RE = re.compile(r"^(https?://)?(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,24}(:\d+)?(/\S*)?$", re.I)
ISO_FORMATS = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y/%m/%d",
               "%d %b %Y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y", "%Y-%m", "%b %Y"]
DAY_FIRST = ["%d.%m.%Y", "%d.%m.%Y %H:%M", "%d/%m/%Y", "%d/%m/%Y %H:%M", "%d-%m-%Y"]
MONTH_FIRST = ["%m/%d/%Y", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p", "%m-%d-%Y"]
NUMERIC_DATE = re.compile(r"^(\d{1,2})([./-])(\d{1,2})\2\d{4}")


def date_order(values: list[str]) -> str:
    """'day' or 'month' first for a whole column of d/m vs m/d dates.
    A part above 12 decides; if every value is ambiguous, dots mean day-first (European)
    and slashes month-first (US-style CRM exports such as Salesforce and HubSpot)."""
    seps = []
    for v in values:
        m = NUMERIC_DATE.match((v or "").strip())
        if not m:
            continue
        a, sep, b = int(m.group(1)), m.group(2), int(m.group(3))
        if a > 12:
            return "day"
        if b > 12:
            return "month"
        seps.append(sep)
    return "month" if seps and seps.count("/") > len(seps) / 2 else "day"


def cell_text(v) -> str:
    """Spreadsheet value -> plain text. Dates become ISO; nothing is evaluated."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def parse_date(s: str, order: str = "day") -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", s):            # Excel serial date that lost its format in a CSV
        n = float(s)
        if 20000 < n < 80000:
            return (date(1899, 12, 30) + timedelta(days=int(n))).isoformat()
        return None
    s2 = re.sub(r"\s*(UTC|GMT|[+-]\d{2}:?\d{2})$", "", s)
    for fmt in ISO_FORMATS + (DAY_FIRST + MONTH_FIRST if order == "day" else MONTH_FIRST + DAY_FIRST):
        try:
            return datetime.strptime(s2, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def looks_like_domain(s: str) -> bool:
    s = (s or "").strip()
    return bool(s) and " " not in s and "@" not in s and bool(DOMAIN_RE.match(s))


# ------------------------------------------------------------------ reading files

def sniff_kind(filename: str, raw: bytes) -> str:
    """'csv' or 'xlsx' from extension AND content; anything else is rejected (415)."""
    name = (filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in ("xls", "xlsm", "xlsb", "xltm", "ods", "numbers"):
        raise ImportError_(415, "unsupported_media_type",
                           f".{ext} is not supported: export the sheet as .xlsx or .csv")
    is_zip = raw[:4] == b"PK\x03\x04"
    if ext == "xlsx" or (is_zip and ext in ("", "csv")):
        if not is_zip:
            raise ImportError_(415, "unsupported_media_type", "file is not a valid .xlsx workbook")
        return "xlsx"
    if ext in ("csv", "txt", "tsv", ""):
        if b"\x00" in raw[:4096] and raw[:2] not in (b"\xff\xfe", b"\xfe\xff"):   # UTF-16 text has NULs
            raise ImportError_(415, "unsupported_media_type", "file is not a text CSV")
        return "csv"
    raise ImportError_(415, "unsupported_media_type", "upload a .csv or .xlsx file")


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("cp1252", errors="replace")


def read_csv(raw: bytes) -> tuple[list[list[str]], bool]:
    text = _decode(raw)
    lines = text.splitlines()
    simulated = any(l.lstrip().startswith("#") and "SIMULATED" in l.upper() for l in lines[:20])
    body = "\n".join(l for l in lines if not l.lstrip().startswith("#"))
    sample = body[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = max(",;\t|", key=lambda d: sample.count(d))
    rows = []
    for row in csv.reader(io.StringIO(body), delimiter=delim):
        if len(rows) > MAX_ROWS + HEADER_SCAN_ROWS:
            raise ImportError_(413, "too_many_rows", f"the file must have at most {MAX_ROWS} rows")
        rows.append([c.strip() for c in row[:MAX_COLS]])
    return rows, simulated


def read_xlsx(raw: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = set(z.namelist())
            if "xl/workbook.xml" not in names:
                raise ImportError_(415, "unsupported_media_type", "file is not a valid .xlsx workbook")
            if "xl/vbaProject.bin" in names:
                raise ImportError_(415, "unsupported_media_type", "workbooks with macros are not accepted")
            if sum(i.file_size for i in z.infolist()) > MAX_XLSX_UNCOMPRESSED:
                raise ImportError_(413, "too_large", "workbook expands to more than 64 MB")
    except zipfile.BadZipFile:
        raise ImportError_(415, "unsupported_media_type", "file is not a valid .xlsx workbook")
    import openpyxl   # read-only + data_only: cached values only, no formula evaluation
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True, keep_links=False)
    except ImportError_:
        raise
    except Exception:
        raise ImportError_(400, "unreadable_file", "could not read the .xlsx workbook")
    try:
        ws = wb.worksheets[0]
        rows = []
        for row in ws.iter_rows(values_only=True, max_col=MAX_COLS):
            if len(rows) > MAX_ROWS + HEADER_SCAN_ROWS:
                raise ImportError_(413, "too_many_rows", f"the file must have at most {MAX_ROWS} rows")
            rows.append([cell_text(v) for v in row])
    finally:
        wb.close()
    return rows


# ------------------------------------------------------------------ column detection

def _header_score(field: str, header: str) -> float:
    h = _norm_text(header)
    if not h or (field == "company" and PERSON_HEADER.search(h)):
        return 0.0
    if field != "company" and PERSON_HEADER.search(h) and not any(k in h for k in ("date", "status", "stage")):
        return 0.0
    rank = _HEADER_RANK[field]
    if h in rank:
        base = 3.0 - min(rank[h], 30) / 30            # exact synonym: 2.0 .. 3.0
        if field == "company" and h in DEAL_TITLE_HEADERS:
            base -= 1.2                                # deal titles ("Acme - Seed") are a weaker signal
        if field == "company" and h == "name":
            base -= 0.6
        return base
    tokens = set(h.split())
    for syn in rank:
        if len(syn) > 3 and set(syn.split()) <= tokens:
            return 1.5                                 # synonym contained, e.g. "Organization - Name"
    return 0.0


def _value_score(field: str, values: list[str]) -> float:
    vals = [v for v in values if v]
    if not vals:
        return 0.0
    n = len(vals)
    if field == "website":
        return 2.0 * sum(looks_like_domain(v) for v in vals) / n
    if field == "date":
        return 2.0 * sum(parse_date(v) is not None for v in vals) / n
    if field == "status":
        known = sum(map_status(v) in ("invested", "passed") or bool(re.search(
            r"(review|diligence|dd|sourc|screen|meeting|pitch|ic|term|lead|contact|qualif|negotiat|pipeline|"
            r"new|open|progress|hold|monitor|track|intro|prospect)", _norm_text(v))) for v in vals)
        decisions = sum(map_status(v) in ("invested", "passed") for v in vals)
        distinct = len(set(vals)) / n
        # Columns holding decisions (won/lost, passed, portfolio) beat pure pipeline-stage columns.
        return min(2.0, known / n + decisions / n) * (1.0 if distinct <= 0.5 else 0.5)
    if field == "company":
        texty = sum(bool(re.search(r"[A-Za-z]", v)) and not looks_like_domain(v) and parse_date(v) is None
                    and map_status(v) == "in_review" for v in vals)
        distinct = len(set(vals)) / n
        return 1.5 * texty / n * distinct
    return 0.0


def detect_header_row(rows: list[list[str]]) -> int:
    """Index of the header row among the first rows (skips report titles and blank lines)."""
    best, best_score = 0, -1.0
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        cells = [c for c in row if c]
        if len(cells) < 1:
            continue
        score = sum(max(_header_score(f, c) for f in FIELDS) for c in cells) + 0.2 * len(cells)
        if score > best_score + 1e-9:
            best, best_score = i, score
    return best


def detect_mapping(headers: list[str], rows: list[list[str]]) -> dict[str, Optional[str]]:
    """Field -> header, from header synonyms (up to 3 points) plus sample values (up to 2 points)."""
    sample = rows[:200]
    scores = []
    for j, h in enumerate(headers):
        col = [r[j] if j < len(r) else "" for r in sample]
        for f in FIELDS:
            hs = _header_score(f, h)
            vs = _value_score(f, col)
            if f == "company" and hs == 0 and vs < 1.0:
                continue
            total = hs + vs
            if total >= 1.6 and (hs > 0 or vs >= 1.4):
                scores.append((total, hs, f, j))
    mapping: dict[str, Optional[str]] = {f: None for f in FIELDS}
    used = set()
    for total, hs, f, j in sorted(scores, key=lambda x: (-x[0], -x[1], FIELDS.index(x[2]), x[3])):
        if mapping[f] is None and j not in used:
            mapping[f] = headers[j]
            used.add(j)
    return mapping


# ------------------------------------------------------------------ public entry point

def load_table(filename: str, raw: bytes) -> dict:
    """Parse an upload into {'kind', 'headers', 'rows', 'simulated'} (rows below the header)."""
    kind = sniff_kind(filename, raw)
    if kind == "csv":
        rows, simulated = read_csv(raw)
    else:
        rows, simulated = read_xlsx(raw), False
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        raise ImportError_(422, "empty_file", "the file has no rows")
    h = detect_header_row(rows)
    width = max(len(r) for r in rows[h:h + 50])
    headers = [(rows[h][j] if j < len(rows[h]) else "") or f"Column {j + 1}" for j in range(width)]
    data = rows[h + 1:]
    if len(data) > MAX_ROWS:
        raise ImportError_(413, "too_many_rows", f"the file must have at most {MAX_ROWS} rows")
    return {"kind": kind, "headers": headers, "rows": data, "simulated": simulated}


def resolve_mapping(table: dict, override: Optional[dict] = None) -> dict[str, Optional[str]]:
    mapping = detect_mapping(table["headers"], table["rows"])
    if override:
        unknown = [v for v in override.values() if v and v not in table["headers"]]
        bad_keys = [k for k in override if k not in FIELDS]
        if unknown or bad_keys:
            raise ImportError_(422, "invalid_mapping",
                               f"mapping must use fields {list(FIELDS)} and existing column headers")
        for k, v in override.items():
            mapping[k] = v or None
    if not mapping["company"] and not mapping["website"]:
        raise ImportError_(422, "no_company_column",
                           "could not find a company name or website column; send a mapping")
    return mapping


def normalize_rows(table: dict, mapping: dict) -> list[dict]:
    """Rows as {company, website, status, raw_status, date}; rows without company and website are dropped."""
    idx = {f: table["headers"].index(h) for f, h in mapping.items() if h}

    def get(row, f):
        j = idx.get(f)
        return row[j].strip() if j is not None and j < len(row) and row[j] else ""

    order = date_order([get(r, "date") for r in table["rows"][:500]]) if "date" in idx else "day"
    out = []
    for row in table["rows"]:
        company, website = get(row, "company"), get(row, "website")
        if not company and not website:
            continue
        if website and not looks_like_domain(website):
            website = ""
        raw_status = get(row, "status")
        out.append({"company": company, "website": normalize_domain(website) or website, "status": map_status(raw_status),
                    "raw_status": raw_status, "date": parse_date(get(row, "date"), order)})
    return out
