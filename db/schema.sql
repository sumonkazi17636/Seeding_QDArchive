-- SQ26 Seeding QDArchive — SQLite Schema
-- Student: 23293505
-- Do NOT change data when downloading; quality fixed in Part 2.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS REPOSITORIES (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL,
    url  TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS PROJECTS (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_string                TEXT,
    repository_id               INTEGER NOT NULL REFERENCES REPOSITORIES(id),
    repository_url              TEXT    NOT NULL,
    project_url                 TEXT    NOT NULL UNIQUE,
    version                     TEXT,
    title                       TEXT    NOT NULL,
    description                 TEXT    NOT NULL,
    language                    TEXT,
    doi                         TEXT,
    upload_date                 TEXT,
    download_date               TEXT    NOT NULL,
    download_repository_folder  TEXT    NOT NULL,
    download_project_folder     TEXT    NOT NULL,
    download_version_folder     TEXT,
    download_method             TEXT    NOT NULL
        CHECK(download_method IN ('SCRAPING','API-CALL'))
);

CREATE TABLE IF NOT EXISTS FILES (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES PROJECTS(id),
    file_name   TEXT    NOT NULL,
    file_type   TEXT    NOT NULL,
    status      TEXT    NOT NULL
        CHECK(status IN (
            'SUCCEEDED',
            'FAILED_SERVER_UNRESPONSIVE',
            'FAILED_LOGIN_REQUIRED',
            'FAILED_TOO_LARGE'
        ))
);

CREATE TABLE IF NOT EXISTS KEYWORDS (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES PROJECTS(id),
    keyword     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS PERSON_ROLE (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES PROJECTS(id),
    name        TEXT    NOT NULL,
    role        TEXT    NOT NULL
        CHECK(role IN ('AUTHOR','UPLOADER','OWNER','OTHER','UNKNOWN'))
);

CREATE TABLE IF NOT EXISTS LICENSES (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES PROJECTS(id),
    license     TEXT    NOT NULL
);
