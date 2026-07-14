# Seeding QDArchive – Part 1: Data Acquisition + Part 2: Data Classification

**Student:** Sumon Kazi · Matriculation ID: 23293505
**Programme:** MSc in Data Science
**Course:** SQ26 Seeding QDArchive — Applied Software Engineering Project (ASEP) · 10 ECTS
**Scope:** Part 1 Data Acquisition + Part 2 Data Classification
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

# Part 2 — Data Classification

*This is the classification half of the 10 ECTS Applied Software Engineering
Project (Acquisition + Classification).*

Part 2 turns the Part 1 seeding database into a **classification database**:
every project is assigned a *project type*, and every qualitative-data / QDA
project is classified against the UN **ISIC Rev. 5** taxonomy (down to the
division level), for both the project as a whole and its primary data files.

## What it produces

| Output | File |
|--------|------|
| Classification database (tag `classification-results`) | `23293505-sq26-classification.db` |
| Results table (Step 4c) | `export/23293505-sq26-classification.xlsx` |
| Professional PDF report (Step 4d) | `reports/23293505-sq26-classification-report.pdf` |

## Pipeline

```bash
python classification/run_classification.py      # build the classification .db
python export/export_classification_table.py     # write the XLSX results table
python reports/generate_classification_report.py # write the PDF report
```

`run_classification.py` copies `23293505-seeding.db` to
`23293505-sq26-classification.db` (the Part 1 database is never modified),
applies `db/schema_classification.sql`, deduplicates, assigns `PROJECTS.type`,
and runs the ISIC classifier — populating the new `PROJECT_CLASSIFICATION`,
`FILE_CLASSIFICATION` and `TAGS` tables. The console output prints the
by-repository × project-type distribution and the dominant class (needed for
the course's Google Form, Step 4b).

## Schema additions (`db/schema_classification.sql`)

- `PROJECTS.type` — `QDA_PROJECT` / `QD_PROJECT` / `OTHER_PROJECT` / `NOT_A_PROJECT`
- `PROJECT_CLASSIFICATION` — primary/secondary ISIC class per project
- `FILE_CLASSIFICATION` — primary/secondary ISIC class per primary data file
- `TAGS` — search tags (top TF-IDF terms) per project

## Method

- **Project type** is derived from the file *extensions* present in each
  project (`classification/file_types.py`, `classification/project_type.py`).
  QDA detection is based on a file of a QDA type being *listed* in the project
  (e.g. `.qdpx`, `.nvp`, `.nvpx`), independent of whether that restricted file
  could be downloaded in Part 1.
- **ISIC classification** (`classification/isic_classifier.py`) uses TF-IDF +
  cosine similarity between each project's metadata text (title + description +
  keywords) and the 87 ISIC Rev. 5 division reference documents. Crucially,
  each division is represented not by its short title alone but by an
  **enriched reference document** built from its section name plus the names of
  *all* its official groups and classes (from the full ISIC hierarchy,
  `classification/isic_rev5_full.csv`, sourced from the UN Statistics
  Division). This grounds each division in its own official vocabulary and
  markedly improves the match (e.g. it raises the recall of *N72 Scientific
  research and development* and cuts spurious manufacturing matches versus a
  title-only baseline). The method is offline, deterministic and
  reproducible — no external API or model.

## Results (this dataset)

| Project type | Count | Share |
|--------------|-------|-------|
| QDA_PROJECT   | 4   | 1.7%  |
| QD_PROJECT    | 221 | 95.3% |
| OTHER_PROJECT | 7   | 3.0%  |
| NOT_A_PROJECT | 0   | 0.0%  |

225 QDA/QD projects were classified into **51 distinct ISIC Rev. 5 divisions**.
Top classes: **R86 Human health activities** (29), **Q85 Education** (28),
**N72 Scientific research and development** (17), R87 Residential care (13),
N73 Market research / public relations (11) — a profile consistent with QDR's
qualitative health and social-science focus. All 232 projects are from QDR;
ICPSR yielded none in Part 1 (see challenges above).

## Validation

Because no ground-truth labels exist, classification quality was assessed by a
**manual review of a reproducible 30-project sample** (Appendix A of the PDF
report). The primary division was judged appropriate for ~60% of the sample and
appropriate-or-defensible for ~73%, with a well-understood failure mode
(generic tokens such as "paper"/"food" occasionally pulling a project toward a
manufacturing division). This is reported honestly as an indicative figure.

## Limitations

Classification uses project **metadata only** (file text was not parsed), and
ISIC describes economic activities rather than research subjects, so some
lexical matches are approximate. These caveats are documented in the PDF
report (Sections 5–7). Each primary data file inherits its project's class.

---

## Submission Checklist

| Item | Status |
|------|--------|
| **Part 1** | |
| `23293505-seeding.db` in repo root | ✅ |
| Git tag `part-1-release` pushed | ✅ |
| REPOSITORIES / PROJECTS / FILES rows | ✅ 2 / 232 / 20,517 |
| KEYWORDS / PERSON_ROLE / LICENSES rows | ✅ 794 / 178 / 122 |
| ICPSR recorded | ✅ (0 projects — blocked, documented above) |
| **Part 2** | |
| `23293505-sq26-classification.db` in repo root | ✅ |
| Git tag `classification-results` | ✅ |
| XLSX results table | ✅ `export/23293505-sq26-classification.xlsx` |
| PDF report | ✅ `reports/23293505-sq26-classification-report.pdf` |
| Google Form (Step 4b) | ⬜ submit using console summary |
| Moodle upload (XLSX + PDF) | ⬜ |