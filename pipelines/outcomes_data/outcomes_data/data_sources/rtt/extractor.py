from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import chardet

from outcomes_data.utils.files import ensure_dir


@dataclass
class ExtractedCsv:
    csv_path: Path
    encoding: str
    header_idx: int
    csv_member: str


class ZipCsvExtractor:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root
        self.extract_dir = cache_root / "extracted_csv"
        self.manifest_dir = cache_root / "manifests"
        ensure_dir(self.extract_dir)
        ensure_dir(self.manifest_dir)

    def _manifest_path(self, zip_path: Path) -> Path:
        return self.manifest_dir / f"extract::{zip_path.stem}.json".replace("/", "_")

    def _choose_main_csv_from_zip(self, zf: zipfile.ZipFile) -> Optional[str]:
        names = zf.namelist()
        csvs = [n for n in names if n.lower().endswith(".csv")]
        if not csvs:
            return None
        preferred = [n for n in csvs if "full" in n.lower() or "csv" in n.lower()]
        if preferred:
            preferred.sort(key=lambda s: (len(s), s))
            return preferred[-1]
        csvs.sort(key=lambda s: (len(s), s))
        return csvs[-1]

    def _detect_header_and_columns_from_csv_bytes(self, raw: bytes) -> tuple[int, str]:
        enc = chardet.detect(raw).get("encoding") or "utf-8"
        try:
            text = raw.decode(enc)
        except Exception:
            try:
                text = raw.decode("utf-8-sig")
                enc = "utf-8-sig"
            except Exception:
                text = raw.decode("latin-1", errors="replace")
                enc = "latin-1"
        lines = text.splitlines()
        header_idx = 0
        for i, line in enumerate(lines[:15]):
            if line.count(",") >= 3 and any(c.isalpha() for c in line):
                header_idx = i
                break
        return header_idx, enc

    def extract(self, zip_path: Path) -> ExtractedCsv:
        manifest_path = self._manifest_path(zip_path)
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text())
            csv_path = Path(data["csv_path"])
            if csv_path.exists():
                return ExtractedCsv(csv_path=csv_path, encoding=data["encoding"], header_idx=data["header_idx"], csv_member=data["csv_member"])

        with zipfile.ZipFile(zip_path, "r") as zf:
            csv_member = self._choose_main_csv_from_zip(zf)
            if not csv_member:
                raise RuntimeError(f"No CSV member found in {zip_path}")
            raw = zf.read(csv_member)
        header_idx, enc = self._detect_header_and_columns_from_csv_bytes(raw)
        safe_name = Path(csv_member).name
        out_path = self.extract_dir / f"{zip_path.stem}__{safe_name}"
        if not out_path.exists():
            out_path.write_bytes(raw)
        manifest = {
            "csv_path": str(out_path),
            "encoding": enc,
            "header_idx": header_idx,
            "csv_member": csv_member,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        return ExtractedCsv(csv_path=out_path, encoding=enc, header_idx=header_idx, csv_member=csv_member)
