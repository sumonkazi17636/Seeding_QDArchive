"""
pipeline/downloader.py
Handles actual HTTP downloads, with retry logic and failure classification.
Student ID: 23293505
"""

import os
import time
import requests
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

DATA_ROOT    = Path(__file__).resolve().parents[1] / "data"
MAX_FILE_MB  = 500          # Files larger than this → FAILED_TOO_LARGE
TIMEOUT_SEC  = 30           # Per request timeout
RETRY_COUNT  = 3            # How many times to retry on transient error
RETRY_DELAY  = 5            # Seconds between retries
RATE_DELAY   = 1.0          # Courtesy delay between requests (seconds)

# Friendly headers to avoid being blocked
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; QDArchiveSeedBot/1.0; "
        "+https://github.com/sumonkazi17636/Seeding_QDArchive)"
    )
}


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


SESSION = _make_session()


def _classify_error(exc: Exception, response=None) -> str:
    """Map an exception / HTTP response to a DOWNLOAD_RESULT enum value."""
    if response is not None:
        if response.status_code in (401, 403):
            return "FAILED_LOGIN_REQUIRED"
        if response.status_code in (500, 502, 503, 504):
            return "FAILED_SERVER_UNRESPONSIVE"
    if isinstance(exc, (requests.exceptions.ConnectionError,
                         requests.exceptions.Timeout)):
        return "FAILED_SERVER_UNRESPONSIVE"
    return "FAILED_SERVER_UNRESPONSIVE"  # safe default


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def download_file(
    url: str,
    repo_folder: str,
    project_folder: str,
    filename: str,
    version_folder: str = "",
) -> str:
    """
    Download a file to:
        data/{repo_folder}/{project_folder}[/{version_folder}]/{filename}

    Returns one of the DOWNLOAD_RESULT enum values:
        SUCCEEDED | FAILED_LOGIN_REQUIRED | FAILED_SERVER_UNRESPONSIVE | FAILED_TOO_LARGE
    """
    # Build local path
    parts = [DATA_ROOT, repo_folder, project_folder]
    if version_folder:
        parts.append(version_folder)
    dest_dir = Path(*parts)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    # Skip if already downloaded (idempotent)
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"  [skip] already exists: {dest_path.relative_to(DATA_ROOT)}")
        return "SUCCEEDED"

    # Check Content-Length before downloading to catch FAILED_TOO_LARGE
    try:
        head = SESSION.head(url, timeout=TIMEOUT_SEC, allow_redirects=True)
        content_length = int(head.headers.get("Content-Length", 0))
        if content_length > MAX_FILE_MB * 1024 * 1024:
            print(f"  [skip-large] {filename}: {content_length / 1e6:.0f} MB > {MAX_FILE_MB} MB limit")
            return "FAILED_TOO_LARGE"
        if head.status_code in (401, 403):
            return "FAILED_LOGIN_REQUIRED"
    except Exception:
        pass  # HEAD not always supported; proceed to GET

    # Download with retry
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = SESSION.get(url, timeout=TIMEOUT_SEC, stream=True)
            if resp.status_code == 200:
                downloaded = 0
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        downloaded += len(chunk)
                        if downloaded > MAX_FILE_MB * 1024 * 1024:
                            f.close()
                            dest_path.unlink(missing_ok=True)
                            return "FAILED_TOO_LARGE"
                        f.write(chunk)
                print(f"  [ok] {filename} ({downloaded / 1024:.1f} KB)")
                time.sleep(RATE_DELAY)
                return "SUCCEEDED"
            else:
                status = _classify_error(None, resp)
                if attempt < RETRY_COUNT and status == "FAILED_SERVER_UNRESPONSIVE":
                    print(f"  [retry {attempt}] HTTP {resp.status_code} for {filename}")
                    time.sleep(RETRY_DELAY)
                    continue
                return status
        except Exception as exc:
            status = _classify_error(exc)
            if attempt < RETRY_COUNT:
                print(f"  [retry {attempt}] {exc} for {filename}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  [fail] {exc} for {filename}")
                return status

    return "FAILED_SERVER_UNRESPONSIVE"


def get_json(url: str, params: dict = None) -> dict | None:
    """GET a JSON endpoint with retries. Returns parsed dict or None on failure."""
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=TIMEOUT_SEC)
            resp.raise_for_status()
            time.sleep(RATE_DELAY)
            return resp.json()
        except Exception as exc:
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)
            else:
                print(f"  [get_json fail] {url}: {exc}")
                return None
