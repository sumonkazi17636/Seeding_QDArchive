"""
scrapers/qdr_scraper.py
QDR (Qualitative Data Repository, Syracuse University)
Uses TWO methods:
  1. OAI-PMH  — bulk harvest all metadata quickly (no login needed)
  2. Dataverse Search API — targeted keyword queries for extra coverage

Files: attempted via Dataverse file access API.
       Most require login → recorded as FAILED_LOGIN_REQUIRED.

Student: 23293505  –  SQ26
"""
import re
import sys
import time
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import db.database as db

log = logging.getLogger(__name__)

REPO_NAME   = "qdr"
REPO_URL    = "https://data.qdr.syr.edu"
OAI_URL     = "https://data.qdr.syr.edu/oai"          # OAI-PMH endpoint
API_SEARCH  = "https://data.qdr.syr.edu/api/search"
API_DS      = "https://data.qdr.syr.edu/api/datasets"
DATA_ROOT   = Path(__file__).parent.parent / "data" / REPO_NAME

NS = {
    "oai":  "http://www.openarchives.org/OAI/2.0/",
    "dc":   "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}

HEADERS = {"User-Agent": "SQ26-FAU-Student/1.0 (23293505@stud.uni-erlangen.de)"}

# Queries for the Dataverse Search API pass (extra coverage)
SEARCH_QUERIES = [
    "qdpx", "interview qualitative", "qualitative data",
    "focus group", "ethnograph", "oral history", "transcript",
]


# ── helpers ────────────────────────────────────────────────────────────────

def _get(url, params=None, timeout=30):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                time.sleep(10)
            else:
                return r
        except requests.exceptions.RequestException as e:
            log.warning(f"Request error (attempt {attempt+1}): {e}")
            time.sleep(5)
    return None


def _text(el, tag, ns_key):
    found = el.find(f"{{{NS[ns_key]}}}{tag}")
    return found.text.strip() if found is not None and found.text else ""


def _normalise_license(raw: str) -> str:
    """Store as-is per professor's rule; normalise common CC names."""
    mappings = {
        "cc0": "CC0", "cc-zero": "CC0", "publicdomain": "CC0",
        "cc by": "CC BY", "cc-by": "CC BY",
        "cc by 4.0": "CC BY 4.0", "cc-by-4.0": "CC BY 4.0",
        "cc by-sa": "CC BY-SA", "cc-by-sa": "CC BY-SA",
        "cc by-nc": "CC BY-NC", "cc-by-nc": "CC BY-NC",
        "cc by-nd": "CC BY-ND", "cc-by-nd": "CC BY-ND",
        "cc by-nc-nd": "CC BY-NC-ND", "cc-by-nc-nd": "CC BY-NC-ND",
        "odbl": "ODbL", "odc-by": "ODC-By", "pddl": "PDDL",
    }
    key = raw.lower().strip()
    return mappings.get(key, raw)  # store as-is if unknown


def _try_download(file_id: int, fname: str, dest: Path) -> str:
    """Attempt download; detect login walls honestly."""
    url = f"{REPO_URL}/api/access/datafile/{file_id}"
    r = _get(url, timeout=60)
    if r is None:
        return "FAILED_SERVER_UNRESPONSIVE"
    if r.status_code in (401, 403):
        return "FAILED_LOGIN_REQUIRED"
    ct = r.headers.get("Content-Type", "")
    if "text/html" in ct:
        return "FAILED_LOGIN_REQUIRED"
    if r.status_code >= 500:
        return "FAILED_SERVER_UNRESPONSIVE"
    cl = int(r.headers.get("Content-Length", 0))
    if cl > 500 * 1024 * 1024:
        return "FAILED_TOO_LARGE"
    dest.mkdir(parents=True, exist_ok=True)
    with open(dest / fname, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    return "SUCCEEDED"


def _save_project(pid_str: str, meta: dict, query: str, repo_id: int):
    """Insert project + related rows into DB."""
    proj_url = meta.get("url") or f"{REPO_URL}/dataset.xhtml?persistentId={pid_str}"
    if db.project_exists(proj_url):
        return None

    folder = re.sub(r"[^\w\-]", "_", pid_str)
    row = {
        "query_string":               query,
        "repository_id":              repo_id,
        "repository_url":             REPO_URL,
        "project_url":                proj_url,
        "version":                    None,
        "title":                      meta.get("title") or "Untitled",
        "description":                meta.get("description") or meta.get("title") or "No description",
        "language":                   meta.get("language"),
        "doi":                        meta.get("doi"),
        "upload_date":                meta.get("upload_date"),
        "download_date":              datetime.now(timezone.utc).isoformat(),
        "download_repository_folder": REPO_NAME,
        "download_project_folder":    folder,
        "download_version_folder":    None,
        "download_method":            meta.get("method", "API-CALL"),
    }
    project_id = db.insert_project(row)

    for name in meta.get("authors", []):
        db.insert_person(project_id, name, "AUTHOR")
    db.insert_keywords(project_id, meta.get("keywords", []))
    if meta.get("license"):
        db.insert_license(project_id, meta["license"])

    # Attempt file downloads
    dest_folder = DATA_ROOT / folder
    files = meta.get("files", [])
    if files:
        for f in files:
            status = _try_download(f["id"], f["name"], dest_folder)
            ftype  = Path(f["name"]).suffix.lstrip(".").lower() or "bin"
            db.insert_file(project_id, f["name"], ftype, status)
            log.info(f"  [{status}] {f['name']}")
            time.sleep(0.3)
    else:
        db.insert_file(project_id, f"{folder}.zip", "zip", "FAILED_LOGIN_REQUIRED")

    return project_id


# ── METHOD 1: OAI-PMH harvest ──────────────────────────────────────────────

def _oai_list_records(resumption_token=None):
    """Fetch one page of OAI-PMH records. Returns (records_xml, next_token)."""
    if resumption_token:
        params = {"verb": "ListRecords", "resumptionToken": resumption_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
    r = _get(OAI_URL, params=params, timeout=60)
    if r is None:
        return [], None
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        log.error(f"XML parse error: {e}")
        return [], None

    records = root.findall(".//oai:record", NS)
    token_el = root.find(".//oai:resumptionToken", NS)
    next_token = token_el.text.strip() if token_el is not None and token_el.text else None
    return records, next_token


def _parse_oai_record(record) -> dict | None:
    """Parse one OAI-PMH <record> into a metadata dict."""
    header = record.find("oai:header", NS)
    if header is not None and header.attrib.get("status") == "deleted":
        return None

    identifier = ""
    id_el = record.find("oai:header/oai:identifier", NS)
    if id_el is not None and id_el.text:
        identifier = id_el.text.strip()

    metadata = record.find("oai:metadata", NS)
    if metadata is None:
        return None
    dc = metadata.find("oai_dc:dc", NS)
    if dc is None:
        # Try without namespace
        dc = metadata.find("{http://www.openarchives.org/OAI/2.0/oai_dc/}dc")
    if dc is None:
        return None

    def dc_vals(tag):
        return [el.text.strip() for el in dc.findall(f"dc:{tag}", NS) if el.text and el.text.strip()]

    title       = dc_vals("title")
    description = dc_vals("description")
    creators    = dc_vals("creator")
    subjects    = dc_vals("subject")
    dates       = dc_vals("date")
    identifiers = dc_vals("identifier")
    rights      = dc_vals("rights")
    languages   = dc_vals("language")

    doi_url = None
    proj_url = None
    for ident in identifiers:
        if "doi.org" in ident or ident.startswith("doi:"):
            doi_url = ident if ident.startswith("http") else "https://doi.org/" + ident.replace("doi:","")
        if "data.qdr.syr.edu" in ident:
            proj_url = ident

    if not proj_url and doi_url:
        proj_url = doi_url
    if not proj_url:
        proj_url = f"{REPO_URL}/dataset.xhtml?persistentId={identifier}"

    license_str = ""
    for r_val in rights:
        if any(cc in r_val.upper() for cc in ["CC", "CREATIVE", "ODC", "PDDL", "PUBLIC DOMAIN"]):
            license_str = _normalise_license(r_val)
            break

    return {
        "url":         proj_url,
        "doi":         doi_url,
        "title":       title[0] if title else identifier,
        "description": " ".join(description) or (title[0] if title else "No description"),
        "authors":     creators,
        "keywords":    subjects,
        "upload_date": dates[0][:10] if dates else None,
        "license":     license_str,
        "language":    languages[0] if languages else None,
        "files":       [],        # OAI gives no file list; we'll try API separately
        "method":      "API-CALL",
    }


def _oai_harvest(repo_id: int, max_projects: int) -> int:
    """Harvest all QDR projects via OAI-PMH."""
    log.info("[QDR/OAI] Starting OAI-PMH harvest …")
    count = 0
    token = None
    page  = 0

    while True:
        records, token = _oai_list_records(token)
        page += 1
        log.info(f"[QDR/OAI] Page {page}: {len(records)} records (token={'yes' if token else 'none'})")

        for rec in records:
            if count >= max_projects:
                log.info(f"[QDR/OAI] Reached limit ({max_projects})")
                return count
            meta = _parse_oai_record(rec)
            if not meta:
                continue
            pid = _save_project(meta["url"], meta, "oai-harvest", repo_id)
            if pid:
                count += 1
                log.info(f"[QDR/OAI] #{count} saved: {meta['title'][:60]}")

        time.sleep(1)
        if not token:
            break

    log.info(f"[QDR/OAI] Done. {count} projects saved.")
    return count


# ── METHOD 2: Dataverse Search API (fills gaps) ───────────────────────────

def _get_ds_files(persistent_id: str) -> list:
    url = f"{API_DS}/:persistentId/versions/:latest/files"
    r = _get(url, params={"persistentId": persistent_id})
    if r is None or r.status_code != 200:
        return []
    try:
        data = r.json().get("data", [])
        return [
            {"id": f["dataFile"]["id"], "name": f["dataFile"]["filename"]}
            for f in data if "dataFile" in f
        ]
    except Exception:
        return []


def _api_search_harvest(repo_id: int, max_extra: int) -> int:
    """Use Dataverse Search API for targeted queries to find extra projects."""
    log.info("[QDR/API] Running targeted keyword queries …")
    count = 0

    for query in SEARCH_QUERIES:
        start = 0
        while count < max_extra:
            r = _get(API_SEARCH, params={
                "q": query, "type": "dataset",
                "per_page": 25, "start": start,
                "sort": "date", "order": "desc",
            })
            if r is None:
                break
            try:
                data = r.json().get("data", {})
            except Exception:
                break
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                if count >= max_extra:
                    break
                pid  = item.get("global_id", "")
                purl = item.get("url") or f"{REPO_URL}/dataset.xhtml?persistentId={pid}"
                if db.project_exists(purl):
                    continue

                doi_url = f"https://doi.org/{pid[4:]}" if pid.startswith("doi:") else None
                lic_raw = ""
                try:
                    ds_r = _get(f"{API_DS}/:persistentId/", params={"persistentId": pid})
                    if ds_r and ds_r.status_code == 200:
                        ds_data = ds_r.json().get("data", {})
                        lv      = ds_data.get("latestVersion", {})
                        lic_obj = lv.get("license", {})
                        if isinstance(lic_obj, dict):
                            lic_raw = _normalise_license(lic_obj.get("name", ""))
                        time.sleep(0.5)
                except Exception:
                    pass

                files = _get_ds_files(pid) if pid else []
                time.sleep(0.5)

                meta = {
                    "url":         purl,
                    "doi":         doi_url,
                    "title":       item.get("name", "Untitled"),
                    "description": item.get("description", item.get("name", "No description")),
                    "authors":     [],
                    "keywords":    [],
                    "upload_date": (item.get("published_at") or "")[:10] or None,
                    "license":     lic_raw,
                    "language":    None,
                    "files":       files,
                    "method":      "API-CALL",
                }
                pid_saved = _save_project(pid, meta, query, repo_id)
                if pid_saved:
                    count += 1
                    log.info(f"[QDR/API] #{count} saved: {meta['title'][:60]}")

            start += 25
            time.sleep(1)

    return count


# ── main entry point ───────────────────────────────────────────────────────

def run(repo_id: int, max_projects: int = 1000) -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    n = _oai_harvest(repo_id, max_projects)
    # fill remaining slots with targeted API queries
    remaining = max_projects - n
    if remaining > 0:
        n += _api_search_harvest(repo_id, remaining)
    return n
