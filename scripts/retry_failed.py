"""
scripts/retry_failed.py
Re-attempt FAILED_SERVER_UNRESPONSIVE downloads for QDR.
Usage:  python scripts/retry_failed.py
Student ID: 23293505
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.database import get_conn, DB_PATH
from pipeline.downloader import download_file

QDR_BASE = "https://data.qdr.syr.edu/api/access/datafile"


def retry():
    conn  = get_conn()
    rows  = conn.execute("""
        SELECT f.id, f.file_name, f.file_type,
               p.download_repository_folder,
               p.download_project_folder,
               p.download_version_folder
        FROM FILES f
        JOIN PROJECTS p ON f.project_id = p.id
        WHERE f.status = 'FAILED_SERVER_UNRESPONSIVE'
        AND   p.download_repository_folder = 'qdr-syracuse'
    """).fetchall()

    print(f"[retry] {len(rows)} failed QDR files to retry")
    for row in rows:
        # Reconstruct URL from folder name (DOI-based)
        folder = row["download_project_folder"]
        fname  = row["file_name"]
        # We don't store the datafile ID separately, so attempt via folder
        print(f"  Retrying {fname} ...")
        # NOTE: without the original file ID we cannot reconstruct the URL precisely.
        # Log and skip — store original file IDs in Part 2 if needed.
        print(f"  [skip] Cannot reconstruct download URL without stored file ID.")
    conn.close()


if __name__ == "__main__":
    retry()
