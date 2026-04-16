"""export/export_csv.py"""
import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import db.database as db

OUT = Path(__file__).parent / "csv"

def export_all():
    OUT.mkdir(parents=True, exist_ok=True)
    with db.conn() as c:
        for table in ["REPOSITORIES","PROJECTS","FILES","KEYWORDS","PERSON_ROLE","LICENSES"]:
            rows = c.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                print(f"  [export] {table}: 0 rows – skipping")
                continue
            with open(OUT / f"{table.lower()}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(rows[0].keys())
                w.writerows(rows)
            print(f"  [export] {table}: {len(rows)} rows → {table.lower()}.csv")
    print(f"[main] CSVs written to: {OUT}")

if __name__ == "__main__":
    export_all()
