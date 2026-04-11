"""
db/database.py
Database helper module for the QDArchive seeding pipeline.
Student ID: 23293505
"""

import sqlite3
import os
from pathlib import Path

# Default DB path: repo root so it is committed
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "23293505-seeding.db"
SCHEMA_PATH     = Path(__file__).resolve().parent / "schema.sql"

REPOSITORIES = [
    {"id": 1, "name": "qdr-syracuse", "url": "https://data.qdr.syr.edu"},
    {"id": 2, "name": "icpsr",        "url": "https://www.icpsr.umich.edu"},
]


# ──────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────

def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ──────────────────────────────────────────────────────────────
# Initialisation
# ──────────────────────────────────────────────────────────────

def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create all tables (if not exist) and seed REPOSITORIES."""
    conn = get_connection(db_path)
    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    _seed_repositories(conn)
    conn.commit()
    print(f"[db] Initialised database at: {db_path}")
    return conn


def _seed_repositories(conn: sqlite3.Connection) -> None:
    for repo in REPOSITORIES:
        existing = conn.execute(
            "SELECT id FROM REPOSITORIES WHERE id = ?", (repo["id"],)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO REPOSITORIES (id, name, url) VALUES (?, ?, ?)",
                (repo["id"], repo["name"], repo["url"]),
            )


# ──────────────────────────────────────────────────────────────
# PROJECTS
# ──────────────────────────────────────────────────────────────

def insert_project(conn: sqlite3.Connection, data: dict) -> int:
    """
    Insert a project row.  Returns the new project id.
    `data` must have all required fields (see schema).
    """
    cur = conn.execute(
        """
        INSERT INTO PROJECTS (
            query_string, repository_id, repository_url, project_url,
            version, title, description, language, doi,
            upload_date, download_date,
            download_repository_folder, download_project_folder,
            download_version_folder, download_method
        ) VALUES (
            :query_string, :repository_id, :repository_url, :project_url,
            :version, :title, :description, :language, :doi,
            :upload_date, :download_date,
            :download_repository_folder, :download_project_folder,
            :download_version_folder, :download_method
        )
        """,
        data,
    )
    conn.commit()
    return cur.lastrowid


def project_exists(conn: sqlite3.Connection, project_url: str) -> bool:
    row = conn.execute(
        "SELECT id FROM PROJECTS WHERE project_url = ?", (project_url,)
    ).fetchone()
    return row is not None


# ──────────────────────────────────────────────────────────────
# FILES
# ──────────────────────────────────────────────────────────────

def insert_file(conn: sqlite3.Connection, project_id: int, file_name: str,
                file_type: str, status: str) -> int:
    cur = conn.execute(
        "INSERT INTO FILES (project_id, file_name, file_type, status) VALUES (?, ?, ?, ?)",
        (project_id, file_name, file_type.lower().lstrip("."), status),
    )
    conn.commit()
    return cur.lastrowid


# ──────────────────────────────────────────────────────────────
# KEYWORDS
# ──────────────────────────────────────────────────────────────

def insert_keywords(conn: sqlite3.Connection, project_id: int,
                    keywords: list[str]) -> None:
    rows = [(project_id, kw.strip()) for kw in keywords if kw.strip()]
    conn.executemany(
        "INSERT INTO KEYWORDS (project_id, keyword) VALUES (?, ?)", rows
    )
    conn.commit()


# ──────────────────────────────────────────────────────────────
# PERSON_ROLE
# ──────────────────────────────────────────────────────────────

_VALID_ROLES = {"AUTHOR", "UPLOADER", "OWNER", "OTHER", "UNKNOWN"}


def insert_person(conn: sqlite3.Connection, project_id: int,
                  name: str, role: str) -> int:
    role = role.upper() if role.upper() in _VALID_ROLES else "UNKNOWN"
    cur = conn.execute(
        "INSERT INTO PERSON_ROLE (project_id, name, role) VALUES (?, ?, ?)",
        (project_id, name.strip(), role),
    )
    conn.commit()
    return cur.lastrowid


def insert_persons(conn: sqlite3.Connection, project_id: int,
                   persons: list[dict]) -> None:
    """persons = [{"name": "...", "role": "AUTHOR"}, ...]"""
    for p in persons:
        insert_person(conn, project_id, p.get("name", ""), p.get("role", "UNKNOWN"))


# ──────────────────────────────────────────────────────────────
# LICENSES
# ──────────────────────────────────────────────────────────────

def insert_license(conn: sqlite3.Connection, project_id: int,
                   license_str: str) -> int:
    cur = conn.execute(
        "INSERT INTO LICENSES (project_id, license) VALUES (?, ?)",
        (project_id, license_str.strip()),
    )
    conn.commit()
    return cur.lastrowid


def insert_licenses(conn: sqlite3.Connection, project_id: int,
                    licenses: list[str]) -> None:
    for lic in licenses:
        if lic and lic.strip():
            insert_license(conn, project_id, lic)
