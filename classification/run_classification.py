"""
classification/run_classification.py
Part 2 pipeline entry point: turns the Part 1 seeding database into a
classification database.

Usage:
    python classification/run_classification.py
    python classification/run_classification.py --src 23293505-seeding.db \
        --out 23293505-sq26-classification.db

Steps (per the SQ26 project description, Part 2):
    1. Copy --src to --out (the Part 1 db is never modified).
    2. Apply db/schema_classification.sql (adds PROJECTS.type,
       PROJECT_CLASSIFICATION, FILE_CLASSIFICATION, TAGS).
    3. Dedup projects (by DOI, then by repository+title).
    4. Derive PROJECT_TYPE for every project from its file types.
    5. Run the ISIC classifier for QDA_PROJECT / QD_PROJECT projects, both
       for the project as a whole and for each of its primary data files.
    6. Print a by-repository / by-type summary (for the course's Google Form).
"""

import argparse
import pathlib
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from classification.file_types import PRIMARY_DATA_EXTENSIONS, is_metadata_sidecar
from classification.project_type import classify_project_type
from classification.isic_classifier import IsicClassifier, ProjectDoc, build_project_text

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_DEFAULT = str(ROOT / "23293505-seeding.db")
OUT_DEFAULT = str(ROOT / "23293505-sq26-classification.db")
SCHEMA_FILE = ROOT / "db" / "schema_classification.sql"


def get_connection(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def prepare_output_db(src: str, out: str) -> None:
    # Copy the main db file (and drop any stale WAL/SHM side files at the target).
    shutil.copyfile(src, out)
    for ext in ("-wal", "-shm"):
        side = pathlib.Path(out + ext)
        if side.exists():
            side.unlink()
    conn = get_connection(out)
    conn.execute("PRAGMA journal_mode = DELETE")  # single self-contained file
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    print(f"[1/5] Copied {pathlib.Path(src).name} -> {pathlib.Path(out).name} "
          f"and applied classification schema")


def dedup_projects(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT id, repository_id, title, doi FROM PROJECTS").fetchall()

    duplicate_ids = []
    seen_doi = {}
    seen_title = {}
    for r in rows:
        doi = (r["doi"] or "").strip()
        key_doi = doi if doi else None
        key_title = (r["repository_id"], _normalize_title(r["title"]))

        if key_doi and key_doi in seen_doi:
            duplicate_ids.append(r["id"])
            continue
        if key_title in seen_title:
            duplicate_ids.append(r["id"])
            continue

        if key_doi:
            seen_doi[key_doi] = r["id"]
        seen_title[key_title] = r["id"]

    for pid in duplicate_ids:
        for tbl in ("FILES", "KEYWORDS", "PERSON_ROLE", "LICENSES"):
            conn.execute(f"DELETE FROM {tbl} WHERE project_id = ?", (pid,))
        conn.execute("DELETE FROM PROJECTS WHERE id = ?", (pid,))
    conn.commit()

    remaining = len(rows) - len(duplicate_ids)
    print(f"[2/5] Dedup: removed {len(duplicate_ids)} duplicate project(s), "
          f"{remaining} remain")
    return len(duplicate_ids)


def assign_project_types(conn: sqlite3.Connection) -> dict:
    projects = conn.execute("SELECT id FROM PROJECTS").fetchall()
    files_by_project = defaultdict(list)
    for f in conn.execute("SELECT project_id, file_name, file_type FROM FILES"):
        files_by_project[f["project_id"]].append(f)

    type_by_project = {}
    for p in projects:
        ptype = classify_project_type(files_by_project.get(p["id"], []))
        type_by_project[p["id"]] = ptype
        conn.execute("UPDATE PROJECTS SET type = ? WHERE id = ?", (ptype, p["id"]))
    conn.commit()

    counts = Counter(type_by_project.values())
    print(f"[3/5] Assigned PROJECT_TYPE: {dict(counts)}")
    return type_by_project


def run_isic_classification(conn: sqlite3.Connection, type_by_project: dict) -> None:
    target_ids = [pid for pid, t in type_by_project.items()
                  if t in ("QDA_PROJECT", "QD_PROJECT")]

    if not target_ids:
        print("[4/5] No QDA_PROJECT/QD_PROJECT projects to classify")
        return

    keywords_by_project = defaultdict(list)
    for k in conn.execute("SELECT project_id, keyword FROM KEYWORDS"):
        keywords_by_project[k["project_id"]].append(k["keyword"])

    project_rows = {
        p["id"]: p for p in conn.execute("SELECT id, title, description FROM PROJECTS")
    }

    docs = [
        ProjectDoc(
            project_id=pid,
            text=build_project_text(
                project_rows[pid]["title"],
                project_rows[pid]["description"],
                keywords_by_project.get(pid, []),
            ),
        )
        for pid in target_ids
    ]

    classifier = IsicClassifier()
    classifier.fit(docs)
    results = classifier.classify_all()

    files_by_project = defaultdict(list)
    for f in conn.execute("SELECT id, project_id, file_name, file_type FROM FILES"):
        files_by_project[f["project_id"]].append(f)

    n_files = 0
    for res in results:
        conn.execute(
            """INSERT INTO PROJECT_CLASSIFICATION
               (project_id, primary_class_code, primary_class_name,
                secondary_class_code, secondary_class_name)
               VALUES (?, ?, ?, ?, ?)""",
            (res.project_id, res.primary_code, res.primary_name,
             res.secondary_code, res.secondary_name),
        )
        for tag in res.tags:
            conn.execute("INSERT INTO TAGS (project_id, tag) VALUES (?, ?)",
                         (res.project_id, tag))

        for f in files_by_project.get(res.project_id, []):
            if is_metadata_sidecar(f["file_name"]):
                continue
            if (f["file_type"] or "").lower() not in PRIMARY_DATA_EXTENSIONS:
                continue
            conn.execute(
                """INSERT INTO FILE_CLASSIFICATION
                   (file_id, primary_class_code, primary_class_name,
                    secondary_class_code, secondary_class_name)
                   VALUES (?, ?, ?, ?, ?)""",
                (f["id"], res.primary_code, res.primary_name,
                 res.secondary_code, res.secondary_name),
            )
            n_files += 1

    conn.commit()
    print(f"[4/5] Classified {len(results)} project(s) "
          f"(QDA_PROJECT + QD_PROJECT) and {n_files} primary data file(s)")


def print_summary(conn: sqlite3.Connection) -> None:
    print("\n[5/5] Summary by repository x project_type "
          "(for the course's Google Form, Step 4b):\n")

    rows = conn.execute("""
        SELECT r.name AS repo, p.type, COUNT(*) AS n
        FROM PROJECTS p JOIN REPOSITORIES r ON r.id = p.repository_id
        GROUP BY r.name, p.type
        ORDER BY r.name, n DESC
    """).fetchall()

    by_repo = defaultdict(dict)
    for r in rows:
        by_repo[r["repo"]][r["type"]] = r["n"]

    for repo, counts in by_repo.items():
        total = sum(counts.values())
        print(f"  {repo} (total {total} projects)")
        for ptype, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"    {ptype:<16} {n:>5}")

    print("\n  Dominant primary_class by repository:")
    dom_rows = conn.execute("""
        SELECT r.name AS repo, pc.primary_class_name AS cls, COUNT(*) AS n
        FROM PROJECT_CLASSIFICATION pc
        JOIN PROJECTS p ON p.id = pc.project_id
        JOIN REPOSITORIES r ON r.id = p.repository_id
        GROUP BY r.name, pc.primary_class_name
        ORDER BY r.name, n DESC
    """).fetchall()
    seen_repo = set()
    for r in dom_rows:
        if r["repo"] in seen_repo:
            continue
        seen_repo.add(r["repo"])
        print(f"    {r['repo']:<12} {r['cls']}  ({r['n']} projects)")


def main():
    parser = argparse.ArgumentParser(description="SQ26 Part 2 classification pipeline")
    parser.add_argument("--src", default=SRC_DEFAULT, help="Source Part 1 database")
    parser.add_argument("--out", default=OUT_DEFAULT, help="Output classification database")
    args = parser.parse_args()

    prepare_output_db(args.src, args.out)

    conn = get_connection(args.out)
    dedup_projects(conn)
    type_by_project = assign_project_types(conn)
    run_isic_classification(conn, type_by_project)
    print_summary(conn)
    conn.close()

    print(f"\n[OK] Classification database written to {pathlib.Path(args.out).name}")


if __name__ == "__main__":
    main()
