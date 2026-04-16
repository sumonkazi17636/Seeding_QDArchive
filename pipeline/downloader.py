"""
pipeline/downloader.py  —  HTTP download engine
Student ID: 23293505
"""

import time
import requests
from pathlib import Path

DATA_ROOT   = Path(__file__).resolve().parents[1] / "data"
MAX_MB      = 500
TIMEOUT     = 30
RETRIES     = 3
RETRY_WAIT  = 5
RATE_DELAY  = 1.0

HEADERS = {
    "User-Agent": (
        "QDArchiveSeedBot/1.0 (FAU Erlangen SQ26; "
        "github.com/sumonkazi17636/Seeding_QDArchive)"
    )
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _classify(exc=None, response=None):
    if response is not None:
        if response.status_code in (401, 403):
            return "FAILED_LOGIN_REQUIRED"
        if response.status_code in (500, 502, 503, 504):
            return "FAILED_SERVER_UNRESPONSIVE"
    if isinstance(exc, (requests.exceptions.ConnectionError,
                         requests.exceptions.Timeout)):
        return "FAILED_SERVER_UNRESPONSIVE"
    return "FAILED_SERVER_UNRESPONSIVE"


def download_file(url, repo_folder, project_folder, filename, version_folder=""):
    """
    Download one file to  data/{repo_folder}/{project_folder}/{filename}
    Returns a DOWNLOAD_RESULT enum string.
    """
    parts = [DATA_ROOT, repo_folder, project_folder]
    if version_folder:
        parts.append(version_folder)
    dest_dir = Path(*parts)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [skip] {filename} already exists")
        return "SUCCEEDED"

    # Check size via HEAD
    try:
        head = SESSION.head(url, timeout=TIMEOUT, allow_redirects=True)
        cl   = int(head.headers.get("Content-Length", 0))
        if cl > MAX_MB * 1024 * 1024:
            print(f"  [too-large] {filename}: {cl/1e6:.0f} MB")
            return "FAILED_TOO_LARGE"
        if head.status_code in (401, 403):
            return "FAILED_LOGIN_REQUIRED"
    except Exception:
        pass

    for attempt in range(1, RETRIES + 1):
        try:
            resp = SESSION.get(url, timeout=TIMEOUT, stream=True)
            if resp.status_code == 200:
                downloaded = 0
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(65536):
                        downloaded += len(chunk)
                        if downloaded > MAX_MB * 1024 * 1024:
                            f.close()
                            dest.unlink(missing_ok=True)
                            return "FAILED_TOO_LARGE"
                        f.write(chunk)
                print(f"  [ok] {filename} ({downloaded/1024:.1f} KB)")
                time.sleep(RATE_DELAY)
                return "SUCCEEDED"
            else:
                s = _classify(response=resp)
                if attempt < RETRIES and s == "FAILED_SERVER_UNRESPONSIVE":
                    time.sleep(RETRY_WAIT)
                    continue
                return s
        except Exception as exc:
            s = _classify(exc=exc)
            if attempt < RETRIES:
                time.sleep(RETRY_WAIT)
            else:
                return s

    return "FAILED_SERVER_UNRESPONSIVE"


def get_json(url, params=None):
    """GET a JSON endpoint. Returns parsed dict or None."""
    for attempt in range(1, RETRIES + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            time.sleep(RATE_DELAY)
            return resp.json()
        except Exception as exc:
            if attempt < RETRIES:
                time.sleep(RETRY_WAIT)
            else:
                print(f"  [get_json fail] {url}: {exc}")
                return None
