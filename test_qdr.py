"""
check_qdr_open.py
Quickly scans QDR to find open (freely downloadable) datasets
and downloads one file from each to verify it works.

Run:  python check_qdr_open.py
Student ID: 23293505
"""

import requests
import time
import json

API = "https://data.qdr.syr.edu/api/v1"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "QDArchiveSeedBot/1.0 (FAU Erlangen SQ26)"
})

QUERIES = [
    "interview", "qualitative", "qdpx", "focus group",
    "ethnography", "oral history", "transcript", "case study",
    "grounded theory", "thematic analysis", "coding", "narrative",
]


def is_controlled(pid):
    try:
        r = SESSION.get(
            f"{API}/datasets/:persistentId/versions/:latest",
            params={"persistentId": pid},
            timeout=15
        )
        d = r.json()
        latest = d.get("data", {})
        far = latest.get("fileAccessRequest", False)
        lic = latest.get("license", {})
        lic_name = lic.get("name", "") if isinstance(lic, dict) else ""
        return far is True or "Controlled" in lic_name
    except Exception:
        return True  # assume restricted if we can't check


def try_download(file_id, fname):
    """Try downloading a file, return (status, size_kb)"""
    for url in [
        f"{API}/access/datafile/{file_id}?format=original",
        f"{API}/access/datafile/{file_id}",
    ]:
        try:
            r = SESSION.get(url, timeout=30, stream=True, allow_redirects=True)
            if r.status_code == 200:
                data = b""
                for chunk in r.iter_content(65536):
                    data += chunk
                    if len(data) > 5 * 1024 * 1024:  # stop at 5MB for test
                        break
                if len(data) > 0:
                    return "OK", len(data) / 1024
            elif r.status_code in (401, 403):
                return "LOGIN_REQUIRED", 0
        except Exception as e:
            pass
    return "FAILED", 0


def main():
    print("=" * 65)
    print("QDR Open Dataset Scanner")
    print("Finding freely downloadable datasets...")
    print("=" * 65)

    seen       = set()
    open_found = 0
    controlled = 0
    total_checked = 0

    for query in QUERIES:
        if open_found >= 20:
            break

        print(f"\n[query] '{query}'")
        start = 0

        while open_found < 20:
            try:
                r = SESSION.get(
                    f"{API}/search",
                    params={
                        "q": query, "type": "dataset",
                        "per_page": 20, "start": start
                    },
                    timeout=15
                )
                time.sleep(0.5)
                d = r.json()
                items = d.get("data", {}).get("items", [])
                total = d.get("data", {}).get("total_count", 0)

                if start == 0:
                    print(f"  total results: {total}")

                if not items:
                    break

                for item in items:
                    pid = item.get("global_id") or item.get("identifier")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    total_checked += 1

                    title = item.get("name", "")[:55]

                    # Check if controlled access
                    if is_controlled(pid):
                        controlled += 1
                        print(f"  [controlled] {pid}")
                        time.sleep(0.3)
                        continue

                    # It's open — get file list
                    r2 = SESSION.get(
                        f"{API}/datasets/:persistentId/versions/:latest/files",
                        params={"persistentId": pid},
                        timeout=15
                    )
                    time.sleep(0.5)
                    d2 = r2.json()
                    files = d2.get("data", []) if d2.get("status") == "OK" else []

                    if not files:
                        print(f"  [open-nofiles] {pid}")
                        open_found += 1
                        continue

                    # Try downloading the first file
                    df    = files[0].get("dataFile", {})
                    fid   = df.get("id")
                    fname = df.get("filename", "unknown")
                    fsize = df.get("filesize", 0)

                    print(f"\n  [OPEN] {pid}")
                    print(f"         {title}")
                    print(f"         {len(files)} file(s) | first: {fname} ({fsize/1024:.1f} KB)")

                    if fid:
                        status, kb = try_download(fid, fname)
                        print(f"         Download test: {status} ({kb:.1f} KB received)")

                    # Print all file names
                    print(f"         All files:")
                    for f in files[:10]:
                        df2 = f.get("dataFile", {})
                        print(f"           - {df2.get('filename','?')} ({df2.get('filesize',0)/1024:.1f} KB)")
                    if len(files) > 10:
                        print(f"           ... and {len(files)-10} more")

                    open_found += 1

                start += 20
                if start >= total:
                    break

            except Exception as e:
                print(f"  [error] {e}")
                break

    print(f"\n{'='*65}")
    print(f"SUMMARY")
    print(f"  Datasets checked  : {total_checked}")
    print(f"  Controlled access : {controlled}")
    print(f"  Open/downloadable : {open_found}")
    if total_checked > 0:
        pct = controlled / total_checked * 100
        print(f"  Controlled %      : {pct:.0f}%")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()