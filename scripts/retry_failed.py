"""
scripts/retry_failed.py
Re-attempt downloads that previously returned FAILED_SERVER_UNRESPONSIVE.
FAILED_LOGIN_REQUIRED entries are skipped (they need auth, not retries).
FAILED_TOO_LARGE entries are also skipped.

Usage:
    python scripts/retry_failed.py
    python scripts/retry_failed.py --repo qdr-syracuse    # only one repo
Student ID: 23293505
"""

import argparse
import sqlite3
from pathlib import Path

from db.database import DEFAULT_DB_PATH, get_connection
from pipeline.downloader import download_file, DATA_ROOT

# QDR file download URL template
QDR_BASE = "https://data.qdr.syr.edu/api/access/datafile"


def _build_download_url(project_url: str, repo_folder: str, file_name: str, file_id=None) -> str | None:
    """Best-effort reconstruction of the download URL."""
    if repo_folder == "qdr-syracuse" and file_id:
        return f"{QDR_BASE}/{file_id}"
    # ICPSR – we don't have a deterministic URL without auth; skip
    return None


def retry_all(db_path=DEFAULT_DB_PATH, repo_filter: str = None) -> None:
    conn = get_connection(db_path)

    query = """
        SELECT f.id, f.file_name, f.file_type,
               p.download_repository_folder,
               p.download_project_folder,
               p.download_version_folder,
               p.project_url
        FROM FILES f
        JOIN PROJECTS p ON f.project_id = p.id
        WHERE f.status = 'FAILED_SERVER_UNRESPONSIVE'
    """
    if repo_filter:
        query += f" AND p.download_repository_folder = '{repo_filter}'"

    rows = conn.execute(query).fetchall()
    print(f"[retry] {len(rows)} FAILED_SERVER_UNRESPONSIVE file(s) to retry")

    for row in rows:
        file_id_val = None  # Would need to store original datafile ID to reconstruct URL properly
        dl_url = _build_download_url(
            row["project_url"], row["download_repository_folder"],
            row["file_name"], file_id_val
        )
        if not dl_url:
            print(f"  [skip] cannot reconstruct URL for {row['file_name']}")
            continue

        status = download_file(
            url=dl_url,
            repo_folder=row["download_repository_folder"],
            project_folder=row["download_project_folder"],
            filename=row["file_name"],
            version_folder=row["download_version_folder"] or "",
        )
        conn.execute("UPDATE FILES SET status = ? WHERE id = ?", (status, row["id"]))
        conn.commit()
        print(f"  [{status}] {row['file_name']}")

    conn.close()
    print("[retry] Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", help="Filter by repo folder name", default=None)
    args = parser.parse_args()
    retry_all(repo_filter=args.repo)
