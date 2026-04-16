# Seeding QDArchive – Part 1: Data Acquisition

**Student:** 23293505 | **Professor:** Dirk Riehle, FAU Erlangen-Nürnberg | **Course:** SQ26

---

## Assigned Repositories

| ID | Name  | URL |
|----|-------|-----|
| 1  | QDR   | https://data.qdr.syr.edu |
| 2  | ICPSR | https://www.icpsr.umich.edu |

---

## Structure

```
Seeding_QDArchive/
├── 23293505-seeding.db          ← SQLite submission file
├── main.py                      ← Pipeline entry point
├── requirements.txt
├── db/         schema.sql, database.py
├── scrapers/   qdr_scraper.py, icpsr_scraper.py
├── export/     export_csv.py
├── logs/       pipeline.log
└── data/       qdr/{project}/  icpsr/{study_id}/   (not in Git)
```

---

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Running

```bash
python main.py                  # both repos, max 1000 each
python main.py --repo qdr       # QDR only
python main.py --repo icpsr     # ICPSR only
python main.py --max 200        # smaller run for testing
python main.py --export-only    # just regenerate CSVs
```

## Submission

```bash
git add 23293505-seeding.db
git commit -m "Part 1 complete"
git tag part-1-release
git push origin main --tags
```

Upload `data/` folder to FAUbox or Google Drive.

---

## How the Scrapers Work

**QDR:** Uses the Dataverse **OAI-PMH** endpoint (`/oai?verb=ListRecords`) to bulk-harvest
all dataset metadata. A second pass uses the Dataverse Search API with qualitative keywords
for extra coverage. `download_method = API-CALL`.

**ICPSR:** Uses ICPSR's **OAI-PMH** endpoint (`/oai/provider`) to harvest metadata.
Records are filtered by qualitative keywords (interview, transcript, ethnograph, etc.)
in title/description/subjects. `download_method = API-CALL`.

---

## Technical Challenges (Data — not Programming)

### 1. Both Repositories Require Login for File Downloads

QDR and ICPSR use authentication walls for virtually all file downloads. QDR's
Dataverse file access endpoint (`/api/access/datafile/{id}`) returns HTTP 403 or
redirects to an HTML login page for unauthenticated requests. ICPSR requires users
to create a free account and accept per-study terms of use before any download.
All file download attempts are recorded honestly as `FAILED_LOGIN_REQUIRED` in the
FILES table. Metadata (title, description, authors, keywords, DOI, license) is
fully collected without authentication.

### 2. Most ICPSR Qualitative Data is Restricted-Use

Beyond login, many ICPSR qualitative studies carry additional "restricted-use"
flags. These require a signed data-use agreement and institutional approval
before access is granted — even with a valid account. This means that even if
login were achieved, a large fraction of qualitative datasets could still not be
downloaded without a separate approval process, which was outside the scope of
Part 1.

### 3. No .qdpx Files Publicly Accessible

The primary target file type (.qdpx, REFI-QDA format) exists on QDR but is
always behind the authentication wall. Zero .qdpx files were successfully
downloaded in Part 1. This is the most significant gap relative to the
project's stated goal of collecting QDA files.

### 4. Keyword Fields Contain Multi-value Strings (Data Quality)

Both repositories store multiple keywords in a single field, e.g.
`"interlanguage pragmatics, EFL learners, scoping review"`. Per the professor's
primary rule (do not change data), these are stored as-is. Splitting and
normalising keywords is a Part 2 task.

### 5. Inconsistent Date Formats

Upload/publication dates appear in many formats: ISO 8601 (`2023-10-17`),
year-only (`2023`), and human-readable (`October 17, 2023`). Stored as-is;
normalisation deferred to Part 2.

### 6. QDR Search Results Vary by Authentication Level

QDR's own documentation states that guest searches return fewer results than
authenticated searches. As a result, the dataset count collected here may be
lower than what a logged-in user would find, even using the same queries.

### 7. ICPSR DataCite Filter Returns Zero Results

An earlier scraper version used the DataCite REST API filtered to
`client-id=icpsr.umich`. This returned zero results because ICPSR's actual
DataCite client ID differs from this assumed value. The fix was to use
ICPSR's own OAI-PMH endpoint directly, which works correctly.
