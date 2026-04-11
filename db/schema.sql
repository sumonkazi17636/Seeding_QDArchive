-- QDArchive Seeding Project - SQLite Metadata Database Schema
-- Student ID: 23293505
-- Repositories: QDR Syracuse, ICPSR

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────────────────────
-- REPOSITORIES  (our own list of repos we scrape)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS REPOSITORIES (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL,
    url  TEXT    NOT NULL
);

-- ─────────────────────────────────────────────────────────────
-- PROJECTS  (one row = one research-project / dataset found)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS PROJECTS (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_string                TEXT,               -- the search query that found this project
    repository_id               INTEGER NOT NULL REFERENCES REPOSITORIES(id),
    repository_url              TEXT    NOT NULL,   -- top-level URL of repo, e.g. https://data.qdr.syr.edu
    project_url                 TEXT    NOT NULL,   -- full URL to this specific project/dataset page
    version                     TEXT,               -- version string if any
    title                       TEXT    NOT NULL,
    description                 TEXT,
    language                    TEXT,               -- BCP 47 e.g. "en-US"
    doi                         TEXT,               -- DOI URL e.g. https://doi.org/...
    upload_date                 DATE,               -- date of upload on source repo
    download_date               TIMESTAMP NOT NULL, -- when OUR download finished
    download_repository_folder  TEXT    NOT NULL,   -- e.g. "qdr-syracuse" or "icpsr"
    download_project_folder     TEXT    NOT NULL,   -- e.g. "FK2/XXXXX" or "37158"
    download_version_folder     TEXT,               -- version sub-folder if any
    download_method             TEXT    NOT NULL CHECK(download_method IN ('SCRAPING','API-CALL'))
);

-- ─────────────────────────────────────────────────────────────
-- FILES  (every file that belongs to a project)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS FILES (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES PROJECTS(id),
    file_name  TEXT    NOT NULL,
    file_type  TEXT    NOT NULL,  -- just the extension, lower-cased
    status     TEXT    NOT NULL CHECK(status IN (
                   'SUCCEEDED',
                   'FAILED_SERVER_UNRESPONSIVE',
                   'FAILED_LOGIN_REQUIRED',
                   'FAILED_TOO_LARGE'
               ))
);

-- ─────────────────────────────────────────────────────────────
-- KEYWORDS  (one row per keyword, linked to its project)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS KEYWORDS (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES PROJECTS(id),
    keyword    TEXT    NOT NULL
);

-- ─────────────────────────────────────────────────────────────
-- PERSON_ROLE  (authors, uploaders, owners per project)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS PERSON_ROLE (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES PROJECTS(id),
    name       TEXT    NOT NULL,
    role       TEXT    NOT NULL CHECK(role IN (
                   'AUTHOR','UPLOADER','OWNER','OTHER','UNKNOWN'
               ))
);

-- ─────────────────────────────────────────────────────────────
-- LICENSES  (one or more licenses per project)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS LICENSES (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES PROJECTS(id),
    license    TEXT    NOT NULL
    -- Valid values: CC0, CC BY, CC BY 4.0, CC BY-SA, CC BY-NC, CC BY-ND,
    --               CC BY-NC-ND, ODbL, ODbL-1.0, ODC-By, ODC-By-1.0, PDDL
    -- If original string differs, store it as-is (cleaned in Part 2)
);
