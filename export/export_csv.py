"""
export/export_csv.py
Export all tables from the SQLite DB to CSV files for sharing / inspection.
Student ID: 23293505
"""

import csv
import sqlite3
from pathlib import Path

from db.database import DEFAULT_DB_PATH, get_connection

EXPORT_DIR = Path(__file__).resolve().parents[1] / "export_csv"

TABLES = [
    "REPOSITORIES",
    "PROJECTS",
    "FILES",
    "KEYWORDS",
    "PERSON_ROLE",
    "LICENSES",
]


def export_all(db_path=DEFAULT_DB_PATH, out_dir: Path = EXPORT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)

    for table in TABLES:
        out_path = out_dir / f"{table.lower()}.csv"
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"  [export] {table}: empty, skipping")
            continue
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([d[0] for d in conn.execute(f"SELECT * FROM {table}").description])
            writer.writerows(rows)
        print(f"  [export] {table}: {len(rows)} rows → {out_path}")

    conn.close()
    print(f"\n[export] All tables exported to: {out_dir}")


if __name__ == "__main__":
    export_all()
