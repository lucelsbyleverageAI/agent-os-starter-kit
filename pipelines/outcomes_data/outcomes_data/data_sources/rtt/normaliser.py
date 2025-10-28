from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd


MONTH_NAME_TO_NUM = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def normalise_col(col: str) -> str:
    s = (col or "").strip().strip("\ufeff").lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]+", "", s)
    replacements = {
        "ccg_": "icb_",
        "commissioner_org": "commissioner",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s


def derive_period_from_strings(period_str: str | None, filename: str | None) -> str:
    s = (period_str or '').strip()
    if s:
        return s
    name = (filename or '').lower()
    m = re.search(r"(?i)rtt[-_]?([a-z]+)[-_]?(\d{4})", name)
    if m:
        mon_name = m.group(1).lower()
        year = m.group(2)
        return f"RTT-{mon_name.capitalize()}-{year}"
    m2 = re.search(r"(20\d{2})(0[1-9]|1[0-2])", name)
    if m2:
        year = m2.group(1)
        mm = int(m2.group(2))
        mon = list(MONTH_NAME_TO_NUM.keys())[mm - 1].capitalize()
        return f"RTT-{mon}-{year}"
    return ""


def period_to_ym(period_str: str | None) -> str:
    if not period_str:
        return ""
    s = period_str.strip()
    m = re.match(r"(?i)^RTT[-_]?([A-Za-z]+)[-_]?(\d{4})(?:[-_]?(\d{2}))?$", s)
    if m:
        mon_name = m.group(1).lower()
        year1 = int(m.group(2))
        year2_two = m.group(3)
        mm = MONTH_NAME_TO_NUM.get(mon_name)
        if not mm:
            return ""
        if year2_two:
            end_year = (year1 // 100) * 100 + int(year2_two)
            yyyy = end_year if mm in (1, 2, 3) else year1
            return f"{yyyy}-{mm:02d}"
        return f"{year1}-{mm:02d}"
    return ""


def ensure_period_and_parts(df: pd.DataFrame, csv_path: Path) -> pd.DataFrame:
    cols = set(df.columns)
    if 'period' not in cols:
        period_val = None
        if 'year' in cols and 'period_name' in cols and len(df):
            y = str(df['year'].iloc[0]).strip()
            pn = str(df['period_name'].iloc[0]).strip()
            period_val = f"RTT-{pn}-{y}" if y and pn else None
        if not period_val:
            period_val = derive_period_from_strings(None, csv_path.name)
        df['period'] = period_val
    ym = period_to_ym(str(df['period'].iloc[0]) if len(df) else None)
    if ym:
        df['period'] = ym
    if 'rtt_part_type' not in cols and 'rtt_part_name' in cols:
        df.rename(columns={'rtt_part_name': 'rtt_part_type'}, inplace=True)
    return df


def filter_function_totals(df: pd.DataFrame) -> pd.DataFrame:
    if 'treatment_function_name' in df.columns:
        mask_total = df['treatment_function_name'].fillna('').str.strip().str.lower().eq('total')
        df_total = df[mask_total]
        if not df_total.empty:
            return df_total
    if 'treatment_function_code' in df.columns:
        return df[df['treatment_function_code'].fillna('') == 'C_999']
    return df.iloc[0:0]
