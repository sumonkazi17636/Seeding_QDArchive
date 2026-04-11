"""
scrapers/qdr_scraper.py
Scraper for the QDR Syracuse repository (data.qdr.syr.edu).

QDR runs on Dataverse. We use the public Dataverse Search API (no key required)
and the Data Access API for file downloads.

Key API endpoints:
  Search:    GET https://data.qdr.syr.edu/api/search?q=...&type=dataset&per_page=100&start=0
  Dataset:   GET https://data.qdr.syr.edu/api/datasets/:persistentId/?persistentId=doi:...
  Files:     GET https://data.qdr.syr.edu/api/datasets/:persistentId/versions/:latest/files
  Download:  GET https://data.qdr.syr.edu/api/access/datafile/{file_id}

Student ID: 23293505
"""

import re
import time
from datetime import datetime, timezone

from db.database import (
    insert_project, insert_file, insert_keywords,
    insert_persons, insert_licenses, project_exists,
)
from pipeline.downloader import download_file, get_json

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

BASE_URL        = "https://data.qdr.syr.edu"
REPO_FOLDER     = "qdr-syracuse"
REPO_ID         = 1
DOWNLOAD_METHOD = "API-CALL"

SEARCH_QUERIES = [
    "interview",
    "qualitative research",
    "qdpx",
    "interview transcript",
    "focus group",
    "ethnography",
    "grounded theory",
    "thematic analysis",
]

PAGE_SIZE = 100   # max per Dataverse API call


# ──────────────────────────────────────────────────────────────
# License normalisation (do NOT change original data —
# we store original string; Part 2 will canonicalise)
# ──────────────────────────────────────────────────────────────

def _normalise_license(raw: str) -> str:
    """Best-effort map to professor's enum values; keep original if no match."""
    r = raw.strip()
    # Try well-known mappings
    _map = {
        "CC0 1.0":            "CC0",
        "CC0":                "CC0",
        "CC BY 4.0":          "CC BY 4.0",
        "CC BY":              "CC BY",
        "CC BY-SA 4.0":       "CC BY-SA",
        "CC BY-SA":           "CC BY-SA",
        "CC BY-NC 4.0":       "CC BY-NC",
        "CC BY-NC":           "CC BY-NC",
        "CC BY-ND 4.0":       "CC BY-ND",
        "CC BY-ND":           "CC BY-ND",
        "CC BY-NC-ND 4.0":    "CC BY-NC-ND",
        "CC BY-NC-ND":        "CC BY-NC-ND",
        "ODbL":               "ODbL",
        "ODbL 1.0":           "ODbL-1.0",
        "ODC-By":             "ODC-By",
        "PDDL":               "PDDL",
    }
    return _map.get(r, r)  # fall back to original


# ──────────────────────────────────────────────────────────────
# API helpers
# ──────────────────────────────────────────────────────────────

def _search_datasets(query: str, start: int = 0) -> dict | None:
    url = f"{BASE_URL}/api/search"
    params = {
        "q":        query,
        "type":     "dataset",
        "per_page": PAGE_SIZE,
        "start":    start,
    }
    return get_json(url, params)


def _get_dataset_metadata(persistent_id: str) -> dict | None:
    url = f"{BASE_URL}/api/datasets/:persistentId/"
    return get_json(url, {"persistentId": persistent_id})


def _get_dataset_files(persistent_id: str) -> list:
    url = f"{BASE_URL}/api/datasets/:persistentId/versions/:latest/files"
    result = get_json(url, {"persistentId": persistent_id})
    if result and result.get("status") == "OK":
        return result.get("data", [])
    return []


def _extract_meta(ds_meta: dict) -> dict:
    """Pull structured fields from the Dataverse dataset metadata blob."""
    data = ds_meta.get("data", {})

    # Latest version fields
    latest = data.get("latestVersion", {})
    citation_block = {}
    for block in latest.get("metadataBlocks", {}).values():
        for field in block.get("fields", []):
            citation_block[field["typeName"]] = field

    def _get(field_name, sub=None):
        f = citation_block.get(field_name, {})
        val = f.get("value")
        if val is None:
            return None
        if sub and isinstance(val, list):
            results = []
            for item in val:
                v = item.get(sub, {}).get("value") if isinstance(item, dict) else None
                if v:
                    results.append(v)
            return results
        return val

    title       = _get("title") or "Untitled"
    description_list = _get("dsDescription", "dsDescriptionValue") or []
    description = " ".join(description_list) if description_list else None
    language    = (_get("language") or [None])[0]

    # Authors
    authors_raw = _get("author", "authorName") or []
    persons = [{"name": a, "role": "AUTHOR"} for a in authors_raw]

    # Keywords
    keywords_raw = _get("keyword", "keywordValue") or []
    subjects_raw = _get("subject") or []
    keywords = list(keywords_raw) + (subjects_raw if isinstance(subjects_raw, list) else [subjects_raw])

    # License
    license_str = latest.get("license", {})
    if isinstance(license_str, dict):
        license_str = license_str.get("name", "")
    licenses = [_normalise_license(license_str)] if license_str else []

    # Dates
    upload_date_raw = data.get("publicationDate") or latest.get("releaseTime")
    upload_date = None
    if upload_date_raw:
        try:
            upload_date = upload_date_raw[:10]  # YYYY-MM-DD
        except Exception:
            pass

    doi = data.get("persistentUrl") or None

    return {
        "title":       title,
        "description": description,
        "language":    language,
        "persons":     persons,
        "keywords":    keywords,
        "licenses":    licenses,
        "upload_date": upload_date,
        "doi":         doi,
    }


# ──────────────────────────────────────────────────────────────
# Main scrape entry point
# ──────────────────────────────────────────────────────────────

def scrape(conn, max_projects: int = 500) -> None:
    """
    Run the QDR scraper:
      1. For each query, paginate through the Dataverse Search API.
      2. For each unique dataset, fetch detailed metadata.
      3. Download all associated files.
      4. Record everything in the SQLite database.

    conn       : sqlite3.Connection from db.database.init_db()
    max_projects: safety cap — stop after this many NEW projects recorded.
    """
    print(f"\n{'='*60}")
    print(f"QDR Syracuse Scraper  ({BASE_URL})")
    print(f"{'='*60}")

    seen_ids  = set()  # persistent IDs already processed this run
    new_count = 0

    for query in SEARCH_QUERIES:
        if new_count >= max_projects:
            break
        print(f"\n[query] '{query}'")
        start = 0
        total = None

        while True:
            if new_count >= max_projects:
                break

            result = _search_datasets(query, start)
            if not result or result.get("status") != "OK":
                print(f"  [warn] no results or API error for query='{query}' start={start}")
                break

            data       = result.get("data", {})
            items      = data.get("items", [])
            if total is None:
                total = data.get("total_count", 0)
                print(f"  total_count={total}")

            if not items:
                break

            for item in items:
                if new_count >= max_projects:
                    break

                pid = item.get("global_id") or item.get("identifier")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                project_url = item.get("url", "")
                if not project_url:
                    continue

                # Skip if already in DB (idempotent across runs)
                if project_exists(conn, project_url):
                    print(f"  [dup] {pid} already in DB")
                    continue

                print(f"\n  [project] {pid}  {item.get('name','')[:60]}")

                # ── Fetch detailed metadata ──
                meta_resp = _get_dataset_metadata(pid)
                if not meta_resp:
                    print(f"    [warn] could not fetch metadata for {pid}")
                    continue
                meta = _extract_meta(meta_resp)

                # Build project folder name from PID (strip doi: prefix, replace / with -)
                proj_folder = re.sub(r"[^A-Za-z0-9_.\-]", "-", pid.replace("doi:", ""))

                now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                project_row = {
                    "query_string":               query,
                    "repository_id":              REPO_ID,
                    "repository_url":             BASE_URL,
                    "project_url":                project_url,
                    "version":                    None,
                    "title":                      meta["title"],
                    "description":                meta["description"],
                    "language":                   meta["language"],
                    "doi":                        meta["doi"],
                    "upload_date":                meta["upload_date"],
                    "download_date":              now_ts,
                    "download_repository_folder": REPO_FOLDER,
                    "download_project_folder":    proj_folder,
                    "download_version_folder":    None,
                    "download_method":            DOWNLOAD_METHOD,
                }
                project_id = insert_project(conn, project_row)
                insert_keywords(conn, project_id, meta["keywords"])
                insert_persons(conn,   project_id, meta["persons"])
                insert_licenses(conn,  project_id, meta["licenses"])

                # ── Download files ──
                files = _get_dataset_files(pid)
                print(f"    {len(files)} file(s) to download")
                for f in files:
                    fname    = f.get("dataFile", {}).get("filename", "unknown")
                    file_id  = f.get("dataFile", {}).get("id")
                    download_url = f"{BASE_URL}/api/access/datafile/{file_id}"

                    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

                    status = download_file(
                        url=download_url,
                        repo_folder=REPO_FOLDER,
                        project_folder=proj_folder,
                        filename=fname,
                    )
                    insert_file(conn, project_id, fname, ext, status)

                new_count += 1
                print(f"    [recorded] project_id={project_id} ({new_count}/{max_projects})")

            # Pagination
            start += PAGE_SIZE
            if start >= total:
                break

    print(f"\n[qdr] Done. {new_count} new projects recorded.")
