# Seeding QDArchive — Part 1: Data Acquisition

**Student ID:** 23293505  
**Course:** Applied Software Engineering Seminar / Project (SQ26)  
**Professor:** Dirk Riehle, FAU Erlangen — Professorship for Open-Source Software  
**GitHub:** https://github.com/sumonkazi17636/Seeding_QDArchive

---

## Overview

This repository implements Part 1 (Data Acquisition) of the Seeding QDArchive project. The goal is to scrape qualitative research projects from assigned repositories, download all associated files, and store structured metadata in a SQLite database.

**Assigned repositories:**
| # | Name | URL |
|---|------|-----|
| 1 | QDR Syracuse | https://data.qdr.syr.edu |
| 2 | ICPSR | https://www.icpsr.umich.edu |

---

## Submission Artefacts

| Artefact | Location |
|----------|----------|
| SQLite metadata database | `23293505-seeding.db` (repo root) |
| Downloaded files | FAUbox / Google Drive (link in submission form) |
| Git tag | `part-1-release` |

---

## Project Structure

```
Seeding_QDArchive/
│
├── 23293505-seeding.db          # SQLite metadata database (main submission)
├── main.py                      # Pipeline entry point
├── requirements.txt
├── README.md
│
├── db/
│   ├── schema.sql               # All 6 table definitions with enum constraints
│   └── database.py              # DB connection and insert helpers
│
├── pipeline/
│   └── downloader.py            # HTTP download engine (retries, failure classification)
│
├── scrapers/
│   ├── qdr_scraper.py           # QDR Syracuse — Dataverse REST API scraper
│   └── icpsr_scraper.py         # ICPSR — HTML scraper (see Technical Challenges)
│
├── export/
│   └── export_csv.py            # Exports all DB tables to CSV
│
├── scripts/
│   └── retry_failed.py          # Re-attempts FAILED_SERVER_UNRESPONSIVE downloads
│
└── data/
    ├── qdr-syracuse/            # Downloaded QDR files (one subfolder per project)
    └── icpsr/                   # Downloaded ICPSR files
        └── _cookies.txt         # (optional) Browser session cookies for ICPSR auth
```

---

## Database Schema

The SQLite database `23293505-seeding.db` contains six tables.

**Primary rule: Data is never modified during download. Quality issues are resolved in Part 2.**

### REPOSITORIES
| Column | Type |
|--------|------|
| id | INTEGER PK |
| name | TEXT |
| url | TEXT |

### PROJECTS
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| query_string | TEXT | Search query that found this project |
| repository_id | INTEGER FK | → REPOSITORIES |
| repository_url | TEXT | Top-level repo URL |
| project_url | TEXT | Full URL to the project page |
| version | TEXT | |
| title | TEXT | |
| description | TEXT | |
| language | TEXT | BCP 47 e.g. `en-US` |
| doi | TEXT | DOI URL |
| upload_date | DATE | |
| download_date | TIMESTAMP | When our download finished |
| download_repository_folder | TEXT | e.g. `qdr-syracuse` |
| download_project_folder | TEXT | e.g. `10.5064-F6NK3BXQ` |
| download_version_folder | TEXT | |
| download_method | TEXT | `SCRAPING` or `API-CALL` |

### FILES
| Column | Type | Enum values |
|--------|------|-------------|
| status | TEXT | `SUCCEEDED` · `FAILED_SERVER_UNRESPONSIVE` · `FAILED_LOGIN_REQUIRED` · `FAILED_TOO_LARGE` |

### KEYWORDS, PERSON_ROLE, LICENSES
- **PERSON_ROLE.role:** `AUTHOR` · `UPLOADER` · `OWNER` · `OTHER` · `UNKNOWN`
- **LICENSES.license:** stored as-is from source; best-effort normalised to CC0, CC BY, CC BY 4.0, CC BY-SA, CC BY-NC, CC BY-ND, CC BY-NC-ND, ODbL, ODC-By, PDDL

---

## Setup & Usage

### Requirements
- Python 3.10+
- Internet access

### Installation

```bash
git clone https://github.com/sumonkazi17636/Seeding_QDArchive.git
cd Seeding_QDArchive

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

### Running the Pipeline

```bash
# Run both scrapers
python main.py

# Run only one repository
python main.py --repo qdr
python main.py --repo icpsr

# Limit projects per repo (good for testing)
python main.py --max 50

# Export DB to CSV without re-scraping
python main.py --export-only

# Retry failed downloads
python scripts/retry_failed.py
python scripts/retry_failed.py --repo qdr-syracuse
```

### Enabling ICPSR File Downloads (Optional)

ICPSR requires a free account to download files. To enable:

1. Create a free account at https://www.icpsr.umich.edu
2. Log in in your browser
3. Export session cookies to `data/icpsr/_cookies.txt` (Netscape format) using a browser extension like [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
4. Re-run: `python main.py --repo icpsr`

Without cookies, all ICPSR file entries are recorded as `FAILED_LOGIN_REQUIRED` — metadata is still fully collected.

### File Structure on Disk

```
data/
  qdr-syracuse/
    10.5064-F6NK3BXQ/
      interview_data.qdpx
      transcript_01.pdf
  icpsr/
    study-37158/
      icpsr-37158.zip
```

---

## Technical Challenges

> This section documents **data challenges** encountered during acquisition (not programming issues), as required by the project specification.

### 1. ICPSR: No Public Download API — Login Wall

ICPSR does not offer a public REST API for bulk data access. Study metadata is accessible via public HTML pages, but all actual file downloads require a registered account. Unauthenticated download attempts result in an HTTP 302 redirect to a login page rather than a clean 401/403, making programmatic detection non-trivial.

**Impact:** All ICPSR file entries are recorded as `FAILED_LOGIN_REQUIRED` unless valid session cookies are provided. Metadata collection is unaffected.

### 2. QDR: Access-Controlled (Restricted) Datasets

Approximately 15–20% of QDR datasets are under controlled access — they require a formal data access agreement and return HTTP 403 for file downloads, even though their metadata is fully public. These are typically sensitive datasets involving human subjects.

**Impact:** Files in restricted datasets are recorded as `FAILED_LOGIN_REQUIRED`. Project metadata is still collected.

### 3. Inconsistent and Missing License Information

License strings are highly inconsistent across both repositories:

- **QDR** provides Creative Commons licenses but in varying formats: full URLs, short labels, or human-readable strings. Stored as-is per the no-modification rule.
- **ICPSR** often displays no explicit open license on public study pages. Many studies reference ICPSR-specific terms of use rather than standard open licenses. License field is NULL in these cases.

### 4. Large and Unavailable Files

Some qualitative archives include large audio/video recordings of interviews. Files exceeding the 500 MB threshold are recorded as `FAILED_TOO_LARGE`. Additionally, some file URLs return HTTP 404, suggesting files were removed after the dataset record was published — recorded as `FAILED_SERVER_UNRESPONSIVE`.

### 5. Missing or Incomplete Metadata Fields

Many projects are missing one or more expected fields:

- **Language:** Rarely declared explicitly in either repository.
- **Upload date:** Sometimes only year is available, not a full ISO date.
- **Keywords:** Some datasets have no keywords; others have comma-separated strings instead of individual terms (e.g., `"interview study, qualitative, health"`). These are stored raw; splitting is a Part 2 task.
- **Author names:** Some ICPSR studies list institutional names rather than individual persons, making role assignment ambiguous. `UNKNOWN` is used.

### 6. QDR Pagination Limit and Rate Limiting

The Dataverse Search API has a hard limit of 1000 results per query. For broad queries like "interview", the true result count may exceed this, meaning some projects are unreachable via a single query. Multiple targeted queries are used to maximise coverage. A 1-second courtesy delay is applied between all requests to avoid triggering rate limits.

---

## Git Tag

After the final commit:

```bash
git add .
git commit -m "Part 1: Data acquisition pipeline complete"
git tag part-1-release
git push origin main --tags
```
