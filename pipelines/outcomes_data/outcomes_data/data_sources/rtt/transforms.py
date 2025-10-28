from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import chardet
import pandas as pd

from outcomes_data.data_sources.rtt.bins import detect_bin_label, parse_bin_to_bounds
from outcomes_data.data_sources.rtt.normaliser import ensure_period_and_parts, filter_function_totals, normalise_col


CANONICAL_ID_COLS = [
    "period",
    "provider_parent_org_code",
    "provider_parent_name",
    "provider_org_code",
    "provider_org_name",
    "commissioner_parent_org_code",
    "commissioner_parent_name",
    "commissioner_code",
    "commissioner_name",
    "rtt_part_type",
    "rtt_part_description",
    "treatment_function_code",
    "treatment_function_name",
]


def load_bronze_long(csv_path: Path, header_idx: int, encoding: str) -> pd.DataFrame:
    raw = csv_path.read_bytes()
    # Re-decode based on detected encoding (stored by extractor)
    try:
        text = raw.decode(encoding)
    except Exception:
        try:
            text = raw.decode("utf-8-sig")
        except Exception:
            text = raw.decode("latin-1", errors="replace")
    df = pd.read_csv(io.StringIO(text), header=0, skiprows=header_idx, dtype=str)
    df.columns = [normalise_col(c) for c in df.columns]
    df = ensure_period_and_parts(df, csv_path)

    id_cols = [c for c in CANONICAL_ID_COLS if c in df.columns]
    bin_cols: Dict[str, str] = {}
    for c in df.columns:
        label = detect_bin_label(c)
        if label is not None:
            bin_cols[c] = label
    if not bin_cols:
        return pd.DataFrame(columns=id_cols + ["bin", "value"])  # empty

    long_df = df.melt(
        id_vars=id_cols,
        value_vars=list(bin_cols.keys()),
        var_name="bin_raw",
        value_name="value",
    )
    long_df["bin"] = long_df["bin_raw"].map(bin_cols)
    long_df.drop(columns=["bin_raw"], inplace=True)
    long_df = filter_function_totals(long_df)
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    return long_df


def _entity_views(long_df: pd.DataFrame) -> list[tuple[str, pd.DataFrame, str, str]]:
    views: list[tuple[str, pd.DataFrame, str, str]] = []
    if {"provider_org_code", "provider_org_name"}.issubset(long_df.columns):
        views.append((
            "provider",
            long_df.rename(columns={"provider_org_code": "org_code", "provider_org_name": "org_name"}),
            "org_code",
            "org_name",
        ))
    if {"provider_parent_org_code", "provider_parent_name"}.issubset(long_df.columns):
        views.append((
            "parent",
            long_df.rename(columns={"provider_parent_org_code": "org_code", "provider_parent_name": "org_name"}),
            "org_code",
            "org_name",
        ))
    return views


def _is_completed_part(row: pd.Series) -> bool:
    t = str(row.get("rtt_part_type", "")).upper()
    d = str(row.get("rtt_part_description", "")).lower()
    return t.startswith("PART_1") or ("completed" in d)


def _is_incomplete_part(row: pd.Series) -> bool:
    t = str(row.get("rtt_part_type", "")).upper()
    d = str(row.get("rtt_part_description", "")).lower()
    return t.startswith("PART_2") or ("incomplete" in d)


def _estimate_quantile_weeks(bins: pd.Series, values: pd.Series, q: float) -> float | None:
    # Expects aligned series; ignores unknown_clock_start and NaNs
    try:
        df = pd.DataFrame({"bin": bins.astype(str), "v": pd.to_numeric(values, errors="coerce")})
    except Exception:
        return None
    df = df.dropna(subset=["v"]).loc[lambda d: d["bin"] != "unknown_clock_start"]
    if df.empty:
        return None
    rows: list[tuple[int, int | None, float]] = []
    for b, v in zip(df["bin"], df["v"]):
        try:
            lo, hi = parse_bin_to_bounds(str(b))
            rows.append((lo, hi, float(v)))
        except Exception:
            continue
    if not rows:
        return None
    rows.sort(key=lambda t: t[0])
    total = sum(v for _, __, v in rows)
    if total <= 0:
        return None
    target = q * total
    cumulative = 0.0
    for lo, hi, v in rows:
        next_cum = cumulative + v
        if next_cum >= target:
            # Interpolate within the bin (assume uniform)
            # Treat open-ended as width=1 week to avoid zero division; quantiles usually below open-ended tail
            width = (hi - lo) if hi is not None else 1
            if width <= 0:
                return float(lo)
            frac = 0.0 if v == 0 else max(0.0, min(1.0, (target - cumulative) / v))
            return float(lo) + frac * float(width)
        cumulative = next_cum
    # If we get here, return the upper bound of the last bin
    last_lo, last_hi, _ = rows[-1]
    return float(last_hi if last_hi is not None else last_lo)


def build_silver_from_bronze(long_df: pd.DataFrame) -> pd.DataFrame:
    if long_df.empty:
        return pd.DataFrame(
            columns=[
                "period",
                "entity_level",
                "org_code",
                "org_name",
                "rtt_part_type",
                "completed_total",
                "completed_within_18",
                "incomplete_total",
                "over_18",
                "over_26",
                "over_40",
                "over_52",
                "over_65",
                "over_78",
                "unknown_clock_start",
            ]
        )

    silver_frames: list[pd.DataFrame] = []
    for level, view_df, code_col, name_col in _entity_views(long_df):
        gcols = [c for c in ["period", code_col, name_col, "rtt_part_type", "rtt_part_description", "bin"] if c in view_df.columns]
        df = view_df[gcols + ["value"]].copy()

        # Completed metrics
        df_completed = df[df.apply(_is_completed_part, axis=1)]
        within_mask = []
        for b in df_completed["bin"].fillna(""):
            try:
                lo, hi = parse_bin_to_bounds(str(b))
                within_mask.append(bool(hi is not None and hi <= 18))
            except Exception:
                within_mask.append(False)
        df_completed = df_completed.assign(_within18=within_mask)
        grp_c = [c for c in ["period", code_col, name_col, "rtt_part_type"] if c in df_completed.columns]
        agg_completed = df_completed.groupby(grp_c, as_index=False).agg(
            completed_total=("value", "sum"),
            completed_within_18=("_within18", lambda s: df_completed.loc[s.index, "value"].where(s).sum()),
        )
        # Quantiles for completed (median, p95) using distribution across bins
        q_completed = (
            df_completed.groupby(grp_c)
            .apply(lambda d: pd.Series({
                "median_weeks_completed": _estimate_quantile_weeks(d["bin"], d["value"], 0.5),
                "p95_weeks_completed": _estimate_quantile_weeks(d["bin"], d["value"], 0.95),
            }))
            .reset_index()
        )
        agg_completed = agg_completed.merge(q_completed, on=grp_c, how="left")

        # Incomplete metrics
        df_incomplete = df[df.apply(_is_incomplete_part, axis=1)]
        over_cols = {18: "over_18", 26: "over_26", 40: "over_40", 52: "over_52", 65: "over_65", 78: "over_78"}
        def threshold_sum(th: int) -> pd.Series:
            idx = []
            for b in df_incomplete["bin"].fillna(""):
                try:
                    lo, hi = parse_bin_to_bounds(str(b))
                    idx.append(bool(lo >= th))
                except Exception:
                    idx.append(False)
            return pd.Series(idx, index=df_incomplete.index)

        grp_i = [c for c in ["period", code_col, name_col, "rtt_part_type"] if c in df_incomplete.columns]
        base_incomp = df_incomplete.groupby(grp_i, as_index=False).agg(
            incomplete_total=("value", "sum"),
            unknown_clock_start=("value", lambda s: df_incomplete.loc[s.index, "value"].where(df_incomplete["bin"].eq("unknown_clock_start")).sum()),
        )
        # Add threshold sums (vectorised; avoid groupby.apply warning)
        for th, colname in over_cols.items():
            mask = threshold_sum(th)
            sums = (
                df_incomplete.assign(_m=mask)
                .loc[lambda d: d["_m"]]
                .groupby(grp_i, as_index=False)["value"].sum()
                .rename(columns={"value": colname})
            )
            base_incomp = base_incomp.merge(sums, on=grp_i, how="left")
        # Quantiles for waiting list (median, p92) excluding unknowns
        q_incomplete = (
            df_incomplete.groupby(grp_i)
            .apply(lambda d: pd.Series({
                "median_weeks_waiting": _estimate_quantile_weeks(d["bin"], d["value"], 0.5),
                "p92_weeks_waiting": _estimate_quantile_weeks(d["bin"], d["value"], 0.92),
            }))
            .reset_index()
        )
        base_incomp = base_incomp.merge(q_incomplete, on=grp_i, how="left")

        # Merge completed + incomplete
        silver = agg_completed.merge(base_incomp, on=grp_c, how="outer")
        silver.insert(1, "entity_level", level)
        silver.rename(columns={code_col: "org_code", name_col: "org_name"}, inplace=True)
        # Fill NaNs with 0 for numeric
        num_cols = [
            c
            for c in silver.columns
            if c
            not in {
                "period",
                "entity_level",
                "org_code",
                "org_name",
                "rtt_part_type",
                "median_weeks_completed",
                "p95_weeks_completed",
                "median_weeks_waiting",
                "p92_weeks_waiting",
            }
        ]
        for c in num_cols:
            silver[c] = pd.to_numeric(silver[c], errors="coerce").fillna(0)
        silver_frames.append(silver)

    if not silver_frames:
        return pd.DataFrame()
    return pd.concat(silver_frames, ignore_index=True)


def compute_gold_metrics(silver_df: pd.DataFrame) -> pd.DataFrame:
    if silver_df.empty:
        return silver_df.copy()
    df = silver_df.copy()
    # Compliance (completed)
    df["compliance_18w"] = 0.0
    mask_den = df["completed_total"] > 0
    df.loc[mask_den, "compliance_18w"] = (
        df.loc[mask_den, "completed_within_18"] / df.loc[mask_den, "completed_total"]
    )
    # Waiting list (incomplete)
    # Exclude unknown_clock_start from denominator for waiting list percentages
    df["waiting_list_total"] = pd.to_numeric(df.get("incomplete_total", 0), errors="coerce").fillna(0) - pd.to_numeric(
        df.get("unknown_clock_start", 0), errors="coerce"
    ).fillna(0)
    df.loc[df["waiting_list_total"] < 0, "waiting_list_total"] = 0
    # Percentages of list
    for col in ["over_18", "over_26", "over_40", "over_52", "over_65", "over_78"]:
        pct_col = f"pct_{col}"
        df[pct_col] = 0.0
        mask = df["waiting_list_total"] > 0
        if col in df.columns:
            df.loc[mask, pct_col] = df.loc[mask, col] / df.loc[mask, "waiting_list_total"]
        else:
            df[pct_col] = 0.0
    # Build Overall row per entity by summing across relevant parts
    base_keys = ["period", "entity_level", "org_code", "org_name"]
    have_cols = [c for c in base_keys if c in df.columns]
    frames: list[pd.DataFrame] = [df]
    try:
        # Completed overall (sum Part_1* rows)
        is_completed = df.apply(_is_completed_part, axis=1)
        comp_cols = [
            "completed_total",
            "completed_within_18",
        ]
        agg_c = (
            df.loc[is_completed, have_cols + comp_cols]
            .groupby(have_cols, as_index=False)
            .sum()
            .assign(rtt_part_type="Overall")
        )
        # Incomplete overall (sum Part_2* rows)
        is_incomplete = df.apply(_is_incomplete_part, axis=1)
        inc_cols = [
            "incomplete_total",
            "over_18",
            "over_26",
            "over_40",
            "over_52",
            "over_65",
            "over_78",
            "unknown_clock_start",
        ]
        agg_i = (
            df.loc[is_incomplete, have_cols + inc_cols]
            .groupby(have_cols, as_index=False)
            .sum()
            .assign(rtt_part_type="Overall")
        )
        overall = agg_c.merge(agg_i, on=have_cols + ["rtt_part_type"], how="outer")
        # Carry forward quantiles as NaN for overall (not computed across parts here)
        for qcol in [
            "median_weeks_completed",
            "p95_weeks_completed",
            "median_weeks_waiting",
            "p92_weeks_waiting",
        ]:
            if qcol not in overall.columns:
                overall[qcol] = pd.NA
        # Recompute derived metrics for Overall using same logic
        frames.append(overall)
    except Exception:
        pass
    out = pd.concat(frames, ignore_index=True)
    # Recompute derived metrics for any newly added rows
    out["compliance_18w"] = 0.0
    mask_den = out["completed_total"].fillna(0) > 0
    out.loc[mask_den, "compliance_18w"] = (
        out.loc[mask_den, "completed_within_18"].fillna(0) / out.loc[mask_den, "completed_total"].fillna(0)
    )
    out["waiting_list_total"] = pd.to_numeric(out.get("incomplete_total", 0), errors="coerce").fillna(0) - pd.to_numeric(
        out.get("unknown_clock_start", 0), errors="coerce"
    ).fillna(0)
    out.loc[out["waiting_list_total"] < 0, "waiting_list_total"] = 0
    for col in ["over_18", "over_26", "over_40", "over_52", "over_65", "over_78"]:
        pct_col = f"pct_{col}"
        out[pct_col] = 0.0
        mask = out["waiting_list_total"] > 0
        if col in out.columns:
            out.loc[mask, pct_col] = out.loc[mask, col].fillna(0) / out.loc[mask, "waiting_list_total"].fillna(0)
        else:
            out[pct_col] = 0.0
    return out
