# Seeding QDArchive – Part 1: Data Acquisition

**Student:** Sumon Kazi · Matriculation ID: 23293505
**Course:** SQ26 – Applied Software Engineering Seminar/Project
**Professor:** Dirk Riehle, FAU Erlangen-Nürnberg
**GitHub:** https://github.com/sumonkazi17636/Seeding_QDArchive

---

## Assigned Repositories

| ID | Name  | URL |
|----|-------|-----|
| 4  | QDR (Qualitative Data Repository) | https://data.qdr.syr.edu |
| 15 | ICPSR | https://www.icpsr.umich.edu |

---

## Results Summary

| Table        | Rows  |
|-------------|-------|
| REPOSITORIES | 2     |
| PROJECTS     | 232   |
| FILES        | 7,018 |
| KEYWORDS     | 794   |
| PERSON_ROLE  | 178   |
| LICENSES     | 122   |

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
│   ├── qdr_public_scraper.py    ← QDR: API-CALL with fileAccess:Public filter
│   ├── qdr_scraper.py           ← QDR: OAI-PMH fallback
│   └── icpsr_scraper.py         ← ICPSR: OAI-PMH (see Technical Challenges)
├── export/
│   ├── export_csv.py
│   └── csv/                     ← Generated CSVs
└── data/                        ← Downloaded files (not in Git; shared separately)
    └── qdr/{project_folder}/*.pdf, *.txt, *.xlsx ...
```

---

## Database Schema

Six tables exactly as specified by Professor Riehle.

**Enum values:**
- `FILES.status`: `SUCCEEDED` · `FAILED_LOGIN_REQUIRED` · `FAILED_SERVER_UNRESPONSIVE` · `FAILED_TOO_LARGE`
- `PERSON_ROLE.role`: `AUTHOR` · `UPLOADER` · `OWNER` · `OTHER` · `UNKNOWN`
- `download_method`: `API-CALL` (QDR) · `SCRAPING` (ICPSR)

---

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
python main.py --repo qdr --max 500   # QDR only
python main.py --max 500              # both repos
python main.py --export-only          # regenerate CSVs
```

---

## How the QDR Scraper Works

QDR runs on Dataverse and exposes a public REST Search API. The key discovery was that QDR's own search interface uses a `fileAccess:"Public"` filter parameter to show only datasets with openly downloadable files. The scraper uses this same filter in every API call:

```
GET https://data.qdr.syr.edu/api/search
    ?q=interview&type=dataset&fq=fileAccess:"Public"
```

For each matching dataset the scraper fetches full metadata (authors, keywords, license) via the Dataverse dataset API, retrieves the file list, and downloads every file not marked `restricted=True`. Results are recorded with the correct status enum. `download_method = API-CALL`.

---

## Technical Challenges (Data — not Programming)

### 1. QDR: Mixed Access Within "Public" Datasets

The `fileAccess:"Public"` filter identifies datasets where at least one file is public. However, individual files within those datasets can carry their own separate restrictions. A typical dataset has a publicly downloadable interview guide and consent form, but the actual interview transcripts are restricted. The API's per-file `restricted` field correctly identifies this. The scraper attempts every file and records the outcome honestly — which is why the FILES table contains both `SUCCEEDED` and `FAILED_LOGIN_REQUIRED` entries within the same project.

### 2. QDR: No .qdpx Files Publicly Accessible

The primary target file type — `.qdpx` (REFI-QDA format) — exists on QDR but is always individually restricted to registered users. No `.qdpx` or `.nvpx` files were successfully downloaded. This is a fundamental data access policy at QDR: sensitive qualitative analysis files are protected even when the surrounding project is publicly listed.

### 3. ICPSR: OAI-PMH Endpoint Returns HTTP 404

ICPSR's documented OAI-PMH endpoint (`https://www.icpsr.umich.edu/oai/provider`) returned HTTP 404 for all requests. The alternative endpoint found in ICPSR's own documentation (`https://pcms.icpsr.umich.edu/pcms/api/1.0/oai/studies`) also did not return usable data during the collection period. As a result, zero projects were collected from ICPSR. The REPOSITORIES table correctly records ICPSR as an assigned repository. This is a data infrastructure challenge — the endpoint information in public documentation did not match the live system.

### 4. ICPSR: File Downloads Require Institutional Login

Even when ICPSR study pages are publicly browsable, all data file downloads require login with an account linked to a member institution. Attempting to download without authentication redirects to a login page. Even if metadata collection had succeeded, file downloads would have been recorded as `FAILED_LOGIN_REQUIRED`.

### 5. Keyword Data Quality: Multi-value Strings

Both repositories store multiple subject terms in a single field, for example: `"interlanguage pragmatics, EFL learners, scoping review"`. Per the professor's primary rule (do not change data when downloading), these are stored as-is in the KEYWORDS table. Splitting and normalisation is a Part 2 task.

### 6. Inconsistent Date Formats

Upload dates appear in varying formats: ISO 8601, year-only, and human-readable strings. Stored as-is; normalisation deferred to Part 2.

### 7. Module Path Error During Development

During testing, two versions of `main.py` coexisted in the project. Running the newer `main.py` before `scrapers/qdr_public_scraper.py` was placed in the correct folder caused a `ModuleNotFoundError`. Resolved by placing the file in the scrapers subfolder. The final successful run collected all 232 projects.

---

## Submission

| Item | Status |
|---|---|
| `23293505-seeding.db` in repo root | ✅ |
| Git tag `part-1-release` | ✅ pushed |
| `data/` folder | Shared separately via FAUbox/Google Drive |