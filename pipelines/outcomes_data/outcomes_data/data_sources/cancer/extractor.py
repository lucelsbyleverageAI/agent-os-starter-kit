from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chardet

from outcomes_data.utils.files import ensure_dir


@dataclass
class ExtractedCsv:
    csv_path: Path
    encoding: str
    header_idx: int

class CsvExtractor:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root
        self.extract_dir = cache_root / "extracted_csv"
        self.manifest_dir = cache_root / "manifests"
        ensure_dir(self.extract_dir)
        ensure_dir(self.manifest_dir)

    def _manifest_path(self, downloaded_csv_path: Path) -> Path:
        return self.manifest_dir / f"extract::{downloaded_csv_path.stem}.json".replace("/", "_")

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

        # Look for the actual data header - should be a row with column names separated by commas
        for i, line in enumerate(lines[:30]):  # Scan more lines for safety
            line_clean = line.strip().upper()
            # Look for lines that contain actual column headers in CSV format
            # Should have multiple columns and contain specific header patterns
            if (line.count(",") >= 8 and  # Should have many columns
                any(c.isalpha() for c in line) and
                ("ODS CODE" in line_clean and "ACCOUNTABLE PROVIDER" in line_clean) and
                not line_clean.startswith('"TWO MONTH') and  # Skip title rows
                not line_clean.startswith('"FOUR WEEK')):    # Skip title rows
                header_idx = i
                break

        return header_idx, enc

    def extract(self, downloaded_csv_path: Path) -> ExtractedCsv:
        manifest_path = self._manifest_path(downloaded_csv_path)
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text())
            csv_path = Path(data["csv_path"])
            # Ensure the CSV file actually exists, in case cache was moved/cleared
            if csv_path.exists():
                return ExtractedCsv(
                    csv_path=csv_path,
                    encoding=data["encoding"],
                    header_idx=data["header_idx"]
                )

        raw = downloaded_csv_path.read_bytes()
        header_idx, enc = self._detect_header_and_columns_from_csv_bytes(raw)

        manifest = {
            "csv_path": str(downloaded_csv_path),
            "encoding": enc,
            "header_idx": header_idx,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        return ExtractedCsv(csv_path=downloaded_csv_path, encoding=enc, header_idx=header_idx)
