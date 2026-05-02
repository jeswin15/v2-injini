"""
data_fetcher.py  —  Injini MEL Dashboard  (Phase 2)
====================================================
Fetches all monthly reporting records from the four Airtable cohort bases.

Key hardening changes vs V1
-----------------------------
* Field lookup is case-insensitive and strips leading/trailing whitespace from
  Airtable field names (Airtable sometimes adds trailing spaces).
* Linked-record fields (arrays) are unwrapped to their first element before use.
* Every record is wrapped in a per-record try/except so one bad row never
  aborts the entire fetch.
* Numeric coercion happens once, centrally, after the DataFrame is built —
  no silent zeros during per-field extraction.
* Base IDs and table name are defined at the top for easy maintenance.
"""

import os
import pandas as pd
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Credentials ────────────────────────────────────────────────────────────────
_PAT = os.getenv("AIRTABLE_PAT")
# Both tables contain monthly reporting data.
# "Monthly reporting" = current cohort period (7-8 months)
# "Post program reporting" = historical months (makes up the full 31 months)
# We fetch from both and combine into one DataFrame.
_TABLES = ["Monthly reporting", "Post program reporting"]

BASE_IDS = {
    "Cohort 1": "app5MKMARnZAInXVJ",
    "Cohort 2": "app3KJMspt7z8qy9M",
    "Cohort 3": "appBhlIJDu8JvaWxB",
    "Cohort 4": "appzHpcS4aenhjZ8V",
}

# ── Numeric columns (coerced centrally after DataFrame construction) ────────────
NUMERIC_COLS = [
    "Monthly Sales (R)", "Monthly Net Profit",
    "Total Jobs", "Female Jobs", "Youth Jobs",
    "Educ Jobs Total", "Educ Jobs Female",
    "Total Subscribers Students", "Total Subscribers Teachers",
    "New Subscribers Students", "New Subscribers Teachers",
    "Community Learners", "Community Educators",
    "Active Students", "Active Teachers",
    "Female Students", "Female Teachers",
    "Rural Students", "Rural Teachers",
    "Disability Students", "Disability Teachers",
    "Total Schools", "SA Schools", "Q1-3 Schools",
    "Grants Value",
]


# ── Helper: unwrap linked-record arrays ────────────────────────────────────────
def _unwrap(value):
    """Return the first element if value is a list, else value as-is."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


# ── Helper: build a case-insensitive, stripped field lookup ───────────────────
def _build_lookup(fields: dict) -> dict:
    """Return {stripped_lower_key: original_value} for all Airtable fields."""
    return {k.strip().lower(): v for k, v in fields.items()}


def _get(lookup: dict, candidates: list):
    """
    Try each candidate field name (case-insensitive, stripped) in order.
    Returns the first match's value, or None.
    """
    for name in candidates:
        val = lookup.get(name.strip().lower())
        if val is not None:
            return _unwrap(val)
    return None


# ── Main fetch ─────────────────────────────────────────────────────────────────
def fetch_dashboard_data() -> pd.DataFrame:
    """
    Pull all Monthly Reporting records from every cohort base and return a
    single flat DataFrame.  One row = one reporting month for one business.
    """
    api = Api(_PAT)
    all_rows: list[dict] = []

    for cohort, base_id in BASE_IDS.items():
        print(f"Fetching {cohort}...")
        records = []
        for table_name in _TABLES:
            try:
                table_records = api.table(base_id, table_name).all()
                print(f"  -> {len(table_records)} records from '{table_name}'")
                records.extend(table_records)
            except Exception as exc:
                # Table may not exist in all bases (e.g. Post program reporting
                # may not exist in Cohort 4 yet) — skip gracefully
                print(f"  WARNING: Could not fetch '{table_name}' in {cohort}: {exc}")
                continue

        print(f"  -> {len(records)} total records for {cohort}")
        skipped = 0

        for record in records:
            try:
                lk = _build_lookup(record.get("fields", {}))

                # ── Business identity ────────────────────────────────────────
                business_name = _get(lk, [
                    "Business name", "Company name", "Business Name",
                ])
                if not business_name:
                    skipped += 1
                    continue
                if isinstance(business_name, list):
                    business_name = business_name[0]
                business_name = str(business_name).strip()
                if not business_name or business_name.lower() in ("unknown", "n/a", "-"):
                    skipped += 1
                    continue

                reporting_month = _get(lk, [
                    "Reporting month", "Reporting Month",
                    "reporting month", "Reporting  month",
                    "Reporting period", "Reporting Period",
                ]) or "Unknown"
                
                # If Airtable returns a date object directly, convert to string
                if not isinstance(reporting_month, str):
                    reporting_month = str(reporting_month)

                # ── Business financials ──────────────────────────────────────
                # C1: 'Monthly Sales' | C2/C3: 'Monthly sales'
                sales = _get(lk, [
                    "Monthly Sales", "Monthly sales", "# Monthly sales",
                ])
                # C1: 'Monthly net profit' | C2/C3: 'Monthly Net Profit'
                net_profit = _get(lk, [
                    "Monthly net profit", "Monthly Net Profit",
                ])

                # ── Jobs ─────────────────────────────────────────────────────
                # C1: 'Operational jobs - Total' | C2/C3: 'Total operational jobs ' (trailing space stripped)
                total_jobs = _get(lk, [
                    "Operational jobs - Total",
                    "Total operational jobs",      # strip() normalises trailing space
                    "Total Operational Jobs",
                    "Operational Jobs - Total",
                ])
                # C1: 'Operational jobs - female' | C2/C3: 'Female operational jobs'
                female_jobs = _get(lk, [
                    "Operational jobs - female",
                    "Female operational jobs",
                    "Female Operational Jobs",
                    "Operational Jobs - Female",
                ])
                # All cohorts: 'Youth operational jobs' | C1/C2 historical: 'operational jobs - youth'
                youth_jobs = _get(lk, [
                    "Youth operational jobs",
                    "Youth Operational Jobs",
                    "Operational jobs - youth",
                    "operational jobs - youth",
                ])
                # C1: 'Educational resourcing jobs -Total' | C2/C3: 'Total Educational resourcing jobs '
                educ_jobs_total = _get(lk, [
                    "Educational resourcing jobs -Total",
                    "Total Educational resourcing jobs",
                    "Total Educational Resourcing Jobs",
                ]) or 0
                # C1: 'Educational resourcing jobs - Female' | C2/C3: 'Female educational resourcing Jobs '
                educ_jobs_female = _get(lk, [
                    "Educational resourcing jobs - Female",
                    "Female educational resourcing Jobs",
                    "Female Educational Resourcing Jobs",
                ]) or 0

                # ── Reach: Subscribers ───────────────────────────────────────
                # C1: 'Total Subscribers -Students' | C2/C3: 'Total Subscribers - Students'
                total_sub_students = _get(lk, [
                    "Total Subscribers -Students",
                    "Total Subscribers - Students",
                    "Total subscribers - Students",
                    "Monthly Active Subscribers",
                    "Monthly active users- Students",
                ]) or 0
                # C1: 'Total Subscribers - Teachers' | C2/C3: 'Total subscribers - Teachers ' (trailing space stripped)
                total_sub_teachers = _get(lk, [
                    "Total Subscribers - Teachers",
                    "Total subscribers - Teachers",   # strip() normalises trailing space
                    "Total Educators",
                    "Total Teachers",
                    "Monthly active users -Teachers",
                    "Monthly Active subscribers - Teachers",
                ]) or 0
                # C1: 'Net new monthly subscribers  - students' (double space) | C2/C3: 'New Monthly Subscribers - Students'
                new_sub_students = _get(lk, [
                    "Net new monthly subscribers  - students",  # C1 — double space (strip handles)
                    "Net new monthly subscribers - students",
                    "New Monthly Subscribers - Students",
                    "New monthly subscribers- student",
                ]) or 0
                # C1: 'Net new monthly subscribers  - Teachers' (double space) | C2/C3: 'Net new monthly subscribers - Teachers ' (trailing space)
                new_sub_teachers = _get(lk, [
                    "Net new monthly subscribers  - Teachers",  # C1 — double space
                    "Net new monthly subscribers - Teachers",   # C2/C3 — strip handles trailing space
                    "New Monthly Subscribers - Teachers",
                    "New monthly subscribers - teachers",
                ]) or 0

                # ── Reach: Active users ──────────────────────────────────────
                # C1: 'Active users Students - Broad Definition' | C2/C3: 'Monthly Active users - Students'
                active_students = _get(lk, [
                    "Active users Students - Broad Definition",
                    "Monthly Active users - Students",
                ]) or 0
                active_teachers = _get(lk, [
                    "Active users teachers - Broad Definition",
                    "Monthly Active users - Teachers",
                ]) or 0

                # ── Reach: Community (stored but NOT shown on charts) ─────────
                community_learners  = 0   # field removed from charts (Round 2 feedback)
                community_educators = 0

                # ── Reach: Demographics ──────────────────────────────────────
                # C1: 'Subscribers - Female students' | C2/C3: 'Subscribers - Female Students'
                female_students = _get(lk, [
                    "Subscribers - Female students",
                    "Subscribers - Female Students",
                    "Female students",
                ]) or 0
                # C1: 'Subscribers - Female teachers' | C2/C3: 'Subscribers - Female Teachers ' (trailing space stripped)
                female_teachers = _get(lk, [
                    "Subscribers - Female teachers",
                    "Subscribers - Female Teachers",  # strip() normalises trailing space
                ]) or 0
                # C1: 'Subscription - Rural Students' | C2/C3: 'Subscription - Rural Students ' (trailing space stripped)
                rural_students = _get(lk, [
                    "Subscription - Rural Students",  # strip() normalises trailing space variant
                    "Rural Students",
                ]) or 0
                # C1: 'Subscription - Rural Teachers' | C2/C3: 'Subscription - Rural teachers ' (lowercase t, trailing space)
                rural_teachers = _get(lk, [
                    "Subscription - Rural Teachers",
                    "Subscription - Rural teachers",  # strip() normalises trailing space
                ]) or 0
                # C1: NOT IN SCHEMA (returns 0) | C2/C3: 'Subscription - Students with disabilities'
                disability_students = _get(lk, [
                    "Subscription - Students with disabilities",
                    "Subscription - Students with Disabilities",
                    "Students with disabilities",
                    "Students with Disabilities",
                    "Users identify as having a disability - student",
                    "identify as having a disability - student",
                ]) or 0
                # C2: 'Subscribers - Teachers with disabilities ' (trailing space stripped)
                disability_teachers = _get(lk, [
                    "Subscribers - Teachers with disabilities",
                    "Subscribers - Teachers with Disabilities",
                ]) or 0

                # ── Reach: Schools ───────────────────────────────────────────
                # C1/C2: 'Number Quintile 1 - 3 schools ' (trailing space!)
                # C1: 'Subscription- Q1-3 Schools Students' | C2/C3: 'Subscription - Q1-3 schools'
                q13_schools = _get(lk, [
                    "Number Quintile 1 - 3 schools ",
                    "Subscription- Q1-3 Schools Students",  # C1
                    "Subscription - Q1-3 schools",          # C2/C3
                    "Subscription - Q1-3 Schools",
                ]) or 0
                # C1: 'Number of South African schools'
                # C2: 'Number of South African schools solution is being used/tested in'
                # C2/C3: 'Subscription - South African schools'
                sa_schools = _get(lk, [
                    "Number of South African schools",
                    "Number of South African schools solution is being used/tested in",
                    "Subscription - South African schools",
                    "Subscription - South African Schools",
                    "Subscription - SA Schools",
                ]) or 0
                # C1/C2: 'Number schools/learning institutions EdTech solution is being tested in'
                total_schools = _get(lk, [
                    "Number schools/learning institutions EdTech solution is being tested in",
                    "Total number of schools solution being tested in",
                    "Total subscribers (Schools/learning institutions)",
                ]) or ((q13_schools or 0) + (sa_schools or 0))

                # ── Investments ──────────────────────────────────────────────
                # C1: 'Rand value of this new grant/ investment secured. '
                # C2/C3: 'Rand value of grant/investment'
                grants_value = _get(lk, [
                    "Rand value of grant/investment",
                    "Rand value of this new grant/ investment secured.", # C1
                    "New grants and investments",
                ]) or 0
                # C1: 'grant/ investment details' | C2/C3: 'If yes, please specify...'
                grant_funder = _get(lk, [
                    "If yes, please specify from whom this grant/ investment was made.",
                    "grant/ investment details", # C1
                ]) or ""
                income_statement = _get(lk, [
                    "Income statement  ",   # C1 — trailing double space
                    "Income Statement ",    # C2/C3
                    "Income Statement",
                    "Income statement",
                ]) or ""

                all_rows.append({
                    "Cohort":                       cohort,
                    "Business Name":                business_name,
                    "Reporting Month":              reporting_month,
                    # Financials
                    "Monthly Sales (R)":            sales,
                    "Monthly Net Profit":           net_profit,
                    # Jobs
                    "Total Jobs":                   total_jobs,
                    "Female Jobs":                  female_jobs,
                    "Youth Jobs":                   youth_jobs,
                    "Educ Jobs Total":              educ_jobs_total,
                    "Educ Jobs Female":             educ_jobs_female,
                    # Subscribers
                    "Total Subscribers Students":   total_sub_students,
                    "Total Subscribers Teachers":   total_sub_teachers,
                    "New Subscribers Students":     new_sub_students,
                    "New Subscribers Teachers":     new_sub_teachers,
                    # Community (data only — removed from charts per feedback)
                    "Community Learners":           community_learners,
                    "Community Educators":          community_educators,
                    # Active
                    "Active Students":              active_students,
                    "Active Teachers":              active_teachers,
                    # Demographics
                    "Female Students":              female_students,
                    "Female Teachers":              female_teachers,
                    "Rural Students":               rural_students,
                    "Rural Teachers":               rural_teachers,
                    "Disability Students":          disability_students,
                    "Disability Teachers":          disability_teachers,
                    # Schools
                    "Total Schools":                total_schools,
                    "SA Schools":                   sa_schools,
                    "Q1-3 Schools":                 q13_schools,
                    # Investments
                    "Grants Value":                 grants_value,
                    "Grant Funder":                 grant_funder,
                    "Income Statement":             income_statement,
                    "Created Time":                 record.get("createdTime", ""),
                })

            except Exception as row_exc:
                skipped += 1
                print(f"  WARNING: Skipped record in {cohort}: {row_exc}")

        if skipped:
            print(f"  INFO: {skipped} record(s) skipped in {cohort}")

    if not all_rows:
        print("WARNING: No data was fetched from Airtable. Returning empty DataFrame.")
        return pd.DataFrame(columns=["Cohort", "Business Name", "Reporting Month"] + NUMERIC_COLS)

    df = pd.DataFrame(all_rows)

    # ── Central numeric coercion ───────────────────────────────────────────────
    for col in NUMERIC_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"\nTotal rows fetched: {len(df)}")
    return df


# ── Smoke test when run directly ───────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing Airtable connection...")
    df = fetch_dashboard_data()
    print(f"\nShape: {df.shape}")
    print(f"Cohorts: {df['Cohort'].value_counts().to_dict()}")
    print(f"Date NaT rate (before parse): will be checked in logic_engine")
    print(df.head(3).to_string())
