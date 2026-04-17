# Seeding QDArchive – Part 1: Data Acquisition

**Student:** Sumon Kazi · Matriculation ID: 23293505
**Course:** SQ26 – Applied Software Engineering Seminar/Project
**Professor:** Dirk Riehle, FAU Erlangen-Nürnberg
**GitHub:** https://github.com/sumonkazi17636/Seeding_QDArchive

---

## Assigned Repositories

| ID | Name | URL |
|----|------|-----|
| 4  | QDR (Qualitative Data Repository) | https://data.qdr.syr.edu |
| 15 | ICPSR | https://www.icpsr.umich.edu |

---

## Final Results Summary

| Table        | Rows   |
|--------------|--------|
| REPOSITORIES | 2      |
| PROJECTS     | 232    |
| FILES        | 20,517 |
| KEYWORDS     | 794    |
| PERSON_ROLE  | 178    |
| LICENSES     | 122    |

---

## Project Structure

```
Seeding_QDArchive/
├── 23293505-seeding.db          ← SQLite submission file (root of repo)
├── main.py                      ← Pipeline entry point
├── requirements.txt
├── README.md
├── db/
│   ├── schema.sql               ← Six-table schema
│   └── database.py              ← DB helpers
├── scrapers/
│   ├── qdr_scraper.py           ← QDR: OAI-PMH + Dataverse API + File Fetcher
│   └── icpsr_scraper.py         ← ICPSR: OAI-PMH (see Technical Challenges)
├── export/
│   ├── export_csv.py
│   └── csv/                     ← Generated CSVs
└── data/                        ← Downloaded files (not in Git)
    └── qdr/{project_folder}/*.pdf, *.txt, *.tab ...
```
---

## Database Schema

Six tables exactly as specified by Professor Riehle.

**Enum values:**
- `FILES.status`: `SUCCEEDED` · `FAILED_LOGIN_REQUIRED` · `FAILED_SERVER_UNRESPONSIVE` · `FAILED_TOO_LARGE`
- `PERSON_ROLE.role`: `AUTHOR` · `UPLOADER` · `OWNER` · `OTHER` · `UNKNOWN`
- `download_method`: `API-CALL`

---

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
python main.py --repo qdr --max 5000    # QDR only
python main.py --repo icpsr --max 5000  # ICPSR only
python main.py --max 5000               # both repos
python main.py --export-only            # regenerate CSVs only
```

---

## How the Scrapers Work

### QDR Scraper — Three Methods

**Method 1 — OAI-PMH Harvest:**
Bulk harvests all 232 project metadata records across 11 pages using the standard OAI-PMH protocol at `https://data.qdr.syr.edu/oai`. This gives complete coverage of all QDR projects but returns no individual file lists.

**Method 2 — Dataverse Search API:**
Runs targeted keyword queries (qualitative, interview, transcript, focus group, ethnography, oral history, narrative, case study, fieldwork, discourse, survey, election, political, health, education, gender, migration, conflict, governance, democracy, poverty) against `https://data.qdr.syr.edu/api/search` to find any additional projects not captured by OAI-PMH and to enrich existing records.

**Method 3 — File List Fetcher:**
After collecting all 232 projects, the scraper loops through every existing project, fetches the real per-file list from the Dataverse dataset API using each project's DOI, and attempts to download each individual file. This critical step raised the FILES count from 7,018 to 20,517 — adding 13,499 new file records across all 232 projects. Each file download is attempted and the honest outcome is recorded: `SUCCEEDED` for publicly accessible files, `FAILED_LOGIN_REQUIRED` for restricted files.

### ICPSR Scraper

The ICPSR scraper uses the OAI-PMH protocol at `https://www.icpsr.umich.edu/oai/provider`. Due to the technical challenges described below, zero ICPSR projects were successfully collected. The REPOSITORIES table correctly records ICPSR as an assigned repository with its URL.

---

## Technical Challenges

### 1. ICPSR OAI-PMH Endpoint Returns HTTP 404

The documented ICPSR OAI-PMH endpoint (`https://www.icpsr.umich.edu/oai/provider`) returned HTTP 404 for all requests throughout the collection period. Multiple alternative endpoints found in ICPSR documentation were also tested:
- `https://www.icpsr.umich.edu/icpsrweb/ICPSR/oai/studies` → HTTP 404
- `https://www.icpsr.umich.edu/icpsrweb/ICPSR/search/studies` → HTML block page

All failed. As a result, zero ICPSR projects were collected.

### 2. ICPSR Blocks Residential IP Addresses

Every request to ICPSR from a home network connection resulted in one of three errors:
- `HTTP 404` — endpoint not found or blocked
- `Connection timed out (connect timeout=30)` — IP blocked at network level
- `Expecting value: line 9 column 1` — server returning HTML block page instead of JSON/XML
- `Connection forcibly closed by remote host` — active connection reset

ICPSR is a university consortium that restricts automated API access to member institution networks. Without university VPN access (e.g. FAU network), programmatic collection from ICPSR is not possible. This was confirmed after testing multiple endpoint URLs, multiple HTTP headers, and multiple scraper implementations — all producing the same block errors.

### 3. ICPSR File Downloads Require Institutional Login

Even if metadata collection had succeeded, all ICPSR file downloads require a login account linked to a member institution. Any unauthenticated download attempt redirects to a login page and would be recorded as `FAILED_LOGIN_REQUIRED`. This is documented in ICPSR's own access policy.

### 4. QDR: Files Initially Missing from OAI Harvest

The OAI-PMH protocol returns project metadata but no individual file lists. The initial scraper run recorded only 7,018 placeholder file entries (one zip placeholder per project). Method 3 — the dedicated file-fetching pass — was added to retrieve actual file lists for all 232 projects via the Dataverse dataset API, increasing the FILES count to 20,517 and adding 13,499 real file records.

### 5. QDR: Mixed Access Within Projects

Many QDR projects contain both public and restricted files within the same dataset. A typical project has a publicly downloadable README, consent form, and interview guide, but the actual interview transcripts are individually restricted. The scraper attempts every file and records the outcome honestly — which is why the FILES table contains both `SUCCEEDED` and `FAILED_LOGIN_REQUIRED` entries within the same project.

### 6. QDR: No .qdpx Files Publicly Accessible

The primary qualitative file format `.qdpx` (REFI-QDA standard) exists on QDR but is always individually restricted to registered users. No `.qdpx` or `.nvpx` files were successfully downloaded. This is a fundamental QDR data access policy for sensitive qualitative analysis files.

### 7. Database Column Name Mismatch

During development, the file-fetching function queried `SELECT filename FROM files` but the actual column name in the FILES table is `file_name`. This caused an `sqlite3.OperationalError: no such column: filename` on the first run of Method 3. Fixed by correcting the column name in the SQL query. The correct schema was confirmed using `PRAGMA table_info(files)`.

### 8. QDR API Occasional Timeouts

During the file-fetching pass, occasional read timeouts occurred when fetching large file lists from QDR (`Read timed out. (read timeout=30)`). The scraper uses a 3-attempt retry loop with 5-second sleep between attempts. Projects that failed all 3 attempts were skipped and recorded with no new files. This affected approximately 2 of the 232 projects.

### 9. Keyword Data Quality: Multi-value Strings

Both repositories store multiple subject terms concatenated in a single field, for example: `"interlanguage pragmatics, EFL learners, scoping review"`. Per the professor's rule (do not change data when downloading), these are stored as-is in the KEYWORDS table. Splitting and normalisation is deferred to Part 2.

### 10. Inconsistent Date Formats

Upload dates appear in varying formats across projects: ISO 8601 (`2021-03-15`), year-only (`2019`), and human-readable strings. All dates are stored as-is without modification. Normalisation is deferred to Part 2.

---

## Submission Checklist

| Item | Status |
|------|--------|
| `23293505-seeding.db` in repo root | ✅ |
| Git tag `part-1-release` pushed | ✅ |
| REPOSITORIES rows | ✅ 2 |
| PROJECTS rows | ✅ 232 (complete QDR collection) |
| FILES rows | ✅ 20,517 |
| KEYWORDS rows | ✅ 794 |
| PERSON_ROLE rows | ✅ 178 |
| LICENSES rows | ✅ 122 |
| CSVs exported | ✅ |
| ICPSR recorded | ✅ (0 projects — blocked, documented above) |