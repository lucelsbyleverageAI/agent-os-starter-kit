from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from outcomes_data.utils.files import ensure_dir, sha256_of_file
from outcomes_data.utils.http import build_retrying_session


@dataclass
class DownloadRecord:
    url: str
    path: Path
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    sha256: Optional[str] = None


class CacheManager:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root
        self.zip_dir = cache_root / "zip"
        self.csv_dir = cache_root / "csv"
        self.manifest_dir = cache_root / "manifests"
        ensure_dir(self.zip_dir)
        ensure_dir(self.csv_dir)
        ensure_dir(self.manifest_dir)
        self.session = build_retrying_session()

    def _manifest_path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace(":", "_")
        return self.manifest_dir / f"{safe}.json"

    def read_manifest(self, key: str) -> dict:
        mp = self._manifest_path(key)
        if mp.exists():
            return json.loads(mp.read_text())
        return {}

    def write_manifest(self, key: str, data: dict) -> None:
        mp = self._manifest_path(key)
        mp.write_text(json.dumps(data, indent=2, sort_keys=True))

    def download_zip(self, url: str, timeout_s: int = 120) -> DownloadRecord:
        fname = Path(Path(url).name)
        target = self.zip_dir / fname
        manifest_key = f"zip::{url}"
        manifest = self.read_manifest(manifest_key)
        headers = {}
        if manifest.get("etag"):
            headers["If-None-Match"] = manifest["etag"]
        if manifest.get("last_modified"):
            headers["If-Modified-Since"] = manifest["last_modified"]

        with self.session.get(url, stream=True, timeout=timeout_s, headers=headers) as r:
            if r.status_code == 304 and target.exists():
                # Not modified
                sha = manifest.get("sha256") or sha256_of_file(target)
                return DownloadRecord(url=url, path=target, etag=manifest.get("etag"), last_modified=manifest.get("last_modified"), sha256=sha)
            r.raise_for_status()
            with open(target, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        sha = sha256_of_file(target)
        new_manifest = {
            "url": url,
            "path": str(target),
            "etag": r.headers.get("ETag"),
            "last_modified": r.headers.get("Last-Modified"),
            "sha256": sha,
        }
        self.write_manifest(manifest_key, new_manifest)
        return DownloadRecord(url=url, path=target, etag=new_manifest["etag"], last_modified=new_manifest["last_modified"], sha256=sha)

    def download_csv(self, url: str, timeout_s: int = 120) -> DownloadRecord:
        fname = Path(Path(url).name)
        target = self.csv_dir / fname
        manifest_key = f"csv::{url}"
        manifest = self.read_manifest(manifest_key)
        headers = {}
        if manifest.get("etag"):
            headers["If-None-Match"] = manifest["etag"]
        if manifest.get("last_modified"):
            headers["If-Modified-Since"] = manifest["last_modified"]

        with self.session.get(url, stream=True, timeout=timeout_s, headers=headers) as r:
            if r.status_code == 304 and target.exists():
                # Not modified
                sha = manifest.get("sha256") or sha256_of_file(target)
                return DownloadRecord(url=url, path=target, etag=manifest.get("etag"), last_modified=manifest.get("last_modified"), sha256=sha)
            r.raise_for_status()
            with open(target, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        sha = sha256_of_file(target)
        new_manifest = {
            "url": url,
            "path": str(target),
            "etag": r.headers.get("ETag"),
            "last_modified": r.headers.get("Last-Modified"),
            "sha256": sha,
        }
        self.write_manifest(manifest_key, new_manifest)
        return DownloadRecord(url=url, path=target, etag=new_manifest["etag"], last_modified=new_manifest["last_modified"], sha256=sha)
