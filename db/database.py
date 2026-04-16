"""
db/database.py  –  SQ26 Student 23293505
"""
import sqlite3
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DB_PATH  = ROOT / "23293505-seeding.db"
SCHEMA   = Path(__file__).parent / "schema.sql"


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    sql = SCHEMA.read_text(encoding="utf-8")
    with conn() as c:
        c.executescript(sql)
    print(f"[db] Ready: {DB_PATH}")


def upsert_repo(name: str, url: str) -> int:
    with conn() as c:
        row = c.execute("SELECT id FROM REPOSITORIES WHERE url=?", (url,)).fetchone()
        if row:
            return row["id"]
        return c.execute("INSERT INTO REPOSITORIES(name,url) VALUES(?,?)", (name, url)).lastrowid


def project_exists(project_url: str) -> bool:
    with conn() as c:
        return c.execute("SELECT 1 FROM PROJECTS WHERE project_url=?", (project_url,)).fetchone() is not None


def insert_project(p: dict) -> int:
    sql = """INSERT INTO PROJECTS(
        query_string,repository_id,repository_url,project_url,
        version,title,description,language,doi,upload_date,
        download_date,download_repository_folder,download_project_folder,
        download_version_folder,download_method
    ) VALUES(
        :query_string,:repository_id,:repository_url,:project_url,
        :version,:title,:description,:language,:doi,:upload_date,
        :download_date,:download_repository_folder,:download_project_folder,
        :download_version_folder,:download_method
    )"""
    with conn() as c:
        return c.execute(sql, p).lastrowid


def insert_file(project_id, name, ftype, status):
    with conn() as c:
        c.execute("INSERT INTO FILES(project_id,file_name,file_type,status) VALUES(?,?,?,?)",
                  (project_id, name, ftype, status))


def insert_keywords(project_id, keywords: list):
    if not keywords:
        return
    with conn() as c:
        c.executemany("INSERT INTO KEYWORDS(project_id,keyword) VALUES(?,?)",
                      [(project_id, k.strip()) for k in keywords if k.strip()])


def insert_person(project_id, name: str, role: str):
    VALID = {"AUTHOR","UPLOADER","OWNER","OTHER","UNKNOWN"}
    role = role.upper() if role.upper() in VALID else "UNKNOWN"
    with conn() as c:
        c.execute("INSERT INTO PERSON_ROLE(project_id,name,role) VALUES(?,?,?)",
                  (project_id, name, role))


def insert_license(project_id, lic: str):
    if lic:
        with conn() as c:
            c.execute("INSERT INTO LICENSES(project_id,license) VALUES(?,?)", (project_id, lic))


def stats():
    with conn() as c:
        for t in ["REPOSITORIES","PROJECTS","FILES","KEYWORDS","PERSON_ROLE","LICENSES"]:
            n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t:<22} {n:>6} rows")
