import re
import warnings
import pandas as pd
from datetime import datetime
from statistics import median

# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

_NUMERIC_COLS = [
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

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_FMTS = [
    "%B %Y", "%b %Y", "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
    "%m/%Y", "%m-%Y", "%Y/%m", "%d/%m/%Y",
]

# ─────────────────────────────────────────────────────────────────────────────
#  Business Name Normalisation
# ─────────────────────────────────────────────────────────────────────────────

_BUSINESS_NAME_MAP = {
    "digify":                 "Digify Africa",
    "digify africa":          "Digify Africa",
    "fundza":                 "FunDza Literacy Trust",
    "fundza literacy trust":  "FunDza Literacy Trust",
    "ubuntu":                 "Ubuntu Education",
    "ubuntu education":       "Ubuntu Education",
    "huddle":                 "Huddle Education",
    "huddle education":       "Huddle Education",
    "hudlle":                 "Huddle Education",
    "hudlle education":       "Huddle Education",
}


def _normalize_name(name: str) -> str:
    if not name:
        return name
    cleaned = str(name).strip().lower()
    return _BUSINESS_NAME_MAP.get(cleaned, str(name).strip())


# ─────────────────────────────────────────────────────────────────────────────
#  Date Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_reporting_month(val) -> pd.Timestamp:
    if isinstance(val, list):
        val = val[0] if val else None
    if val is None:
        return pd.NaT
    if not isinstance(val, str):
        try:
            val = str(val)
        except Exception:
            return pd.NaT
    val = val.strip()
    if not val or val.lower() in ("unknown", "n/a", "-", "none"):
        return pd.NaT
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(val, fmt).replace(day=1)
        except ValueError:
            continue
    m = re.search(r"\b([A-Za-z]+)\b\s+(\d{4})\b", val)
    if m:
        word, year = m.group(1).lower(), m.group(2)
        if word in _MONTH_ABBR:
            return datetime(int(year), _MONTH_ABBR[word], 1)
        for fmt in ("%B", "%b"):
            try:
                dt = datetime.strptime(m.group(1), fmt)
                return datetime(int(year), dt.month, 1)
            except ValueError:
                continue
    m2 = re.match(r"^([A-Za-z]{3})-(\d{2})$", val)
    if m2:
        mon = m2.group(1).lower()
        yr  = int(m2.group(2)) + 2000
        if mon in _MONTH_ABBR:
            return datetime(yr, _MONTH_ABBR[mon], 1)
    return pd.NaT


# ─────────────────────────────────────────────────────────────────────────────
#  FIX 1 – Duplicate-date deduplication (MAX resolution)
# ─────────────────────────────────────────────────────────────────────────────

def _dedup_business_records(
    df: pd.DataFrame,
    duplicate_warnings: list,
) -> pd.DataFrame:
    """
    For each (Business Name, Date) pair with more than one row, take MAX of all
    numeric columns and keep one canonical row. Non-numeric columns are taken
    from the first occurrence.
    """
    valid   = df[df["Date"].notna()].copy()
    invalid = df[df["Date"].isna()].copy()

    dup_mask = valid.duplicated(subset=["Business Name", "Date"], keep=False)
    dups = valid[dup_mask]

    if not dups.empty:
        for (biz, dt), grp in dups.groupby(["Business Name", "Date"]):
            num_cols  = [c for c in _NUMERIC_COLS if c in grp.columns]
            row_summary = {}
            for col in num_cols:
                vals = grp[col].dropna().tolist()
                if len(vals) > 1 and len(set(vals)) > 1:
                    row_summary[col] = vals
            duplicate_warnings.append({
                "business":          biz,
                "date":              str(dt.date()),
                "n_records":         len(grp),
                "differing_columns": row_summary,
                "resolution":        "max",
            })

    num_cols_present = [c for c in _NUMERIC_COLS if c in valid.columns]
    non_num_cols     = [c for c in valid.columns
                        if c not in num_cols_present
                        and c not in ("Business Name", "Date")]

    agg_dict = {c: "max" for c in num_cols_present}
    agg_dict.update({c: "first" for c in non_num_cols})

    deduped = (
        valid
        .groupby(["Business Name", "Date"], sort=False)
        .agg(agg_dict)
        .reset_index()
    )

    return pd.concat([deduped, invalid], ignore_index=True, sort=False)


# ─────────────────────────────────────────────────────────────────────────────
#  FIX 5 – Inactive / Closed Business Detection
# ─────────────────────────────────────────────────────────────────────────────

def _is_inactive(bs_valid: pd.DataFrame) -> bool:
    """
    Returns True if the business is considered inactive / closed.
    Criteria: all reported Monthly Sales values are zero (or NaN).
    Such businesses are excluded from growth medians (FIX 5) and have their
    current job counts set to zero (FIX 7).
    """
    sales = bs_valid["Monthly Sales (R)"].fillna(0)
    return bool(sales.eq(0).all())


# ─────────────────────────────────────────────────────────────────────────────
#  FIX 6 – Corrected Growth Calculator
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_growth_detailed(series: pd.Series) -> dict:
    """
    Tiered growth formula per Dashboard Indicators Definition:

      n < 6               → Insufficient Data
      6  ≤ n < 12  (k=3)  → (last_3_mean  − first_3_mean)  / |first_3_mean|
      12 ≤ n < 18  (k=6)  → (last_6_mean  − first_6_mean)  / |first_6_mean|

      18 ≤ n < 24  Rule iv  ← FIX 6
          (Annualised residual months − First 12 months total) / |First 12 months total|
          where:
            First 12 months total  = sum(months 1–12)
            Annualised residual    = sum(months 13…n) × (12 / residual_count)
          NOTE: the original engine incorrectly used iloc[-12:] as the last
          window, which for n=22 overlaps months 11–22 with the first window
          and for n=19 overlaps months 8–19. This fix uses all residual months
          (13…n) and annualises them to a 12-month equivalent before comparing
          against the first-12 total.

      n ≥ 24       (k=12) → (last_12_mean − first_12_mean) / |first_12_mean|

    The denominator always uses the absolute value of the first-window figure,
    so that the sign of growth is driven purely by the direction of change even
    when the base period is negative.
    """
    clean = series.dropna()
    n = len(clean)

    if n < 6:
        return {
            "status": "Insufficient Data", "n": n, "k": 0,
            "first_sum": 0, "last_sum": 0,
            "first_mean": 0, "last_mean": 0,
            "growth": "Insufficient Data",
            "rule": "< 6 months",
        }

    # ── Determine window and compute growth ───────────────────────────────────
    if n <= 11:
        k    = 3
        rule = "Rule ii (6–11 months)"
        first_window = clean.iloc[:k]
        last_window  = clean.iloc[-k:]
        first_mean   = first_window.mean()
        last_mean    = last_window.mean()
        fm, lm       = first_mean, last_mean
        denom        = abs(fm)
        first_sum    = first_window.sum()
        last_sum     = last_window.sum()

    elif n <= 17:
        k    = 6
        rule = "Rule iii (12–17 months)"
        first_window = clean.iloc[:k]
        last_window  = clean.iloc[-k:]
        first_mean   = first_window.mean()
        last_mean    = last_window.mean()
        fm, lm       = first_mean, last_mean
        denom        = abs(fm)
        first_sum    = first_window.sum()
        last_sum     = last_window.sum()

    elif n <= 23:
        # ── FIX 6: Rule iv — annualised residual ─────────────────────────────
        k            = 12
        rule         = "Rule iv (18–23 months)"
        first_window = clean.iloc[:12]          # months 1–12
        residual     = clean.iloc[12:]          # months 13…n  (all remaining)
        residual_n   = len(residual)
        first_total  = first_window.sum()
        # Annualise: project residual months to a full 12-month equivalent
        ann_residual = residual.sum() * (12.0 / residual_n)
        first_mean   = first_window.mean()
        last_mean    = residual.mean()          # for reference / display
        fm           = first_total
        lm           = ann_residual
        denom        = abs(first_total)
        first_sum    = first_total
        last_sum     = ann_residual

    else:
        k    = 12
        rule = "Rule v (≥24 months)"
        first_window = clean.iloc[:k]
        last_window  = clean.iloc[-k:]
        first_mean   = first_window.mean()
        last_mean    = last_window.mean()
        fm, lm       = first_mean, last_mean
        denom        = abs(fm)
        first_sum    = first_window.sum()
        last_sum     = last_window.sum()

    # ── Growth ratio ──────────────────────────────────────────────────────────
    if denom == 0 and lm == 0:
        growth = 0.0
    elif denom == 0 and lm > 0:
        growth = 100.0
    elif denom == 0 and lm < 0:
        growth = -100.0
    else:
        growth = round(((lm - fm) / denom) * 100, 1)

    return {
        "status":     "Success",
        "n":          n,
        "k":          k,
        "rule":       rule,
        "first_sum":  first_sum,
        "last_sum":   last_sum,
        "first_mean": first_mean,
        "last_mean":  last_mean,
        "growth":     growth,
    }


def _calculate_growth(series: pd.Series):
    return _calculate_growth_detailed(series)["growth"]


def _calc_pct_change(baseline, current) -> float:
    try:
        b, c = float(baseline), float(current)
        if b == 0 and c == 0: return 0.0
        if b == 0 and c > 0:  return 100.0
        if b == 0 and c < 0:  return -100.0
        return round(((c - b) / abs(b)) * 100, 1)
    except Exception:
        return 0.0


def _safe_round(v):
    try:
        f = float(v)
        return round(f) if pd.notna(f) else None
    except Exception:
        return None


def _safe_float(v):
    try:
        f = float(v)
        return f if pd.notna(f) else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Main KPI Calculator
# ─────────────────────────────────────────────────────────────────────────────

def calculate_kpis(df: pd.DataFrame, time_range: str = "all") -> dict:
    """
    Calculate all dashboard KPIs from a raw Airtable extract DataFrame.

    Parameters
    ----------
    df         : Raw DataFrame (one row per business-month report).
    time_range : 'all' | '6' | '12' | 'ytd'

    Returns
    -------
    dict – full result payload consumed by the dashboard front-end.
           Includes 'Duplicate_Warnings' and 'Inactive_Businesses' keys.
    """
    df = df.copy()
    df["Date"]          = df["Reporting Month"].apply(parse_reporting_month)
    df["Business Name"] = df["Business Name"].apply(_normalize_name)
    df = df[
        df["Business Name"].notna()
        & (df["Business Name"].str.strip() != "")
        & (df["Business Name"].str.lower() != "unknown")
    ].copy()

    # ── FIX 1: resolve duplicate (Business Name, Date) entries via MAX ────────
    duplicate_warnings: list = []
    df = _dedup_business_records(df, duplicate_warnings)

    # ── Optional time-range filter ────────────────────────────────────────────
    global_s_date = global_e_date = None
    if time_range != "all":
        valid_dates = df["Date"].dropna()
        if not valid_dates.empty:
            m_max  = valid_dates.max()
            s_date = None
            e_date = m_max
            if   time_range == "6":   s_date = m_max - pd.DateOffset(months=5)
            elif time_range == "12":  s_date = m_max - pd.DateOffset(months=11)
            elif time_range == "ytd": s_date = pd.to_datetime(f"{m_max.year}-01-01")
            if s_date:
                global_s_date = s_date
                global_e_date = e_date
                df = df[
                    df["Date"].isna()
                    | ((df["Date"] >= s_date) & (df["Date"] <= e_date))
                ].copy()

    # ── Per-business month index ──────────────────────────────────────────────
    df["Month_Index"] = 0
    for biz_name, biz_idx in df.groupby("Business Name").groups.items():
        sorted_idx  = df.loc[biz_idx].sort_values("Date").index
        valid_dates = df.loc[sorted_idx, "Date"].dropna()
        if valid_dates.empty:
            continue
        start = valid_dates.min()
        for idx in sorted_idx:
            d = df.at[idx, "Date"]
            if pd.notna(d):
                df.at[idx, "Month_Index"] = (
                    (d.year - start.year) * 12 + (d.month - start.month) + 1
                )

    # ── Program-level time-series (for charts) ────────────────────────────────
    valid_global = df[df["Date"].notna()].copy()
    program_series: dict = {}
    if not valid_global.empty:
        pm = (
            valid_global
            .groupby("Month_Index")
            .agg({
                "Monthly Sales (R)":           "sum",
                "Monthly Net Profit":          "sum",
                "Total Jobs":                  "sum",
                "Female Jobs":                 "sum",
                "Youth Jobs":                  "sum",
                "Total Subscribers Students":  "sum",
                "Total Subscribers Teachers":  "sum",
                "New Subscribers Students":    "sum",
                "New Subscribers Teachers":    "sum",
                "SA Schools":                  "sum",
                "Q1-3 Schools":                "sum",
            })
            .sort_index()
        )
        program_series = {
            "months":                   [int(m) for m in pm.index.tolist()],
            "sales":                    [_safe_round(v) for v in pm["Monthly Sales (R)"]],
            "profit":                   [_safe_round(v) for v in pm["Monthly Net Profit"]],
            "jobs_total":               [_safe_round(v) for v in pm["Total Jobs"]],
            "jobs_female":              [_safe_round(v) for v in pm["Female Jobs"]],
            "jobs_youth":               [_safe_round(v) for v in pm["Youth Jobs"]],
            "reach_learners":           [_safe_round(v) for v in pm["Total Subscribers Students"]],
            "reach_educators":          [_safe_round(v) for v in pm["Total Subscribers Teachers"]],
            "reach_new_learners_cum":   [_safe_round(v) for v in pm["New Subscribers Students"].cumsum()],
            "reach_new_educators_cum":  [_safe_round(v) for v in pm["New Subscribers Teachers"].cumsum()],
            "reach_sa_schools":         [_safe_round(v) for v in pm["SA Schools"]],
            "reach_q13_schools":        [_safe_round(v) for v in pm["Q1-3 Schools"]],
        }

    # ── Per-cohort computation ────────────────────────────────────────────────
    cohort_summaries    = []
    cohort_detail       = {}
    venture_data        = []
    red_flags           = []
    investment_ledger   = []
    all_time_series     = []
    inactive_businesses = []          # NEW – FIX 5

    # Program-level accumulators
    prog_new_jobs     = prog_female_new  = prog_youth_new   = 0
    prog_new_sub      = 0
    prog_total_jobs   = prog_female_jobs = prog_youth_jobs  = 0
    prog_total_sub_lrn = prog_total_sub_edu = 0
    prog_total_schools = 0
    prog_female_stu   = prog_total_stu = prog_rural_stu = prog_disability_stu = 0
    grand_total_sales = 0.0

    cohort_growth_metrics: dict = {}

    EXPECTED_COHORTS = ["Cohort 1", "Cohort 2", "Cohort 3", "Cohort 4"]

    for cohort_name in EXPECTED_COHORTS:
        cdf = df[df["Cohort"] == cohort_name].copy()

        if cdf.empty:
            cohort_detail[cohort_name] = _empty_cohort_detail()
            cohort_summaries.append({
                "Cohort": cohort_name, "Ventures": 0,
                "Active Ventures": 0, "Inactive Ventures": 0,
                "Total Sales": 0.0, "Total Profit": 0.0,
                "Total Jobs": 0, "Jobs Pct Change": 0.0,
                "Total Learners": 0, "Total Educators": 0,
                "New Learners": 0, "New Educators": 0,
                "Median Sales Growth": "Insufficient Data",
                "Median Profit Growth": "Insufficient Data",
            })
            continue

        coh_months_list: list = []
        coh_sg_list:     list = []   # only active businesses (FIX 5)
        coh_pg_list:     list = []   # only active businesses (FIX 5)

        f_sales:  list = []
        f_profit: list = []
        f_reach:  list = []
        f_jobs:   list = []
        growth_table  = []
        jobs_table    = []
        users_table   = []
        disagg_table  = []
        coh_investments:    list = []
        padded_cohort_dfs:  list = []

        coh_base_j = coh_curr_j = 0
        coh_total_lrn = coh_total_edu = 0
        coh_new_lrn = coh_new_edu = 0
        n_active = n_inactive = 0

        for biz_name, bg in cdf.groupby("Business Name"):
            bs_valid = bg[bg["Date"].notna()].sort_values("Date").copy()
            bs_valid = bs_valid.drop_duplicates(subset=["Date"], keep="first")

            if bs_valid.empty:
                continue

            # ── FIX 5: detect inactive / closed businesses ────────────────────
            inactive = _is_inactive(bs_valid)
            if inactive:
                n_inactive += 1
                inactive_businesses.append({
                    "Business Name": biz_name,
                    "Cohort":        cohort_name,
                    "Reason":        "All monthly sales are zero",
                    "Last Report":   bs_valid["Date"].max().strftime("%b %Y"),
                    "n_months":      len(bs_valid),
                })
            else:
                n_active += 1

            # ── Padded series ─────────────────────────────────────────────────
            pad_s = (
                global_s_date
                if global_s_date is not None and pd.notna(global_s_date)
                else bs_valid["Date"].min()
            )
            pad_e = (
                global_e_date
                if global_e_date is not None and pd.notna(global_e_date)
                else bs_valid["Date"].max()
            )
            all_months = pd.date_range(start=pad_s, end=pad_e, freq="MS")
            bs_padded  = (
                bs_valid
                .set_index("Date")
                .reindex(all_months)
                .ffill()
                .fillna(0)
                .reset_index(names=["Date"])
            )
            padded_cohort_dfs.append(bs_padded)

            n = len(bs_padded)
            coh_months_list.append(n)

            # ── FIX 6: corrected growth formula ──────────────────────────────
            s_res = _calculate_growth_detailed(bs_padded["Monthly Sales (R)"])
            p_res = _calculate_growth_detailed(bs_padded["Monthly Net Profit"])
            sg    = s_res["growth"]
            pg    = p_res["growth"]

            # FIX 5: only include active businesses in cohort median lists
            if not inactive:
                if isinstance(sg, (int, float)): coh_sg_list.append(sg)
                if isinstance(pg, (int, float)): coh_pg_list.append(pg)

            biz_sales = float(bs_valid["Monthly Sales (R)"].sum())
            grand_total_sales += biz_sales

            # ── Latest / first value helpers ──────────────────────────────────
            def _latest(col, default=0.0):
                v = bs_valid[col].dropna()
                return float(v.iloc[-1]) if not v.empty else default

            def _latest_nv(col, default=0.0):
                v  = bs_valid[col].dropna()
                nz = v[v > 0]
                return float(nz.iloc[-1]) if not nz.empty else (
                    float(v.iloc[-1]) if not v.empty else default
                )

            def _first(col, default=0.0):
                v = bs_valid[col].dropna()
                return float(v.iloc[0]) if not v.empty else default

            # ── FIX 7: jobs — set current to 0 for inactive businesses ────────
            f_jobs_val = _first("Total Jobs")
            if inactive:
                # Closed business: current jobs are 0, not the last stale report
                c_jobs_val = 0.0
            else:
                c_jobs_val = _latest("Total Jobs")

            n_jobs = int(c_jobs_val - f_jobs_val) if len(bs_valid) >= 2 else 0

            f_fem_val  = _first("Female Jobs")
            c_fem_val  = 0.0 if inactive else _latest("Female Jobs")
            n_fem      = int(c_fem_val - f_fem_val) if len(bs_valid) >= 2 else 0

            f_yth_val  = _first("Youth Jobs")
            c_yth_val  = 0.0 if inactive else _latest("Youth Jobs")
            n_yth      = int(c_yth_val - f_yth_val) if len(bs_valid) >= 2 else 0

            j_pct = _calc_pct_change(f_jobs_val, c_jobs_val)

            coh_base_j += int(f_jobs_val)
            coh_curr_j += int(c_jobs_val)

            # ── Reach (FIX 2) ─────────────────────────────────────────────────
            c_stu = int(_latest("Total Subscribers Students"))
            c_tea = int(_latest("Total Subscribers Teachers"))

            # FIX 4: new subscribers from deduplicated actual records only
            v_new_stu = int(bs_valid["New Subscribers Students"].sum())
            v_new_tea = int(bs_valid["New Subscribers Teachers"].sum())
            v_new_subs = v_new_stu + v_new_tea

            coh_total_lrn += c_stu
            coh_total_edu += c_tea
            coh_new_lrn   += v_new_stu
            coh_new_edu   += v_new_tea

            prog_total_jobs   += int(c_jobs_val)
            prog_new_jobs     += n_jobs
            prog_female_jobs  += int(c_fem_val)
            prog_youth_jobs   += int(c_yth_val)
            prog_female_new   += n_fem
            prog_youth_new    += n_yth
            prog_total_sub_lrn += c_stu
            prog_total_sub_edu += c_tea
            prog_new_sub       += v_new_subs
            prog_total_schools += int(_latest("Total Schools"))
            prog_female_stu    += _latest_nv("Female Students")
            prog_total_stu     += c_stu
            prog_rural_stu     += _latest_nv("Rural Students")
            prog_disability_stu += _latest_nv("Disability Students")

            # ── Red flags ─────────────────────────────────────────────────────
            biz_flags = []
            if inactive:
                biz_flags.append("Inactive / Closed Business ⚠️")
            if isinstance(sg, (int, float)):
                if sg < 0:   biz_flags.append("Negative Sales Growth ⚠️")
                if sg >= 20: biz_flags.append("Strong Sales Growth ✨")
            if isinstance(pg, (int, float)):
                if pg < 0:   biz_flags.append("Negative Profit Growth ⚠️")
                if pg >= 20: biz_flags.append("Strong Profit Growth ✨")
            if (c_stu + c_tea) > 0 and ((v_new_subs / max(n, 1)) * 12) < 8000:
                biz_flags.append("Low Learner Reach ⚠️")
            if biz_flags:
                red_flags.append({
                    "Business Name": biz_name,
                    "Cohort":        cohort_name,
                    "Flags":         biz_flags,
                })

            # ── Venture-level data ────────────────────────────────────────────
            venture_data.append({
                "Business Name":     biz_name,
                "Cohort":            cohort_name,
                "Status":            "Inactive" if inactive else "Active",
                "Total Sales (R)":   biz_sales,
                "Sales Growth %":    sg,
                "Profit Growth %":   pg,
                "Latest Jobs":       n_jobs,
                "Jobs Pct Change":   j_pct,
                "Female Jobs":       int(c_fem_val),
                "Youth Jobs":        int(c_yth_val),
                "Total Subscribers": int(c_stu + c_tea),
                "Months":            n,
            })

            # ── Rule label ────────────────────────────────────────────────────
            r_text = s_res["rule"]

            growth_table.append({
                "name":               biz_name,
                "status":             "Inactive" if inactive else "Active",
                "sales_growth":       sg,
                "profit_growth":      pg,
                "months":             n,
                "flags":              biz_flags,
                "rule":               r_text,
                "base_val":           s_res["first_sum"],
                "recent_val":         s_res["last_sum"],
                "profit_base_val":    p_res["first_sum"],
                "profit_recent_val":  p_res["last_sum"],
                "excluded_from_median": inactive,   # FIX 5 transparency
            })

            jobs_table.append({
                "name":             biz_name,
                "status":           "Inactive" if inactive else "Active",
                "baseline":         int(f_jobs_val),
                "total":            int(c_jobs_val),   # 0 for inactive (FIX 7)
                "new":              n_jobs,
                "pct_change":       j_pct,
                "new_female":       n_fem,
                "new_youth":        n_yth,
                "youth":            int(c_yth_val),
                "baseline_female":  int(f_fem_val),
                "baseline_youth":   int(f_yth_val),
            })

            users_table.append({
                "name":          biz_name,
                "status":        "Inactive" if inactive else "Active",
                "tot_learners":  c_stu,
                "tot_educators": c_tea,
                "new_learners":  v_new_stu,
                "new_educators": v_new_tea,
                "schools":       int(_latest("Total Schools")),
                "sa_schools":    int(_latest("SA Schools")),
                "q13_schools":   int(_latest("Q1-3 Schools")),
                "flags":         [],
            })

            # ── Disaggregation ────────────────────────────────────────────────
            biz_female_stu = _latest_nv("Female Students", None)
            biz_female_tea = _latest_nv("Female Teachers", None)
            biz_rural_stu  = _latest_nv("Rural Students",  None)
            biz_rural_tea  = _latest_nv("Rural Teachers",  None)
            biz_disab_stu  = _latest_nv("Disability Students", None)
            biz_disab_tea  = _latest_nv("Disability Teachers", None)

            disagg_table.append({
                "name":           biz_name,
                "female_stu":     biz_female_stu,
                "female_tea":     biz_female_tea,
                "rural_stu":      biz_rural_stu,
                "rural_tea":      biz_rural_tea,
                "disability_stu": biz_disab_stu,
                "disability_tea": biz_disab_tea,
            })

            # ── Time-series (chart data) ───────────────────────────────────────
            m_str = bs_padded["Date"].dt.strftime("%Y-%m").tolist()
            f_sales.append({
                "name":   biz_name,
                "status": "Inactive" if inactive else "Active",
                "growth": sg,
                "months": n,
                "data":   [{"x": m, "y": _safe_round(v)}
                           for m, v in zip(m_str, bs_padded["Monthly Sales (R)"])],
            })
            f_profit.append({
                "name":   biz_name,
                "status": "Inactive" if inactive else "Active",
                "growth": pg,
                "months": n,
                "data":   [{"x": m, "y": _safe_round(v)}
                           for m, v in zip(m_str, bs_padded["Monthly Sales (R)"])],
            })

            vbm = (
                bs_valid
                .groupby(bs_valid["Date"].dt.strftime("%Y-%m"))
                .agg({
                    "Total Subscribers Students":  "sum",
                    "Total Subscribers Teachers":  "sum",
                    "New Subscribers Students":    "sum",
                    "New Subscribers Teachers":    "sum",
                    "SA Schools":    "sum",
                    "Q1-3 Schools":  "sum",
                    "Total Jobs":    "sum",
                    "Female Jobs":   "sum",
                    "Youth Jobs":    "sum",
                })
                .sort_index()
            )
            f_reach.append({
                "name":                  biz_name,
                "status":                "Inactive" if inactive else "Active",
                "months":                vbm.index.tolist(),
                "total_learners":        [_safe_round(v) for v in vbm["Total Subscribers Students"]],
                "total_educators":       [_safe_round(v) for v in vbm["Total Subscribers Teachers"]],
                "new_learners_cum":      [_safe_round(v) for v in vbm["New Subscribers Students"].cumsum()],
                "new_educators_cum":     [_safe_round(v) for v in vbm["New Subscribers Teachers"].cumsum()],
                "sa_schools":            [_safe_round(v) for v in vbm["SA Schools"]],
                "q13_schools":           [_safe_round(v) for v in vbm["Q1-3 Schools"]],
            })
            f_jobs.append({
                "name":   biz_name,
                "status": "Inactive" if inactive else "Active",
                "months": vbm.index.tolist(),
                "total":  [_safe_round(v) for v in vbm["Total Jobs"]],
                "female": [_safe_round(v) for v in vbm["Female Jobs"]],
                "youth":  [_safe_round(v) for v in vbm["Youth Jobs"]],
            })

            # ── Investments ledger ────────────────────────────────────────────
            for _, row in bs_valid.iterrows():
                gv = _safe_float(row.get("Grants Value", 0))
                if gv and gv > 0:
                    inv_item = {
                        "name":     biz_name,
                        "value":    gv,
                        "investor": row.get("Grant Funder") or "Not Specified",
                        "month":    row["Date"].strftime("%b %Y") if pd.notna(row.get("Date")) else "N/A",
                    }
                    coh_investments.append(inv_item)
                    investment_ledger.append({
                        "Business Name":        biz_name,
                        "Cohort":               cohort_name,
                        "Total Sales":          _safe_float(row.get("Monthly Sales (R)")),
                        "Net Profit":           _safe_float(row.get("Monthly Net Profit")),
                        "Grants & Investments": gv,
                        "Investor":             inv_item["investor"],
                        "Date":                 inv_item["month"],
                    })

                if pd.notna(row["Date"]):
                    all_time_series.append({
                        "cohort": cohort_name,
                        "month":  row["Date"].strftime("%Y-%m"),
                        "sales":  _safe_float(row["Monthly Sales (R)"]),
                        "profit": _safe_float(row["Monthly Net Profit"]),
                        "jobs":   _safe_float(row["Total Jobs"]),
                    })

        # ── Cohort-level aggregates ───────────────────────────────────────────
        # FIX 5: medians computed from active businesses only
        med_sg  = round(median(coh_sg_list), 1) if coh_sg_list else "Insufficient Data"
        med_pg  = round(median(coh_pg_list), 1) if coh_pg_list else "Insufficient Data"
        avg_mo  = sum(coh_months_list) / len(coh_months_list) if coh_months_list else 0

        cohort_growth_metrics[cohort_name] = {
            "median_sg": med_sg,
            "median_pg": med_pg,
            "exposure":  avg_mo,
        }

        coh_jobs_pct = _calc_pct_change(coh_base_j, coh_curr_j)

        cohort_summaries.append({
            "Cohort":               cohort_name,
            "Ventures":             len(coh_months_list),
            "Active Ventures":      n_active,
            "Inactive Ventures":    n_inactive,
            "Total Sales":          float(cdf["Monthly Sales (R)"].sum()),
            "Total Profit":         float(cdf["Monthly Net Profit"].sum()),
            "Total Jobs":           coh_curr_j,
            "New Jobs":             coh_curr_j - coh_base_j,
            "Jobs Pct Change":      coh_jobs_pct,
            "Total Learners":       coh_total_lrn,
            "Total Educators":      coh_total_edu,
            "New Learners":         coh_new_lrn,
            "New Educators":        coh_new_edu,
            "Median Sales Growth":  med_sg,
            "Median Profit Growth": med_pg,
        })

        # ── Cohort time-series aggregates (for charts) ────────────────────────
        if padded_cohort_dfs:
            coh_padded_df = pd.concat(padded_cohort_dfs, ignore_index=True)
            cg = (
                coh_padded_df
                .groupby(coh_padded_df["Date"].dt.strftime("%Y-%m"))
                .agg({
                    "Monthly Sales (R)":           "sum",
                    "Monthly Net Profit":          "sum",
                    "Total Jobs":                  "sum",
                    "Female Jobs":                 "sum",
                    "Youth Jobs":                  "sum",
                    "Total Subscribers Students":  "sum",
                    "Total Subscribers Teachers":  "sum",
                    "New Subscribers Students":    "sum",
                    "New Subscribers Teachers":    "sum",
                    "SA Schools":                  "sum",
                    "Q1-3 Schools":                "sum",
                })
                .sort_index()
            )
            cohort_aggregate = {
                "months": cg.index.tolist(),
                "sales":  [_safe_round(v) for v in cg["Monthly Sales (R)"]],
                "profit": [_safe_round(v) for v in cg["Monthly Net Profit"]],
            }
            jobs_bar = {
                "months": cg.index.tolist(),
                "total":  [_safe_round(v) for v in cg["Total Jobs"]],
                "female": [_safe_round(v) for v in cg["Female Jobs"]],
                "youth":  [_safe_round(v) for v in cg["Youth Jobs"]],
            }
            reach = {
                "months":             cg.index.tolist(),
                "total_learners":     [_safe_round(v) for v in cg["Total Subscribers Students"]],
                "total_educators":    [_safe_round(v) for v in cg["Total Subscribers Teachers"]],
                "new_learners_cum":   [_safe_round(v) for v in cg["New Subscribers Students"].cumsum()],
                "new_educators_cum":  [_safe_round(v) for v in cg["New Subscribers Teachers"].cumsum()],
                "sa_schools":         [_safe_round(v) for v in cg["SA Schools"]],
                "q13_schools":        [_safe_round(v) for v in cg["Q1-3 Schools"]],
            }
        else:
            cohort_aggregate = {"months": [], "sales": [], "profit": []}
            jobs_bar  = {"months": [], "total": [], "female": [], "youth": []}
            reach     = {
                "months": [], "total_learners": [], "total_educators": [],
                "new_learners_cum": [], "new_educators_cum": [],
                "sa_schools": [], "q13_schools": [],
            }

        cohort_detail[cohort_name] = {
            "cohort_median_sg":   med_sg,
            "cohort_median_pg":   med_pg,
            "cohort_months":      int(avg_mo),
            "cohort_jobs_pct":    coh_jobs_pct,
            "jobs_latest_total":  coh_curr_j,
            "active_ventures":    n_active,
            "inactive_ventures":  n_inactive,
            "fellows_sales":      f_sales,
            "fellows_profit":     f_profit,
            "fellows_reach":      f_reach,
            "fellows_jobs":       f_jobs,
            "cohort_aggregate":   cohort_aggregate,
            "growth_table":       growth_table,
            "jobs_bar":           jobs_bar,
            "jobs_table":         jobs_table,
            "investments_table":  coh_investments,
            "reach":              reach,
            "users_table":        users_table,
            "disaggregation":     disagg_table,
        }

    # ── Program-level TWA growth ──────────────────────────────────────────────
    # Uses float average exposure (not rounded int) to preserve precision
    ts_num = ts_den = tp_num = tp_den = 0.0
    for m in cohort_growth_metrics.values():
        e = m["exposure"]
        if isinstance(m["median_sg"], (int, float)):
            ts_num += m["median_sg"] * e
            ts_den += e
        if isinstance(m["median_pg"], (int, float)):
            tp_num += m["median_pg"] * e
            tp_den += e

    prog_sg_twa = round(ts_num / ts_den, 1) if ts_den > 0 else "Insufficient Data"
    prog_pg_twa = round(tp_num / tp_den, 1) if tp_den > 0 else "Insufficient Data"

    # ── Program-level jobs % change ───────────────────────────────────────────
    prog_base_j = prog_curr_j = 0
    df_valid_final = df[df["Date"].notna()]
    if not df_valid_final.empty:
        for b_name, b_group in df_valid_final.groupby("Business Name"):
            bv_tmp = b_group.sort_values("Date")
            tj = bv_tmp["Total Jobs"].dropna()
            if not tj.empty:
                prog_base_j += tj.iloc[0]
                # FIX 7: current = 0 for inactive businesses
                bv_sales = bv_tmp["Monthly Sales (R)"].fillna(0)
                if bv_sales.eq(0).all():
                    prog_curr_j += 0
                else:
                    prog_curr_j += tj.iloc[-1]

    prog_jobs_pct = _calc_pct_change(prog_base_j, prog_curr_j)

    prog_total_sub = prog_total_sub_lrn + prog_total_sub_edu

    # ── Disaggregation averages ───────────────────────────────────────────────
    def _prog_disagg_avg(key):
        vals = pd.Series([
            d[key]
            for c in cohort_detail.values()
            for d in c.get("disaggregation", [])
        ]).where(lambda x: x > 0).dropna()
        return round(vals.mean(), 1) if not vals.empty else 0

    return {
        "Program_Overview": {
            "Total_Sales_ZAR":         int(grand_total_sales or 0),
            "Net_Jobs_Created":        int(prog_new_jobs or 0),
            "Average_Sales_Growth_%":  prog_sg_twa,
            "Average_Profit_Growth_%": prog_pg_twa,
            "Total_Ventures":          int(df["Business Name"].nunique()),
            "Program_TWA":             prog_sg_twa,
        },
        "Venture_Data":       venture_data,
        "Cohort_Summaries":   cohort_summaries,
        "Investment_Ledger":  investment_ledger,
        "Jobs_Summary": {
            "Total Jobs":      int(prog_total_jobs  or 0),
            "New Jobs":        int(prog_new_jobs    or 0),
            "Jobs Pct Change": prog_jobs_pct,
            "Female Jobs":     int(prog_female_jobs or 0),
            "Youth Jobs":      int(prog_youth_jobs  or 0),
            "New Female Jobs": int(prog_female_new  or 0),
            "New Youth Jobs":  int(prog_youth_new   or 0),
        },
        "Reach_Summary": {
            "Total Subscribers": int(prog_total_sub     or 0),
            "Total Learners":    int(prog_total_sub_lrn or 0),
            "Total Educators":   int(prog_total_sub_edu or 0),
            "New Subscribers":   int(prog_new_sub       or 0),
            "Total Schools":     int(prog_total_schools or 0),
            "Female %":     _prog_disagg_avg("female_stu"),
            "Rural %":      _prog_disagg_avg("rural_stu"),
            "Disability %": _prog_disagg_avg("disability_stu"),
        },
        "Time_Series": {
            "cohort":           {},
            "program":          {},
            "program_extended": program_series,
        },
        "Red_Flags":            red_flags,
        "Cohort_Detail":        cohort_detail,
        "Duplicate_Warnings":   duplicate_warnings,
        "Inactive_Businesses":  inactive_businesses,   # FIX 5 – new output key
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Empty cohort placeholder
# ─────────────────────────────────────────────────────────────────────────────

def _empty_cohort_detail() -> dict:
    return {
        "cohort_median_sg":  "Insufficient Data",
        "cohort_median_pg":  "Insufficient Data",
        "cohort_months":     0,
        "active_ventures":   0,
        "inactive_ventures": 0,
        "fellows_sales":     [],
        "fellows_profit":    [],
        "fellows_reach":     [],
        "fellows_jobs":      [],
        "cohort_aggregate":  {"months": [], "sales": [], "profit": []},
        "growth_table":      [],
        "jobs_bar":          {"months": [], "total": [], "female": [], "youth": []},
        "jobs_table":        [],
        "investments_table": [],
        "reach": {
            "months": [], "total_learners": [], "total_educators": [],
            "new_learners_cum": [], "new_educators_cum": [],
            "sa_schools": [], "q13_schools": [],
        },
        "users_table":    [],
        "disaggregation": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    try:
        from data_fetcher import fetch_dashboard_data
        print("Fetching data …")
        raw = fetch_dashboard_data()
    except ImportError:
        path = sys.argv[1] if len(sys.argv) > 1 else "Raw_Airtable_Extract.xlsx"
        print(f"Loading {path} …")
        raw = pd.read_excel(path)

    print("Calculating KPIs …")
    result = calculate_kpis(raw)

    ov = result["Program_Overview"]
    print(f"\n{'─'*60}")
    print(f"  PROGRAM OVERVIEW")
    print(f"{'─'*60}")
    print(f"  Ventures:             {ov['Total_Ventures']}")
    print(f"  Total Sales (ZAR):    R {ov['Total_Sales_ZAR']:,}")
    print(f"  Net Jobs Created:     {ov['Net_Jobs_Created']}")
    print(f"  Sales Growth  (TWA):  {ov['Average_Sales_Growth_%']}%")
    print(f"  Profit Growth (TWA):  {ov['Average_Profit_Growth_%']}%")

    js = result["Jobs_Summary"]
    print(f"\n{'─'*60}")
    print(f"  JOBS SUMMARY")
    print(f"{'─'*60}")
    print(f"  Total Jobs:           {js['Total Jobs']}")
    print(f"  New Jobs:             {js['New Jobs']}")
    print(f"  Jobs % Change:        {js['Jobs Pct Change']}%")
    print(f"  Female Jobs:          {js['Female Jobs']}")
    print(f"  Youth Jobs:           {js['Youth Jobs']}")
    print(f"  New Female Jobs:      {js['New Female Jobs']}")
    print(f"  New Youth Jobs:       {js['New Youth Jobs']}")

    rs = result["Reach_Summary"]
    print(f"\n{'─'*60}")
    print(f"  REACH SUMMARY")
    print(f"{'─'*60}")
    print(f"  Total Subscribers:    {rs['Total Subscribers']:,}")
    print(f"    Learners:           {rs['Total Learners']:,}")
    print(f"    Educators:          {rs['Total Educators']:,}")
    print(f"  New Subscribers:      {rs['New Subscribers']:,}")
    print(f"  Total Schools:        {rs['Total Schools']:,}")

    print(f"\n{'─'*60}")
    print(f"  COHORT SUMMARIES")
    print(f"{'─'*60}")
    for cs in result["Cohort_Summaries"]:
        print(
            f"  {cs['Cohort']}: {cs['Ventures']} ventures "
            f"({cs['Active Ventures']} active, {cs['Inactive Ventures']} inactive) | "
            f"SG={cs['Median Sales Growth']}% | PG={cs['Median Profit Growth']}% | "
            f"Jobs={cs['Total Jobs']} (new={cs.get('New Jobs','N/A')}) | "
            f"Learners={cs['Total Learners']:,}"
        )

    ib = result.get("Inactive_Businesses", [])
    if ib:
        print(f"\n{'─'*60}")
        print(f"  ⚠  INACTIVE / CLOSED BUSINESSES ({len(ib)} detected)")
        print(f"{'─'*60}")
        for b in ib:
            print(f"  {b['Business Name']} ({b['Cohort']}) — "
                  f"last report {b['Last Report']}, {b['n_months']} months | "
                  f"Reason: {b['Reason']}")
        print(f"  → Excluded from growth medians (FIX 5)")
        print(f"  → Current jobs set to 0 (FIX 7)")

    dw = result.get("Duplicate_Warnings", [])
    if dw:
        print(f"\n{'─'*60}")
        print(f"  ⚠  DATA QUALITY — {len(dw)} DUPLICATE DATE ENTRIES")
        print(f"{'─'*60}")
        for w in dw:
            print(f"  {w['business']} | {w['date']} | "
                  f"{w['n_records']} records | resolution=MAX")
