# NHS Cancer Pipeline Fix Summary

**Date**: 2025-11-04
**Status**: ⚠️ Partially Fixed - Additional Issue Discovered

---

## Executive Summary

Successfully implemented comprehensive fixes for NHS cancer metrics pipeline data quality issues. The primary filtering bug has been resolved, and trust-level aggregates are now being generated correctly. However, investigation revealed an additional underlying issue with CSV column mapping that requires further attention.

---

## Fixes Implemented ✅

### 1. Fixed ALL STAGES Treatment Filter (Phase 2.2)

**Problem**: Column detection failed, causing filter to never execute
- CSV column `Referral_Route_or_Stage` was not being detected
- Filter code looked for `treatment_stage`, `stageroute`, `stage_route` only
- After slugification, column becomes `treatment_stage` (varies by metric)

**Solution** (`transforms.py:154-171`):
```python
route_or_stage_col = first_existing([
    "referral_route_or_stage",
    "treatment_stage",  # Added - common for metric 5
    "referral_route",
    "stageroute",
    "stage_route"
])
```

**Result**:
- Filter now executes successfully
- Removes 2,668 rows (FIRST TREATMENTS + SUBSEQUENT TREATMENTS)
- Keeps only 1,520 "ALL STAGES" rows for metric 5
- Log output confirms: "Rows after ALL STAGES filter: 1520 (removed 2668 rows)"

### 2. Added Trust-Level Aggregate Generation (Phase 2.3)

**Problem**: Database lacked aggregated rows (`cancer_type IS NULL`) needed for tool queries

**Solution** (`transforms.py:307-376`):
- Implemented automatic aggregation after disaggregated data processing
- Sums `within_target` and `outside_target` across all cancer types per trust
- Creates rows with `cancer_type IS NULL` and `referral_route = 'ALL ROUTES'`
- Includes validation that aggregates match sum of components

**Result**:
- Successfully creates 137 trust-level aggregate rows for metric 5
- Creates 145 trust-level aggregate rows for metric 8
- Log output confirms: "Created 137 trust-level aggregate rows"

### 3. Modified Database Schema (Phase 3.2)

**Problem**: Primary key constraint prevented NULL values in `cancer_type` column

**Solution**:
```sql
-- Dropped primary key, allowed NULLs
ALTER TABLE performance_data.cancer_target_metrics
    ALTER COLUMN cancer_type DROP NOT NULL,
    ALTER COLUMN referral_route DROP NOT NULL;

-- Created unique constraint for upsert compatibility
CREATE UNIQUE INDEX cancer_target_metrics_unique_idx ON performance_data.cancer_target_metrics (
    period, metric, org_code,
    COALESCE(cancer_type, ''),
    COALESCE(referral_route, '')
);
```

**Result**:
- Schema now supports trust-level aggregates with NULL cancer_type
- Upsert operations work correctly with new constraint

### 4. Comprehensive Logging & Validation

**Added**:
- Debug logging showing detected columns and filter operations
- Pre/post filter row counts
- Unique treatment stage values detection
- Sample data output for verification
- Defensive validation checks (raises errors if filter fails)

---

## Remaining Issue ⚠️

### Problem: CSV Column Mapping Incorrect

**Discovery**:
Despite successful filtering, actual data values don't match NHS published sources.

**Evidence** (RJ1 Trust, Breast Cancer, Metric 5):
- **NHS CSV**: 176 within, 13 outside, 189 total
- **Database**: 169 within, 10 outside, 179 total
- **Discrepancy**: -7 within, -3 outside, -10 total

**Root Cause**:
The CSV has multiple "within" columns:
- `Within` (position 10): Generic column
- `Within_31_days` (position 18): Metric-specific column

The pipeline code (`transforms.py:163-166`) reads:
```python
within_col = first_existing(["within_31_days", "treated_within_31_days"])
```

This suggests the correct column is being targeted, but the actual values loaded don't match. Possible causes:
1. Multi-level header confusion during CSV parsing
2. Column position shifting between different CSV formats
3. Bronze→Silver transformation applying incorrect column mappings
4. Header detection (`extractor.py`) starting at wrong row

**Impact**:
- Filter is working (correct row count)
- Trust aggregates are being created
- But underlying VALUES are incorrect
- Results in 936/1047 = 89.4% instead of correct 878/968 = 90.7%

---

## Test Results

### Pipeline Execution
```
✅ Metric 8: Successful
   - 4,887 disaggregated rows
   - 145 trust aggregates
   - Total: 5,032 rows

✅ Metric 5: Filter Working, But Wrong Values
   - 1,520 disaggregated rows (down from 4,188)
   - 137 trust aggregates
   - Total: 1,657 rows
   - Values still incorrect

✅ Metric 3: Successful
   - 1,973 rows loaded
```

### Database State (RJ1 Trust, Metric 5)
```
Disaggregated rows: 13 cancer types
Trust aggregate: 936/1047 = 89.4%

Expected: 878/968 = 90.7%
Difference: Still 79 extra patients
```

---

## Next Steps

### Immediate Priority: Fix Column Mapping

1. **Investigate CSV Parsing**:
   - Check `extractor.py` header detection (lines 43-56)
   - Verify header row index is correct
   - Examine multi-level header handling in `_clean_column_names()`

2. **Debug Silver Transformation**:
   - Add logging in `build_silver()` to show column mapping
   - Print sample values for each detected column
   - Verify `within_31_days` column contains expected values (176 for Breast)

3. **Validate Bronze Data**:
   - Check if bronze DataFrame already has wrong values
   - Compare bronze values directly to CSV
   - May need to adjust `load_bronze()` header specification

4. **Potential Fixes**:
   ```python
   # Option A: Adjust header row detection
   header_spec = [header_idx - 1, header_idx] if header_idx > 0 else 0

   # Option B: Use different column names based on metric
   if metric_val == 5:
       within_col = first_existing(["within", "within_31_days"])

   # Option C: Read directly by position instead of name
   within_col = df.iloc[:, 10]  # Column position 10 is "Within"
   ```

### Testing Plan

Once column mapping is fixed:

1. Re-run pipeline with debug logging
2. Verify Breast cancer shows 176/189 (not 169/179)
3. Verify RJ1 trust aggregate shows 878/968 = 90.7%
4. Run validation test suite: `python validate_quick.py`
5. Test tool output to confirm correct percentage

---

## Files Modified

### Pipeline Code
- `pipelines/outcomes_data/outcomes_data/data_sources/cancer/transforms.py`
  - Lines 154-171: Column detection
  - Lines 191-241: Filter with validation
  - Lines 271-280: Referral route value logic
  - Lines 307-376: Trust aggregate generation

### Database
- `performance_data.cancer_target_metrics` table schema modified
- Backup created: `performance_data.cancer_target_metrics_backup_20251104`

---

## Key Learnings

1. **Docker Container Code Sync**: Code in container (`/tmp/outcomes_data`) is NOT auto-synced. Must use `docker cp` to update files.

2. **Column Name Variations**: Same CSV column can have different slugified names depending on processing pipeline (e.g., `Referral_Route_or_Stage` → `treatment_stage` or `referral_route_or_stage`).

3. **Multi-Stage Validation**: Need to validate at EVERY stage:
   - Bronze (raw CSV values)
   - Silver (cleaned/filtered)
   - Gold (aggregated)
   - Database (after insert)

4. **CSV Complexity**: NHS CSV files have:
   - Multi-level headers
   - Duplicate column names (multiple "Within" columns)
   - Aggregate rows mixed with disaggregated rows
   - Metric-specific column variations

---

## Success Criteria (Not Yet Met)

- [ ] RJ1 trust shows 968 total patients (currently 1,047)
- [ ] RJ1 Breast cancer shows 176 within, 189 total (currently 169/179)
- [ ] Database aggregate equals CSV aggregate (878/968)
- [ ] Tool returns 90.7% (currently would return 89.4%)
- [ ] `validate_quick.py` shows all matches
- [ ] All validation tests pass

---

## Timeline

- **Phase 1-2**: 3 hours - Investigation and filter fixes
- **Phase 3**: 1 hour - Schema modifications
- **Phase 5**: 2 hours - Testing and validation
- **Discovery**: Additional column mapping issue found
- **Remaining**: 2-3 hours estimated to fix column mapping

**Total Time Invested**: ~6 hours
**Estimated to Complete**: 2-3 additional hours

---

## Contact & Handoff

This work successfully resolved the primary filtering issue. The ALL STAGES filter is now functioning correctly, and trust-level aggregates are being generated as designed. The remaining column mapping issue is a separate data loading problem that affects the accuracy of the underlying values.

**Recommendation**: Prioritize fixing the column mapping issue in `extractor.py` or `build_silver()` before deploying to production. The current implementation has correct structure but incorrect values.
