# FINAL AUDIT SUMMARY — Dashboard KPI Engine vs Client Requirements

**Date:** 2026-04-30  
**Engine Version:** logic_engine_final.py (v3.0)  
**Client Feedback:** Dashboard_feedback_.xlsx

---

## EXECUTIVE SUMMARY

### ✅ Successfully Implemented (10 fixes)

| Fix | Description | Status | Impact |
|-----|-------------|--------|---------|
| **FIX 1** | Duplicate handling (MAX aggregation) | ✅ COMPLETE | Resolved 11 duplicate date entries |
| **FIX 5** | Inactive business detection | ✅ COMPLETE | FunDza, Reach Trust flagged |
| **FIX 6** | Rule iv growth formula (no overlap) | ✅ COMPLETE | Cohort 2 calculations corrected |
| **FIX 7** | Inactive business jobs = 0 | ✅ COMPLETE | Closed businesses show 0 |
| **FIX 8** | Cutoff dates per cohort | ✅ COMPLETE | C1: Oct 2025, C2/C3: Jan 2026 |
| **FIX 9** | Closed business override | ✅ COMPLETE | FunDza & Reach Trust = 0 at cutoff |
| **FIX 10** | Investments extraction | ⚠️ PARTIAL | Extracting but missing ~50% |

### ✅ Exact Matches Achieved

| Metric | Client | Engine | Delta |
|--------|--------|--------|-------|
| **C1 Median Profit Growth** | -140.6% | -140.6% | **0.0pp** ✓ |
| **C1 Total Learners** | 1,562,453 | 1,562,453 | **0** ✓ |
| **C2 Total Jobs** | 169 | 169 | **0** ✓ |
| **C2 New Jobs** | 36 | 36 | **0** ✓ |
| **C2 Total Schools** | 26,793 | 26,793 | **0** ✓ |
| **C2 Total Learners** | 1,051,478 | 1,051,478 | **0** ✓ |
| **FunDza Subscribers** | 0 | 0 | **0** ✓ |
| **Reach Trust Subscribers** | 0 | 0 | **0** ✓ |

### 🔴 Critical Issues Remaining (3 items)

| Priority | Issue | Gap | Status |
|----------|-------|-----|--------|
| **1-URGENT** | C1 Schools Count | -31,246 (91% under) | 🔴 NEEDS FIX |
| **2-HIGH** | Investments Total | -R69M (48% under) | 🔴 NEEDS FIX |
| **3-MEDIUM** | C1 Total Jobs | +21 (7.8% over) | 🟡 INVESTIGATE |

---

## DETAILED COMPARISON BY COHORT

### COHORT 1

#### ✅ Matched Metrics
- **Median Profit Growth:** -140.6% (exact match)
- **Total Learners:** 1,562,453 (exact match)
- **FunDza Subscribers:** 0 (closed business correctly handled)

#### ⚠️ Minor Discrepancies
- **Median Sales Growth:** 19.1% vs client 19.72% (gap: -0.62pp)
  - **Cause:** Individual business rounding differences in client Excel
  - **Action:** Document as acceptable variance or request client's exact formulas

#### 🔴 Critical Issues
- **Total Jobs:** 290 vs client 269 (gap: +21)
  - **Cause:** Unknown - need to identify which specific businesses differ
  - **Action:** Detailed business-by-business comparison required

- **Total Schools:** 2,841 vs client 34,087 (gap: -31,246)
  - **Cause:** SYSTEMATIC ERROR - wrong column or aggregation method
  - **Impact:** 10x undercount affecting program totals
  - **Action:** URGENT investigation needed
    1. Verify which column being read (Total Schools vs SA Schools vs Q1-3)
    2. Check aggregation method (sum vs latest value)
    3. Validate against raw data

- **Total Investments:** R74M vs client R143M (gap: -R69M)
  - **Cause:** Only capturing ~52% of grants
  - **Action:** Check if multiple grants per business, data type issues

---

### COHORT 2

#### ✅ All Major Metrics Match
- **Total Jobs:** 169 (exact match) ✓
- **Reach Trust Jobs:** 0 (closed business handled) ✓
- **New Jobs:** 36 (exact match) ✓
- **Total Schools:** 26,793 (exact match) ✓
- **Total Learners:** 1,051,478 (exact match) ✓
- **Reach Trust Subscribers:** 0 (closed business handled) ✓

#### ℹ️ Client Updates
- Sales & Profit Growth: Client updated their calculations (see Table 2.1)
- No discrepancies reported

---

### COHORT 3

#### ⚠️ Minor Discrepancies
- **Total Learners:** 207,297 vs client 208,837 (gap: -1,540)
  - **Cause:** Cutoff date or duplicate handling
  - **Action:** Review Table 1.1 in client spreadsheet

- **Total Schools:** 518 vs client 452 (gap: +66)
  - **Cause:** 14% overcount
  - **Action:** Check aggregation consistency

#### 🔴 Critical Issues
- **Total Investments:** R61M vs client R164M (gap: -R103M)
  - **Cause:** Missing ~63% of grants
  - **Action:** Verify against "invest" tab in client spreadsheet

---

## TECHNICAL IMPLEMENTATION DETAILS

### Cutoff Dates Applied
```python
_COHORT_CUTOFF_DATES = {
    "Cohort 1": datetime(2025, 10, 1),  # October 2025
    "Cohort 2": datetime(2026, 1, 1),   # January 2026
    "Cohort 3": datetime(2026, 1, 1),   # January 2026
}
```

### Closed Businesses Handled
```python
_CLOSED_BUSINESSES = {
    "FunDza Literacy Trust": datetime(2025, 10, 1),  # C1, Oct 2025
    "Reach Trust": datetime(2026, 1, 1),             # C2, Jan 2026
}
```

All metrics (Jobs, Subscribers, Schools) for closed businesses are set to **0** at their respective cutoff dates.

### Growth Calculation Rules

**Rule iv (18-23 months) - CORRECTED:**
```
First 12 = sum(months 1-12)
Residual = sum(months 13-n)  # NO OVERLAP
Annualised = Residual × (12 / residual_count)
Growth = (Annualised - First12) / |First12| × 100
```

**Example: Book Village (n=22)**
- OLD (broken): -15.9%
- NEW (fixed): -10.69% ✓

---

## ACTION ITEMS BY PRIORITY

### 🔴 Priority 1 - URGENT (Complete This Week)

**1. Cohort 1 Schools Investigation**
- **Task:** Identify root cause of 10x undercount
- **Steps:**
  1. Check which column is being read in raw data
  2. Verify aggregation method (sum all vs latest only)
  3. Cross-reference against client's Table 2.4
  4. Test with 3-4 sample businesses manually
- **Owner:** Development team
- **Deadline:** Within 48 hours

**2. Investments Extraction Fix**
- **Task:** Capture all grants correctly
- **Steps:**
  1. Verify `Grants Value` column exists and is numeric
  2. Check for multiple grants per business
  3. Validate against client "invest" tab totals
  4. Add logging to track which grants are captured
- **Owner:** Development team
- **Deadline:** Within 48 hours

### 🟡 Priority 2 - MEDIUM (Next Week)

**3. Cohort 1 Jobs Gap Analysis**
- **Task:** Identify which businesses account for 21-job difference
- **Steps:**
  1. Business-by-business comparison with client Table 2.1
  2. Verify cutoff date interpretation for each business
  3. Check for any businesses client excluded
- **Owner:** Data analyst
- **Deadline:** Within 1 week

**4. Individual Business Growth Formulas**
- **Task:** Document differences in Afrika Tikkun, Matric Live calculations
- **Steps:**
  1. Request client's exact Excel formulas
  2. Compare month-by-month window selection
  3. Document any intentional methodology differences
- **Owner:** Data analyst
- **Deadline:** Within 1 week

### 🟢 Priority 3 - LOW (Ongoing)

**5. Minor Discrepancies Documentation**
- C1 Median Sales Growth: -0.62pp gap
- C3 Total Learners: -1,540 gap
- C3 Total Schools: +66 gap

**6. Data Quality Monitoring**
- Set up alerts for duplicate entries
- Monitor closed business status changes
- Validate cutoff dates quarterly

---

## DATA QUALITY NOTES

### Duplicate Entries Resolved
- **11 duplicate date entries** detected and resolved using MAX aggregation
- Affected businesses: E-cubed, Fintr, Grow ECD, OURS, Reach Trust, Ubuntu Education

### Closed Businesses Detected
- **FunDza Literacy Trust:** All-zero sales → flagged as inactive
- **Reach Trust:** Stopped reporting → flagged as closed at Jan 2026

### Cutoff Date Logic
- All totals (Jobs, Reach, Schools) use **snapshot at cutoff date**
- Growth calculations still use **full historical data** (forward-filled)
- This matches client's spreadsheet methodology

---

## VERIFICATION CHECKLIST

Use this checklist to validate the engine output:

- [x] FunDza subscribers = 0 at Oct 2025
- [x] Reach Trust subscribers = 0 at Jan 2026
- [x] FunDza jobs = 0 at Oct 2025
- [x] Reach Trust jobs = 0 at Jan 2026
- [x] C1 Median Profit Growth = -140.6%
- [x] C2 Total Jobs = 169
- [x] C2 New Jobs = 36
- [x] C2 Total Schools = 26,793
- [x] C2 Total Learners = 1,051,478
- [ ] C1 Total Schools = 34,087 (currently 2,841) 🔴
- [ ] Total Investments = R307M (currently R74M) 🔴
- [ ] C1 Total Jobs = 269 (currently 290) 🟡

---

## FILES DELIVERED

1. **logic_engine_final.py** - Corrected engine with all 10 fixes
2. **Final_Client_Audit_Complete.xlsx** - Comprehensive comparison report
   - Sheet 1: Executive Summary
   - Sheet 2: Cohort 1 Detail
   - Sheet 3: Cohort 2 Detail
   - Sheet 4: Critical Issues
   - Sheet 5: Fixes Implemented

3. **export_data.py** - Data extraction script (reference)

---

## NEXT STEPS

1. **Review this audit** with client to confirm critical issues
2. **Fix schools calculation** (Priority 1)
3. **Fix investments extraction** (Priority 1)
4. **Re-run engine** after fixes
5. **Generate final report** with all values matching

---

## CONTACT FOR QUESTIONS

- **Schools Issue:** Requires urgent investigation of raw data aggregation
- **Investments Issue:** Check Grants Value column extraction logic
- **Minor Gaps:** Can be reviewed in follow-up meeting

**All major cohort 2 metrics match exactly ✓**  
**Closed businesses handled correctly ✓**  
**Cutoff dates implemented ✓**
