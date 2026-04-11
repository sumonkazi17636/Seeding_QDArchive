"""
scrapers/icpsr_scraper.py
Scraper for ICPSR (Inter-university Consortium for Political and Social Research).
https://www.icpsr.umich.edu

IMPORTANT – DATA CHALLENGE (documented in README):
  ICPSR does NOT provide a public REST API for bulk data access.
  - Metadata (study descriptions, authors, keywords) can be scraped from the
    public search results HTML pages.
  - Actual DATA FILE downloads require creating a free account and logging in.
    Downloads via curl/wget redirect to a login wall.
  - Consequently, files are recorded as FAILED_LOGIN_REQUIRED in the FILES table
    unless a valid session cookie is injected (see README for workaround).

  Workaround supported: if you export your browser session cookies to
  data/icpsr/_cookies.txt (Netscape format), this scraper will use them.

Student ID: 23293505
"""

import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from db.database import (
    insert_project, insert_file, insert_keywords,
    insert_persons, insert_licenses, project_exists,
)
from pipeline.downloader import download_file, get_json, SESSION, RATE_DELAY

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

BASE_URL        = "https://www.icpsr.umich.edu"
REPO_FOLDER     = "icpsr"
REPO_ID         = 2
DOWNLOAD_METHOD = "SCRAPING"      # HTML scraping for metadata

COOKIES_FILE    = Path(__file__).resolve().parents[1] / "data" / "icpsr" / "_cookies.txt"

SEARCH_QUERIES = [
    "interview",
    "qualitative research",
    "interview transcript",
    "focus group",
    "ethnography",
    "grounded theory",
]

PAGE_SIZE = 25    # ICPSR UI default

SEARCH_URL = f"{BASE_URL}/web/ICPSR/search/studies"


# ──────────────────────────────────────────────────────────────
# Cookie loading (optional – allows actual file downloads)
# ──────────────────────────────────────────────────────────────

def _load_cookies(session: requests.Session) -> bool:
    """Load Netscape-format cookies into session. Returns True if loaded."""
    if not COOKIES_FILE.exists():
        return False
    try:
        import http.cookiejar
        jar = http.cookiejar.MozillaCookieJar(str(COOKIES_FILE))
        jar.load(ignore_discard=True, ignore_expires=True)
        session.cookies.update(jar)
        print(f"  [icpsr] Loaded cookies from {COOKIES_FILE}")
        return True
    except Exception as exc:
        print(f"  [icpsr] Could not load cookies: {exc}")
        return False


# ──────────────────────────────────────────────────────────────
# HTML parsing helpers
# ──────────────────────────────────────────────────────────────

def _search_page(query: str, start: int = 0) -> BeautifulSoup | None:
    params = {
        "q":    query,
        "paging.startRow": start,
        "paging.rows":     PAGE_SIZE,
        "dataType":        "qualitative",   # filter to qualitative studies
    }
    try:
        resp = SESSION.get(SEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        time.sleep(RATE_DELAY)
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"  [icpsr] search error: {exc}")
        return None


def _parse_study_links(soup: BeautifulSoup) -> list[dict]:
    """Return list of {url, title, study_id} from a search results page."""
    results = []
    for a in soup.select("h2.study-title a, a.study-title"):
        href = a.get("href", "")
        if "/web/ICPSR/studies/" in href:
            study_id_match = re.search(r"/studies/(\d+)", href)
            study_id = study_id_match.group(1) if study_id_match else None
            full_url = href if href.startswith("http") else BASE_URL + href
            results.append({
                "url":      full_url,
                "title":    a.get_text(strip=True),
                "study_id": study_id,
            })
    return results


def _parse_total_count(soup: BeautifulSoup) -> int:
    """Extract total result count from search results page."""
    for el in soup.select("span.result-count, .results-count, h1"):
        text = el.get_text()
        m = re.search(r"([\d,]+)\s+stud", text)
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


def _fetch_study_page(url: str) -> BeautifulSoup | None:
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        time.sleep(RATE_DELAY)
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"  [icpsr] study page error {url}: {exc}")
        return None


def _parse_study_metadata(soup: BeautifulSoup, study_url: str) -> dict:
    """Extract all available metadata from a study detail page."""
    meta = {
        "title":       "",
        "description": None,
        "language":    None,
        "doi":         None,
        "upload_date": None,
        "persons":     [],
        "keywords":    [],
        "licenses":    [],
        "files":       [],
    }

    # Title
    title_el = soup.select_one("h1.study-title, h1")
    if title_el:
        meta["title"] = title_el.get_text(strip=True)

    # Abstract / description
    for sel in ["div.summary p", "div#summary", "section.summary"]:
        el = soup.select_one(sel)
        if el:
            meta["description"] = el.get_text(separator=" ", strip=True)[:5000]
            break

    # Principal investigators (= AUTHORS)
    for pi in soup.select("span.pi-name, .principal-investigator"):
        name = pi.get_text(strip=True)
        if name:
            meta["persons"].append({"name": name, "role": "AUTHOR"})

    # Keywords / subject terms
    for kw in soup.select("a.keyword, .keyword-link, span.subject-term"):
        meta["keywords"].append(kw.get_text(strip=True))

    # DOI / persistent URL
    doi_el = soup.select_one("a[href*='doi.org'], span.doi")
    if doi_el:
        meta["doi"] = doi_el.get("href") or doi_el.get_text(strip=True)

    # Release date
    for sel in ["span.release-date", "dd.release-date"]:
        date_el = soup.select_one(sel)
        if date_el:
            raw = date_el.get_text(strip=True)
            m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
            if m:
                meta["upload_date"] = m.group(1)
                break

    # License
    for sel in ["a[href*='creativecommons']", "span.license", "div.license"]:
        lic_el = soup.select_one(sel)
        if lic_el:
            lic_text = lic_el.get_text(strip=True) or lic_el.get("href", "")
            if lic_text:
                meta["licenses"].append(lic_text)
                break

    # File list – ICPSR lists files on the study page
    for file_row in soup.select("tr.file-row, div.file-item, li.file-item"):
        fname_el = file_row.select_one("a.file-name, span.file-name")
        if not fname_el:
            continue
        fname    = fname_el.get_text(strip=True)
        file_url = fname_el.get("href", "")
        if file_url and not file_url.startswith("http"):
            file_url = BASE_URL + file_url
        meta["files"].append({"name": fname, "url": file_url})

    return meta


# ──────────────────────────────────────────────────────────────
# Main scrape entry point
# ──────────────────────────────────────────────────────────────

def scrape(conn, max_projects: int = 300) -> None:
    """
    Run the ICPSR scraper.

    NOTE: Actual file downloads require login. If cookies are present at
          data/icpsr/_cookies.txt, file downloads are attempted.
          Otherwise all files are recorded as FAILED_LOGIN_REQUIRED.

    conn        : sqlite3.Connection
    max_projects: safety cap
    """
    print(f"\n{'='*60}")
    print(f"ICPSR Scraper  ({BASE_URL})")
    print(f"{'='*60}")

    has_auth = _load_cookies(SESSION)
    if not has_auth:
        print("  [warn] No cookies found. Files will be recorded as FAILED_LOGIN_REQUIRED.")
        print(f"  [hint] Export your ICPSR session cookies to: {COOKIES_FILE}")

    seen_ids  = set()
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

            soup = _search_page(query, start)
            if soup is None:
                break

            if total is None:
                total = _parse_total_count(soup)
                print(f"  total_count≈{total}")

            links = _parse_study_links(soup)
            if not links:
                break

            for link in links:
                if new_count >= max_projects:
                    break
                study_id = link["study_id"]
                if not study_id or study_id in seen_ids:
                    continue
                seen_ids.add(study_id)

                study_url = link["url"]
                if project_exists(conn, study_url):
                    print(f"  [dup] study {study_id} already in DB")
                    continue

                print(f"\n  [study] {study_id}  {link['title'][:60]}")

                study_soup = _fetch_study_page(study_url)
                if study_soup is None:
                    continue
                meta = _parse_study_metadata(study_soup, study_url)

                if not meta["title"]:
                    meta["title"] = link["title"]

                proj_folder = f"study-{study_id}"
                now_ts      = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                project_row = {
                    "query_string":               query,
                    "repository_id":              REPO_ID,
                    "repository_url":             BASE_URL,
                    "project_url":                study_url,
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

                # ── Files ──
                if meta["files"]:
                    for f in meta["files"]:
                        fname = f["name"]
                        furl  = f["url"]
                        ext   = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

                        if has_auth and furl:
                            status = download_file(
                                url=furl,
                                repo_folder=REPO_FOLDER,
                                project_folder=proj_folder,
                                filename=fname,
                            )
                        else:
                            status = "FAILED_LOGIN_REQUIRED"

                        insert_file(conn, project_id, fname, ext, status)
                else:
                    # No file list parsed from page —
                    # record a placeholder for the study itself
                    insert_file(conn, project_id,
                                f"icpsr-{study_id}.zip", "zip",
                                "FAILED_LOGIN_REQUIRED")

                new_count += 1
                print(f"    [recorded] project_id={project_id} ({new_count}/{max_projects})")

            # Pagination
            start += PAGE_SIZE
            if total and start >= total:
                break

    print(f"\n[icpsr] Done. {new_count} new projects recorded.")
