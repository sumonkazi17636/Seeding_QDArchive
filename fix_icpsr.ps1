# Run this script from inside your repo folder:
# cd C:\Users\sumon\Desktop\Seeding_QDArchive
# powershell -ExecutionPolicy Bypass -File fix_icpsr.ps1

Write-Host "=== Replacing icpsr_scraper.py ===" -ForegroundColor Cyan

$content = @'
"""
scrapers/icpsr_scraper.py
ICPSR scraper using OAI-PMH public harvesting endpoint.
No login required for metadata. Files recorded as FAILED_LOGIN_REQUIRED.
Student ID: 23293505
"""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
import requests

from db.database import (
    insert_project, insert_file, insert_keywords,
    insert_persons, insert_licenses, project_exists,
)

BASE_URL        = "https://www.icpsr.umich.edu"
OAI_ENDPOINT    = "https://www.icpsr.umich.edu/icpsr-web/ICPSR/oai/repository"
REPO_FOLDER     = "icpsr"
REPO_ID         = 2
DOWNLOAD_METHOD = "API-CALL"
RATE_DELAY      = 2.0

NS = {
    "oai":    "http://www.openarchives.org/OAI/2.0/",
    "dc":     "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}

QUALITATIVE_KEYWORDS = {
    "interview", "qualitative", "focus group", "ethnograph",
    "grounded theory", "thematic analysis", "oral history",
    "transcript", "narrative", "participant observation",
    "in-depth interview", "fieldwork", "discourse analysis",
    "content analysis", "phenomenolog", "interpretive",
    "mixed method", "case study", "coding", "interviewee",
}


def _make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "QDArchiveSeedBot/1.0 (FAU Erlangen SQ26; OAI-PMH harvesting)",
        "Accept": "text/xml, application/xml, */*",
    })
    return s


def _oai_request(session, params):
    try:
        resp = session.get(OAI_ENDPOINT, params=params, timeout=60)
        time.sleep(RATE_DELAY)
        if resp.status_code != 200:
            print(f"  [oai] HTTP {resp.status_code}")
            return None
        return ET.fromstring(resp.content)
    except Exception as exc:
        print(f"  [oai] Request error: {exc}")
        return None


def _get_text(el, tag, ns):
    child = el.find(f"{ns}:{tag}", NS)
    return child.text.strip() if child is not None and child.text else None


def _get_all(el, tag, ns):
    return [c.text.strip() for c in el.findall(f"{ns}:{tag}", NS) if c.text and c.text.strip()]


def _is_qualitative(text):
    t = text.lower()
    return any(kw in t for kw in QUALITATIVE_KEYWORDS)


def _parse_record(record):
    meta = {
        "study_id": None, "title": None, "description": None,
        "language": None, "doi": None, "date": None,
        "creators": [], "subjects": [], "rights": [],
    }
    header = record.find("oai:header", NS)
    if header is not None:
        id_el = header.find("oai:identifier", NS)
        if id_el is not None and id_el.text:
            m = re.search(r"ICPSR(\d+)", id_el.text)
            if m:
                meta["study_id"] = m.group(1)

    dc = record.find(".//oai_dc:dc", NS)
    if dc is None:
        return meta

    meta["_text"]       = ET.tostring(dc, encoding="unicode")
    meta["title"]       = _get_text(dc, "title",       "dc")
    meta["description"] = _get_text(dc, "description", "dc")
    meta["language"]    = _get_text(dc, "language",    "dc")
    meta["creators"]    = _get_all(dc,  "creator",     "dc")
    meta["subjects"]    = _get_all(dc,  "subject",     "dc")
    meta["rights"]      = _get_all(dc,  "rights",      "dc")

    for d in _get_all(dc, "date", "dc"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", d)
        if m:
            meta["date"] = m.group(1); break
        m = re.search(r"\b(\d{4})\b", d)
        if m:
            meta["date"] = m.group(1); break

    for ident in _get_all(dc, "identifier", "dc"):
        if "doi.org" in ident:
            meta["doi"] = ident; break
        if ident.startswith("10."):
            meta["doi"] = f"https://doi.org/{ident}"; break

    if not meta["doi"] and meta["study_id"]:
        meta["doi"] = f"https://doi.org/10.3886/ICPSR{meta['study_id']}"

    return meta


def _save_project(conn, meta):
    sid         = meta["study_id"]
    proj_folder = f"study-{sid}"
    now_ts      = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    project_url = f"{BASE_URL}/web/ICPSR/studies/{sid}"

    row = {
        "query_string":               "OAI-PMH harvest (qualitative filter)",
        "repository_id":              REPO_ID,
        "repository_url":             BASE_URL,
        "project_url":                project_url,
        "version":                    None,
        "title":                      meta["title"] or f"ICPSR Study {sid}",
        "description":                (meta["description"] or "")[:5000] or None,
        "language":                   meta["language"],
        "doi":                        meta["doi"],
        "upload_date":                meta["date"],
        "download_date":              now_ts,
        "download_repository_folder": REPO_FOLDER,
        "download_project_folder":    proj_folder,
        "download_version_folder":    None,
        "download_method":            DOWNLOAD_METHOD,
    }
    pid = insert_project(conn, row)
    insert_keywords(conn, pid, meta["subjects"])
    insert_persons(conn, pid, [{"name": c, "role": "AUTHOR"} for c in meta["creators"]])
    for r in meta["rights"]:
        if r.strip():
            insert_licenses(conn, pid, [r.strip()[:200]])
    insert_file(conn, pid, f"ICPSR_{sid}.zip", "zip", "FAILED_LOGIN_REQUIRED")
    return pid


def scrape(conn, max_projects=500):
    print("=" * 60)
    print("ICPSR Scraper — OAI-PMH Public Harvesting")
    print(f"Endpoint: {OAI_ENDPOINT}")
    print("Metadata: public, no auth needed.")
    print("Files: FAILED_LOGIN_REQUIRED (ICPSR login wall).")
    print("=" * 60)

    session          = _make_session()
    new_count        = 0
    page_num         = 0
    resumption_token = None

    while new_count < max_projects:
        page_num += 1

        if resumption_token is None:
            params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
            print(f"\n[oai] Page 1 — sending initial OAI-PMH request ...")
        else:
            params = {"verb": "ListRecords", "resumptionToken": resumption_token}
            print(f"\n[oai] Page {page_num} — continuing with resumption token ...")

        root = _oai_request(session, params)
        if root is None:
            print("  [oai] No response — stopping.")
            break

        err = root.find("oai:error", NS)
        if err is not None:
            print(f"  [oai] Server error: {err.get('code')} — {err.text}")
            break

        list_records = root.find("oai:ListRecords", NS)
        if list_records is None:
            print("  [oai] No ListRecords element — stopping.")
            break

        records = list_records.findall("oai:record", NS)
        print(f"  [oai] Received {len(records)} records")

        page_saved = 0
        for record in records:
            if new_count >= max_projects:
                break

            header = record.find("oai:header", NS)
            if header is not None and header.get("status") == "deleted":
                continue

            meta = _parse_record(record)
            if not meta["study_id"]:
                continue

            combined = " ".join([
                meta.get("_text", ""),
                " ".join(meta["subjects"]),
                meta["description"] or "",
                meta["title"] or "",
            ])
            if not _is_qualitative(combined):
                continue

            project_url = f"{BASE_URL}/web/ICPSR/studies/{meta['study_id']}"
            if project_exists(conn, project_url):
                continue

            print(f"\n  [study] {meta['study_id']}  {(meta['title'] or '')[:60]}")
            pid = _save_project(conn, meta)
            new_count += 1
            page_saved += 1
            print(f"    [saved] project_id={pid} ({new_count}/{max_projects})")

        print(f"  [oai] Page {page_num}: {page_saved} saved | running total: {new_count}")

        token_el = list_records.find("oai:resumptionToken", NS)
        if token_el is not None and token_el.text and token_el.text.strip():
            resumption_token = token_el.text.strip()
            total  = token_el.get("completeListSize", "?")
            cursor = token_el.get("cursor", "?")
            print(f"  [oai] Repository: scanned {cursor} / {total} total records")
        else:
            print("  [oai] Harvest complete — no more pages.")
            break

    if new_count == 0:
        print("\n[icpsr] Zero records harvested — OAI-PMH endpoint may be down.")
        print("[icpsr] Recording a placeholder entry in the database.")
        _record_placeholder(conn)
    else:
        print(f"\n[icpsr] Done. {new_count} qualitative projects recorded via OAI-PMH.")


def _record_placeholder(conn):
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "query_string":               "OAI-PMH harvest",
        "repository_id":              REPO_ID,
        "repository_url":             BASE_URL,
        "project_url":                f"{BASE_URL}/web/ICPSR/search/studies?q=qualitative",
        "version":                    None,
        "title":                      "ICPSR — OAI-PMH Endpoint Unavailable",
        "description":                (
            "ICPSR is a JavaScript SPA that blocks unauthenticated scraping. "
            "OAI-PMH public endpoint was attempted but returned no data. "
            "See Technical Challenges 1 and 2 in README."
        ),
        "language":                   None,
        "doi":                        None,
        "upload_date":                None,
        "download_date":              now_ts,
        "download_repository_folder": REPO_FOLDER,
        "download_project_folder":    "oai-unavailable",
        "download_version_folder":    None,
        "download_method":            DOWNLOAD_METHOD,
    }
    pid = insert_project(conn, row)
    insert_file(conn, pid, "icpsr-oai.zip", "zip", "FAILED_LOGIN_REQUIRED")
    print(f"  [icpsr] Placeholder recorded (project_id={pid})")
'@

# Write the file
$content | Set-Content -Path "scrapers\icpsr_scraper.py" -Encoding UTF8
Write-Host "File written successfully!" -ForegroundColor Green

# Verify it worked
$first = Get-Content "scrapers\icpsr_scraper.py" | Select-Object -First 5
Write-Host "First 5 lines of new file:" -ForegroundColor Yellow
$first

Write-Host ""
Write-Host "Now running the ICPSR scraper..." -ForegroundColor Cyan
python main.py --repo icpsr --max 500

Write-Host ""
Write-Host "Committing to GitHub..." -ForegroundColor Cyan
git add .
git commit -m "Fix ICPSR: replace with OAI-PMH scraper, add ICPSR projects"
git push
