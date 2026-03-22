"""
Pull TRX artifacts from the test repo using a read-only PAT.

Usage:
    GITHUB_PAT=ghp_xxx uv run python src/fetch_artifacts.py

Environment variables (required):
    GITHUB_PAT   Fine-grained PAT with Actions: Read on the test repo
    TEST_ORG     GitHub org name              e.g. "my-company"
    TEST_REPO    Repo where tests run         e.g. "my-app"

Optional:
    MAX_RUNS     How many recent runs to fetch (default 100)
    ARTIFACT_KEY Substring to match artifact name (default "test")
    OUT_DIR      Where to write TRX files (default "data/runs")
"""

import io
import os
import zipfile
from pathlib import Path

import requests

PAT          = os.environ["GITHUB_PAT"]
ORG          = os.environ["TEST_ORG"]
REPO         = os.environ["TEST_REPO"]
MAX_RUNS     = int(os.getenv("MAX_RUNS", "100"))
ARTIFACT_KEY = os.getenv("ARTIFACT_KEY", "test").lower()
OUT_DIR      = Path(os.getenv("OUT_DIR", "data/runs"))

BASE  = "https://api.github.com"
HDR   = {
    "Authorization": f"Bearer {PAT}",
    "Accept":        "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def get(url, **params):
    r = requests.get(url, headers=HDR, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_runs():
    """Return up to MAX_RUNS completed workflow runs."""
    url   = f"{BASE}/repos/{ORG}/{REPO}/actions/runs"
    runs  = []
    page  = 1
    while len(runs) < MAX_RUNS:
        data  = get(url, per_page=100, page=page, status="completed")
        batch = data.get("workflow_runs", [])
        if not batch:
            break
        runs.extend(batch)
        page += 1
    return runs[:MAX_RUNS]


def fetch_artifacts_for_run(run_id: int):
    url = f"{BASE}/repos/{ORG}/{REPO}/actions/runs/{run_id}/artifacts"
    return get(url).get("artifacts", [])


def download_artifact(artifact: dict, dest: Path):
    """Download and unzip a single artifact into dest/."""
    dest.mkdir(parents=True, exist_ok=True)
    dl_url = artifact["archive_download_url"]
    r = requests.get(dl_url, headers=HDR, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        # Only extract .trx and .xml files
        for name in z.namelist():
            if name.endswith((".trx", ".xml")):
                z.extract(name, dest)
    return dest


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    runs       = fetch_runs()
    downloaded = 0
    skipped    = 0

    print(f"Fetching artifacts from {ORG}/{REPO}  ({len(runs)} runs)")

    for run in runs:
        run_id   = run["id"]
        run_name = f"run_{run_id}"
        dest     = OUT_DIR / run_name

        if dest.exists():
            skipped += 1
            continue  # already have this one

        artifacts = fetch_artifacts_for_run(run_id)
        matched   = [a for a in artifacts if ARTIFACT_KEY in a["name"].lower()]

        if not matched:
            continue

        for art in matched:
            download_artifact(art, dest)
            print(f"  ✓ {run_name}  →  {art['name']}")
            downloaded += 1

    print(f"\nDone.  Downloaded: {downloaded}  Already cached: {skipped}")


if __name__ == "__main__":
    main()
