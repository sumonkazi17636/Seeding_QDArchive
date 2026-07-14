-- SQ26 Part 2 — Data Classification schema additions
-- Applied on top of a COPY of the Part 1 seeding database (schema.sql),
-- never on the original 23277555-seeding.db.

PRAGMA foreign_keys = ON;

ALTER TABLE PROJECTS ADD COLUMN type TEXT
    CHECK(type IN ('QDA_PROJECT', 'QD_PROJECT', 'OTHER_PROJECT', 'NOT_A_PROJECT'));

-- ISIC Rev. 5 classification (section+division, e.g. "J62") of the project
-- as a whole (the sum of its files), one row per project.
CREATE TABLE IF NOT EXISTS PROJECT_CLASSIFICATION (
    project_id            INTEGER PRIMARY KEY REFERENCES PROJECTS(id),
    primary_class_code    TEXT NOT NULL,
    primary_class_name    TEXT NOT NULL,
    secondary_class_code  TEXT,
    secondary_class_name  TEXT
);

-- ISIC Rev. 5 classification of each individual primary data file, one row
-- per file, for files belonging to QDA_PROJECT / QD_PROJECT projects.
CREATE TABLE IF NOT EXISTS FILE_CLASSIFICATION (
    file_id                INTEGER PRIMARY KEY REFERENCES FILES(id),
    primary_class_code    TEXT NOT NULL,
    primary_class_name    TEXT NOT NULL,
    secondary_class_code  TEXT,
    secondary_class_name  TEXT
);

-- Search tags derived from project metadata, one keyword-style tag per row
-- (same convention as KEYWORDS).
CREATE TABLE IF NOT EXISTS TAGS (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES PROJECTS(id),
    tag         TEXT NOT NULL
);
