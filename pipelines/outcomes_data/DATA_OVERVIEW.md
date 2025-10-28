# NHS Performance Data Overview

This document provides a comprehensive guide to NHS England performance data stored in the `performance_data` database schema. It explains **what data exists**, not how it's collected or processed.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Data Sources](#data-sources)
3. [Organizations](#organizations)
4. [Tables & Schemas](#tables--schemas)
5. [Analytical Views](#analytical-views)
6. [Metrics Catalogue](#metrics-catalogue)
7. [Data Relationships](#data-relationships)
8. [Understanding Key Concepts](#understanding-key-concepts)

---

## Executive Summary

### What This Database Contains

NHS England performance data across three major domains:

1. **RTT (Referral to Treatment)** - Elective surgery waiting times
2. **Cancer Waiting Times** - Cancer pathway performance against national standards
3. **NHS Oversight Framework** - Comprehensive trust performance assessment

### Schema Structure

The database contains:
- **Core Tables**: Fact tables containing performance data across RTT, Cancer, and Oversight domains
- **Views**: Real-time aggregations and transformations
- **Materialized Views**: Pre-computed benchmarks with percentiles
- **Public API Views**: PostgREST-exposed endpoints for external access

> **Note**: Sample values and data distributions shown throughout this document represent typical patterns. Actual data values, volumes, and distributions will vary as new data is ingested over time.

---

## Data Sources

### 1. RTT (Referral to Treatment) Waiting Times

**What it measures**: The time patients wait from GP referral to consultant-led hospital treatment for non-emergency (elective) care.

**Why it matters**: RTT is a critical NHS access metric. Long waiting times delay patient treatment and indicate capacity pressures in the NHS.

**NHS Target**: 92% of patients should start treatment within 18 weeks.

**Two Types of Data**:

1. **Incomplete Pathways (Stock)** - The waiting list
   - Snapshot of patients still waiting at month-end
   - Used for: Capacity planning, backlog management
   - Key metrics: Total waiting, number waiting >52 weeks, percentile waiting times

2. **Completed Pathways (Flow)** - Patients treated
   - Patients who started treatment during the month
   - Used for: Performance against 18-week target
   - Key metric: % completed within 18 weeks (compliance)

**Pathway Types**:
- **Part_1A**: Admitted pathways (inpatient/day case treatment)
- **Part_1B**: Non-admitted pathways (outpatient treatment)
- **Part_2**: Incomplete pathways (waiting list)
- **Overall**: Aggregate across all pathway types

**Entity Levels**:
- **Provider**: Trust-level aggregation
- **Parent**: Parent organization level aggregation

**Data Grain**: One row per month × provider × pathway type × entity level

---

### 2. Cancer Waiting Times

**What it measures**: Speed of cancer diagnosis and treatment against three NHS standards.

**Why it matters**: Fast cancer diagnosis and treatment significantly improve patient outcomes and survival rates.

**Three NHS Standards**:

| Standard | Code | Target | What It Measures |
|----------|------|--------|------------------|
| **28-Day Faster Diagnosis (FDS)** | 3 | 75% | Time from referral to diagnosis outcome (cancer confirmed or ruled out) |
| **31-Day First Treatment** | 5 | 96% | Time from decision to treat to first treatment start |
| **62-Day Treatment** | 8 | 85% | Time from urgent referral to first treatment start |

**Cancer Types Covered** (31 cancer sites):
- Specific cancers: Breast, Lung, Colorectal, Urological, Gynaecological, Haematological, Head & Neck, Skin, Upper GI, Lower GI
- Suspected cancers: Tracked separately during diagnostic phase
- Special categories: Acute leukaemia, brain/CNS tumours, sarcoma, testicular

**Referral Routes**:
- **ALL ROUTES**: All referral pathways combined (pre-aggregated in source data)
- **URGENT SUSPECTED CANCER**: Two-week wait referrals (fast-track for suspected cancer)
- **NATIONAL SCREENING PROGRAMME**: Cancers detected via screening (breast, bowel, cervical)
- **Consultant Upgrade**: Routine referrals upgraded to cancer pathway
- **Breast Symptomatic**: Non-suspicious breast symptoms

**Data Grain**: One row per month × provider × standard × cancer type × referral route

---

### 3. NHS Oversight Framework

**What it measures**: Comprehensive trust performance across 6 domains, with segmentation indicating level of support needed.

**Why it matters**: The Oversight Framework assesses overall trust health and determines which trusts need NHS England intervention.

**Segmentation System**:
- **Segment 1** (Best): Minimal support needs
- **Segment 2**: Good performance
- **Segment 3**: Some support needs or financial concerns
- **Segment 4** (Worst): Significant support required

**Six Performance Domains**:
1. **Quality of Care, Safety & Outcomes** - Mortality, safety incidents, effectiveness
2. **Preventing Ill Health & Reducing Inequalities** - Population health, health equity
3. **People** - Workforce: vacancies, turnover, culture
4. **Finance & Use of Resources** - Financial position, cost improvement, deficit
5. **Local Health Systems** - System collaboration, integrated care
6. **Operational Performance** - Access metrics, waiting times, A&E performance

**Two Data Tables**:

1. **Metrics Raw**:
   - Detailed metric-level data
   - Includes national benchmarks: median, lower quartile, upper quartile
   - Tracks multiple distinct metrics across all domains
   - Reporting periods vary: monthly, quarterly, or annual

2. **League Table**:
   - Overall trust scores and segment assignments
   - Composite performance ranking
   - Financial deficit flag
   - Confidence intervals for scores and ranks

**Data Grain**: One row per trust × metric × reporting period

---

## Organizations

### Trust Dimension (`dim_organisations`)

**Coverage**: NHS trusts across England

**Trust Types**:
- **Acute**: Hospital trusts providing emergency and elective care
- **Non-Acute**: Mental health, community, and specialist trusts
- **Ambulance**: Emergency ambulance services

**Regional Distribution**: Trusts are distributed across 7 NHS England regions:
- North West
- Midlands
- North East and Yorkshire
- London
- South East
- East of England
- South West

**Organization Codes**:
- All NHS organizations identified by 3-5 character ODS (Organisation Data Service) codes
- Examples: `RJ1` (Guy's and St Thomas'), `RRK` (University College London Hospitals)
- ODS codes are the universal linking key across all datasets

---

### Extended Organization Data (`ods_org_current`)

**Coverage**: Comprehensive NHS organization directory (includes all NHS entities, not just acute trusts)

**What it contains**:
- Full NHS directory from ODS FHIR API
- Includes trusts, GP practices, commissioning organizations, pharmacies, etc.
- Organization roles, addresses, contact information
- Foundation trust status (special governance model)

**Key Fields**:
- Organization name and code
- Primary role (e.g., NHS TRUST, GP PRACTICE, ICB)
- Active status
- Contact details (phone, website)
- Full address (JSONB)

---

## Tables & Schemas

### Table 1: `rtt_metrics_gold`

**Purpose**: Monthly RTT waiting times performance for NHS providers.

**Data Volume**: Varies by reporting period

**Grain**: One row per **period × entity_level × org_code × rtt_part_type**

**Primary Key**: `(period, entity_level, org_code, rtt_part_type)`

#### Column Schema

| Column | Type | Description | Sample Values |
|--------|------|-------------|---------------|
| **Identifiers** | | | |
| `period` | TEXT | Reporting month | `'2025-08'` |
| `entity_level` | TEXT | Aggregation level | `'provider'`, `'parent'` |
| `org_code` | TEXT | NHS ODS code | `'RJ1'`, `'RRK'` |
| `org_name` | TEXT | Trust name | `'Guy''s and St Thomas'''` |
| `rtt_part_type` | TEXT | Pathway type | `'Overall'`, `'Part_1A'`, `'Part_1B'`, `'Part_2'`, `'Part_2A'` |
| **Completed Pathways (Flow)** | | | |
| `completed_total` | NUMERIC | Total pathways completed | `5432` |
| `completed_within_18` | NUMERIC | Completed ≤18 weeks | `4821` |
| `compliance_18w` | DOUBLE PRECISION | % completed ≤18 weeks | `0.887` (88.7%) |
| `median_weeks_completed` | DOUBLE PRECISION | Median weeks for completed | `9.2` |
| `p95_weeks_completed` | DOUBLE PRECISION | 95th percentile weeks | `24.1` |
| **Incomplete Pathways (Stock)** | | | |
| `incomplete_total` | NUMERIC | Total waiting list (with unknowns) | `12500` |
| `waiting_list_total` | NUMERIC | Known waiting list size | `12411` |
| `unknown_clock_start` | NUMERIC | Patients with unknown referral date | `89` |
| **Waiting Time Thresholds** | | | |
| `over_18` | NUMERIC | Waiting >18 weeks | `2340` |
| `over_26` | NUMERIC | Waiting >26 weeks | `1200` |
| `over_40` | NUMERIC | Waiting >40 weeks | `650` |
| `over_52` | NUMERIC | Waiting >52 weeks | `320` |
| `over_65` | NUMERIC | Waiting >65 weeks | `150` |
| `over_78` | NUMERIC | Waiting >78 weeks | `45` |
| **Waiting Time Percentages** | | | |
| `pct_over_18` | DOUBLE PRECISION | % waiting >18 weeks | `0.187` (18.7%) |
| `pct_over_26` | DOUBLE PRECISION | % waiting >26 weeks | `0.096` |
| `pct_over_40` | DOUBLE PRECISION | % waiting >40 weeks | `0.052` |
| `pct_over_52` | DOUBLE PRECISION | % waiting >52 weeks | `0.026` |
| `pct_over_65` | DOUBLE PRECISION | % waiting >65 weeks | `0.012` |
| `pct_over_78` | DOUBLE PRECISION | % waiting >78 weeks | `0.004` |
| **Waiting Time Quantiles** | | | |
| `median_weeks_waiting` | DOUBLE PRECISION | Median weeks on waiting list | `11.5` |
| `p92_weeks_waiting` | DOUBLE PRECISION | 92nd percentile weeks | `38.7` |

#### Data Patterns

**RTT Part Type Coverage**:

The table contains data for multiple pathway types, with coverage varying by provider:
- Overall
- Part_1A (Admitted)
- Part_1B (Non-Admitted)
- Part_2 (Incomplete)
- Part_2A (Incomplete, decision to admit)

**Note**: Not all providers report all pathway types in every period.

**Key Data Quirk**: `waiting_list_total` ≠ `incomplete_total`

The `waiting_list_total` excludes patients with `unknown_clock_start` (unknown referral dates). This is the **denominator for all percentage calculations** (`pct_over_18`, `pct_over_52`, etc.).

```
waiting_list_total = incomplete_total - unknown_clock_start
```

**Why**: Patients with unknown start dates cannot be accurately classified by waiting time, so they're excluded from percentage metrics.

**Quantile Notes**:
- Quantiles are **NULL for "Overall"** rows (cannot aggregate quantiles from parts)
- Use Part_1A, Part_1B, Part_2 rows for quantile analysis

---

### Table 2: `cancer_target_metrics`

**Purpose**: Cancer waiting times performance against three NHS standards.

**Data Volume**: Varies by reporting period

**Grain**: One row per **period × metric × org_code × cancer_type × referral_route**

**Primary Key**: `(period, metric, org_code, cancer_type, referral_route)`

#### Column Schema

| Column | Type | Description | Sample Values |
|--------|------|-------------|---------------|
| `period` | VARCHAR | Reporting month | `'2025-08'` |
| `metric` | BIGINT | Standard code | `3` (28-day), `5` (31-day), `8` (62-day) |
| `metric_label` | VARCHAR | Standard name | `'28_day_faster_diagnosis'` |
| `org_code` | VARCHAR | NHS ODS code | `'RJ1'` |
| `org_name` | VARCHAR | Trust name | `'Guy''s and St Thomas'''` |
| `cancer_type` | VARCHAR | Cancer site or "Suspected..." | `'Breast'`, `'Suspected lung cancer'` |
| `referral_route` | VARCHAR | Referral pathway | `'ALL ROUTES'`, `'URGENT SUSPECTED CANCER'` |
| `within_target` | NUMERIC | Patients meeting target | `125` |
| `outside_target` | NUMERIC | Patients missing target | `23` |
| `pct_within_target` | DOUBLE PRECISION | % meeting target | `0.845` (84.5%) |

#### Data Patterns

**Metric Coverage**:

The table contains data for three standards (metrics 3, 5, and 8), with varying coverage across providers:
- Different providers report different cancer types
- Metric 8 (62-day) typically has the broadest referral route breakdown
- Not all metrics are reported for all cancer types

**Cancer Types**:

**Note**: The database tracks multiple cancer types. Example categories include:

**Treated Cancers** (confirmed diagnosis):
- Breast, Lung, Gynaecological, Haematological (Lymphoma, Other), Head & Neck
- Lower Gastrointestinal, Upper Gastrointestinal (Hepatobiliary, Oesophagus & Stomach)
- Urological (Prostate, Other), Skin

**Suspected Cancers** (during diagnostic phase):
- Suspected breast, lung, lower GI, upper GI, urological, gynaecological, haematological
- Suspected head & neck, skin, testicular, sarcoma, children's, brain/CNS
- Suspected acute leukaemia, non-specific symptoms, other

**Special Categories**:
- "Exhibited (non-cancer) breast symptoms - cancer not initially suspected"
- "Missing or Invalid" (data quality category)

**Referral Routes**:

The database includes multiple referral route categorizations. Common routes include:
- **ALL ROUTES**: Pre-aggregated total (not derived from other routes)
- **URGENT SUSPECTED CANCER / Urgent Suspected Cancer**: Two-week wait referrals
- **Consultant Upgrade**: Routine referrals upgraded to cancer pathway
- **NATIONAL SCREENING PROGRAMME / Screening**: Screening-detected cancers
- **BREAST SYMPTOMATIC** variants: Breast symptoms pathways

**Note**: Referral route labels may appear in different case formats in the data.

**Important**: "ALL ROUTES" is **source data** (pre-aggregated in NHS publications), not a calculated sum of other routes. Other routes are subsets, not exhaustive breakdowns.

---

### Table 3: `oversight_metrics_raw`

**Purpose**: Detailed NHS Oversight Framework metrics across 6 performance domains.

**Data Volume**: Varies by reporting period

**Grain**: One row per **org_code × metric_id × reporting_date**

**Primary Key**: `(org_code, metric_id, reporting_date)`

#### Column Schema

| Column | Type | Description | Sample Values |
|--------|------|-------------|---------------|
| **Organization** | | | |
| `region` | TEXT | NHS region | `'London'`, `'North West'` |
| `trust_type` | TEXT | Trust classification | `'Acute trust'`, `'Ambulance trust'` |
| `trust_subtype` | TEXT | Trust subtype | `'Acute - Teaching'` |
| `org_code` | TEXT | NHS ODS code | `'RJ1'` |
| `trust_name` | TEXT | Trust name | `'Guy''s and St Thomas'''` |
| **Metric Details** | | | |
| `domain` | TEXT | Performance domain | `'Quality'`, `'Finance'`, `'Access'` |
| `sub_domain` | TEXT | Sub-domain | `'Patient Safety'`, `'Waiting Times'` |
| `metric_id` | TEXT | Metric identifier | `'ED_4hr_performance'` |
| `metric_description` | TEXT | Human-readable name | `'Emergency Department 4-hour standard'` |
| `reporting_date` | TEXT | Reporting period | `'Q1 2025/26'`, `'2024-09'`, `'2023'` |
| `units` | TEXT | Unit of measure | `'Percentage'`, `'Rate per 1000'` |
| **Performance Data** | | | |
| `value` | NUMERIC | Trust's value | `72.5`, `1.03` |
| `median_value` | NUMERIC | National median | `75.0` |
| `lower_quartile` | NUMERIC | 25th percentile | `68.2` |
| `upper_quartile` | NUMERIC | 75th percentile | `82.1` |
| `rank` | NUMERIC | Trust rank (1=best) | `45` |

#### Data Patterns

**Reporting Date Formats**:

The `reporting_date` column contains **mixed formats** reflecting different metric reporting cadences:
- Quarterly: e.g., `"Q1 2025/26"`, `"Q2 2024-25"`
- Monthly: e.g., `"2024-09"`
- Annual: e.g., `"2023"`, `"2024"`
- Date ranges: e.g., `"Jul 24 - Jun 25"`, `"Apr 24 - Mar 25"`
- Year-to-date: e.g., `"Year to date 25/26"`

This reflects that different metrics report at different cadences (monthly, quarterly, annually).

**Example formats shown above represent possible patterns; actual values will vary.**

**Domain Coverage**: Metrics span 6 performance domains with varying numbers of metrics per domain.

**National Benchmarks**: Provides quartile benchmarks (median, lower, upper) for peer comparison.

---

### Table 4: `oversight_league_table_raw`

**Purpose**: Overall trust scores, segments, and rankings from the NHS Oversight Framework.

**Data Volume**: One row per trust per reporting period

**Grain**: One row per **org_code × reporting_date**

**Primary Key**: `(org_code, reporting_date)`

#### Column Schema

| Column | Type | Description | Sample Values |
|--------|------|-------------|---------------|
| **Organization** | | | |
| `region` | TEXT | NHS region | `'London'` |
| `trust_type` | TEXT | Trust classification | `'Acute trust'` |
| `trust_subtype` | TEXT | Trust subtype | `'Acute - Teaching'` |
| `org_code` | TEXT | NHS ODS code | `'RJ1'` |
| `trust_name` | TEXT | Trust name | `'Guy''s and St Thomas'''` |
| **Performance Summary** | | | |
| `reporting_date` | TEXT | Reporting period | `'Q1 2025/26'` |
| `average_score` | NUMERIC | Composite performance score | `2.3` |
| `likely_range_of_average_score` | TEXT | Score confidence interval | `'2.1 - 2.5'` |
| `segment` | NUMERIC | Segmentation tier | `1`, `2`, `3`, `4` |
| `trust_in_financial_deficit` | TEXT | Deficit flag | `'Yes'`, `'No'` |
| `rank` | NUMERIC | National rank | `35` |
| `likely_range_of_rank` | TEXT | Rank confidence interval | `'28 - 42'` |

#### Understanding Segments

| Segment | Meaning | Support Level |
|---------|---------|---------------|
| **1** | Strongest performers | Minimal oversight, share best practices |
| **2** | Good performance | Light-touch support |
| **3** | Some concerns | Targeted support, may include financial issues |
| **4** | Significant concerns | Intensive support, mandated improvement plans |

**Financial Override**: Trusts in financial deficit are automatically capped at Segment 3 maximum, even if quality metrics would place them higher.

---

### Table 5: `dim_organisations`

**Purpose**: Master dimension table for NHS trusts.

**Data Volume**: One row per NHS trust

**Grain**: One row per **org_code**

**Primary Key**: `org_code`

#### Column Schema

| Column | Type | Description | Sample Values |
|--------|------|-------------|---------------|
| `org_code` | TEXT | NHS ODS code (PK) | `'RJ1'`, `'RRK'`, `'R1H'` |
| `trust_name` | TEXT | Organization name | `'Guy''s and St Thomas'' NHS Foundation Trust'` |
| `region` | TEXT | NHS region | `'London'`, `'North West'`, `'South East'` |
| `trust_type` | TEXT | Trust classification | `'Acute trust'`, `'Ambulance trust'`, `'Non-acute hospital trust'` |
| `trust_subtype` | TEXT | Trust subtype | `'Acute - Teaching'`, `'Acute - Non-Teaching'` |

This table serves as the universal organization reference for joining performance data across RTT, Cancer, and Oversight datasets.

---

### Table 6: `ods_org_current`

**Purpose**: Extended NHS organization directory from ODS FHIR API.

**Data Volume**: Comprehensive directory of all NHS organizations

**Grain**: One row per **org_code**

**Primary Key**: `org_code`

#### Column Schema (Selected Key Fields)

| Column | Type | Description | Sample Values |
|--------|------|-------------|---------------|
| `org_code` | TEXT | NHS ODS code | `'RJ1'`, `'Y00032'` (GP practice) |
| `org_name` | TEXT | Organization name | `'Guy''s and St Thomas'''` |
| `primary_role_code` | TEXT | Primary ODS role | `'RO197'` (NHS TRUST), `'RO76'` (GP PRACTICE) |
| `primary_role_display` | TEXT | Role description | `'NHS TRUST'` |
| `is_foundation_trust` | BOOLEAN | Foundation trust status | `true`, `false` |
| `active` | BOOLEAN | Currently active | `true`, `false` |
| `last_change_date` | TIMESTAMP | Last ODS update | `'2024-09-15'` |
| `address_json` | JSONB | Full FHIR address object | `{"line": ["123 High St"], "city": "London", ...}` |
| `roles_json` | JSONB | Array of all roles | `[{"code": "RO197"}, {"code": "RO57"}]` |
| `phone` | TEXT | Contact phone | `'020 7188 7188'` |
| `website` | TEXT | Organization website | `'https://www.guysandstthomas.nhs.uk'` |

**Coverage**: Includes all NHS entities - trusts, GP practices, ICBs, pharmacies, dentists, commissioning organizations, etc. Much broader coverage than `dim_organisations`.

**Foundation Trust Status**: Foundation trusts (role code `RO57`) have special governance and financial autonomy. Identified by `is_foundation_trust = true`.

---

### Table 7: `metric_catalogue`

**Purpose**: Metadata registry defining all metrics in the unified analytics layer.

**Data Volume**: Registry of all defined metrics in the unified analytics layer

**Grain**: One row per **metric_id**

**Primary Key**: `metric_id`

#### Column Schema

| Column | Type | Description | Sample Values |
|--------|------|-------------|---------------|
| `metric_id` | TEXT | Stable metric identifier | `'rtt_pct_within_18'`, `'cancer_62d_pct_within_target'` |
| `metric_label` | TEXT | Human-readable name | `'RTT waiting list: % within 18 weeks (stock)'` |
| `domain` | TEXT | Dataset family | `'rtt'`, `'cancer'`, `'oversight'` |
| `unit` | TEXT | Unit of measure | `'percentage'`, `'weeks'`, `'count'`, `'score'` |
| `higher_is_better` | BOOLEAN | Performance direction | `true`, `false` |
| `target_threshold` | NUMERIC | NHS target (if applicable) | `0.85` (85%), `NULL` |
| `min_denominator` | INTEGER | Sample size threshold | `20`, `50` |
| `disaggregation_dims` | TEXT[] | Disaggregation dimensions | `{referral_route,cancer_type}` |
| `source_table` | TEXT | Source table name | `'performance_data.rtt_trust_snapshot'` |
| `notes` | TEXT | Additional context | `'Excludes unknown clock start...'` |

#### Defined Metrics

**RTT Metrics**:

| metric_id | metric_label | unit | target | direction |
|-----------|--------------|------|--------|-----------|
| `rtt_pct_within_18` | RTT waiting list: % within 18 weeks (stock) | percentage | — | higher better |
| `rtt_pct_over_52` | RTT waiting list: % over 52 weeks (stock) | percentage | — | lower better |
| `rtt_p92_weeks_waiting` | RTT waiting list: 92nd percentile weeks (stock) | weeks | — | lower better |
| `rtt_compliance_18w` | RTT completed pathways: % within 18 weeks (flow) | percentage | — | higher better |
| `rtt_unknown_clock_start_rate` | RTT: % unknown clock start (data quality) | percentage | — | lower better |

**Cancer Metrics**:

| metric_id | metric_label | unit | target | direction |
|-----------|--------------|------|--------|-----------|
| `cancer_28d_pct_within_target` | Cancer 28-day FDS: % within target | percentage | 75% | higher better |
| `cancer_31d_pct_within_target` | Cancer 31-day: % first treatment within 31 days | percentage | 96% | higher better |
| `cancer_62d_pct_within_target` | Cancer 62-day: % treatment within 62 days | percentage | 85% | higher better |
| `cancer_28d_gap_usc_all` | Cancer 28-day: USC minus All Routes (pp) | percentage | — | higher better |
| `cancer_31d_gap_usc_all` | Cancer 31-day: USC minus All Routes (pp) | percentage | — | higher better |
| `cancer_62d_gap_usc_all` | Cancer 62-day: USC minus All Routes (pp) | percentage | — | higher better |

**Gap Metrics**: Measure equity between Urgent Suspected Cancer (USC) and All Routes. Positive gap = USC patients treated faster (expected), but large gaps may indicate delays in other routes.

**Oversight Metrics**:

| metric_id | metric_label | unit | target | direction |
|-----------|--------------|------|--------|-----------|
| `oversight_average_score` | Oversight: average metric score | score | — | higher better |
| `oversight_segment_inverse` | Oversight: segment (higher is better, inverted) | ordinal | — | higher better |

**Segment Inversion**: Raw oversight segments are 1 (best) to 4 (worst). The `segment_inverse` metric inverts this so higher is better, aligning with other metrics for unified benchmarking.

---

## Analytical Views

### View 1: `rtt_trust_snapshot_v`

**Purpose**: Convenience view over `rtt_metrics_gold` that adds a calculated field.

**Type**: Regular view (real-time)

**What it adds**:
```sql
pct_within_18 = 1 - pct_over_18
```

**Why it exists**: The gold table stores `pct_over_18` (% waiting list >18 weeks), but dashboards often want to show "% waiting list ≤18 weeks" as a positive metric. This view calculates it automatically.

**Usage**: Same as `rtt_metrics_gold` but with additional `pct_within_18` column for easier "positive framing" of performance.

---

### View 2: `metric_values_base`

**Purpose**: **Unified long-format view** combining RTT, Cancer, and Oversight metrics into a single queryable table.

**Type**: Regular view (real-time)

**What it provides**:
- All metrics from all three domains in one normalized structure
- Disaggregation dimensions (rtt_part_type, cancer_type, referral_route) as columns
- Organization enrichment (region, trust_type, trust_subtype)
- Metric metadata (units, direction, targets)
- Data quality flags (valid_sample, target_met)

**Key Columns**:

| Column | Description |
|--------|-------------|
| `period` | Reporting period (YYYY-MM or other format) |
| `metric_id` | From metric_catalogue |
| `metric_label` | Human-readable name |
| `domain` | 'rtt', 'cancer', or 'oversight' |
| `org_code`, `org_name` | Organization identifiers |
| `region`, `trust_type`, `trust_subtype` | Organization attributes |
| `value` | Metric value |
| `numerator`, `denominator` | For ratio metrics |
| `referral_route`, `cancer_type`, `rtt_part_type`, `entity_level` | Disaggregation dimensions |
| `valid_sample` | Boolean: Does denominator meet `min_denominator`? |
| `target_met` | Boolean: Does value meet `target_threshold`? |
| `is_rollup`, `rollup_method` | Flags for aggregated rows |
| `disagg_key` | Canonical key for disaggregation signature |

**Disaggregation Key**: A concatenated string representing the "grain" of each row:
```
disagg_key = concat_ws(' | ', referral_route, cancer_type, rtt_part_type, entity_level)
```
Example: `"URGENT SUSPECTED CANCER | Breast | ~ | provider"` (`~` = null dimension)

**Why it exists**: Single source for all metrics, enabling cross-domain dashboards and APIs without complex UNION queries.

---

### View 3: `insight_metrics_latest`

**Purpose**: Latest period snapshot per metric × disaggregation.

**Type**: Regular view (real-time)

**What it provides**: Filters `insight_metrics_long` to show only the most recent period for each metric/disaggregation combination.

**Logic**:
```sql
SELECT * FROM insight_metrics_long
WHERE (metric_id, disagg_key, period) IN (
  SELECT metric_id, disagg_key, MAX(period)
  FROM insight_metrics_long
  GROUP BY metric_id, disagg_key
)
```

**Why it exists**: Dashboard homepages often show "current performance" - this view eliminates date filtering in application code.

**Usage**: Query for latest performance without specifying periods:
```sql
SELECT org_name, value, percentile_overall
FROM performance_data.insight_metrics_latest
WHERE metric_id = 'rtt_compliance_18w';
```

---

### Materialized View: `insight_metrics_long`

**Purpose**: **Pre-computed benchmarks with percentile rankings** for cohort comparison.

**Type**: Materialized view (requires refresh)

**What it adds to `metric_values_base`**:

| Column | Description |
|--------|-------------|
| `percentile_overall` | Percentile rank across all providers (0-1) |
| `percentile_trust_type` | Percentile within trust type cohort (0-1) |
| `percentile_trust_subtype` | Percentile within trust subtype cohort (0-1) |
| `normalised_score_0_100_overall` | Direction-aware score where higher is always better (0-100) |
| `last_refreshed_at` | Timestamp of last refresh |

**Percentile Calculation**:
- Uses `PERCENT_RANK()` window function
- Partitioned by `metric_id`, `period`, `disagg_key` (for overall)
- Ordered by `value` with direction handling via `higher_is_better`
- Example: `percentile_overall = 0.85` means this organization performed better than 85% of peers

**Normalized Score**:
```sql
normalised_score_0_100_overall = 100 * (
  CASE WHEN higher_is_better
    THEN percentile_overall
    ELSE 1 - percentile_overall
  END
)
```
- All scores oriented so **higher is always better**
- Simplifies dashboard logic and enables cross-metric comparisons
- Example: 85.0 = top 15% performance

**Sample Size Filtering**: Excludes rows where `valid_sample = false` (denominator < `min_denominator`) to avoid noise from low-sample outliers.

**Indexes**:
- `idx_insight_metrics_long_org` on `org_code`
- `idx_insight_metrics_long_metric_period` on `(metric_id, period)`
- `idx_insight_metrics_long_cohorts` on `(trust_type, trust_subtype, region)`

**Refresh Strategy**: Manual refresh required after data updates:
```sql
REFRESH MATERIALIZED VIEW performance_data.insight_metrics_long;
```

**Why it exists**: Percentile calculations are computationally expensive. Pre-computing them enables fast dashboard queries like "Show me trusts below 25th percentile for cancer 62-day standard."

---

### Public API Views (3)

These views expose `performance_data` schema to PostgREST (Supabase's REST API layer):

1. **public.performance_insight_metrics_latest** → `performance_data.insight_metrics_latest`
2. **public.performance_insight_metrics_long** → `performance_data.insight_metrics_long`
3. **public.performance_dim_organisations** → `performance_data.dim_organisations`

**Why they exist**:
- PostgREST only exposes tables/views in `public` schema by default
- Keeps analytics schema isolated from API layer
- Allows independent access control (`anon` and `authenticated` roles have SELECT)

---

## Data Relationships

### Primary Key → Foreign Key Relationships

```
dim_organisations (org_code)
    ↓ (1:N)
    ├── rtt_metrics_gold (org_code)
    ├── cancer_target_metrics (org_code)
    ├── oversight_metrics_raw (org_code)
    └── oversight_league_table_raw (org_code)

metric_catalogue (metric_id)
    ↓ (1:N)
    └── metric_values_base (metric_id)  [via LEFT JOIN]
```

### Join Patterns

**1. Organization Enrichment**:
```sql
-- Add trust_name, region, trust_type to performance data
SELECT r.*, o.trust_name, o.region, o.trust_type
FROM performance_data.rtt_metrics_gold r
LEFT JOIN performance_data.dim_organisations o ON r.org_code = o.org_code;
```

**2. Cross-Domain Analysis**:
```sql
-- Compare RTT and Cancer performance for same trust
SELECT
  rtt.org_name,
  rtt.compliance_18w AS rtt_compliance,
  cancer.pct_within_target AS cancer_62d_compliance
FROM performance_data.rtt_metrics_gold rtt
INNER JOIN performance_data.cancer_target_metrics cancer
  ON rtt.org_code = cancer.org_code
  AND rtt.period = cancer.period
WHERE rtt.rtt_part_type = 'Overall'
  AND cancer.metric = 8
  AND cancer.referral_route = 'ALL ROUTES';
```

**3. Unified Metrics**:
```sql
-- Query all metrics for a trust using unified view
SELECT metric_id, metric_label, value, target_met
FROM performance_data.metric_values_base
WHERE org_code = 'RJ1' AND period = '2025-08'
ORDER BY domain, metric_id;
```

---

## Understanding Key Concepts

### 1. Stock vs Flow Metrics

**Stock Metrics** - Snapshot at a point in time:
- "How many people are waiting RIGHT NOW?"
- RTT incomplete pathways: Total waiting, over_52, median_weeks_waiting
- Like a photograph of the waiting list

**Flow Metrics** - Rate over a period:
- "How many people started treatment THIS MONTH?"
- RTT completed pathways: compliance_18w
- Cancer standards: All three (28-day, 31-day, 62-day)
- Like a video showing throughput

**Why it matters**: Different metrics answer different questions:
- **Capacity planning**: Use stock (how big is the backlog?)
- **Performance evaluation**: Use flow (are we meeting targets?)

---

### 2. Disaggregation Dimensions

Different metrics can be broken down by different dimensions:

| Metric Domain | Disaggregation Dimensions |
|---------------|---------------------------|
| **RTT** | `rtt_part_type` (Overall, Part_1A, Part_1B, Part_2), `entity_level` (provider, parent) |
| **Cancer** | `cancer_type` (Breast, Lung, etc.), `referral_route` (USC, ALL ROUTES, Screening, etc.) |
| **Oversight** | None (trust-level only) |

**Disagg Key**: The `disagg_key` column in `metric_values_base` creates a canonical representation:
```
"referral_route | cancer_type | rtt_part_type | entity_level"
```

This ensures percentile rankings compare "apples to apples" - e.g., Breast cancer USC performance vs other Breast cancer USC, not vs Lung cancer.

---

### 3. Valid Sample Filtering

The `valid_sample` flag protects against unstable estimates from small sample sizes:

```sql
valid_sample = (denominator >= min_denominator)
```

**Why it matters**: A trust with 5 cancer patients hitting 80% compliance is statistically noisier than a trust with 500 patients. The `insight_metrics_long` view excludes `valid_sample = false` rows from percentile rankings.

**Thresholds** (from `metric_catalogue`):
- Most metrics: `min_denominator = 20`
- Can be customized per metric

---

### 4. Target Evaluation

The `target_met` boolean evaluates performance against NHS standards:

```sql
target_met = (
  CASE WHEN higher_is_better
    THEN value >= target_threshold
    ELSE value <= target_threshold
  END
)
```

**Examples**:
- Cancer 62-day: `target_threshold = 0.85`, `higher_is_better = true` → `target_met = (value >= 0.85)`
- RTT pct_over_52: `target_threshold = 0.06`, `higher_is_better = false` → `target_met = (value <= 0.06)`

**Usage**: Quick filtering for trusts meeting/missing targets:
```sql
SELECT org_name, value
FROM performance_data.metric_values_base
WHERE metric_id = 'cancer_62d_pct_within_target'
  AND target_met = false  -- Trusts missing 85% target
ORDER BY value ASC;
```

---

### 5. Roll-up Rows

The `is_rollup` and `rollup_method` columns identify aggregated data:

| is_rollup | rollup_method | Meaning |
|-----------|---------------|---------|
| `false` | `'source'` | Raw data from tables |
| `true` | `'weighted'` | Weighted aggregation from finer grains |
| `true` | `'derived'` | Calculated from other metrics |
| `true` | `'derived_gap'` | Gap metrics (USC - ALL ROUTES) |

**Why flag them**: Dashboards showing detailed breakdowns may want to exclude roll-ups to avoid double-counting.

---

### 6. Financial Year Period Mapping (RTT & Cancer)

NHS financial year runs April 1 - March 31. Period strings like "January 2024-25" must be mapped to calendar months:

**Rule**:
- Jan/Feb/Mar: Use END year of financial year
- Apr-Dec: Use START year of financial year

**Examples**:
- "January 2024-25" (FY 2024-25) → `2025-01` (calendar month)
- "May 2024-25" (FY 2024-25) → `2024-05`

**Why it matters**: When joining RTT/Cancer data to other datasets, ensure period alignment.

---

### 7. ALL ROUTES is Source Data (Cancer)

**Critical Understanding**: "ALL ROUTES" rows in `cancer_target_metrics` are **pre-aggregated in NHS publications**, NOT derived by summing other referral routes.

**Why**: Other routes (USC, Screening, Consultant Upgrade) are subsets, not exhaustive breakdowns. You cannot reconstruct "ALL ROUTES" by adding them up.

**Implication**: Use "ALL ROUTES" for overall trust performance. Use specific routes (e.g., "URGENT SUSPECTED CANCER") for pathway-specific analysis.

---

### 8. Oversight Date Format Variability

The `reporting_date` column in `oversight_metrics_raw` contains mixed formats:
- Quarterly: `"Q1 2025/26"`, `"Q2 2024-25"`
- Monthly: `"2024-09"`
- Annual: `"2023"`, `"2024"`
- Date ranges: `"Jul 24 - Jun 25"`, `"Apr 24 - Mar 25"`
- Year-to-date: `"Year to date 25/26"`

**Why**: Different metrics report at different cadences (mortality = annual, ED performance = monthly, etc.).

**Implication**: Requires flexible date parsing for time-series analysis. Cannot assume consistent YYYY-MM format.

---

## Summary

This database provides comprehensive NHS performance data across three major domains:

1. **RTT** - Waiting times for elective care
2. **Cancer** - Treatment speed against three standards
3. **Oversight** - Trust-level performance assessment

**Coverage**: NHS trusts across 7 England regions, with an extended directory covering the full NHS organizational landscape.

**Analytical Capabilities**:
- Unified metrics view (`metric_values_base`) for cross-domain analysis
- Pre-computed percentile benchmarks (`insight_metrics_long`) for cohort comparison
- Organization dimension for regional/type-based filtering
- Metric catalogue for semantic metadata

**Key Design Principles**:
- Long-format normalization for flexible querying
- Direction-aware scoring (higher always better)
- Valid sample filtering for statistical rigor
- Disaggregation support for granular analysis
- API-ready via PostgREST-compatible public views

This data enables trust-level dashboards, peer benchmarking, longitudinal trend analysis, cohort comparisons, equity analysis, and target monitoring for the NHS.
