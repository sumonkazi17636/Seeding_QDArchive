"""
main.py  –  SQ26 Seeding QDArchive, Student 23293505
============================================================
Usage:
  python main.py                     # run QDR + ICPSR (default max=1000 each)
  python main.py --repo qdr          # only QDR
  python main.py --repo icpsr        # only ICPSR
  python main.py --max 200           # cap per repository
  python main.py --export-only       # only export CSVs
============================================================
"""
import argparse, logging, sys
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("main")

import db.database as db
from scrapers import qdr_scraper, icpsr_scraper
from export.export_csv import export_all

BANNER = """
============================================================
QDArchive Seeding — Part 1: Data Acquisition
Student ID : 23293505
Database   : {}
============================================================"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo",        choices=["qdr","icpsr","both"], default="both")
    parser.add_argument("--max", type=int, default=5000)
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()

    db.init_db()
    print(BANNER.format(db.DB_PATH))

    qdr_id   = db.upsert_repo("qdr",   "https://data.qdr.syr.edu")
    icpsr_id = db.upsert_repo("icpsr", "https://www.icpsr.umich.edu")

    if args.export_only:
        export_all()
        _stats()
        return

    if args.repo in ("qdr", "both"):
        log.info(f"=== QDR scraper (max={args.max}) ===")
        try:
            n = qdr_scraper.run(qdr_id, args.max)
            log.info(f"=== QDR done: {n} projects ===")
        except Exception as e:
            log.error(f"QDR failed: {e}", exc_info=True)

    if args.repo in ("icpsr", "both"):
        log.info(f"=== ICPSR scraper (max={args.max}) ===")
        try:
            n = icpsr_scraper.run(icpsr_id, args.max)
            log.info(f"=== ICPSR done: {n} projects ===")
        except Exception as e:
            log.error(f"ICPSR failed: {e}", exc_info=True)

    log.info("[main] Exporting tables to CSV ...")
    export_all()
    _stats()
    print(f"\n[main] Done. Database: {db.DB_PATH}")
    print("[main] Next: git add . && git commit -m 'Part 1 complete' && git tag part-1-release && git push --tags")


def _stats():
    print("\n============================================================")
    print("DATABASE SUMMARY")
    print("============================================================")
    db.stats()
    print("============================================================")


if __name__ == "__main__":
    main()
