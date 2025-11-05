"""
SQL query builders for NHS analytics tools.

This module provides functions that build and execute SQL queries against
the performance_data schema. All functions return raw query results as
dictionaries - no analysis or interpretation.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
import logging

logger = logging.getLogger(__name__)


def get_latest_period(engine: Engine, domain: Optional[str] = None) -> str:
    """
    Get the most recent reporting period available in the data.

    Args:
        engine: SQLAlchemy engine
        domain: Optional domain filter ('rtt', 'cancer', 'oversight')

    Returns:
        Latest period string (e.g., '2025-08')
    """
    query = """
        SELECT MAX(period) as latest_period
        FROM performance_data.insight_metrics_long
    """

    if domain:
        query += f" WHERE domain = :domain"

    with engine.connect() as conn:
        result = conn.execute(text(query), {"domain": domain} if domain else {})
        row = result.fetchone()
        return row[0] if row and row[0] else None


def get_latest_periods_by_domain(engine: Engine, domains: List[str]) -> Dict[str, Optional[str]]:
    """
    Get the most recent reporting period for each domain independently.

    Different domains have different reporting cadences and period formats:
    - RTT: Monthly (YYYY-MM, e.g., '2025-08')
    - Cancer: Monthly (YYYY-MM)
    - Oversight: Quarterly (e.g., 'Q1 2025/26')

    Args:
        engine: SQLAlchemy engine
        domains: List of domains to get periods for ('rtt', 'cancer', 'oversight')

    Returns:
        Dictionary mapping domain to its latest period (None if no data exists)
    """
    query = """
        SELECT
            domain,
            MAX(period) as latest_period
        FROM performance_data.insight_metrics_long
        WHERE domain = ANY(:domains)
        GROUP BY domain
    """

    periods_by_domain = {}

    with engine.connect() as conn:
        result = conn.execute(text(query), {"domains": domains})
        for row in result:
            periods_by_domain[row[0]] = row[1]

    # Ensure all requested domains are in the result (even if None)
    for domain in domains:
        if domain not in periods_by_domain:
            periods_by_domain[domain] = None

    logger.info(f"Detected periods by domain: {periods_by_domain}")
    return periods_by_domain


def get_latest_periods_per_metric(
    engine: Engine,
    domain: str,
    org_code: Optional[str] = None
) -> Dict[str, str]:
    """
    Get the most recent reporting period for EACH metric within a domain.

    This is essential for oversight metrics where different metrics have different
    reporting cadences:
    - Some metrics report quarterly (Q1 2025/26)
    - Some metrics report annually (2024)
    - Some metrics report monthly (Jun-25)
    - Some metrics report on rolling periods (Jul 24 - Jun 25)

    Args:
        engine: SQLAlchemy engine
        domain: Domain to query ('rtt', 'cancer', 'oversight')
        org_code: Optional organization code to filter by (for oversight, to get
                 only metrics this org reports)

    Returns:
        Dictionary mapping metric_id to its latest period
        Example: {'OF0010': 'Q1 2025/26', 'OF0061': '2024', 'OF0023': 'Jun-25'}
    """
    query = """
        SELECT
            metric_id,
            MAX(period) as latest_period
        FROM performance_data.insight_metrics_long
        WHERE domain = :domain
    """

    params = {"domain": domain}

    if org_code:
        query += " AND org_code = :org_code"
        params["org_code"] = org_code

    query += """
        GROUP BY metric_id
        ORDER BY metric_id
    """

    metric_periods = {}

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        for row in result:
            metric_periods[row[0]] = row[1]

    logger.info(f"Detected {len(metric_periods)} metrics for {domain} domain" +
                (f" (org: {org_code})" if org_code else ""))
    logger.debug(f"Sample metric periods: {list(metric_periods.items())[:5]}")

    return metric_periods


def get_trust_info(engine: Engine, org_code: str) -> Optional[Dict[str, Any]]:
    """
    Get basic trust information from dim_organisations.

    Args:
        engine: SQLAlchemy engine
        org_code: NHS organisation code

    Returns:
        Dictionary with trust details or None if not found
    """
    query = """
        SELECT
            org_code,
            trust_name,
            region,
            trust_type,
            trust_subtype
        FROM performance_data.dim_organisations
        WHERE org_code = :org_code
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), {"org_code": org_code})
        row = result.fetchone()
        if row:
            return {
                "org_code": row[0],
                "trust_name": row[1],
                "region": row[2],
                "trust_type": row[3],
                "trust_subtype": row[4]
            }
        return None


def _query_oversight_with_metric_periods(
    engine: Engine,
    org_code: str,
    metric_periods: Dict[str, str],
    trust_info: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Query oversight metrics where each metric uses its own latest period.

    This is necessary because oversight metrics have different reporting cadences:
    - Some quarterly (Q1 2025/26)
    - Some annual (2024)
    - Some monthly (Jun-25)
    - Some rolling (Jul 24 - Jun 25)

    Args:
        engine: SQLAlchemy engine
        org_code: NHS organisation code
        metric_periods: Dict mapping metric_id to its latest period
        trust_info: Trust metadata (region, type, subtype)

    Returns:
        List of metric dictionaries with cohort statistics
    """
    if not metric_periods:
        logger.warning(f"No metric periods provided for oversight query")
        return []

    # Create VALUES clause for (metric_id, period) pairs
    metric_period_pairs = [(mid, period) for mid, period in metric_periods.items()]

    # Build the VALUES clause
    values_clause = ", ".join([f"('{mid}', '{period}')" for mid, period in metric_period_pairs])

    query = f"""
        WITH metric_latest_periods AS (
            -- Explicitly list which period to use for each metric
            SELECT * FROM (VALUES
                {values_clause}
            ) AS t(metric_id, period)
        ),
        trust_metrics AS (
            SELECT
                i.metric_id,
                i.metric_label,
                i.domain,
                i.period,
                i.value,
                i.unit,
                i.numerator,
                i.denominator,
                i.target_threshold,
                i.target_met,
                i.higher_is_better,
                i.percentile_overall,
                i.percentile_trust_type,
                i.percentile_trust_subtype,
                i.rtt_part_type,
                i.cancer_type,
                i.referral_route,
                i.entity_level
            FROM performance_data.insight_metrics_long i
            INNER JOIN metric_latest_periods mlp
                ON i.metric_id = mlp.metric_id
                AND i.period = mlp.period
            WHERE i.org_code = :org_code
                AND i.domain = 'oversight'
                AND i.valid_sample = true
        ),
        cohort_stats AS (
            -- National cohort stats per metric (using each metric's own latest period)
            SELECT
                i.metric_id,
                'national' as cohort_type,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY i.value) as q1,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY i.value) as median,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY i.value) as q3
            FROM performance_data.insight_metrics_long i
            INNER JOIN metric_latest_periods mlp
                ON i.metric_id = mlp.metric_id
                AND i.period = mlp.period
            WHERE i.domain = 'oversight'
                AND i.valid_sample = true
            GROUP BY i.metric_id

            UNION ALL

            -- Trust type cohort
            SELECT
                i.metric_id,
                'trust_type' as cohort_type,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY i.value) as q1,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY i.value) as median,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY i.value) as q3
            FROM performance_data.insight_metrics_long i
            INNER JOIN metric_latest_periods mlp
                ON i.metric_id = mlp.metric_id
                AND i.period = mlp.period
            JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
            WHERE i.domain = 'oversight'
                AND i.valid_sample = true
                AND o.trust_type = :trust_type
            GROUP BY i.metric_id

            UNION ALL

            -- Trust subtype cohort
            SELECT
                i.metric_id,
                'trust_subtype' as cohort_type,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY i.value) as q1,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY i.value) as median,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY i.value) as q3
            FROM performance_data.insight_metrics_long i
            INNER JOIN metric_latest_periods mlp
                ON i.metric_id = mlp.metric_id
                AND i.period = mlp.period
            JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
            WHERE i.domain = 'oversight'
                AND i.valid_sample = true
                AND o.trust_subtype = :trust_subtype
            GROUP BY i.metric_id

            UNION ALL

            -- Regional cohort
            SELECT
                i.metric_id,
                'region' as cohort_type,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY i.value) as q1,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY i.value) as median,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY i.value) as q3
            FROM performance_data.insight_metrics_long i
            INNER JOIN metric_latest_periods mlp
                ON i.metric_id = mlp.metric_id
                AND i.period = mlp.period
            JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
            WHERE i.domain = 'oversight'
                AND i.valid_sample = true
                AND o.region = :region
            GROUP BY i.metric_id
        ),
        regional_ranks AS (
            SELECT
                i.metric_id,
                i.org_code,
                ROW_NUMBER() OVER (
                    PARTITION BY i.metric_id
                    ORDER BY CASE WHEN i.higher_is_better THEN i.value ELSE -i.value END DESC
                ) as regional_rank,
                COUNT(*) OVER (PARTITION BY i.metric_id) as regional_total
            FROM performance_data.insight_metrics_long i
            INNER JOIN metric_latest_periods mlp
                ON i.metric_id = mlp.metric_id
                AND i.period = mlp.period
            JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
            WHERE i.domain = 'oversight'
                AND i.valid_sample = true
                AND o.region = :region
        )
        SELECT
            tm.*,
            cs_nat.q1 as national_q1,
            cs_nat.median as national_median,
            cs_nat.q3 as national_q3,
            cs_type.q1 as trust_type_q1,
            cs_type.median as trust_type_median,
            cs_type.q3 as trust_type_q3,
            cs_subtype.q1 as trust_subtype_q1,
            cs_subtype.median as trust_subtype_median,
            cs_subtype.q3 as trust_subtype_q3,
            cs_region.q1 as region_q1,
            cs_region.median as region_median,
            cs_region.q3 as region_q3,
            rr.regional_rank,
            rr.regional_total
        FROM trust_metrics tm
        LEFT JOIN cohort_stats cs_nat
            ON tm.metric_id = cs_nat.metric_id AND cs_nat.cohort_type = 'national'
        LEFT JOIN cohort_stats cs_type
            ON tm.metric_id = cs_type.metric_id AND cs_type.cohort_type = 'trust_type'
        LEFT JOIN cohort_stats cs_subtype
            ON tm.metric_id = cs_subtype.metric_id AND cs_subtype.cohort_type = 'trust_subtype'
        LEFT JOIN cohort_stats cs_region
            ON tm.metric_id = cs_region.metric_id AND cs_region.cohort_type = 'region'
        LEFT JOIN regional_ranks rr
            ON tm.metric_id = rr.metric_id AND rr.org_code = :org_code
        ORDER BY tm.metric_id
    """

    metrics = []
    with engine.connect() as conn:
        result = conn.execute(text(query), {
            "org_code": org_code,
            "trust_type": trust_info["trust_type"],
            "trust_subtype": trust_info["trust_subtype"],
            "region": trust_info["region"]
        })

        for row in result:
            metrics.append(dict(row._mapping))

    return metrics


def get_aggregated_cancer_percentiles(
    engine: Engine,
    org_code: str,
    period: str,
    trust_type: str,
    trust_subtype: str
) -> Dict[str, Dict[str, float]]:
    """
    Calculate percentile rankings for aggregated cancer performance.

    Since cancer metrics are disaggregated by cancer_type in the database,
    we need to aggregate them first (sum numerators/denominators across all
    cancer types) and then rank trusts to calculate percentiles.

    Args:
        engine: SQLAlchemy engine
        org_code: Target trust code
        period: Reporting period (e.g., '2025-08')
        trust_type: Trust type for cohort comparison
        trust_subtype: Trust subtype for cohort comparison

    Returns:
        Dictionary mapping metric_id to percentiles:
        {
            'cancer_28d': {'overall': 0.75, 'trust_type': 0.82},
            'cancer_31d': {'overall': 0.65, 'trust_type': 0.71},
            'cancer_62d': {'overall': 0.45, 'trust_type': 0.52}
        }
    """
    logger.info(f"Calculating aggregated cancer percentiles for {org_code} in period {period}")

    # Query to aggregate cancer metrics across all cancer types for each trust
    query = text("""
        WITH aggregated_by_trust AS (
            SELECT
                i.metric_id,
                i.org_code,
                o.trust_type,
                o.trust_subtype,
                SUM(i.numerator) as total_numerator,
                SUM(i.denominator) as total_denominator,
                CASE
                    WHEN SUM(i.denominator) > 0
                    THEN SUM(i.numerator)::float / SUM(i.denominator)::float
                    ELSE NULL
                END as aggregate_value
            FROM performance_data.insight_metrics_long i
            JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
            WHERE i.domain = 'cancer'
                AND i.period = :period
                AND (i.referral_route = 'ALL ROUTES' OR i.referral_route IS NULL)
                AND i.valid_sample = true
            GROUP BY i.metric_id, i.org_code, o.trust_type, o.trust_subtype
            HAVING SUM(i.denominator) > 0
        ),
        percentiles AS (
            SELECT
                metric_id,
                org_code,
                aggregate_value,
                -- Overall percentile (all trusts)
                PERCENT_RANK() OVER (
                    PARTITION BY metric_id
                    ORDER BY aggregate_value
                ) as percentile_overall,
                -- Trust type percentile
                PERCENT_RANK() OVER (
                    PARTITION BY metric_id, trust_type
                    ORDER BY aggregate_value
                ) as percentile_trust_type,
                -- Trust subtype percentile
                PERCENT_RANK() OVER (
                    PARTITION BY metric_id, trust_subtype
                    ORDER BY aggregate_value
                ) as percentile_trust_subtype
            FROM aggregated_by_trust
            WHERE aggregate_value IS NOT NULL
        )
        SELECT
            metric_id,
            percentile_overall,
            percentile_trust_type,
            percentile_trust_subtype
        FROM percentiles
        WHERE org_code = :org_code
    """)

    result_dict = {}

    with engine.connect() as conn:
        result = conn.execute(query, {
            "period": period,
            "org_code": org_code
        })

        for row in result:
            result_dict[row[0]] = {
                'overall': row[1],
                'trust_type': row[2],
                'trust_subtype': row[3]
            }

    logger.info(f"Calculated aggregated percentiles for {len(result_dict)} cancer metrics")
    return result_dict


def get_comprehensive_performance(
    engine: Engine,
    org_code: str,
    period: Optional[str] = None,
    domains: Optional[List[str]] = None,
    include_rtt_breakdown: bool = False,
    include_cancer_breakdown: bool = False
) -> Dict[str, Any]:
    """
    Get comprehensive performance metrics for a single trust across multiple domains.

    This function handles different reporting periods for each domain automatically.
    Different domains have different reporting cadences:
    - RTT: Monthly (YYYY-MM, e.g., '2025-08')
    - Cancer: Monthly (YYYY-MM)
    - Oversight: Quarterly (e.g., 'Q1 2025/26')

    Args:
        engine: SQLAlchemy engine
        org_code: NHS organisation code
        period: Reporting period for ALL domains (optional, overrides auto-detection)
                If provided, uses this period for all domains (may result in missing data)
                If None, automatically detects latest period per domain
        domains: List of domains to include (defaults to all: ['rtt', 'cancer', 'oversight'])
        include_rtt_breakdown: Include RTT pathway breakdown (Part_1A, Part_1B, Part_2)
        include_cancer_breakdown: Include cancer type and referral route breakdowns

    Returns:
        Dictionary with:
        - trust_info: Trust details (name, region, type, subtype)
        - periods: Dict mapping domain to its reporting period
        - metrics: List of metric dictionaries with cohort comparisons
    """
    if domains is None:
        domains = ['rtt', 'cancer', 'oversight']

    # Get trust info
    trust_info = get_trust_info(engine, org_code)
    if not trust_info:
        return {"error": f"Organisation code {org_code} not found"}

    # Determine periods to use for each domain
    logger.info(f"Fetching comprehensive performance for org_code={org_code}, domains={domains}")

    if period is not None:
        # User specified a period - use it for all domains (backward compatibility)
        periods_by_domain = {domain: period for domain in domains}
        oversight_metric_periods = None
        logger.info(f"Using period override: {period} for all domains")
    else:
        # Auto-detect latest period for each domain independently
        periods_by_domain = get_latest_periods_by_domain(engine, domains)

        # For oversight, get per-metric periods (different metrics have different latest periods)
        oversight_metric_periods = None
        if 'oversight' in domains:
            oversight_metric_periods = get_latest_periods_per_metric(engine, 'oversight', org_code)
            logger.info(f"Oversight: Using per-metric periods for {len(oversight_metric_periods)} metrics")

    # Query each domain independently with its respective period
    all_metrics = []

    for domain in domains:
        domain_period = periods_by_domain.get(domain)

        # Skip domains with no data
        if domain_period is None:
            logger.warning(f"Domain {domain}: No period detected, skipping")
            continue

        # Special handling for oversight: use per-metric periods
        if domain == 'oversight' and oversight_metric_periods and period is None:
            logger.info(f"Processing oversight domain with {len(oversight_metric_periods)} metric-specific periods")
            # Query oversight metrics using per-metric periods
            oversight_results = _query_oversight_with_metric_periods(
                engine, org_code, oversight_metric_periods, trust_info
            )
            all_metrics.extend(oversight_results)
            logger.info(f"Oversight: Retrieved {len(oversight_results)} metrics")
            continue

        # Build domain-specific query with DISTINCT ON to eliminate duplicates
        # Prioritizes 'Overall' over NULL for rtt_part_type and 'ALL ROUTES' over NULL for referral_route

        # Determine DISTINCT ON key based on breakdown parameters
        # When breakdown is requested, we need to keep multiple rows per metric_id
        # IMPORTANT: ORDER BY must start with the same columns as DISTINCT ON
        if domain == 'rtt' and include_rtt_breakdown:
            distinct_on_clause = "DISTINCT ON (metric_id, rtt_part_type, entity_level)"
            order_by_clause = """metric_id,
                    rtt_part_type NULLS LAST,
                    entity_level NULLS LAST,
                    -- Additional columns for tie-breaking
                    cancer_type NULLS LAST,
                    referral_route NULLS LAST"""
        elif domain == 'cancer' and include_cancer_breakdown:
            distinct_on_clause = "DISTINCT ON (metric_id, cancer_type, referral_route)"
            order_by_clause = """metric_id,
                    cancer_type NULLS LAST,
                    referral_route NULLS LAST,
                    -- Additional columns for tie-breaking
                    rtt_part_type NULLS LAST,
                    entity_level NULLS LAST"""
        else:
            # Default: deduplicate to one row per metric_id
            distinct_on_clause = "DISTINCT ON (metric_id)"
            # Prioritize 'Overall', 'ALL ROUTES', and NULL cancer_type (trust-level aggregates)
            order_by_clause = """metric_id,
                    -- Prioritize NULL cancer_type (trust-level aggregates) for cancer domain
                    cancer_type NULLS FIRST,
                    -- Prioritize 'Overall' and 'ALL ROUTES'
                    CASE WHEN rtt_part_type = 'Overall' THEN 0
                         WHEN rtt_part_type IS NULL THEN 1
                         ELSE 2 END,
                    CASE WHEN referral_route = 'ALL ROUTES' THEN 0
                         WHEN referral_route IS NULL THEN 1
                         ELSE 2 END,
                    CASE WHEN entity_level = 'provider' THEN 0
                         WHEN entity_level IS NULL THEN 1
                         ELSE 2 END,
                    rtt_part_type NULLS LAST,
                    entity_level NULLS LAST,
                    referral_route NULLS LAST"""

        query = f"""
            WITH trust_metrics_raw AS (
                SELECT
                    i.org_code,
                    i.metric_id,
                    i.metric_label,
                    i.domain,
                    i.period,
                    i.value,
                    i.unit,
                    i.numerator,
                    i.denominator,
                    i.target_threshold,
                    i.target_met,
                    i.higher_is_better,
                    i.percentile_overall,
                    i.percentile_trust_type,
                    i.percentile_trust_subtype,
                    i.rtt_part_type,
                    i.cancer_type,
                    i.referral_route,
                    i.entity_level,
                    i.disagg_key
                FROM performance_data.insight_metrics_long i
                WHERE i.org_code = :org_code
                    AND i.period = :period
                    AND i.domain = :domain
                    AND i.valid_sample = true
            ),
            trust_metrics AS (
                SELECT {distinct_on_clause}
                    org_code,
                    metric_id,
                    metric_label,
                    domain,
                    period,
                    value,
                    unit,
                    numerator,
                    denominator,
                    target_threshold,
                    target_met,
                    higher_is_better,
                    percentile_overall,
                    percentile_trust_type,
                    percentile_trust_subtype,
                    rtt_part_type,
                    cancer_type,
                    referral_route,
                    entity_level,
                    disagg_key
                FROM trust_metrics_raw
                ORDER BY
                    {order_by_clause}
            ),
            cohort_stats AS (
                SELECT
                    i.metric_id,
                    i.domain,
                    i.disagg_key,
                    'national' as cohort_type,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY i.value) as q1,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY i.value) as median,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY i.value) as q3
                FROM performance_data.insight_metrics_long i
                WHERE i.period = :period
                    AND i.domain = :domain
                    AND i.valid_sample = true
                    AND i.is_rollup = false
                GROUP BY i.metric_id, i.domain, i.disagg_key

                UNION ALL

                SELECT
                    i.metric_id,
                    i.domain,
                    i.disagg_key,
                    'trust_type' as cohort_type,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY i.value) as q1,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY i.value) as median,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY i.value) as q3
                FROM performance_data.insight_metrics_long i
                JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
                WHERE i.period = :period
                    AND i.domain = :domain
                    AND i.valid_sample = true
                    AND i.is_rollup = false
                    AND o.trust_type = :trust_type
                GROUP BY i.metric_id, i.domain, i.disagg_key

                UNION ALL

                SELECT
                    i.metric_id,
                    i.domain,
                    i.disagg_key,
                    'trust_subtype' as cohort_type,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY i.value) as q1,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY i.value) as median,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY i.value) as q3
                FROM performance_data.insight_metrics_long i
                JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
                WHERE i.period = :period
                    AND i.domain = :domain
                    AND i.valid_sample = true
                    AND i.is_rollup = false
                    AND o.trust_subtype = :trust_subtype
                GROUP BY i.metric_id, i.domain, i.disagg_key

                UNION ALL

                SELECT
                    i.metric_id,
                    i.domain,
                    i.disagg_key,
                    'region' as cohort_type,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY i.value) as q1,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY i.value) as median,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY i.value) as q3
                FROM performance_data.insight_metrics_long i
                JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
                WHERE i.period = :period
                    AND i.domain = :domain
                    AND i.valid_sample = true
                    AND i.is_rollup = false
                    AND o.region = :region
                GROUP BY i.metric_id, i.domain, i.disagg_key
            ),
            regional_ranks AS (
                SELECT
                    i.metric_id,
                    i.disagg_key,
                    i.org_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY i.metric_id, i.disagg_key
                        ORDER BY CASE WHEN i.higher_is_better THEN i.value ELSE -i.value END DESC
                    ) as regional_rank,
                    COUNT(*) OVER (PARTITION BY i.metric_id, i.disagg_key) as regional_total
                FROM performance_data.insight_metrics_long i
                JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
                WHERE i.period = :period
                    AND i.domain = :domain
                    AND i.valid_sample = true
                    AND i.is_rollup = false
                    AND o.region = :region
            )
            SELECT
                tm.*,
                cs_nat.q1 as national_q1,
                cs_nat.median as national_median,
                cs_nat.q3 as national_q3,
                cs_type.q1 as trust_type_q1,
                cs_type.median as trust_type_median,
                cs_type.q3 as trust_type_q3,
                cs_subtype.q1 as trust_subtype_q1,
                cs_subtype.median as trust_subtype_median,
                cs_subtype.q3 as trust_subtype_q3,
                cs_region.q1 as region_q1,
                cs_region.median as region_median,
                cs_region.q3 as region_q3,
                rr.regional_rank,
                rr.regional_total
            FROM trust_metrics tm
            LEFT JOIN cohort_stats cs_nat
                ON tm.metric_id = cs_nat.metric_id AND tm.disagg_key = cs_nat.disagg_key AND cs_nat.cohort_type = 'national'
            LEFT JOIN cohort_stats cs_type
                ON tm.metric_id = cs_type.metric_id AND tm.disagg_key = cs_type.disagg_key AND cs_type.cohort_type = 'trust_type'
            LEFT JOIN cohort_stats cs_subtype
                ON tm.metric_id = cs_subtype.metric_id AND tm.disagg_key = cs_subtype.disagg_key AND cs_subtype.cohort_type = 'trust_subtype'
            LEFT JOIN cohort_stats cs_region
                ON tm.metric_id = cs_region.metric_id AND tm.disagg_key = cs_region.disagg_key AND cs_region.cohort_type = 'region'
            LEFT JOIN regional_ranks rr
                ON tm.metric_id = rr.metric_id AND tm.disagg_key = rr.disagg_key AND rr.org_code = :org_code
        """

        # Add filtering for RTT and cancer breakdowns
        # Note: DISTINCT ON already prioritizes 'Overall'/'ALL ROUTES' over NULL
        # WHERE clauses below further filter to exclude unwanted breakdown parts (e.g., Part_1A)
        where_clauses = []

        if domain == 'rtt':
            # Filter to provider-level data (DISTINCT ON already deduplicated)
            where_clauses.append("(tm.entity_level = 'provider' OR tm.entity_level IS NULL)")
            if not include_rtt_breakdown:
                # Exclude pathway breakdowns (Part_1A, Part_1B, Part_2), keep Overall/NULL only
                where_clauses.append("(tm.rtt_part_type = 'Overall' OR tm.rtt_part_type IS NULL)")

        if domain == 'cancer' and not include_cancer_breakdown:
            # Exclude route/type breakdowns, keep trust-level aggregates only (cancer_type IS NULL)
            where_clauses.append("tm.cancer_type IS NULL")
            where_clauses.append("(tm.referral_route = 'ALL ROUTES' OR tm.referral_route IS NULL)")

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY tm.metric_id"

        # Execute query for this domain
        logger.info(f"Querying {domain} domain: period={domain_period}, breakdown={include_rtt_breakdown if domain=='rtt' else include_cancer_breakdown}")

        domain_metrics_before = len(all_metrics)
        query_params = {
            "org_code": org_code,
            "period": domain_period,
            "domain": domain,
            "trust_type": trust_info["trust_type"],
            "trust_subtype": trust_info["trust_subtype"],
            "region": trust_info["region"]
        }
        logger.info(f"{domain}: Query params: org_code={org_code}, period={domain_period}, domain={domain}")

        with engine.connect() as conn:
            result = conn.execute(text(query), query_params)

            for row in result:
                all_metrics.append(dict(row._mapping))

        domain_metrics_count = len(all_metrics) - domain_metrics_before
        logger.info(f"{domain}: Retrieved {domain_metrics_count} metrics")

        # Log sample of retrieved data for debugging
        if domain_metrics_count > 0:
            sample_org_codes = list(set([m.get('org_code', 'N/A') for m in all_metrics[-min(10, domain_metrics_count):]]))
            logger.info(f"{domain}: Sample org_codes from last {min(10, domain_metrics_count)} rows: {sample_org_codes}")

        if domain_metrics_count == 0:
            logger.warning(f"{domain}: NO METRICS retrieved for org_code={org_code}, period={domain_period}. " +
                         f"Check if data exists in database for this combination.")

    # Sort combined metrics by domain and metric_id
    all_metrics.sort(key=lambda m: (m.get('domain', ''), m.get('metric_id', '')))

    logger.info(f"Total metrics retrieved across all domains: {len(all_metrics)}")

    return {
        "trust_info": trust_info,
        "periods": periods_by_domain,
        "metrics": all_metrics
    }


def compare_trusts(
    engine: Engine,
    org_codes: List[str],
    period: Optional[str] = None,
    metric_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Compare performance metrics across multiple trusts.

    Args:
        engine: SQLAlchemy engine
        org_codes: List of NHS organisation codes (2-10 trusts)
        period: Reporting period (defaults to latest)
        metric_ids: Specific metrics to compare (defaults to key metrics)

    Returns:
        Dictionary with trust comparisons
    """
    if period is None:
        period = get_latest_period(engine)

    # Default to key metrics if not specified
    if metric_ids is None:
        metric_ids = [
            'rtt_compliance_18w',
            'rtt_pct_over_52',
            'cancer_28d_pct_within_target',
            'cancer_31d_pct_within_target',
            'cancer_62d_pct_within_target',
            'oversight_average_score',
            'oversight_segment_inverse'
        ]

    query = """
        SELECT
            o.org_code,
            o.trust_name,
            o.region,
            o.trust_type,
            o.trust_subtype,
            i.metric_id,
            i.metric_label,
            i.domain,
            i.value,
            i.unit,
            i.target_threshold,
            i.target_met,
            i.percentile_overall,
            i.higher_is_better
        FROM performance_data.insight_metrics_long i
        JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
        WHERE i.org_code = ANY(:org_codes)
            AND i.period = :period
            AND i.metric_id = ANY(:metric_ids)
            AND i.valid_sample = true
            AND i.is_rollup = false
        ORDER BY i.metric_id, o.trust_name
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), {
            "org_codes": org_codes,
            "period": period,
            "metric_ids": metric_ids
        })

        comparisons = []
        for row in result:
            comparisons.append(dict(row._mapping))

    return {
        "period": period,
        "org_codes": org_codes,
        "comparisons": comparisons
    }


def get_domain_rankings(
    engine: Engine,
    domain: str,
    metric_id: Optional[str] = None,
    period: Optional[str] = None,
    cohort_filter: Optional[Dict[str, str]] = None,
    top_n: int = 10,
    bottom_n: int = 10,
    highlight_org_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get rankings for a specific domain/metric.

    Args:
        engine: SQLAlchemy engine
        domain: 'rtt', 'cancer', or 'oversight'
        metric_id: Specific metric (defaults to primary for domain)
        period: Reporting period (defaults to latest)
        cohort_filter: Optional filter dict (e.g., {'trust_type': 'Acute trust'})
        top_n: Number of top performers to return
        bottom_n: Number of bottom performers to return
        highlight_org_code: Optional org code to highlight

    Returns:
        Dictionary with rankings data
    """
    if period is None:
        period = get_latest_period(engine, domain)

    # Default metrics by domain
    if metric_id is None:
        default_metrics = {
            'rtt': 'rtt_compliance_18w',
            'cancer': 'cancer_62d_pct_within_target',
            'oversight': 'oversight_average_score'
        }
        metric_id = default_metrics.get(domain, '')

    # Build cohort filter clause
    cohort_where = ""
    cohort_params = {}
    if cohort_filter:
        clauses = []
        for key, value in cohort_filter.items():
            param_name = f"cohort_{key}"
            clauses.append(f"o.{key} = :{param_name}")
            cohort_params[param_name] = value
        if clauses:
            cohort_where = "AND " + " AND ".join(clauses)

    query = f"""
        WITH ranked_trusts AS (
            SELECT
                o.org_code,
                o.trust_name,
                o.region,
                o.trust_type,
                o.trust_subtype,
                i.value,
                i.unit,
                i.higher_is_better,
                i.percentile_overall,
                ROW_NUMBER() OVER (
                    ORDER BY CASE WHEN i.higher_is_better THEN i.value ELSE -i.value END DESC
                ) as rank,
                COUNT(*) OVER () as total_trusts
            FROM performance_data.insight_metrics_long i
            JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
            WHERE i.metric_id = :metric_id
                AND i.period = :period
                AND i.valid_sample = true
                AND i.is_rollup = false
                {cohort_where}
        ),
        cohort_stats AS (
            SELECT
                MIN(value) as min_val,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY value) as q1,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY value) as median,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY value) as q3,
                MAX(value) as max_val
            FROM ranked_trusts
        )
        SELECT
            rt.*,
            cs.min_val,
            cs.q1,
            cs.median,
            cs.q3,
            cs.max_val
        FROM ranked_trusts rt
        CROSS JOIN cohort_stats cs
        WHERE rt.rank <= :top_n
            OR rt.rank > (rt.total_trusts - :bottom_n)
            OR (:highlight_org_code IS NOT NULL AND rt.org_code = :highlight_org_code)
        ORDER BY rt.rank
    """

    params = {
        "metric_id": metric_id,
        "period": period,
        "top_n": top_n,
        "bottom_n": bottom_n,
        "highlight_org_code": highlight_org_code,
        **cohort_params
    }

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rankings = []
        for row in result:
            rankings.append(dict(row._mapping))

    # Get metric info
    metric_query = """
        SELECT DISTINCT
            metric_id,
            metric_label,
            unit,
            higher_is_better,
            target_threshold
        FROM performance_data.insight_metrics_long
        WHERE metric_id = :metric_id
        LIMIT 1
    """

    with engine.connect() as conn:
        result = conn.execute(text(metric_query), {"metric_id": metric_id})
        metric_info = dict(result.fetchone()._mapping) if result.rowcount > 0 else {}

    return {
        "domain": domain,
        "metric_info": metric_info,
        "period": period,
        "cohort_filter": cohort_filter,
        "rankings": rankings
    }


def get_trust_trends(
    engine: Engine,
    org_code: str,
    metric_ids: Optional[List[str]] = None,
    start_period: Optional[str] = None,
    end_period: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get time series trends for a trust's metrics.

    Args:
        engine: SQLAlchemy engine
        org_code: NHS organisation code
        metric_ids: Specific metrics (defaults to key metrics)
        start_period: Start period (optional)
        end_period: End period (defaults to latest)

    Returns:
        Dictionary with trend data
    """
    if end_period is None:
        end_period = get_latest_period(engine)

    if metric_ids is None:
        metric_ids = [
            'rtt_compliance_18w',
            'cancer_62d_pct_within_target',
            'oversight_average_score'
        ]

    # Build period filter
    period_where = "AND i.period <= :end_period"
    params = {"org_code": org_code, "metric_ids": metric_ids, "end_period": end_period}

    if start_period:
        period_where += " AND i.period >= :start_period"
        params["start_period"] = start_period

    query = f"""
        WITH trust_trends AS (
            SELECT
                i.period,
                i.metric_id,
                i.metric_label,
                i.domain,
                i.value,
                i.unit,
                i.percentile_overall,
                i.target_threshold,
                i.target_met,
                LAG(i.value) OVER (PARTITION BY i.metric_id ORDER BY i.period) as previous_value
            FROM performance_data.insight_metrics_long i
            WHERE i.org_code = :org_code
                AND i.metric_id = ANY(:metric_ids)
                AND i.valid_sample = true
                AND i.is_rollup = false
                {period_where}
        )
        SELECT
            period,
            metric_id,
            metric_label,
            domain,
            value,
            unit,
            percentile_overall,
            target_threshold,
            target_met,
            previous_value,
            CASE
                WHEN previous_value IS NOT NULL THEN value - previous_value
                ELSE NULL
            END as change_from_previous
        FROM trust_trends
        ORDER BY metric_id, period
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        trends = []
        for row in result:
            trends.append(dict(row._mapping))

    # Get trust info
    trust_info = get_trust_info(engine, org_code)

    return {
        "trust_info": trust_info,
        "start_period": start_period,
        "end_period": end_period,
        "trends": trends
    }


def get_cohort_benchmark(
    engine: Engine,
    org_code: str,
    cohort_type: str,
    metric_ids: Optional[List[str]] = None,
    period: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get detailed cohort benchmarking for a trust.

    Args:
        engine: SQLAlchemy engine
        org_code: NHS organisation code
        cohort_type: 'trust_type', 'trust_subtype', or 'region'
        metric_ids: Specific metrics (defaults to all)
        period: Reporting period (defaults to latest)

    Returns:
        Dictionary with cohort benchmark data
    """
    if period is None:
        period = get_latest_period(engine)

    # Get trust info to determine cohort
    trust_info = get_trust_info(engine, org_code)
    if not trust_info:
        return {"error": f"Organisation code {org_code} not found"}

    cohort_value = trust_info.get(cohort_type)
    if not cohort_value:
        return {"error": f"Invalid cohort_type: {cohort_type}"}

    # Build metric filter
    metric_where = ""
    params = {
        "org_code": org_code,
        "period": period,
        "cohort_type": cohort_type,
        "cohort_value": cohort_value
    }

    if metric_ids:
        metric_where = "AND i.metric_id = ANY(:metric_ids)"
        params["metric_ids"] = metric_ids

    query = f"""
        WITH cohort_data AS (
            SELECT
                i.metric_id,
                i.metric_label,
                i.domain,
                i.unit,
                i.higher_is_better,
                i.org_code,
                o.trust_name,
                i.value,
                i.percentile_overall
            FROM performance_data.insight_metrics_long i
            JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
            WHERE i.period = :period
                AND o.{cohort_type} = :cohort_value
                AND i.valid_sample = true
                AND i.is_rollup = false
                {metric_where}
        ),
        trust_metrics AS (
            SELECT
                metric_id,
                metric_label,
                domain,
                unit,
                higher_is_better,
                value,
                percentile_overall
            FROM cohort_data
            WHERE org_code = :org_code
        ),
        cohort_stats AS (
            SELECT
                metric_id,
                COUNT(*) as cohort_size,
                MIN(value) as min_val,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY value) as q1,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY value) as median,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY value) as q3,
                MAX(value) as max_val
            FROM cohort_data
            GROUP BY metric_id
        ),
        cohort_ranks AS (
            SELECT
                metric_id,
                org_code,
                ROW_NUMBER() OVER (
                    PARTITION BY metric_id
                    ORDER BY CASE WHEN higher_is_better THEN value ELSE -value END DESC
                ) as cohort_rank
            FROM cohort_data
        ),
        similar_performers AS (
            SELECT
                cd.metric_id,
                cd.org_code,
                cd.trust_name,
                cd.value,
                cd.percentile_overall
            FROM cohort_data cd
            JOIN trust_metrics tm ON cd.metric_id = tm.metric_id
            WHERE ABS(cd.percentile_overall - tm.percentile_overall) <= 0.05
                AND cd.org_code != :org_code
        )
        SELECT
            tm.metric_id,
            tm.metric_label,
            tm.domain,
            tm.unit,
            tm.higher_is_better,
            tm.value as trust_value,
            tm.percentile_overall,
            cs.cohort_size,
            cs.min_val,
            cs.q1,
            cs.median,
            cs.q3,
            cs.max_val,
            cr.cohort_rank,
            (
                SELECT json_agg(json_build_object(
                    'org_code', org_code,
                    'trust_name', trust_name,
                    'value', value,
                    'percentile', percentile_overall
                ))
                FROM similar_performers sp
                WHERE sp.metric_id = tm.metric_id
            ) as similar_performers
        FROM trust_metrics tm
        LEFT JOIN cohort_stats cs ON tm.metric_id = cs.metric_id
        LEFT JOIN cohort_ranks cr ON tm.metric_id = cr.metric_id AND cr.org_code = :org_code
        ORDER BY tm.domain, tm.metric_id
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        benchmarks = []
        for row in result:
            benchmarks.append(dict(row._mapping))

    return {
        "trust_info": trust_info,
        "cohort_type": cohort_type,
        "cohort_value": cohort_value,
        "period": period,
        "benchmarks": benchmarks
    }


def get_metric_outliers(
    engine: Engine,
    metric_id: str,
    period: Optional[str] = None,
    threshold_percentile: int = 10,
    cohort_filter: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Identify outlier trusts for a specific metric.

    Args:
        engine: SQLAlchemy engine
        metric_id: Metric identifier
        period: Reporting period (defaults to latest)
        threshold_percentile: Percentile threshold for outliers (default 10)
        cohort_filter: Optional filter dict

    Returns:
        Dictionary with outlier data
    """
    if period is None:
        period = get_latest_period(engine)

    # Build cohort filter
    cohort_where = ""
    cohort_params = {}
    if cohort_filter:
        clauses = []
        for key, value in cohort_filter.items():
            param_name = f"cohort_{key}"
            clauses.append(f"o.{key} = :{param_name}")
            cohort_params[param_name] = value
        if clauses:
            cohort_where = "AND " + " AND ".join(clauses)

    threshold_decimal = threshold_percentile / 100.0

    query = f"""
        WITH all_trusts AS (
            SELECT
                o.org_code,
                o.trust_name,
                o.region,
                o.trust_type,
                o.trust_subtype,
                i.value,
                i.unit,
                i.higher_is_better,
                i.percentile_overall,
                ROW_NUMBER() OVER (
                    ORDER BY CASE WHEN i.higher_is_better THEN i.value ELSE -i.value END DESC
                ) as rank,
                COUNT(*) OVER () as total_trusts
            FROM performance_data.insight_metrics_long i
            JOIN performance_data.dim_organisations o ON i.org_code = o.org_code
            WHERE i.metric_id = :metric_id
                AND i.period = :period
                AND i.valid_sample = true
                AND i.is_rollup = false
                {cohort_where}
        ),
        percentile_thresholds AS (
            SELECT
                PERCENTILE_CONT(:threshold_low) WITHIN GROUP (ORDER BY value) as low_threshold,
                PERCENTILE_CONT(:threshold_high) WITHIN GROUP (ORDER BY value) as high_threshold
            FROM all_trusts
        )
        SELECT
            at.*,
            pt.low_threshold,
            pt.high_threshold,
            CASE
                WHEN at.percentile_overall >= :threshold_high THEN 'high'
                WHEN at.percentile_overall <= :threshold_low THEN 'low'
                ELSE 'middle'
            END as outlier_type
        FROM all_trusts at
        CROSS JOIN percentile_thresholds pt
        WHERE at.percentile_overall >= :threshold_high
            OR at.percentile_overall <= :threshold_low
        ORDER BY at.rank
    """

    params = {
        "metric_id": metric_id,
        "period": period,
        "threshold_low": threshold_decimal,
        "threshold_high": 1 - threshold_decimal,
        **cohort_params
    }

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        outliers = []
        for row in result:
            outliers.append(dict(row._mapping))

    # Get metric info
    metric_query = """
        SELECT DISTINCT
            metric_id,
            metric_label,
            domain,
            unit,
            higher_is_better,
            target_threshold
        FROM performance_data.insight_metrics_long
        WHERE metric_id = :metric_id
        LIMIT 1
    """

    with engine.connect() as conn:
        result = conn.execute(text(metric_query), {"metric_id": metric_id})
        metric_info = dict(result.fetchone()._mapping) if result.rowcount > 0 else {}

    return {
        "metric_info": metric_info,
        "period": period,
        "threshold_percentile": threshold_percentile,
        "cohort_filter": cohort_filter,
        "outliers": outliers
    }


def get_cancer_pathway_analysis(
    engine: Engine,
    org_code: str,
    standard: Optional[str] = None,
    include_cancer_types: bool = False,
    include_referral_routes: bool = False,
    period: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get detailed cancer pathway performance analysis.

    Args:
        engine: SQLAlchemy engine
        org_code: NHS organisation code
        standard: '28_day', '31_day', '62_day', or None for all
        include_cancer_types: Include breakdown by cancer type
        include_referral_routes: Include breakdown by referral route
        period: Reporting period (defaults to latest)

    Returns:
        Dictionary with cancer pathway data
    """
    if period is None:
        period = get_latest_period(engine, 'cancer')

    # Get trust info
    trust_info = get_trust_info(engine, org_code)
    if not trust_info:
        return {"error": f"Organisation code {org_code} not found"}

    # Map standard to metric_id
    standard_mapping = {
        '28_day': 'cancer_28d_pct_within_target',
        '31_day': 'cancer_31d_pct_within_target',
        '62_day': 'cancer_62d_pct_within_target'
    }

    if standard:
        metric_ids = [standard_mapping.get(standard)]
        if not metric_ids[0]:
            return {"error": f"Invalid standard: {standard}"}
    else:
        metric_ids = list(standard_mapping.values())

    # Overall performance (ALL ROUTES, no cancer type breakdown)
    overall_query = """
        SELECT
            i.metric_id,
            i.metric_label,
            i.value,
            i.unit,
            i.target_threshold,
            i.target_met,
            i.percentile_overall,
            i.percentile_trust_type,
            i.numerator,
            i.denominator
        FROM performance_data.insight_metrics_long i
        WHERE i.org_code = :org_code
            AND i.period = :period
            AND i.metric_id = ANY(:metric_ids)
            AND i.valid_sample = true
            AND (i.referral_route = 'ALL ROUTES' OR i.referral_route IS NULL)
            AND i.cancer_type IS NULL
        ORDER BY i.metric_id
    """

    with engine.connect() as conn:
        result = conn.execute(text(overall_query), {
            "org_code": org_code,
            "period": period,
            "metric_ids": metric_ids
        })
        overall_performance = []
        for row in result:
            overall_performance.append(dict(row._mapping))

    result_data = {
        "trust_info": trust_info,
        "period": period,
        "overall_performance": overall_performance
    }

    # Cancer type breakdown if requested
    if include_cancer_types:
        cancer_type_query = """
            SELECT
                i.metric_id,
                i.cancer_type,
                i.value,
                i.percentile_overall,
                i.numerator,
                i.denominator
            FROM performance_data.insight_metrics_long i
            WHERE i.org_code = :org_code
                AND i.period = :period
                AND i.metric_id = ANY(:metric_ids)
                AND i.valid_sample = true
                AND i.cancer_type IS NOT NULL
                AND (i.referral_route = 'ALL ROUTES' OR i.referral_route IS NULL)
            ORDER BY i.metric_id, i.denominator DESC
        """

        with engine.connect() as conn:
            result = conn.execute(text(cancer_type_query), {
                "org_code": org_code,
                "period": period,
                "metric_ids": metric_ids
            })
            cancer_type_breakdown = []
            for row in result:
                cancer_type_breakdown.append(dict(row._mapping))

        result_data["cancer_type_breakdown"] = cancer_type_breakdown

    # Referral route breakdown if requested
    if include_referral_routes:
        route_query = """
            SELECT
                i.metric_id,
                i.referral_route,
                i.value,
                i.percentile_overall,
                i.numerator,
                i.denominator
            FROM performance_data.insight_metrics_long i
            WHERE i.org_code = :org_code
                AND i.period = :period
                AND i.metric_id = ANY(:metric_ids)
                AND i.valid_sample = true
                AND i.referral_route IS NOT NULL
                AND i.cancer_type IS NULL
            ORDER BY i.metric_id, i.referral_route
        """

        with engine.connect() as conn:
            result = conn.execute(text(route_query), {
                "org_code": org_code,
                "period": period,
                "metric_ids": metric_ids
            })
            referral_route_breakdown = []
            for row in result:
                referral_route_breakdown.append(dict(row._mapping))

        result_data["referral_route_breakdown"] = referral_route_breakdown

        # Calculate equity gaps (USC vs ALL ROUTES)
        gap_query = """
            WITH all_routes AS (
                SELECT
                    metric_id,
                    value as all_routes_value
                FROM performance_data.insight_metrics_long
                WHERE org_code = :org_code
                    AND period = :period
                    AND metric_id = ANY(:metric_ids)
                    AND referral_route = 'ALL ROUTES'
                    AND cancer_type IS NULL
            ),
            usc_routes AS (
                SELECT
                    metric_id,
                    value as usc_value
                FROM performance_data.insight_metrics_long
                WHERE org_code = :org_code
                    AND period = :period
                    AND metric_id = ANY(:metric_ids)
                    AND referral_route = 'URGENT SUSPECTED CANCER'
                    AND cancer_type IS NULL
            ),
            national_gaps AS (
                SELECT
                    ar.metric_id,
                    AVG(usc.value - ar.value) as national_avg_gap
                FROM performance_data.insight_metrics_long ar
                JOIN performance_data.insight_metrics_long usc
                    ON ar.metric_id = usc.metric_id
                    AND ar.period = usc.period
                    AND ar.org_code = usc.org_code
                WHERE ar.period = :period
                    AND ar.metric_id = ANY(:metric_ids)
                    AND ar.referral_route = 'ALL ROUTES'
                    AND usc.referral_route = 'URGENT SUSPECTED CANCER'
                    AND ar.cancer_type IS NULL
                    AND usc.cancer_type IS NULL
                    AND ar.valid_sample = true
                    AND usc.valid_sample = true
                GROUP BY ar.metric_id
            )
            SELECT
                ar.metric_id,
                usc.usc_value,
                ar.all_routes_value,
                usc.usc_value - ar.all_routes_value as gap,
                ng.national_avg_gap
            FROM all_routes ar
            LEFT JOIN usc_routes usc ON ar.metric_id = usc.metric_id
            LEFT JOIN national_gaps ng ON ar.metric_id = ng.metric_id
        """

        with engine.connect() as conn:
            result = conn.execute(text(gap_query), {
                "org_code": org_code,
                "period": period,
                "metric_ids": metric_ids
            })
            equity_gaps = []
            for row in result:
                equity_gaps.append(dict(row._mapping))

        result_data["equity_gaps"] = equity_gaps

    return result_data
