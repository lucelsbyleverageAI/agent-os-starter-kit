from __future__ import annotations

import logging
import math
from typing import Optional, Sequence

try:
    import psycopg
    from psycopg.rows import tuple_row
    from psycopg.types.json import Json
except Exception:  # pragma: no cover - optional dependency for now
    psycopg = None  # type: ignore


logger = logging.getLogger(__name__)


SCHEMA_NAME = "performance_data"

# Note: Table creation is now handled by migration 007_performance_data_init.sql
# This module only creates the schema and views, which may not exist yet.

CREATE_SCHEMA_SQL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME};
"""

CREATE_TRUST_SNAPSHOT_VIEW_SQL = f"""
CREATE OR REPLACE VIEW {SCHEMA_NAME}.rtt_trust_snapshot_v AS
SELECT
  period,
  entity_level,
  org_code,
  org_name,
  rtt_part_type,
  completed_total,
  completed_within_18,
  compliance_18w,
  waiting_list_total,
  (1 - NULLIF(pct_over_18, 0))::double precision AS pct_within_18,
  median_weeks_completed,
  p95_weeks_completed,
  median_weeks_waiting,
  p92_weeks_waiting,
  over_18,
  over_26,
  over_40,
  over_52,
  over_65,
  over_78,
  unknown_clock_start
FROM {SCHEMA_NAME}.rtt_metrics_gold;
"""

CREATE_ODS_ORG_CURRENT_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.ods_org_current (
    org_code TEXT PRIMARY KEY,
    org_name TEXT,
    primary_role_code TEXT,
    primary_role_display TEXT,
    matched_role_code TEXT,
    matched_role_display TEXT,
    is_foundation_trust BOOLEAN,
    active BOOLEAN,
    last_change_date TIMESTAMP,
    address_json JSONB,
    roles_json JSONB,
    phone TEXT,
    website TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


UPSERT_GOLD_SQL = f"""
INSERT INTO {SCHEMA_NAME}.rtt_metrics_gold (
  period, entity_level, org_code, org_name, rtt_part_type,
  completed_total, completed_within_18, incomplete_total, over_18,
  over_26, over_40, over_52, over_65, over_78, unknown_clock_start,
  compliance_18w, waiting_list_total, pct_over_18, pct_over_26,
  pct_over_40, pct_over_52, pct_over_65, pct_over_78,
  median_weeks_completed, p95_weeks_completed, median_weeks_waiting,
  p92_weeks_waiting
) VALUES (
  %(period)s, %(entity_level)s, %(org_code)s, %(org_name)s, %(rtt_part_type)s,
  %(completed_total)s, %(completed_within_18)s, %(incomplete_total)s, %(over_18)s,
  %(over_26)s, %(over_40)s, %(over_52)s, %(over_65)s, %(over_78)s, %(unknown_clock_start)s,
  %(compliance_18w)s, %(waiting_list_total)s, %(pct_over_18)s, %(pct_over_26)s,
  %(pct_over_40)s, %(pct_over_52)s, %(pct_over_65)s, %(pct_over_78)s,
  %(median_weeks_completed)s, %(p95_weeks_completed)s, %(median_weeks_waiting)s,
  %(p92_weeks_waiting)s
)
ON CONFLICT (period, entity_level, org_code, rtt_part_type) DO UPDATE SET
  org_name = EXCLUDED.org_name,
  completed_total = EXCLUDED.completed_total,
  completed_within_18 = EXCLUDED.completed_within_18,
  incomplete_total = EXCLUDED.incomplete_total,
  over_18 = EXCLUDED.over_18,
  over_26 = EXCLUDED.over_26,
  over_40 = EXCLUDED.over_40,
  over_52 = EXCLUDED.over_52,
  over_65 = EXCLUDED.over_65,
  over_78 = EXCLUDED.over_78,
  unknown_clock_start = EXCLUDED.unknown_clock_start,
  compliance_18w = EXCLUDED.compliance_18w,
  waiting_list_total = EXCLUDED.waiting_list_total,
  pct_over_18 = EXCLUDED.pct_over_18,
  pct_over_26 = EXCLUDED.pct_over_26,
  pct_over_40 = EXCLUDED.pct_over_40,
  pct_over_52 = EXCLUDED.pct_over_52,
  pct_over_65 = EXCLUDED.pct_over_65,
  pct_over_78 = EXCLUDED.pct_over_78,
  median_weeks_completed = EXCLUDED.median_weeks_completed,
  p95_weeks_completed = EXCLUDED.p95_weeks_completed,
  median_weeks_waiting = EXCLUDED.median_weeks_waiting,
  p92_weeks_waiting = EXCLUDED.p92_weeks_waiting;
"""


class PostgresWriter:
    def __init__(self, db_url: Optional[str]) -> None:
        self.db_url = db_url
        if psycopg is None:
            logger.warning("psycopg not installed; PostgresWriter will be a no-op")

    def _connect(self):  # type: ignore
        if psycopg is None or not self.db_url:
            return None
        return psycopg.connect(self.db_url, autocommit=False, row_factory=tuple_row)

    def ensure_schema_and_tables(self) -> None:
        """
        Ensures the performance_data schema exists and creates/updates views.

        NOTE: Table creation is now handled by migration 007_performance_data_init.sql.
        This method only ensures:
        1. Schema exists (idempotent)
        2. Views are up-to-date (CREATE OR REPLACE)
        3. Backward compatibility columns exist (ALTER TABLE IF NOT EXISTS)

        Run migration 007_performance_data_init.sql before using this pipeline.
        """
        conn = self._connect()
        if conn is None:
            logger.info("Skipping DB init (no DB connection configured)")
            return
        with conn:
            with conn.cursor() as cur:
                # Create schema (idempotent)
                cur.execute(CREATE_SCHEMA_SQL)

                # Add columns for backward compatibility if table exists from older schema
                # (Migration 007 creates these columns, but this ensures compatibility
                # if someone is migrating from an older version)
                cur.execute(f"ALTER TABLE IF EXISTS {SCHEMA_NAME}.rtt_metrics_gold ADD COLUMN IF NOT EXISTS median_weeks_completed double precision;")
                cur.execute(f"ALTER TABLE IF EXISTS {SCHEMA_NAME}.rtt_metrics_gold ADD COLUMN IF NOT EXISTS p95_weeks_completed double precision;")
                cur.execute(f"ALTER TABLE IF EXISTS {SCHEMA_NAME}.rtt_metrics_gold ADD COLUMN IF NOT EXISTS median_weeks_waiting double precision;")
                cur.execute(f"ALTER TABLE IF EXISTS {SCHEMA_NAME}.rtt_metrics_gold ADD COLUMN IF NOT EXISTS p92_weeks_waiting double precision;")

                # Create ODS org table (idempotent)
                cur.execute(CREATE_ODS_ORG_CURRENT_SQL)

                # Create or replace views (idempotent)
                cur.execute(CREATE_TRUST_SNAPSHOT_VIEW_SQL)
        conn.close()

    @staticmethod
    def _coerce(val):
        if val is None:
            return None
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        # Convert plain dicts to JSON for jsonb columns
        try:
            if isinstance(val, (dict, list)):
                return Json(val)  # type: ignore[name-defined]
        except Exception:
            pass
        return val

    def upsert_gold(self, records: Sequence[dict]) -> int:
        conn = self._connect()
        if conn is None:
            logger.info("Skipping upsert (no DB connection configured)")
            return 0
        inserted = 0
        with conn:
            with conn.cursor() as cur:
                for rec in records:
                    safe = {k: self._coerce(v) for k, v in rec.items()}
                    cur.execute(UPSERT_GOLD_SQL, safe)
                    inserted += 1
        conn.close()
        return inserted

    def upsert(self, table_name: str, records: Sequence[dict], p_keys: Sequence[str]) -> int:
        conn = self._connect()
        if conn is None:
            logger.info("Skipping upsert (no DB connection configured)")
            return 0
        if not records:
            return 0

        inserted = 0
        with conn:
            with conn.cursor() as cur:

                # Dynamically build the upsert statement
                first_record = records[0]
                columns = first_record.keys()

                # Check that p_keys are in columns
                if not all(k in columns for k in p_keys):
                    raise ValueError("All primary keys must be in the record columns")

                cols_sql = ", ".join(f'"{c}"' for c in columns)
                p_keys_sql = ", ".join(f'"{k}"' for k in p_keys)

                # Create the placeholder string: %(col1)s, %(col2)s ...
                placeholders = ", ".join(f"%({c})s" for c in columns)

                # Create the ON CONFLICT...DO UPDATE SET part
                update_cols = [c for c in columns if c not in p_keys]
                update_sql = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)

                sql = f"""
                INSERT INTO {SCHEMA_NAME}.{table_name} ({cols_sql})
                VALUES ({placeholders})
                ON CONFLICT ({p_keys_sql})
                DO UPDATE SET {update_sql};
                """

                for rec in records:
                    safe = {k: self._coerce(v) for k, v in rec.items()}
                    cur.execute(sql, safe)
                    inserted += 1

        conn.close()
        return inserted
