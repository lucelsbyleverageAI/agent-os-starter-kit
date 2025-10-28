from __future__ import annotations

import re
from typing import Optional


BIN_PATTERN = re.compile(r"^(?P<prefix>gt|ge|lt|le|eq)_(?P<lo>\d{2,3})(?:_to_(?P<hi>\d{2,3})|_plus)?_weeks(?:_sum_1)?$")


def detect_bin_label(col: str) -> Optional[str]:
    m = BIN_PATTERN.match(col)
    if m:
        lo = m.group("lo")
        hi = m.group("hi")
        return f"weeks_{lo}_plus" if hi is None else f"weeks_{lo}_{hi}"
    name = col.lower()
    if "unknown" in name and "clock" in name and "start" in name:
        return "unknown_clock_start"
    if name in {"total", "total_all"}:
        return None
    return None


def parse_bin_to_bounds(bin_label: str) -> tuple[int, int | None]:
    # Returns (lower_inclusive_weeks, upper_exclusive_weeks or None for open-ended)
    if bin_label.endswith("_plus"):
        lo = int(bin_label.split("_")[1])
        return lo, None
    parts = bin_label.split("_")
    if len(parts) == 3 and parts[0] == "weeks":
        return int(parts[1]), int(parts[2])
    raise ValueError(f"Unrecognised bin label: {bin_label}")
