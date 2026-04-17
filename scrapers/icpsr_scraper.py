"""
scrapers/icpsr_scraper.py
ICPSR (Inter-university Consortium for Political and Social Research, U of Michigan)

Uses OAI-PMH endpoint — this is the correct bulk method, NOT DataCite.
ICPSR's OAI-PMH: https://www.icpsr.umich.edu/oai/provider
Files: require institutional login → FAILED_LOGIN_REQUIRED (correctly recorded).

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

REPO_NAME = "icpsr"
REPO_URL  = "https://www.icpsr.umich.edu"
OAI_URL   = OAI_URL   = "https://www.icpsr.umich.edu/icpsrweb/ICPSR/oai/studies"
DATA_ROOT = Path(__file__).parent.parent / "data" / REPO_NAME

NS = {
    "oai":    "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc":     "http://purl.org/dc/elements/1.1/",
}

HEADERS = {
    "User-Agent": "SQ26-FAU-Student/1.0 (23293505@stud.uni-erlangen.de)",
    "Accept": "text/xml,application/xml,*/*",
}

# ICPSR OAI-PMH supports set-based filtering.
# We filter to qualitative / interview-related sets.
# If no sets available we harvest all and filter by keyword in description.
QUALITATIVE_KEYWORDS = {
    "interview", "qualitative", "transcript", "focus group",
    "ethnograph", "oral history", "grounded theory", "phenomenolog",
    "narrative", "thematic analysis", "participant observation",
    "in-depth interview", "case study",
}


def _get_xml(url, params, timeout=60):
    """GET with retry; returns parsed XML root or None."""
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                try:
                    return ET.fromstring(r.content), r
                except ET.ParseError as e:
                    log.error(f"XML parse error: {e}")
                    return None, r
            if r.status_code == 503:
                log.warning(f"503 – waiting 30s (attempt {attempt+1})")
                time.sleep(30)
            elif r.status_code == 429:
                log.warning("Rate limited – waiting 60s")
                time.sleep(60)
            else:
                log.warning(f"HTTP {r.status_code} from {url}")
                return None, r
        except requests.exceptions.RequestException as e:
            log.warning(f"Request error attempt {attempt+1}: {e}")
            time.sleep(10)
    return None, None


def _dc_vals(dc_el, tag):
    return [
        el.text.strip()
        for el in dc_el.findall(f"dc:{tag}", NS)
        if el.text and el.text.strip()
    ]


def _is_qualitative(meta: dict) -> bool:
    """Return True if project looks qualitative based on title/description/keywords."""
    text = " ".join([
        meta.get("title", ""),
        meta.get("description", ""),
        " ".join(meta.get("keywords", [])),
    ]).lower()
    return any(kw in text for kw in QUALITATIVE_KEYWORDS)


def _normalise_license(raw: str) -> str:
    mappings = {
        "cc0": "CC0", "cc-zero": "CC0",
        "cc by": "CC BY", "cc-by": "CC BY",
        "cc by 4.0": "CC BY 4.0", "cc-by-4.0": "CC BY 4.0",
        "cc by-sa": "CC BY-SA", "cc by-nc": "CC BY-NC",
        "cc by-nd": "CC BY-ND", "cc by-nc-nd": "CC BY-NC-ND",
        "odbl": "ODbL", "odc-by": "ODC-By", "pddl": "PDDL",
    }
    return mappings.get(raw.lower().strip(), raw)


def _parse_record(record) -> dict | None:
    """Parse one OAI-PMH record into a metadata dict."""
    header = record.find("oai:header", NS)
    if header is not None and header.attrib.get("status") == "deleted":
        return None

    identifier_el = record.find("oai:header/oai:identifier", NS)
    identifier    = identifier_el.text.strip() if identifier_el is not None and identifier_el.text else ""

    metadata = record.find("oai:metadata", NS)
    if metadata is None:
        return None

    # Try namespace-qualified dc element
    dc = metadata.find("oai_dc:dc", NS)
    if dc is None:
        # Fallback: find any dc element
        for child in metadata:
            if "dc" in child.tag.lower():
                dc = child
                break
    if dc is None:
        return None

    titles       = _dc_vals(dc, "title")
    descriptions = _dc_vals(dc, "description")
    creators     = _dc_vals(dc, "creator")
    subjects     = _dc_vals(dc, "subject")
    dates        = _dc_vals(dc, "date")
    identifiers  = _dc_vals(dc, "identifier")
    rights       = _dc_vals(dc, "rights")
    languages    = _dc_vals(dc, "language")

    # Extract study ID from identifier like "icpsr-study:12345" or URL
    study_id = ""
    proj_url = ""
    doi_url  = None
    for ident in identifiers:
        if "doi.org" in ident:
            doi_url = ident
        if "icpsr.umich.edu" in ident and "studies" in ident:
            proj_url = ident
            m = re.search(r"/studies/(\d+)", ident)
            if m:
                study_id = m.group(1)
    if not study_id:
        m = re.search(r"(\d{4,6})$", identifier)
        if m:
            study_id = m.group(1)
    if not proj_url and study_id:
        proj_url = f"{REPO_URL}/web/ICPSR/studies/{study_id}"
    if not proj_url:
        proj_url = f"{REPO_URL}/oai/{identifier}"

    license_str = ""
    for r_val in rights:
        if any(cc in r_val.upper() for cc in ["CC", "CREATIVE", "ODC", "PDDL", "PUBLIC DOMAIN", "LICENSE"]):
            license_str = _normalise_license(r_val)
            break

    upload_date = None
    for d in dates:
        m = re.search(r"\d{4}-\d{2}-\d{2}", d)
        if m:
            upload_date = m.group(0)
            break
        m = re.search(r"\d{4}", d)
        if m:
            upload_date = m.group(0)
            break

    return {
        "identifier":  identifier,
        "study_id":    study_id,
        "url":         proj_url,
        "doi":         doi_url,
        "title":       titles[0] if titles else identifier,
        "description": " ".join(descriptions) if descriptions else (titles[0] if titles else "No description"),
        "authors":     creators,
        "keywords":    subjects,
        "upload_date": upload_date,
        "license":     license_str,
        "language":    languages[0] if languages else "en",
    }


def _list_sets() -> list[str]:
    """Return available OAI set specs from ICPSR."""
    root, _ = _get_xml(OAI_URL, {"verb": "ListSets"})
    if root is None:
        return []
    sets = []
    for s in root.findall(".//oai:set", NS):
        spec_el = s.find("oai:setSpec", NS)
        if spec_el is not None and spec_el.text:
            sets.append(spec_el.text.strip())
    return sets


def _harvest_set(set_spec: str | None, repo_id: int, max_projects: int,
                 count_ref: list) -> None:
    """Harvest one OAI-PMH set (or all records if set_spec=None)."""
    params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
    if set_spec:
        params["set"] = set_spec
    token = None
    page  = 0

    while count_ref[0] < max_projects:
        if token:
            p = {"verb": "ListRecords", "resumptionToken": token}
        else:
            p = params

        root, resp = _get_xml(OAI_URL, p)
        if root is None:
            break

        page += 1
        records = root.findall(".//oai:record", NS)
        log.info(f"[ICPSR] set={set_spec or 'ALL'} page={page}: {len(records)} records")

        for rec in records:
            if count_ref[0] >= max_projects:
                return
            meta = _parse_record(rec)
            if not meta:
                continue
            if not _is_qualitative(meta):
                continue
            if db.project_exists(meta["url"]):
                continue

            folder = meta["study_id"] or re.sub(r"[^\w]", "_", meta["identifier"])[-40:]
            row = {
                "query_string":               set_spec or "oai-harvest",
                "repository_id":              repo_id,
                "repository_url":             REPO_URL,
                "project_url":                meta["url"],
                "version":                    None,
                "title":                      meta["title"],
                "description":                meta["description"],
                "language":                   meta["language"],
                "doi":                        meta["doi"],
                "upload_date":                meta["upload_date"],
                "download_date":              datetime.now(timezone.utc).isoformat(),
                "download_repository_folder": REPO_NAME,
                "download_project_folder":    folder,
                "download_version_folder":    None,
                "download_method":            "API-CALL",
            }
            project_id = db.insert_project(row)
            db.insert_keywords(project_id, meta["authors"])   # creators as authors
            for name in meta["authors"]:
                db.insert_person(project_id, name, "AUTHOR")
            db.insert_keywords(project_id, meta["keywords"])
            if meta["license"]:
                db.insert_license(project_id, meta["license"])

            # ICPSR file download always requires login
            db.insert_file(project_id, f"{folder}.zip", "zip", "FAILED_LOGIN_REQUIRED")
            count_ref[0] += 1
            log.info(f"[ICPSR] #{count_ref[0]} saved: {meta['title'][:60]}")

        token_el = root.find(".//oai:resumptionToken", NS)
        token = token_el.text.strip() if token_el is not None and token_el.text else None
        if not token:
            break
        time.sleep(2)


def run(repo_id: int, max_projects: int = 1000) -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    count_ref = [0]

    # Try to find a qualitative-specific set
    log.info("[ICPSR] Checking available OAI sets …")
    sets = _list_sets()
    log.info(f"[ICPSR] {len(sets)} sets found: {sets[:10]}")

    qual_sets = [s for s in sets if any(
        kw in s.lower() for kw in ["qualitative", "interview", "mixed"]
    )]

    if qual_sets:
        log.info(f"[ICPSR] Harvesting qualitative sets: {qual_sets}")
        for s in qual_sets:
            if count_ref[0] >= max_projects:
                break
            _harvest_set(s, repo_id, max_projects, count_ref)
    else:
        # No targeted sets — harvest ALL and filter by keyword
        log.info("[ICPSR] No specific qualitative set found. Harvesting all records with keyword filter …")
        _harvest_set(None, repo_id, max_projects, count_ref)

    log.info(f"[ICPSR] Done. {count_ref[0]} qualitative projects saved.")
    return count_ref[0]
