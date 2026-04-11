"""
main.py
QDArchive Seeding Pipeline — Part 1: Data Acquisition
Student ID: 23293505
Repositories: QDR Syracuse, ICPSR

Usage:
    python main.py                  # run both scrapers
    python main.py --repo qdr       # only QDR
    python main.py --repo icpsr     # only ICPSR
    python main.py --export-only    # just export CSV, no scraping
    python main.py --max 50         # cap new projects per scraper
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on the path (for db.*, scrapers.*, etc.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db.database import init_db, DEFAULT_DB_PATH
from scrapers import qdr_scraper, icpsr_scraper
from export.export_csv import export_all


def main():
    parser = argparse.ArgumentParser(description="QDArchive Seeding Pipeline – Part 1")
    parser.add_argument(
        "--repo", choices=["qdr", "icpsr", "both"], default="both",
        help="Which repository to scrape (default: both)"
    )
    parser.add_argument(
        "--max", type=int, default=500,
        help="Maximum new projects to record per repository (default: 500)"
    )
    parser.add_argument(
        "--export-only", action="store_true",
        help="Skip scraping, just export CSV files from existing DB"
    )
    parser.add_argument(
        "--db", default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("QDArchive Seeding Pipeline — Part 1: Data Acquisition")
    print(f"DB:  {args.db}")
    print("=" * 60)

    # ── Initialise DB ──
    conn = init_db(args.db)

    if not args.export_only:
        # ── QDR Syracuse ──
        if args.repo in ("qdr", "both"):
            qdr_scraper.scrape(conn, max_projects=args.max)

        # ── ICPSR ──
        if args.repo in ("icpsr", "both"):
            icpsr_scraper.scrape(conn, max_projects=args.max)

    # ── Export to CSV ──
    print("\n[main] Exporting tables to CSV …")
    export_all(db_path=args.db)

    conn.close()
    print("\n[main] Pipeline complete.")
    print(f"[main] Database: {args.db}")
    print("[main] Commit everything and tag: git tag part-1-release")


if __name__ == "__main__":
    main()
